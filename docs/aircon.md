# 空调扩展与迁移

此 fork 在原项目上保留了已实机接入的 2ANJ 空调扩展，使用原 HiLink SDK、原网关绑定。仅 amd64、`lumi.acpartner.mcn02` 型号经过当前实现验证。它不是通用空调 SDK。

## 安装与本地设置

HACS 自定义仓库添加 `Kratosmax/ha_hwhomebridge`，类别选择集成。已有原项目时先只移除旧的 HACS 仓库登记，保留 HA 集成条目和绑定，再从本 fork 安装。不要删除 HA 网关集成，不要覆盖 `.storage/hwhomebridge`。

一个支持型号的 climate 实体会自动选择；多个实体时在 HA 配置根目录创建 `hwhomebridge_local.json`：

```json
{"enabled": true, "entity_id": "climate.example", "capture_native_events": false}
```

这份文件是本地配置，不上传 Git。不要在仓库写实体 ID、设备 ID、SN、令牌、内网地址或个人路径。插件目录之外的此配置不会被 HACS 更新覆盖。

候选库随集成安装在 `hilink_bridge/aircon`，状态文件写入 HA 的 `.storage/hwhomebridge/aircon`，不再依赖实验目录。默认不接管 stdout；只有显式开启诊断时采集数字事件，并在注册诊断结束后恢复 stdout。

## 实现

- `aircon_runtime.py`：限定 PID009 的运行时适配；其他产品委托原逻辑。
- `aircon_conversion.py`：下行控制与状态转换。模式 1制冷、2制热、3送风、4除湿；风速仅 2低、3中、4高。Profile 不含自动风或摆风，不用其他档位冒充。
- `aircon_settings.py`：从本地设置或支持型号确定实体。
- 原生槽5替换为公开 2ANJ 产品元数据：类型012、制造商312、型号U2-86QMP-Z02(HW)、协议3、四服务 switch/mode/temperature/fan。原灭蚊器槽与空调不能并用。
- 保持现有 `HBAC + sha256(device_id + ':2ANJ-v2')[:12]` 算法，迁移不改变已接入空调身份。
- 等待网关在线，再延迟60秒进行新设备注册及上线；再延迟60秒启用状态上报。调用成功不等于云端成功，需智慧生活端验证。

## 温度语义和已知问题

HA `temperature` 是目标设定温度，对应 `temperature.target`；`current_temperature` 是环境实测温度，对应 `temperature.current`。当前源集成可能不提供环境温度，此时省略 `current`，不伪造数值、不用目标温度代替环境温度。智慧生活显示固定值的问题仍需区分源缺失与卡片缓存；不能把调节目标温度当成环境温度也应变化。

## 升级与回滚

部署前把当前集成目录、HACS 登记和本地设置备份到仓库外的私有位置。保留既有 `config/adapters/local`；本 fork 同时提供不含个人信息的型号级插座开关适配。不要删除这些适配导致插座失配。

回滚恢复备份的集成目录后重启 HA，保留网关 `.storage`。若停用空调，在设备管理中先排除它；不要通过重新绑定网关解决代码升级问题。

## 本地验证

```text
python -m unittest discover -s tests -v
python custom_components/hwhomebridge/validate_config.py
python tools/check_privacy.py
```

测试使用虚拟实体和模拟服务，不操作实际设备。新功能或新 SDK 修改需要另行验证真实 App 卡片、在线状态及云端下行。
