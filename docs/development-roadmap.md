# 后续适配与已核实边界

更新日期：2026-10-17。

最新决定：用户要求将华为 `temperature.current` 与 `temperature.target` 都映射到 HA 设置温度。1.1.1 已实现该兼容策略，不绑定外部温度计，不改变模式或风速。以下源室温缺失与卡片默认值是背景证据；不再以等待环境温度来源作为此项的阻塞。小艺查询效果待用户复测。

## 已验收功能

用户已在智慧生活实测空调开关、目标温度、模式、风速均成功。保留现有四种模式，不新增自动模式。待研究的是**自动风速**。

## 优先级

| 项目 | 优先级 | 下一步及当前限制 |
|---|---|---|
| 空调显示/语音查询固定 26℃ | 中 | 1.1.1 按用户要求将 current/target 都上报为设置温度；等待小艺和 App 复测。不绑定其他房间的传感器。 |
| 传感器 | 中 | 先研究温湿度、门磁、水浸的原生产品定义与服务表，再加型号适配；当前尚未部署这些品类。 |
| 喂食器 | 低偏中 | 核实华为产品定义、单次喂食语义及份量单位；暂未找到可核实的产品定义，不使用电源开关模拟喂食。 |
| 插座/开关品类与定时 | 低 | 研究真正插座产品定义和 timer/delay 结构；保持已接入的断路器身份，未迁移品类。 |
| 自动风速 | 低 | 当前 2ANJ Profile 只有风速 2/3/4；需卡片和产品定义支持自动风速，不将自动伪装为低速。 |

## 卡片默认值证据与语音查询待核实项

官方 [2ANJ Profile](https://smarthome-drcn.dbankcdn.com/device/guide/2ANJ/2ANJ.json) 的 `temperature.current` 与 `temperature.target` 是不同字段。当前桥接在源室温为空时省略 `current`，见 `aircon_runtime.snapshot`。

官方 [卡片脚本](https://smarthome-drcn.dbankcdn.com/device/guide/2ANJ/h5_001/js/index.js) 的 `scope.data.temperature.current` 初始化为 **26**。`scope.translate` 仅在收到有效 `temperature.current`（含零值）时更新室温，目标温度单独更新 `target`。因此缺少室温上报时会保留卡片默认值；把 `null` 发过去也无法经该判断清空显示。

该结论描述已下载的官方脚本及本次源实体读数；若华为更换卡片版本，或源集成开始提供真实室温，需要重新核验。不能据此把所有设备的固定温度都归因于卡片。

用户补充：将设置温度改为27℃后，小艺查询仍回答26℃。HA历史记录可见目标温度曾到达27℃，但诊断并不证明云端收到或小艺读取的是哪个字段。此前“固定26℃根因已查实”的概括过宽，现收窄为“卡片默认室温值已查实”。随后用户明确指定两个字段都使用设置温度；兼容实现遵循这一决定，不能把该 current 值解释成实测室温。

## 已获取的官方候选定义

以下为候选产品，不代表旧 SDK 或云端已经验证接受。需要先核验原生单设备/批量注册元数据及服务表，再测试真实上报，最后由 App 验收。

| 用途 | 官方定义 | 关键服务 |
|---|---|---|
| 温湿度 | [113D](https://smarthome-drcn.dbankcdn.com/device/guide/113D/113D.json) | `airDetector.temperature/humidity`、`battery.lowBattery` |
| 门磁 | [113B](https://smarthome-drcn.dbankcdn.com/device/guide/113B/113B.json) | `doorSensor.status`，事件/防拆仅在存在源数据时映射 |
| 水浸 | [2BE7](https://smarthome-drcn.dbankcdn.com/device/guide/2BE7/2BE7.json) | `alarm.alarm`、`battery.alarm/level` |
| 插座及定时 | [105M](https://smarthome-drcn.dbankcdn.com/device/guide/105M/105M.json) | `switch.on`、`timer`、`delay`、`timerID` |

当前 Python 注册表只含压力传感器产品；原生库固定产品表也没有上述候选。不得仅添加 JSON 就声称支持，或将门磁/水浸改名后当压力传感器上报。

烟雾源若仅有事件，必须定义触发与恢复语义，不能把未触发的 `unknown` 当成无烟；燃气状态必须区分预热、故障、寿命到期和报警。先读取真实状态，不为测试主动触发报警、自检、消音或喂食。

## 验收要求

1. 不改变已验收空调及已有设备的身份，不重建网关。
2. 离线测试真实产品字段、状态范围、不可用处理及报警方向；原生改动需单独进程核验。
3. 新品类先做一个真实设备，核对 HA → SDK 上报与智慧生活显示，再扩展同型号。
4. 用户本地设备选择、传感器来源和身份仅保存在本地配置，不进入仓库。
