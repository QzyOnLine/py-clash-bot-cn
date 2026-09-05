"""Configuration for PyClashBot interface elements."""

from __future__ import annotations

from dataclasses import dataclass

from pyclashbot.emulators.google_play import GooglePlayEmulatorController
from pyclashbot.interface.enums import (
    BATTLE_STAT_FIELDS,
    BATTLE_STAT_LABELS,
    BOT_STAT_LABELS,
    COLLECTION_STAT_FIELDS,
    COLLECTION_STAT_LABELS,
    WIN_RATE_STAT_FIELDS,
    WIN_RATE_STAT_LABELS,
    BotStatField,
    StatField,
    UIField,
)
from pyclashbot.utils.platform import is_macos


@dataclass
class StatConfig:
    """Configuration for a stat display element."""

    key: StatField | BotStatField
    title: str
    size: tuple[int, int] = (6, 1)


@dataclass
class JobConfig:
    """Configuration for a job checkbox element."""

    key: UIField
    title: str
    default: bool = False
    tooltip: str = ""
    extras: dict[UIField, ComboConfig] | None = None


@dataclass
class RadioConfig:
    """Configuration for a radio button element."""

    key: UIField
    title: str
    group_id: str
    default: bool = False


@dataclass
class ComboConfig:
    """Configuration for a combo box element."""

    key: UIField
    label: str
    values: list[str | int]
    default: str | int = ""
    size: tuple[int, int] = (5, 1)
    label_size: tuple[int, int] = (6, 1)
    tooltip: str = ""


# Statistics Configuration
WIN_RATE_STATS = [StatConfig(field, WIN_RATE_STAT_LABELS[field]) for field in WIN_RATE_STAT_FIELDS]

BATTLE_STATS = [StatConfig(field, BATTLE_STAT_LABELS[field]) for field in BATTLE_STAT_FIELDS]

COLLECTION_STATS = [StatConfig(field, COLLECTION_STAT_LABELS[field]) for field in COLLECTION_STAT_FIELDS]

BOT_STATS = [
    StatConfig(BotStatField.RESTARTS_AFTER_FAILURE, BOT_STAT_LABELS[BotStatField.RESTARTS_AFTER_FAILURE]),
    StatConfig(BotStatField.TIME_SINCE_START, BOT_STAT_LABELS[BotStatField.TIME_SINCE_START], size=(8, 1)),
]

# Job Configuration (order matches bot state machine: switch_account → upgrade → …)
JOBS = [
    JobConfig(
        UIField.SWITCH_ACCOUNTS_USER_TOGGLE,
        "🔀 切换账号",
        default=False,
        tooltip="在每个机器人循环结束时切换已关联的 Supercell 账号。",
        extras={
            UIField.MAX_ACCOUNT_SELECTION: ComboConfig(
                key=UIField.MAX_ACCOUNT_SELECTION,
                label="循环账号数",
                values=[2, 3],
                default=2,
                label_size=(15, 1),
                tooltip="要循环切换的已关联账号数量 (2-3)。",
            )
        },
    ),
    JobConfig(
        UIField.CARD_UPGRADE_USER_TOGGLE,
        "⬆️ 升级卡牌",
        default=False,
        tooltip="金币足够时在收藏中升级卡牌。",
    ),
    JobConfig(
        UIField.UPGRADE_PRINCESS_USER_TOGGLE,
        "👑 升级公主塔",
        default=False,
        tooltip="金币足够时从卡牌菜单升级公主塔。",
    ),
    JobConfig(
        UIField.CARD_MASTERY_USER_TOGGLE,
        "🎯 卡牌精通奖励",
        default=False,
        tooltip="可从卡牌菜单领取卡牌精通奖励时自动领取。",
    ),
    JobConfig(
        UIField.SHOP_DAILY_OFFER_USER_TOGGLE,
        "🛒 商店每日免费礼包",
        default=False,
        tooltip="领取商店中的每日免费礼包。",
    ),
    JobConfig(
        UIField.CLAN_DONATE_USER_TOGGLE,
        "📤 捐赠卡牌",
        default=False,
        tooltip="从部落聊天界面向部落成员捐赠卡牌。",
    ),
    JobConfig(
        UIField.CLAN_REQUEST_CARDS_USER_TOGGLE,
        "📥 请求卡牌",
        default=False,
        tooltip="在部落聊天中向部落成员请求卡牌。",
    ),
    JobConfig(
        UIField.CLAN_CLAIM_GIFTS_USER_TOGGLE,
        "🎁 领取礼物",
        default=False,
        tooltip="从部落聊天领取皇室通行证金币礼物。",
    ),
    JobConfig(
        UIField.WAR_USER_TOGGLE,
        "🛡️ 部落战",
        default=False,
        tooltip="从部落战页面进行部落战战斗。",
    ),
    JobConfig(
        UIField.CLASSIC_1V1_USER_TOGGLE,
        "⚔️ 经典 1v1",
        default=True,
        tooltip="进行经典 1v1 天梯对战。",
    ),
    JobConfig(
        UIField.CLASSIC_2V2_USER_TOGGLE,
        "👥 经典 2v2",
        default=False,
        tooltip="进行经典 2v2 对战。",
    ),
    JobConfig(
        UIField.TROPHY_ROAD_USER_TOGGLE,
        "🏆 天梯对战",
        default=False,
        tooltip="进行天梯 1v1 对战。",
    ),
    JobConfig(
        UIField.RANDOM_DECKS_USER_TOGGLE,
        "🎲 随机卡组",
        default=False,
        tooltip="每次对战前随机洗牌一个卡组中的卡牌槽位。",
        extras={
            UIField.DECK_NUMBER_SELECTION: ComboConfig(
                key=UIField.DECK_NUMBER_SELECTION,
                label="卡组槽位",
                values=[1, 2, 3, 4, 5],
                default=2,
                label_size=(10, 1),
                tooltip="每次对战前要随机洗牌的卡组槽位 (1-5)。",
            )
        },
    ),
    JobConfig(
        UIField.CYCLE_DECKS_USER_TOGGLE,
        "♻️ 轮换卡组",
        default=False,
        tooltip="在多次对战之间轮换多个卡组槽位。",
        extras={
            UIField.MAX_DECK_SELECTION: ComboConfig(
                key=UIField.MAX_DECK_SELECTION,
                label="轮换卡组数",
                values=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                default=2,
                label_size=(15, 1),
                tooltip="要轮换的卡组槽位数量 (1-10)。",
            )
        },
    ),
    JobConfig(
        UIField.RANDOM_PLAYS_USER_TOGGLE,
        "❔ 随机出牌",
        default=False,
        tooltip="战斗中在随机位置出牌，而非使用默认策略。",
    ),
    JobConfig(
        UIField.DISABLE_WIN_TRACK_TOGGLE,
        "📊 胜负统计",
        default=False,
        tooltip="每次对战后在统计页记录胜场和负场。",
    ),
]

# Emulator Settings Configuration
MEMU_SETTINGS = [
    RadioConfig(UIField.OPENGL_TOGGLE, "OpenGL", "render_mode_radio"),
    RadioConfig(UIField.DIRECTX_TOGGLE, "DirectX", "render_mode_radio", default=True),
]

# BlueStacks specific renderer settings
# DirectX is default on Windows, Vulkan on macOS (DirectX not available on macOS)
BLUESTACKS_SETTINGS = [
    RadioConfig(UIField.BS_RENDERER_GL, "OpenGL", "bs_render_mode_radio"),
    RadioConfig(UIField.BS_RENDERER_DX, "DirectX", "bs_render_mode_radio", default=not is_macos()),
    RadioConfig(UIField.BS_RENDERER_VK, "Vulkan", "bs_render_mode_radio", default=is_macos()),
]

EMULATOR_CHOICE = [
    RadioConfig(UIField.MEMU_EMULATOR_TOGGLE, "MEmu", "emulator_type_radio", default=True),
    RadioConfig(UIField.GOOGLE_PLAY_EMULATOR_TOGGLE, "Google Play Games", "emulator_type_radio"),
    RadioConfig(UIField.BLUESTACKS_EMULATOR_TOGGLE, "BlueStacks 5", "emulator_type_radio"),
]

# Google Play Settings Configuration
GOOGLE_PLAY_SETTINGS = [
    ComboConfig(UIField.GP_ANGLE, "angle", ["true", "false"]),
    ComboConfig(UIField.GP_VULKAN, "vulkan", ["true", "false"]),
    ComboConfig(UIField.GP_GLES, "gles", ["true", "false"]),
    ComboConfig(UIField.GP_SURFACELESS, "surfaceless", ["true", "false"]),
    ComboConfig(UIField.GP_EGL, "egl", ["true", "false"]),
    ComboConfig(UIField.GP_BACKEND, "backend", ["gfxstream", "angle", "swiftshader"]),
    ComboConfig(UIField.GP_WSI, "wsi", ["vk", "glx"]),
]

# Device Serial Configuration (for ADB device targeting)
GOOGLE_PLAY_DEVICE_CONFIG = ComboConfig(
    UIField.GP_DEVICE_SERIAL,
    "Device",
    [],
    default=GooglePlayEmulatorController.DEFAULT_DEVICE_SERIAL,
    size=(15, 1),
    label_size=(6, 1),
)

BLUESTACKS_DEVICE_CONFIG = ComboConfig(
    UIField.BS_DEVICE_SERIAL, "Device", [], default="", size=(15, 1), label_size=(6, 1)
)


def _job_setting_keys() -> list[str]:
    keys: list[str] = []
    for job in JOBS:
        keys.append(job.key.value)
        if job.extras:
            keys.extend(extra.value for extra in job.extras)
    return keys


# All user configuration keys (auto-generated from configs)
USER_CONFIG_KEYS = (
    _job_setting_keys()
    + [radio.key.value for radio in MEMU_SETTINGS + BLUESTACKS_SETTINGS + EMULATOR_CHOICE]
    + [combo.key.value for combo in GOOGLE_PLAY_SETTINGS]
    + [
        UIField.THEME_NAME.value,
        UIField.RECORD_FIGHTS_TOGGLE.value,
        UIField.RECORDING_FOLDER_PATH.value,
    ]  # Data settings
    + [UIField.GP_DEVICE_SERIAL.value, UIField.BS_DEVICE_SERIAL.value]  # Device serial settings
)

# Keys to disable when bot is running
DISABLE_KEYS = [*USER_CONFIG_KEYS, "Start"]
