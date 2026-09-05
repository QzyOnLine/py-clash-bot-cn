"""Pure screen-detection helpers.

Imports only from pyclashbot.detection.*, pyclashbot.utils.*, and pyclashbot.bot.coords.
Never imports from other pyclashbot.bot.* modules, with one exception:
detect_upgradable_cards reuses pixel_indicates_upgradable from state_detect (a leaf
predicate module that does not import from find).
"""

from pyclashbot.bot.coords import UPGRADE_POINTS
from pyclashbot.bot.state_detect import pixel_indicates_upgradable
from pyclashbot.detection.image_rec import find_image, pixel_is_equal


def find_war_battle_icon(emulator):
    """Find the war battle icon on the clan war page.

    Returns (x, y) of the icon, or None if not found.
    """
    image = emulator.screenshot()
    return find_image(image, "war_battle_icon", tolerance=0.9, show_image=False)


def find_fight_mode_icon(emulator, mode: str):
    expected_mode_types = ["Classic 1v1", "Classic 2v2", "Trophy Road"]

    # Check if the mode is valid
    if mode not in expected_mode_types:
        print(f'[!] Fatal error: Mode "{mode}" is not a valid mode type. Expected one of {expected_mode_types}.')
        return None

    mode2folder = {
        "Classic 1v1": "fight_mode_1v1",
        "Classic 2v2": "fight_mode_2v2",
        "Trophy Road": "fight_mode_trophy_road",
    }

    look_folder = mode2folder[mode]

    image = emulator.screenshot()

    fight_mode_1v1_button_location = find_image(
        image,
        look_folder,
        tolerance=0.9,
        show_image=False,
    )
    if fight_mode_1v1_button_location is not None:
        return fight_mode_1v1_button_location
    return None


def find_post_battle_button(emulator):
    """Find and return coordinates for post-battle exit/OK button.

    Tries multiple detection methods in order:
    1. Pixel-based detection (fastest)
    2. Image recognition for OK button
    3. Image recognition for exit button

    Returns:
        tuple[int, int] | None: Button coordinates (x, y) or None if not found
    """
    iar = emulator.screenshot()

    pixels = [
        iar[545][178],
        iar[547][239],
        iar[553][214],
        iar[554][201],
    ]
    colors = [
        [255, 187, 104],
        [255, 187, 104],
        [255, 255, 255],
        [255, 255, 255],
    ]

    pixel_match = True
    for i, p in enumerate(pixels):
        if not pixel_is_equal(p, colors[i], tol=20):
            pixel_match = False
            break

    if pixel_match:
        return (200, 550)

    # CN (Tencent) client result screen: bottom buttons are "再来一场" (orange,
    # left) and "确定" (blue, right), centered around y~588 at 419x633. Sampled
    # off a live CN client. Prefer 确定 — the post-fight flow returns to the
    # main menu rather than queuing another battle.
    cn_pixels = [
        iar[588][115],  # 再来一场 button body (left edge, clear of text)
        iar[588][225],  # 确定 button body (left edge, clear of text)
        iar[585][210],  # dark gap between the two buttons
    ]
    cn_colors = [
        [43, 190, 255],
        [255, 175, 78],
        [43, 22, 21],
    ]
    cn_match = True
    for i, p in enumerate(cn_pixels):
        if not pixel_is_equal(p, cn_colors[i], tol=35):
            cn_match = False
            break
    if cn_match:
        return (265, 588)

    # CN (Tencent) client LOSS screen: a single centered "确定" (blue) button at
    # ~(210, 568) on 419x633 (no 再来一场). Sampled 2026-09-04 from a real
    # trophy-road loss. Without this, the bot stalls on the result screen after
    # losing and never returns to the main menu.
    cn_single_pixels = [
        iar[568][190],  # 确定 button body (left of text)
        iar[568][225],  # 确定 button body (right of text)
        iar[568][209],  # 确定 button body center
        iar[585][209],  # dark background just below the button
    ]
    cn_single_colors = [
        [255, 175, 78],
        [255, 175, 78],
        [255, 175, 78],
        [46, 46, 64],
    ]
    cn_single_match = True
    for i, p in enumerate(cn_single_pixels):
        if not pixel_is_equal(p, cn_single_colors[i], tol=35):
            cn_single_match = False
            break
    if cn_single_match:
        return (210, 568)

    coord = find_image(iar, "ok_post_battle_button", tolerance=0.85)
    if coord is not None:
        return coord

    coord = find_image(iar, "exit_battle_button", tolerance=0.9)
    if coord is not None:
        return coord

    return None


def locate_free_shop_offer_icon(emulator) -> tuple[int, int] | None:
    """Find the free daily shop offer icon anywhere on the current screen.

    Returns (x, y) of the match, or None if not found.
    """
    image = emulator.screenshot()
    return find_image(image, "daily_free_shop_offer_icon", tolerance=0.9)


def detect_upgradable_cards(emulator):
    img = emulator.screenshot()
    upgradable = []

    for i, (x, y) in enumerate(UPGRADE_POINTS, start=1):
        if pixel_indicates_upgradable(img[y][x]):
            upgradable.append(i)

    return upgradable
