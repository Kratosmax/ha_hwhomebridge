# 本轮兼容性结论（2026-10-18）

以下停止结论针对当前设备来源、现有卡片和已检查资料，不代表华为平台永远无法实现。
公开定义及本机证据清单留在项目 `temp/autonomous-validation/`，其中账号数据不进入仓库。

## 水浸

修正2GB5服务类型（`alarm/warterAlarm`、`fault/commonFaultDetection`、`ota/update`），
保留官方Mesh协议6、原设备身份和服务ID；新建只提交新增，不再紧接上线覆盖。
独立进程已验证单台、双台服务表及其余七槽不变。
定向测试一只在线水浸，SDK发送单设备batchBind后两次记录云错误23，
上报返回-12，账号清单中2GB5数量仍为0。因此本轮停止这条产品适配，
不把23解释成已知官方错误含义，不再尝试第二只或更换SN/协议。

未登记水浸只在显式测试期间允许上报，结束后清理测试名单；正常启动不反复新增或发送失败上报。
若今后取得逐设备拒绝原因或匹配的桥接注册条件，可重新核验这条结论。

## 烟感

重新读取公开[MIoT原始定义](https://miot-spec.org/miot-spec-v2/instance?type=urn%3Amiot-spec-v2%3Adevice%3Asmoke-sensor%3A0000A023%3Alumi-mcn02%3A1)，
并与HA实际实体及Xiaomi Home事件处理代码对照。此型号只提供工作状态
Busy/Fault、电量和无参数的`high-concentration-of-smoke-detected`事件，
没有可读烟雾报警状态或报警解除事件；不是HA漏映射已有字段。

一次烟雾事件后，“仍有烟”和“烟已散去”可能具有完全相同的这些输入，
适配器无法可靠区分。保留HA原事件，不做会自动误清警或永久锁警的烟感卡片。
源集成提供持续报警及恢复状态后，这个停止条件才会改变。

## 门磁光照

公开[门磁源定义](https://miot-spec.org/miot-spec-v2/instance?type=urn%3Amiot-spec-v2%3Adevice%3Amagnet-sensor%3A0000A016%3Aisa-dw2hl%3A1)
的illumination仅有1=Weak、2=Strong，无lux读数。
当前[113B定义](https://smarthome-drcn.dbankcdn.com/device/guide/113B/113B.json)
只有`doorSensor.status/event/tamper`，没有光照字段。
另外核对的[2GB4](https://smarthome-drcn.dbankcdn.com/device/guide/2GB4/2GB4.json)、
[2Q8M](https://smarthome-drcn.dbankcdn.com/device/guide/2Q8M/2Q8M.json)是人体传感器，
不是同时保留门磁功能的替代品；它们要求的数字光照/多级光照也不是源的二值照度。

本轮不改现有门磁卡片、不生成lux、不伪造人体存在。HA中的强弱实体保持原样。
若有支持门磁加二值光照的产品定义，或用户另行要求独立光照卡片，可重新评估。

## 喂食器

已核对公开[MIoT原始定义](https://miot-spec.org/miot-spec-v2/instance?type=urn%3Amiot-spec-v2%3Adevice%3Apet-feeder%3A0000A06C%3Axiaomi-pi2001%3A3)
与HA实际实体，源端有余粮、份量和出粮动作，HA侧并不缺控制入口。
当前原生库的八个已知产品定义没有喂食器；检查186个参考适配器源码文件及四组公开代码搜索，
没有取得可验证的华为喂食器prodId、服务定义和对应卡片。
唯一相关接入文章是创建开发者产品的示例，不是可以直接使用的产品定义。

本轮在缺少华为端契约这一环停止，不用插座开关模拟出粮、不猜份数和克数换算，也未实际喂食。
这说明当前资料不足以交付适配，不证明平台不支持；取得真实产品定义后可继续。

## 空调自动风速

重新下载的[2ANJ定义](https://smarthome-drcn.dbankcdn.com/device/guide/2ANJ/2ANJ.json)
中`fan.gear`只有2=低速、3=中速、4=高速，没有自动。
对应H5的ConditioningWind组件从枚举生成下拉项，也只处理这三档。
HA确实支持自动，限制在当前华为产品定义和卡片。

保留现有空调身份、模式和已验收温控，不给未定义的gear编造自动含义。
离线测试确认自动不会误报为低速，未对实际空调下发测试命令。
HA改为自动时，当前卡片可能保留先前一档；不能宣称已支持自动风速。
若换用经过验证且兼容现有功能的产品定义，这一结论须重新核验。
