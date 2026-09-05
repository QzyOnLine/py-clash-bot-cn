"""Clan chat actions: donate, claim Pass Royale gifts, and request cards."""

from __future__ import annotations

import os
import time
from os.path import abspath, dirname, join

import cv2
import numpy as np

from pyclashbot.bot.coords import (
    BOTTOM_NAV_BATTLE_TAB_COORD,
    CLAN_CHAT_FEED_SUBCROP,
    CLAN_CHAT_FOOTER_SUBCROP,
    REVEAL_MORE_CLAN_CHAT_CARD_OPTIONS_BUTTON_COORD,
)
from pyclashbot.bot.nav import (
    PAGE_CLAN_CHAT,
    PAGE_MAIN,
    PAGE_SOCIAL,
    handle_trophy_reward_menu,
    navigate_main_page,
)
from pyclashbot.bot.state_detect import (
    check_for_more_clan_chat_card_options,
    check_for_trophy_reward_menu,
    check_if_on_clan_chat,
    check_if_on_clash_main_menu,
    check_if_on_social,
    clan_button_pixel_is_active_green,
    clan_button_pixel_is_active_yellow,
)

REFERENCE_ROOT = abspath(join(dirname(__file__), "..", "detection", "reference_images"))

MAX_FEED_ACTIONS = 10
TEMPLATE_TOLERANCE = 0.88
PICKER_OPEN_TIMEOUT = 8.0


def _load_template(folder: str) -> np.ndarray | None:
    path = join(REFERENCE_ROOT, folder)
    names = [n for n in os.listdir(path) if n.endswith(".png")]
    if not names:
        return None
    # cv2.imread fails silently on Windows when the path mixes separators and
    # contains non-ASCII (e.g. the 皇室战争 project dir). np.fromfile+imdecode
    # handles both, matching the rest of the project's template loading.
    full = join(path, names[0])
    data = np.fromfile(full, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _template_size(folder: str) -> tuple[int, int]:
    template = _load_template(folder)
    if template is None:
        return (40, 20)
    h, w = template.shape[:2]
    return w, h


def _sample_pixel(image: np.ndarray, x: int, y: int) -> np.ndarray:
    height, width = image.shape[:2]
    sx = min(max(x, 0), width - 1)
    sy = min(max(y, 0), height - 1)
    return image[sy][sx]


def _region_passes_color_check(
    image: np.ndarray,
    x: int,
    y: int,
    tw: int,
    th: int,
    color_check,
) -> bool:
    """Sample around the template box — text crops are white on green/grey, not solid fill."""
    height, width = image.shape[:2]
    probes = [
        (x + 2, y + 2),
        (x + tw - 2, y + 2),
        (x + 2, y + th - 2),
        (x + tw - 2, y + th - 2),
        (x + tw // 2, y + th // 2),
        (min(x + tw + 3, width - 1), y + th // 2),
    ]
    return any(color_check(_sample_pixel(image, px, py)) for px, py in probes)


def _find_all_template_coords(
    image: np.ndarray,
    folder: str,
    *,
    subcrop: tuple[int, int, int, int],
    tolerance: float,
) -> list[tuple[int, int]]:
    """All template hits in subcrop (full-image x,y), best scores first. Masks grey duplicates."""
    template = _load_template(folder)
    if template is None:
        return []

    x1, y1, x2, y2 = subcrop
    region = image[y1:y2, x1:x2]
    th, tw = template.shape[:2]
    if th > region.shape[0] or tw > region.shape[1]:
        return []

    region_work = region.copy()
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    coords: list[tuple[int, int]] = []

    for _ in range(MAX_FEED_ACTIONS * 3):
        region_gray = cv2.cvtColor(region_work, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(region_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val < tolerance:
            break
        local_x, local_y = int(max_loc[0]), int(max_loc[1])
        coords.append((x1 + local_x, y1 + local_y))
        pad = 4
        y_a = max(local_y - pad, 0)
        y_b = min(local_y + th + pad, region_work.shape[0])
        x_a = max(local_x - pad, 0)
        x_b = min(local_x + tw + pad, region_work.shape[1])
        region_work[y_a:y_b, x_a:x_b] = 0

    return coords


def _click_active_templates(
    emulator,
    logger,
    folder: str,
    *,
    subcrop: tuple[int, int, int, int],
    color_check,
    action_label: str,
    on_success,
) -> int:
    clicks = 0
    for _ in range(MAX_FEED_ACTIONS):
        image = emulator.screenshot()
        tw, th = _template_size(folder)
        clicked = False
        for x, y in _find_all_template_coords(
            image,
            folder,
            subcrop=subcrop,
            tolerance=TEMPLATE_TOLERANCE,
        ):
            if not _region_passes_color_check(image, x, y, tw, th, color_check):
                continue
            emulator.click(x + tw // 2, y + th // 2)
            clicks += 1
            on_success()
            logger.change_status(f"{action_label} ({clicks})")
            time.sleep(1.5)
            clicked = True
            break
        if not clicked:
            break
    return clicks


MAX_REVEAL_MORE_PASSES = 5


def _donate_visible_pass(emulator, logger, starting_count: int) -> int:
    """One pass: scan, click any green donate button, count, repeat until none visible.

    Returns updated running total of donations after this pass.
    """
    tw, th = _template_size("clan_chat/donate_active")
    donations = starting_count

    for _ in range(MAX_FEED_ACTIONS):
        image = emulator.screenshot()

        target = None
        for x, y in _find_all_template_coords(
            image,
            "clan_chat/donate_active",
            subcrop=CLAN_CHAT_FEED_SUBCROP,
            tolerance=TEMPLATE_TOLERANCE,
        ):
            if _region_passes_color_check(image, x, y, tw, th, clan_button_pixel_is_active_green):
                target = (x, y)
                break

        if target is None:
            break

        x, y = target
        emulator.click(x + tw // 2, y + th // 2)
        donations += 1
        logger.add_donate()
        logger.change_status(f"Donating ({donations})")
        time.sleep(1.5)

    return donations


def _donate_in_clan_chat(emulator, logger) -> int:
    """Donate to every visible request, then scroll up for more, repeat.

    Each successful click (template match + green pixel check) counts as one
    donation. A rare/epic request that Clash splits across N card-icon clicks
    therefore counts as N; making one whole request count once would require
    grouping icons by chat-row and is a separate follow-up.
    """
    donations = _donate_visible_pass(emulator, logger, 0)

    for _ in range(MAX_REVEAL_MORE_PASSES):
        if not check_for_more_clan_chat_card_options(emulator):
            break
        emulator.click(*REVEAL_MORE_CLAN_CHAT_CARD_OPTIONS_BUTTON_COORD)
        time.sleep(1.5)
        donations = _donate_visible_pass(emulator, logger, donations)

    return donations


# CN request-picker layout (fixed 419x633 emulator, verified live):
#   * click the footer "请求卡牌" button -> picker opens
#   * click the first card in the grid  -> the card is selected and a left
#     sidebar appears: blue "信息" on top, orange "请求" below it
#   * click the orange "请求" button     -> request placed, picker closes by itself
#   * if the picker stays open, close it via the title-bar X as a fallback
REQUEST_PICKER_CARD_FIRST_COORD = (57, 245)
REQUEST_PICKER_ORANGE_BUTTON_REGION = (20, 295, 180, 400)
REQUEST_PICKER_CLOSE_COORD = (370, 75)


def _picker_is_open(emulator) -> bool:
    """CN card-request picker: dark brown title bar, unlike the light clan feed header."""
    image = emulator.screenshot()
    if image is None:
        return False
    dark = 0
    for x, y in [(80, 60), (210, 60), (340, 60)]:
        b, g, r = image[y][x].astype(int)
        if b + g + r < 500:
            dark += 1
    return dark >= 2


def _open_request_picker(emulator, logger) -> bool:
    image = emulator.screenshot()
    tw, th = _template_size("clan_chat/request_footer_text")
    footer = None
    for x, y in _find_all_template_coords(
        image,
        "clan_chat/request_footer_text",
        subcrop=CLAN_CHAT_FOOTER_SUBCROP,
        tolerance=TEMPLATE_TOLERANCE,
    ):
        if _region_passes_color_check(image, x, y, tw, th, clan_button_pixel_is_active_yellow):
            footer = (x, y)
            break

    if footer is None:
        if _find_all_template_coords(
            image,
            "clan_chat/request_footer_text",
            subcrop=CLAN_CHAT_FOOTER_SUBCROP,
            tolerance=TEMPLATE_TOLERANCE,
        ):
            logger.change_status("Request Cards on cooldown")
        else:
            logger.change_status("Request Cards button not found")
        return False

    fx, fy = footer
    emulator.click(fx + tw // 2, fy + th // 2)
    logger.change_status("Opening card request picker...")
    time.sleep(2.5)

    start = time.time()
    while time.time() - start < PICKER_OPEN_TIMEOUT:
        if _picker_is_open(emulator):
            return True
        time.sleep(0.5)

    logger.change_status("Card request picker did not open")
    return False


def _find_colored_button(image, x1, y1, x2, y2, *, colors=("orange", "blue"), min_area: int = 300) -> tuple[int, int] | None:
    """Centroid of the largest matching-color UI button blob in the region, or None."""
    if image is None:
        return None
    region = image[y1:y2, x1:x2]
    r = region[..., 2].astype(int)
    g = region[..., 1].astype(int)
    b = region[..., 0].astype(int)
    mask = np.zeros(region.shape[:2], dtype=bool)
    if "orange" in colors:
        mask |= (r > 170) & (g > 100) & (b < 140) & (r - b > 60)
    if "blue" in colors:
        mask |= (b > 150) & (b > r + 30) & (g < 230)
    umask = mask.astype(np.uint8) * 255
    num, _labels, stats, cent = cv2.connectedComponentsWithStats(umask, 8)
    best, best_area = None, 0
    for i in range(1, num):
        x, y, w, h, area = stats[i]
        if area > best_area:
            best_area = area
            best = (int(cent[i][0]) + x1, int(cent[i][1]) + y1)
    return best if best_area >= min_area else None


def _request_cards_from_picker(emulator, logger) -> bool:
    # 1. Select the first card in the grid.
    emulator.click(*REQUEST_PICKER_CARD_FIRST_COORD)
    time.sleep(1.5)

    # 2. Click the orange "请求" button that appears in the left sidebar.
    orange = _find_colored_button(
        emulator.screenshot(),
        *REQUEST_PICKER_ORANGE_BUTTON_REGION,
        colors=("orange",),
    )
    if orange is None:
        logger.change_status("Request button not found after selecting card")
        return False
    emulator.click(*orange)
    logger.add_request()
    logger.change_status("Requested cards from clan")

    # 3. The picker usually closes on its own; if it stays open, close it via the X.
    start = time.time()
    while time.time() - start < PICKER_OPEN_TIMEOUT:
        if not _picker_is_open(emulator):
            return True
        time.sleep(0.5)
    emulator.click(*REQUEST_PICKER_CLOSE_COORD)
    time.sleep(1.5)
    return True


def _ensure_clan_chat(emulator, logger) -> bool:
    if check_if_on_clan_chat(emulator):
        return True
    if not check_if_on_clash_main_menu(emulator):
        logger.change_status("Not on main menu — cannot open clan chat")
        return False
    if not navigate_main_page(emulator, logger, PAGE_MAIN, PAGE_CLAN_CHAT):
        logger.change_status("Failed to navigate to clan chat")
        return False
    time.sleep(1)
    return check_if_on_clan_chat(emulator)


def _tap_battle_tab(emulator, logger) -> None:
    """Center/battle bottom-nav tab — returns to main from Social hub or clan chat."""
    logger.change_status("Tapping battle tab to reach main menu...")
    emulator.click(*BOTTOM_NAV_BATTLE_TAB_COORD)
    time.sleep(2)


def _open_clan_chat_via_bottom_nav(emulator, logger) -> bool:
    """Social tab then clan chat sub-tab — fallback when navigate_main_page can't determine the current page."""
    logger.change_status("Opening clan chat via bottom nav...")
    if not navigate_main_page(emulator, logger, PAGE_MAIN, PAGE_CLAN_CHAT):
        return False
    return check_if_on_clan_chat(emulator)


def _recover_clan_chat_from_social(emulator, logger) -> bool:
    """Clan chat lives under the Social bottom-nav tab; mis-clicks can land here without chat open."""
    if check_if_on_clan_chat(emulator):
        return True
    if check_if_on_social(emulator):
        logger.change_status("On Social tab — reopening clan chat...")
        if navigate_main_page(emulator, logger, PAGE_SOCIAL, PAGE_CLAN_CHAT):
            time.sleep(1)
            return check_if_on_clan_chat(emulator)
    return _open_clan_chat_via_bottom_nav(emulator, logger)


def _wait_for_main_after_clan(emulator, logger, timeout: float = 25) -> bool:
    """Return to main from clan/social without generic wait (trophy check false-positives there)."""
    start = time.time()
    while time.time() - start < timeout:
        if check_if_on_clash_main_menu(emulator):
            return True

        if check_if_on_clan_chat(emulator):
            if navigate_main_page(emulator, logger, PAGE_CLAN_CHAT, PAGE_MAIN):
                time.sleep(1)
            continue

        if check_if_on_social(emulator):
            if navigate_main_page(emulator, logger, PAGE_SOCIAL, PAGE_MAIN):
                logger.change_status("On Social tab — returning to main menu...")
                time.sleep(3)
            continue

        if (
            not check_if_on_social(emulator)
            and not check_if_on_clan_chat(emulator)
            and check_for_trophy_reward_menu(emulator)
        ):
            handle_trophy_reward_menu(emulator, logger)
            time.sleep(1)
            continue

        _tap_battle_tab(emulator, logger)

    return check_if_on_clash_main_menu(emulator)


def _return_to_main(emulator, logger) -> bool:
    if check_if_on_clash_main_menu(emulator):
        return True

    if check_if_on_clan_chat(emulator):
        if navigate_main_page(emulator, logger, PAGE_CLAN_CHAT, PAGE_MAIN):
            time.sleep(1)
            if check_if_on_clash_main_menu(emulator):
                return True

    if check_if_on_social(emulator):
        logger.change_status("On Social tab — returning to main menu...")
        if navigate_main_page(emulator, logger, PAGE_SOCIAL, PAGE_MAIN):
            time.sleep(1)
            if check_if_on_clash_main_menu(emulator):
                return True

    _tap_battle_tab(emulator, logger)
    if check_if_on_clash_main_menu(emulator):
        return True

    return _wait_for_main_after_clan(emulator, logger)


def clan_chat_state(
    emulator,
    logger,
    *,
    donate_enabled: bool,
    claim_enabled: bool,
    request_enabled: bool,
) -> bool:
    if not donate_enabled and not claim_enabled and not request_enabled:
        return True

    logger.change_status("Running clan chat jobs...")
    if not _ensure_clan_chat(emulator, logger):
        return False

    if claim_enabled:
        count = _click_active_templates(
            emulator,
            logger,
            "clan_chat/claim_active",
            subcrop=CLAN_CHAT_FEED_SUBCROP,
            color_check=clan_button_pixel_is_active_green,
            action_label="Claiming clan gift",
            on_success=logger.add_clan_gift_claim,
        )
        if count == 0:
            logger.change_status("No claimable clan gifts visible")

    if donate_enabled:
        count = _donate_in_clan_chat(emulator, logger)
        if count == 0:
            logger.change_status("No active donate buttons visible")
        if not _recover_clan_chat_from_social(emulator, logger):
            return _return_to_main(emulator, logger)

    if request_enabled:
        if _open_request_picker(emulator, logger):
            _request_cards_from_picker(emulator, logger)

    return _return_to_main(emulator, logger)
