# py-clash-bot 国服适配版（CN）

基于开源项目 **[pyclashbot/py-clash-bot](https://github.com/pyclashbot/py-clash-bot)** 修改的皇室战争 **国服（腾讯版）** 适配分支。

## 说明

本仓库**已完全适配皇室战争国服**（腾讯版，包名 `com.tencent.tmgp.supercell.clashroyale`），
开发与测试使用 **MuMu Player 12 模拟器**（ADB 模式，分辨率 419x633@160dpi）。

适配范围仅涉及以下功能，用于个人在游戏内刷奖杯（Trophy Road）、皇冠（部落战）等游戏内奖励：

- **天梯对战**：Trophy Road / 经典 1v1 / 经典 2v2 的战斗流程与结算页识别
- **部落聊天**：捐赠卡牌 / 请求卡牌 / 领取礼包
- **部落战（war）**：部落战页面识别与对战流程
- **奖杯之路奖励**：战斗后奖励弹窗的识别与领取
- **ADB 设备管理**：自动发现可用模拟器设备并显示名称（MuMu 等）

未适配或不适用的原功能（如每日商店、卡牌精通等）默认关闭，保持原项目行为。

## 主要改动

- 识别国服包名 `com.tencent.tmgp.supercell.clashroyale`，优先国际服、回退国服
- 中文化界面下的像素指纹、按钮颜色（橙色/蓝色/绿色）与坐标适配
- 修复 Windows 中文路径下模板图片加载失败问题（`np.fromfile` + `cv2.imdecode`）
- ADB 设备列表自动刷新、设备名称显示、刷新按钮高 DPI 点击修复
- 国服专属弹窗处理（活动页、奖杯奖励页、部落战结算页等）
- MuMu 模拟器实例自动发现与 PATH 注入

## 出处与许可

- **原项目**：[pyclashbot/py-clash-bot](https://github.com/pyclashbot/py-clash-bot)
- **许可证**：遵循原项目 [py-clash-bot Non-Commercial Copyleft License 1.0 (NC-CL-1.0)](py-clash-bot/LICENSE)
- 本项目为个人学习与娱乐用途的修改版，非商业使用

## 风险提示

任何游戏自动化都违反 Supercell / 腾讯用户协议，存在封号风险，请使用小号并自担风险。
