# 维护接续

最后校准：2026-10-17。本 fork 在上游基础上整理了已部署的 amd64 空调扩展和型号级插座开关适配。

## 接手先读

1. `AGENTS.md`、本文件、`docs/aircon.md`。
2. `git status --short --branch`、`git log -5 --oneline`、`git remote -v`。
3. 版本源 `custom_components/hwhomebridge/manifest.json`。

## 当前实现

- `aircon_runtime.py`：保持空调 SN 算法与原网关绑定；PID009只对支持型号启用，其余设备委托原逻辑。
- `aircon_settings.py`：从 HA 根目录的本地配置选择实体，单个受支持实体可以自动选择；禁止把实际实体 ID 写回源码。
- `aircon_conversion.py`：温度/模式/风速转换。环境温度缺失时不伪造；自动风不映射成低档。
- `hilink_bridge/aircon`：随包安装的固定版本候选库和静态配置，不依赖某台机器的实验路径。
- `tools/build_aircon_library.py`：按固定源库哈希重建候选库；补丁不含设备身份或登录状态。
- `config/adapters/xiaomi/plugs_switch_only.json`：通用型号级主开关适配，无个人实体信息。

## 本轮验收记录

2026-10-17：10项单测、配置验证、固定版本候选库重建哈希、隐私扫描和编译检查通过。运行版1.1.0已从维护分支代码部署，HACS只保留本fork来源，HA/HACS均loaded，网关状态为在线；迁移前后设备SN集合和空调SN一致，状态上报已启用。未操作实际设备，未重新进行手机端云控验收。运行代码基线为提交8b5cbd6，后续本记录提交仅更新文档。

部署主机下载GitHub归档出现多次超时，本轮由开发机部署经过哈希核验的Git源码，并将准确提交交给HACS登记管理；没有修改HACS源码或主机网络。网络下载链路仍需单独解决，不能把来源登记成功当成自动更新下载成功。

## 当前待办及边界

- 后续从手机端核验迁移后的真实云控；HA侧映射、SN保持及网关在线已核验。
- 环境温度显示固定值：源 climate 可能返回 `current_temperature=None`，必须先区分目标温度与环境实测值，不把卡片缓存当成传感器读数，也不伪造环境温度。
- 固定候选库只适用于此版本 amd64；槽5与原灭蚊器不能并用。
- 注册回调成功或本地路由通过，不等于 App 端在线或真实物理控制已验证。
- 本地单测不调用 SDK，不操作实际设备；不把开发机/NAS路径、日志、令牌、SN或设备ID提交。

## 验证命令

```text
python -m unittest discover -s tests -v
python custom_components/hwhomebridge/validate_config.py
python tools/build_aircon_library.py
python tools/check_privacy.py
git diff --check
```

本轮发布和迁移结果以最后提交、远端分支、HACS实际登记与本地私有核验记录为准。仅有本文件不能证明设备端部署成功。
