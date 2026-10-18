# 维护接续

## v1.2.0 发布收尾（2026-10-18，优先于下方历史）

用户已明确授权提交、推送并发布最新版，覆盖下方历史中的“不推送”限制。版本源 manifest.json 已更新为1.2.0。本版包含已验收空调整数温度同步、统一插座开关/倒计时/计量、温湿度/门磁/燃气适配、服务表ABI修正与上报去重。

发布检查发现socket_runtime还依赖HA临时目录中手工预置的验证计划、脚本和候选库；现改为从集成内hilink_bridge/plans及native_metadata_probe.py读取。随包加入socket_test/gas_test及燃气校验基底，插座库afbd689、组合库a96d53哈希与已验收运行版一致，验证脚本与既有Linux验证版本逐字节一致；临时目录仅保存检查结果。未改设备身份、上报顺序或控制语义，未覆盖正在运行的HA、重启或操作设备。

新增tests/test_release_assets.py验证两种启动路径在无预置temp文件时仍能找到校验脚本、计划和哈希正确的库；全套58项测试、配置、编译、隐私与diff检查通过。已从Git暂存树导出干净源码，在独立目录再次通过58项测试、编译和配置检查，并逐文件扫描归档隐私；校验结果在temp/release-v1.2.0。没有新Linux进程启动或手机验收，不将模拟路径测试称为新的手机验收。私有会话、令牌、HA本地配置和原始证据不入库。发布说明明确水浸、烟感、光照、喂食器、自动风速的未实现边界，周定时不在需求内。

本次发布改动：本轮已列出的源码/测试/文档及此前工作树中尚未提交的适配；另改README.md、manifest.json、socket_runtime.py、native_probe_service.py、tests/test_gas_candidate.py、docs/aircon.md和本文件，新增tests/test_release_assets.py、hilink_bridge/plans/{gas,socket}.json、hilink_bridge/{gas_test,socket_test}的静态库/配置与燃气验证基底。非仓库产物仅在项目temp/release-v1.2.0，最终以Git提交文件清单为准。

可重跑：python -m unittest discover -s tests -q；python -m compileall -q custom_components/hwhomebridge；python custom_components/hwhomebridge/validate_config.py；python tools/check_privacy.py；git diff --check。回滚点为此前v1.1.1标签及私有部署备份；历史v1.1.1温度存在已知问题，不建议仅为回滚测试而覆盖现有正常HA。

## 2026-10-18 最新状态（优先于下方历史记录）

### 当前权威摘要（下方按历史过程保留）

**本轮自主计划已收尾（2026-10-18）**：最后一次真实重启及云端复查通过。`temp/autonomous-validation/registration-live/verification.json`确认原有全部SN集合不变、网关/四插座在线、传感器报告启用、部署哈希匹配；传感器启动窗口绑定新增0、云错误0、未登记水浸上报0、队列末值0。`cloud-final-verification.json`再次精确对应SDK与云端：温湿度1/门磁3/燃气1共五只均在线且值逐字段一致，四插座开关一致，空调在线。最新57项测试通过（新增真正的混合新旧传感器启动回归测试），配置/编译/隐私/diff检查通过，未提交或推送。

计划状态已全部给出结论：上述五只云验证通过；水浸修正后仍云拒绝23/SDK-12/账号0条，本轮停止；烟感缺解除状态、门磁光照缺当前卡片字段、自动风速缺2ANJ枚举，均有原始定义证据而停止；喂食器缺可验证华为定义，作为资料阻塞停止，不宣称平台不支持。插座周定时已明确移除。没有待用户验证/确认事项，也不再后台持续水浸试错。依据、边界、验证覆盖和本轮已改完整列表见下面记录及 `docs/autonomous-validation.md` / `docs/compatibility-limits.md`。手机原生卡片逐字段、真实报警和喂食未测试，不计为实机验收。下文“session36448进行中/待复查/56项”均为收尾前过程，现在已完成。

用户最新授权：建立计划，自主处理到全部项目得到通过或有证据停止的结果，不提问。传感器8/10、门磁光照3/10、喂食器和自动风速1/10；**插座周定时从需求删除，不能继续列为待办**。计划 `docs/autonomous-validation.md`，停止依据 `docs/compatibility-limits.md`。不推送、不删除现有设备、不进行真实报警/自检/消音/喂食/断电测试。

本轮新增水浸修正：slot6的serviceType与serviceId原先混写，已从官方2GB5修正类型，ID/协议6/其他七槽不变；隔离单台双台验证通过。组合库新SHA256 `a96d53ea538146c4572c5e07d86979cc2b27e7af53c35a50093974c21f829138`。新工具 `tools/build_water_candidate.py` 从旧efa燃气候选重建。已定向部署socket_runtime新哈希、contact_moisture_runtime、aircon_settings、组合so与计划文件，清单在 `temp/autonomous-validation/water-live/deployment.json`，没有整目录覆盖。

水浸单只新顺序测试仍获两次云错误23、SDK-12，实际账号2GB5清单0；停止重试，不新增身份/乱改协议。修复未登记水浸后台重复失败上报：仅显式测试期间允许发送，结束清理WATER_TRIALS。源设备及旧SN均保留。最终重启检查发现一只原门磁仍因3/1竞态发新增，已将门磁/水浸/燃气策略统一为未登记只新增、已登记只上线；三只门磁已由SDK设备编号摘要与真实云记录逐一核实，SN写本地 `sensor_registered_sns`。修正后正在做最后一次重启验证，进程session36448；结果应在 `temp/autonomous-validation/registration-live/verification.json`。不要把此前 `final-live` 的0新增断言失败当作水浸重试，实际是index20门磁新增，已据证据修正。

上一轮云端独立核验已通过：温湿度1、门磁3、燃气1均在线，值逐字段一致；四插座在线且开关状态一致，空调在线；另有旧燃气记录离线未删。证据 `temp/autonomous-validation/cloud-final-verification.json`，最后一次重启后还需刷新云端再比对。原native身份摘要探针 `temp/gas-payload-audit/sdk-sensor-fingerprints.json`仅读父进程、无attach/stop/write/活动原生调用，设备编号及SN只保存摘要。

其他项已按证据停止：公开原始MIoT烟感只有Busy/Fault及无参数烟雾事件，无恢复，不能实现可靠持续报警；门磁只有Weak/Strong而113B无光照字段，核对替代为人体产品；喂食器HA入口存在，但186个参考源码及四组搜索无可验证华为产品定义，不能断言平台不存在；2ANJ新取官方定义/H5仍仅低中高，无自动。定义HTTP200及SHA、原始MIoT、搜索清单与机器断言在 `temp/autonomous-validation/definitions/`、`compatibility-findings.json`、`feeder-research.json`。本轮不再将这些标为等用户验证。

本轮源码/文档修改完整列表：`contact_moisture_runtime.py`、`aircon_settings.py`、`socket_runtime.py`、`tools/build_water_candidate.py`(新)、`tests/test_water_metadata.py`(新)、`tests/test_gas_candidate.py`、`docs/autonomous-validation.md`(新)、`docs/compatibility-limits.md`(新)、`docs/development-roadmap.md`、`docs/socket-countdown.md`、`docs/contact-moisture.md`、`docs/gas-sensor.md`、本文件。其余大量工作树更改为前序遗留，不能重置。私有辅助脚本和证据均在项目temp，`read_cloud_devices.py`已扩展`--products`可一次读取指定品类缓存，仍禁止设备控制端点。

最近必要检查56项unittest、compileall、配置校验、隐私扫描、diff检查通过，均由agent执行，用户没有手动执行这些测试。尚未推送/发布。剩余本轮收尾：session36448完成后，用缓存脚本更新`cloud-final.json`，将`verify_cloud_final.py`输入指向`registration-live/after-all.json`重跑；确认未登记水浸无上报/新绑定、原设备SN及云值保持，更新计划为结束。不存在其他需询问用户的事项。

2026-10-18缓存复用实测通过：用户完成新版登录后，已自主运行 `python temp/gas-payload-audit/read_cloud_devices.py --cached --state`，无交互读取成功。用SDK设备编号摘要精确对应到当前云端燃气记录，确认在线，且与已验收空调/四插座/温湿度/门磁同家庭同网关。云端三项缓存与HA逐字段一致：alarm=0，fault code/status=0，gas current=0、level=1。另一条燃气记录离线，未删除。网关与四插座在线；本地enabled/registered均true，后续启动只上线。独立校验结果 `temp/gas-payload-audit/cached-access-verification.json`。以下“待新版登录/待缓存复用/待对应云记录”均为此前过程，已完成；真实报警、自检、消音及手机逐字段显示未测试。会话密文只在Git忽略的temp目录，不保存密码，不推送。

最新纠正：账号清单脚本已由用户成功登录读取，28条记录中2条2MXG均有家庭和上级网关关联；用户随后确认燃气设备在手机被折叠。燃气“未出现/注册失败”不再是当前结论，不能反推最早成功时间。保留两条记录，不自行删除；待用脚本读取当前鲜活身份对应云记录及浓度/报警/故障缓存值，不触发设备动作。后台新诊断部署检查通过：网关/四插座在线，原有SN保持，队列末值0。`temp/gas-payload-audit/live/verification.json`已落盘；新增诊断没捕获原始绑定响应或授权状态，不能解释为不存在授权。

用户明确要求“让我登录一次，后续自行用脚本查”。本机脚本 `temp/gas-payload-audit/read_cloud_devices.py` 现支持 `--login`（当前Windows用户DPAPI加密会话持久化）、`--cached`（无需交互读取、过期刷新）、`--state`（仅指定燃气的云缓存读接口，无控制命令）。会话密文为 `temp/huawei-account/session.dpapi`，已确认被Git忽略；密码/验证码不保存。DPAPI合成数据加解密、接口白名单、脱敏自检通过。用户刚才成功运行的旧版不保存会话，因此需新版再登录一次完成保存；尚待此步骤和自主复用验证。不要宣称已经可免登录复用。

已基于账号设备记录及用户折叠发现，将本地 `gas_sensor_registered` 设true，其他设置逐项保持；未重启、删设备或控制设备。下次启动只上线，不再新增。证据与原设置备份在 `temp/gas-payload-audit/registration-confirmed.json` / `settings.before-mark-registered.json`。本机最新cloud查询仍需新版登录：之前会话未保留，不能凭空恢复。待登录后执行 `python temp/gas-payload-audit/read_cloud_devices.py --cached --state` 自主验证，并比对SDK鲜活设备编号摘要（`sdk-memory-fingerprints.json`）与云清单摘要；不再要求用户刷新猜测。不要调用 `contact_moisture_retry_gas`，该强制重试入口仍会新增。新增临时工具均未入仓库；本轮公开代码改动是native_log_probe、其隐私测试及进度文档，52项测试通过，没有推送。

继续排查更新：用户要求继续后，已重新开启燃气实验，沿用 `gas_sensor_identity_version=2` 和原稳定SN，只部署 `native_log_probe.py` 的脱敏绑定诊断，未改产品/协议/原生库。隔离实际注册JSON对照验证插座124U和燃气2MXG字段完整，PLC=5不会在序列化时被拒绝；公开IotcProtType枚举佐证PLC=5。52项测试通过。采集恢复检查进行中，最终以 `temp/gas-payload-audit/live/verification.json` 为准；下条关闭记录为历史。已准备一次性只读云设备清单工具 `temp/gas-payload-audit/read_cloud_devices.py`，仅完成离线自检，未登录账号；密码、验证码、令牌不落盘，设备API限定两个GET端点。尚无手机成功结论，未提交/推送。

- 燃气新身份对照的手机结果仍是完全没有设备，未接入成功。已关闭本地燃气实验，已验收插座基底恢复验证通过：网关与四插座在线，原有非燃气SN集合保持，温湿度和门磁上报启用，15次队列采样均0，实际加载afbd基底；结果读取 `temp/gas-trial-disabled/verification.json`。没有删除云端设备或物理操作，也没有要求重复手机验收。准确失败环节未知，SDK新增/同步/上线响应不等于家庭绑定或手机显示成功。禁止继续盲换SN、协议或反复要求刷新。
- 餐桌显示延迟已通过SDK服务表ABI修正解决，用户确认两次进入都立即显示开启。基底SHA256为 `afbd689f2b9f10137428a51898cf83dad72de87a51cf9f9c09f493bbc9861a12`。四插座统一实现，床头/厨房功率直接使用W。下文显示延迟、状态错误及名称重建记录均为历史，不是当前待修结论。
- 空调温度同步、温湿度读数与重启NEW修复、三门磁状态、餐桌开关和倒计时关闭均已获用户验收。小艺温度查询、自动风速、喂食器、门磁光照、水浸及周定时仍未完成；烟感缺持续报警恢复来源，不能自行清警。
- 最近代码验证51项unittest、compileall、配置校验、隐私检查和diff检查通过。未提交、推送或发布；后续推送必须另获用户明确授权。不要整目录部署仓库，运行目录与仓库有意不同。

### 历史记录

状态/名称修正最新核验：32项测试通过，本机只读刷新8项SDK结果均0，之后实际定时补报已发生。床头开关HA为on，明确发往其独立SN的三次switch上报均为{"on":1}且返回0；四个实体均保持on，physical_commands_observed=0。没有执行用户禁止的开关操作，也没有把状态取反。手机是否已同步开启不能由此独立确认，仍不得声称已验收。

餐桌云端名称仍未修好：HA registry的name/name_by_user均已是餐桌排插，但本轮同SN DEV_ADD没有触发name_supplied回调，不能称改名成功。公开SDK头文件存在HiLinkSyncBrgDevInfo接口，但当前固定so的dynsym未导出它或其他可调用改名入口；当前可调用桥接状态入口不能完成已存在卡片的名称更新。没有擅自删除已验收的新卡以重建。各本地registered现已设true，避免维护重启继续重复新增。状态补报证据在temp/socket-state-name-fix/verification.json，名称同步失败的证据names_supplied为空。

用户反馈后的最新待修项：餐桌排插云端仍为旧测试名，床头开关智慧生活显示关闭，但用户明确实际开启，并要求不得操作开关。只读核查四个HA总开关均为on，socket诊断也均为switch.on=1，因此不能取反、不能归因为已查实的设备型号问题，也不能要求用户重复证明读数。当前尚未查明云端/卡片显示不一致的准确根因。

本轮增加每60秒只读状态补报、socket_refresh_state只读服务、SDK查询/上报实际payload和SN记录、名称回调name_supplied证据。没有调用apply或switch服务。32项单测通过，包括周期补报不触发任何开关操作。已部署socket_runtime.py并重启一次，餐桌卡同SN仅补一次新增元数据以同步名称，其余三卡设registered=true避免重复新增；等待启动后连续补报及名称回调核验。证据和回滚点在temp/socket-state-name-fix。不可提前声称手机显示问题已经解决；不推送/发布。

批量迁移后台核验完成：4张124U新卡的switch/delay均返回0，对应4张旧008卡的定向删除均返回0，排除记录已落盘，HA旧桥接条目已移除。原始4个HA设备保留，4个总开关迁移前后均为on，没有收到或发送物理开关命令；网关在线、空调SN与其他无关SN保持。证据在temp/socket-migration/verification.json、registry-verification.json、retirement-result.json。已请用户确认手机端四张新卡在线、旧卡消失，仍待手机回复；不要仅凭SDK0宣称云删除已验收。餐桌排插registered已为true，其余三张本地socket_entities中的registered仍为false，手机确认后需改true防止后续重启重复新增。未重启/推送/发布任何额外改动。

插座批量迁移进行中：用户明确授权“删除原卡片，然后将其他插座也都处理”。已核对008旧卡对应的4个总开关：餐桌排插、床头开关、厨房开关、电脑。socket_runtime.py扩展为按SN隔离多个实体、命令和倒计时，餐桌排插沿用已验收的固定新SN；新增31项测试中的多设备隔离、删除白名单及替代未就绪不删除测试均通过。候选so完全未改，只更新Python运行时并重启一次。

新增socket_retire_legacy仅接受本地迁移清单的显式旧SN，核对旧品类008、同一开关实体与新插座两项上报0后才删除该旧卡并保存排除记录，防止重启重生；不删除原始HA设备或实体。迁移清单、部署前组件/配置/排除记录和后续验证放项目temp/socket-migration。正在等待新卡上报，后台没有执行物理开关操作，电脑插座不做断电测试。未提交/推送/发布。

插座最新验收：用户确认124U新卡出现、在线、有倒计时入口；随后确认餐桌排插实际开关和1分钟倒计时关闭均成功。SDK trace记录delay命令、switch命令及countdown_executed(turn_on=false)，HA独立历史记录确认对应时刻off、之后手动on；当前已恢复on。已将本地socket_test_registered设为true，后续启动只发送在线，未重启。此项“正确插座品类+总开关+倒计时关闭”完成单设备实机验收；倒计时开启、取消/修改的手机验收、每周循环定时及其余插座品类迁移尚未完成。原断路器卡保留，未删除绑定、未发布。用户验收证据在temp/socket-live-test/user-card-verification.json，HA独立历史在ha-switch-history.json。

本轮续做插座：用户选定餐桌排插，新增独立SN的124U单设备测试卡，原断路器设备保持。新增native_probe_service.py、socket_runtime.py、tests/test_socket_runtime.py、tools/build_socket_candidate.py；调整socket_delay.py使落盘移出HA事件循环，入口增加默认关闭的测试开关，更新docs/socket-countdown.md。29项单测、编译、配置和隐私检查通过，未提交/推送/发布。

124U候选哈希c625e224bb57c9a869008180f9769f052c2632dc05bb9481f88277c8e7c06fb9：独立进程、空网络命名空间验证成功，单设备/批量元数据一致，其他七槽完全不变；检测未启动SDK、读取绑定或注册设备。只读检测入口最初尝试集成重载未读取新Python，随后一次HA重启加载成功。之后为加载单插座测试候选再次重启；没有热覆盖运行so。

本机插座测试已进入手机验收阶段：query读取真实开关为on，switch和delay两项SDK上报返回0。注册日志同时有cloud_add_success_marker与多次云错误23，不能将成功标记单独归属到该插座，也不能将23解释成已知官方含义。网关在线、旧SN集合和空调SN保持，未发送物理开关指令。已询问用户新卡片是否出现/在线/有倒计时，未确认前不记作接入完成、不设置socket_test_registered。证据及完整回滚点在项目temp/socket-live-test，原生检测结果在temp/socket-research/native-probe-result.json。

- 用户已确认燃气回滚后原有设备恢复。燃气仍关闭，运行中的组件采用燃气前备份；仓库中的燃气候选和注册探针仍属未验实验，不能整目录覆盖部署。
- 温湿度NEW修复已部署，运行文件只更新thermohygrometer_runtime.py。保留原发现流程的新旧判断，延迟期间仅记住真正的新设备请求，启动不再无条件发status=3。本机重启只出现status=1，原温湿度SN保持、读数上报恢复。用户确认NEW已清除且原有设备正常。以后维护重启时再复核是否重现，不为此连续重启。
- 本轮新增socket_delay.py、tests/test_socket_delay.py、docs/socket-countdown.md，并更新温湿度脚本、测试与docs/thermohygrometer.md。插座倒计时仅离线开发：官方124U H5命令解析、原子保存、修改、取消及模拟到时执行已测；未接入HA调度、未部署、未操作实际插座。不把此项记作智慧生活定时已完成。周定时尚未实现。
- 本轮验证：26项unittest、compileall、validate_config、check_privacy、git diff --check通过。公开源码无用户实体、身份或令牌；运行证据和回滚点在项目temp/thermo-registration-fix/。没有提交、推送、发布。
- 下一步注册测试的实质限制：开发机未发现可运行Linux SDK的WSL发行版或Docker；生产HA已有设备刚恢复，不再直接替换运行库做新品类试错。需先准备与生产网关身份隔离的原生验证，再考虑正确插座品类。喂食器仍缺可核实产品定义，113B门磁仍无光照字段；详见docs/socket-countdown.md。

最后校准：2026-10-17。本 fork 在上游基础上整理了已部署的 amd64 空调扩展和型号级插座开关适配。

门窗/水浸本地测试：新增113B门磁与2BE7水浸，19项单测通过。新候选独立进程隔离检查通过，只替换未使用夜灯槽2和电饭煲槽6，电水壶槽4保留；单个/批量元数据一致，其余六槽完全不变。三只门磁App开关状态已获用户确认，门磁光照仍仅在HA保留，当前113B卡片无光照字段。两只水浸App未出现，SDK上报返回-12，尚未接入成功，正在收集有界原生日志重试注册。所有旧设备SN、空调SN核对保持，未推送/发布。详见 docs/contact-moisture.md。

温湿度计本地适配已通过用户验收：新增113D适配，型号 `miaomiaoce.sensor_ht.t2`，默认关闭、通过本地 `thermohygrometer_enabled` 开启。独立子进程网络隔离检查通过，单设备/批量元数据及服务名一致，仅使用原未使用压力槽3，其他七槽与工作空调候选完全相同。第一轮手机显示0.2℃/0.9%，核对官方H5查实两个字段均除100，修正为物理值乘100后发送整数（23.8℃/95%对应2380/9500），用户已再次确认温湿度都正确。15项单测通过，候选库可按固定哈希补丁重建，SDK上报返回0；已核对旧设备SN保持、空调SN保持、网关在线、部署文件哈希一致。详见 `docs/thermohygrometer.md`。以上所有改动均未提交/推送/发布，未经用户确认不得发布。

当前本机最新状态（优先于下文历史记录）：温度同步修正已由用户复测成功，退出主页再进空调详情可同步显示。未提交、未推送、未发布。`snapshot` 将华为 current/target 都映射到 HA 设置温度，并按2ANJ的int字段要求转换为整数；没有环境温度含义。新增有界温度诊断记录，保存SDK查询、上报值和SDK返回码；实际观察到SDK查询为27/27，上报返回0。仅此返回码不等于云端验收，App成功结论来自用户明确复测；小艺查询尚未单独复测。11项单测、配置校验、隐私扫描通过，部署文件哈希匹配；网关在线、状态上报启用、原空调SN及全部设备SN保持。所有后续远端推送/发布必须先取得用户明确确认。本机manifest仍为回退后的1.1.0，HACS历史登记/远端1.1.1与此本地未发布补丁不等价，不要用HACS重装覆盖它。

1.1.1 已本机撤回：用户报告重新打开详情时温度回到26℃。撤回前HA与Python快照均为27℃，因此尚不能断言是字段取值反了，SDK/云端回读链路仍待核验。本机运行文件和开发工作区恢复1.1.0温度逻辑；远端1.1.1已发布，未擅自修改远端记录。后续只本地测试，未经用户明确确认不得推送或发布。

最新补充：用户已在智慧生活实测空调开关、目标温度、模式、风速成功。待改进的是自动风速，模式不改。用户另报告设为27℃后小艺仍查询为26℃：语音查询/目标上报异常尚未定位，不能用卡片默认值解释全部现象。官方卡片确有默认室温26℃且源室温缺失；不绑定其他房间的温湿度计。优先级、官方脚本证据、传感器/插座候选定义及未完成的原生适配见 `docs/development-roadmap.md`。

HACS 后续已通过本机限定范围的 GitHub 下载代理成功下载安装 v1.1.0，重启后状态为 installed；桥接网关在线、身份保持、状态上报核验通过。代理是本机 HACS 补丁，不属于本 fork，HACS 自身升级可能覆盖。下面“本轮验收记录”保留的是初次迁移时的历史过程，不能代表后续下载验证结果。

## 接手先读

1. `AGENTS.md`、本文件、`docs/aircon.md`。
2. `git status --short --branch`、`git log -5 --oneline`、`git remote -v`。
3. 版本源 `custom_components/hwhomebridge/manifest.json`。

## 当前实现

- `aircon_runtime.py`：保持空调 SN 算法与原网关绑定；PID009只对支持型号启用，其余设备委托原逻辑。
- `aircon_settings.py`：从 HA 根目录的本地配置选择实体，单个受支持实体可以自动选择；禁止把实际实体 ID 写回源码。
- `aircon_conversion.py`：温度/模式/风速转换；`aircon_runtime.snapshot` 按1.1.1兼容策略报告温度。自动风不映射成低档。
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

水浸注册重试证据：有界原生日志观察到batchBind请求后云端错误码23，连续三次；探针已关闭，无原始请求/密钥落盘。说明云注册尚未接受，错误码准确含义未知，不将它等同于SDK不支持。错误记录与回滚点留在项目temp，后续应先查产品/协议注册条件，不盲试枚举。

水浸追加排查：2BE7协议6→1对照仍失败，替换为完整官方2GB5服务定义（warterAlarm/battery/commonFaultDetection/update/netInfo）也失败，SDK均-12且未观察到水浸状态查询。当前本机加载2GB5候选，哈希ea844c3bd54d324f116ca69bf0dc3ed94e3987f3f6946a8cceea32aa5be88de0，门磁及其他六槽对照不变；三只门磁仍是已验收成果。正在核对云端已绑定子设备数量/遗留设备，未删除任何绑定，数量限制尚属待证假设。无推送或发布。后续部署共享库必须同目录临时文件+原子替换，不得截断覆盖运行中已加载so（可能使映射失效）。

用户清理多余设备后的同参数复测：batchBind请求含两只水浸，华为云仍多次返回23，之后SDK上报依然-12。数量上限假设未获支持；2BE7协议6、协议1与2GB5完整Profile对照均未成功。故障边界已收窄为云端注册阶段，不能将它归因温湿度/水浸状态字段转换，也不能声称某个错误码官方含义已确认。无删除绑定、无新网关、无发布。

2026-10-18 燃气排查：用户明确反馈设备列表完全没有。此前 SDK 查询和三项上报返回0仅证明本地处理，不能作为智慧生活接入成功。新增仅针对PID013的注册诊断服务，以及启动注册阶段的短时数值日志探针；保留水浸低优先级，不重试其注册。首次燃气重复注册诊断未捕获batchBind或云端错误（probe_error为空），故不能据此宣称云端拒绝。正在捕获首次启动注册；未触发报警、自检、消音，未删除绑定，无提交/推送/发布。

紧急回滚：用户反馈燃气不在网关子设备列表，且大量原有设备离线。立即终止燃气诊断，使用本轮燃气部署前完整备份原子恢复4个差异文件及原本本地配置，gas_sensor_enabled关闭；未触碰.storage身份及绑定。HA已发起重启，正在验证旧设备SN、网关在线和状态上报恢复。此次离线的准确原因未查明，不能仅归因重启延时或产品元数据；恢复前禁止继续接入新设备。燃气候选源码仅作未验实验保留，不得部署或发布。

回滚后API核验完成：网关在线，空调与传感器上报启用，空调SN及原有设备SN集合保持；燃气禁用，运行文件和配置与燃气前备份逐字节一致。证据位于项目temp/safety-sensors/rollback-verification.json和emergency-rollback.json。手机端恢复尚待用户确认；不能将HA侧online当作智慧生活在线。


2026-10-18 插座补充：用户已确认床头状态显示修复。已部署功率整瓦换算与新增Wh上报，38项测试通过。用户明确授权四张新插座卡重建后，已按先一张、再三张执行；四张均触发预期名称/房间回调，删除、新增、上线及后续状态上报返回0，SN集合和四路开关状态不变，观察到的物理控制命令为0。证据在项目temp/socket-energy-rooms/cloud-recreation-verification.json。手机端最终名称、分房和能耗显示待验收；无浏览器控制工具，未做Playwright/手机界面验证。无提交、推送或发布。

2026-10-18 用户反馈床头详情停留时开关仍跳变，功率卡片2W而米家180～190W。实读HA功率180W，确认此前按属性描述乘0.01错误；床头、厨房本地power_scale已改1，原子部署并重启加载，仅改socket_runtime.py及本地配置。39项测试、配置验证、编译、隐私扫描通过。新增独立查询/源状态有界记录，避免被周期上报挤出；状态跳变根因仍未查明，不声称已修复。私有证据及回滚文件在temp/socket-status-power-fix，无物理开关操作、无卡片重建、无提交推送。

本轮部署后独立REST核验：床头HA功率189W、桥接189W，厨房1W、桥接1W；四路源开关和桥接均开启，switch/delay/power上报返回0，SN集合不变、网关在线，观察到的物理命令0。手机仍待用户反馈。新增query_trace/source_trace仅作定位，尚未查明或修复详情页开关跳变；不要要求用户重复证明既有现象。证据temp/socket-status-power-fix/verification.json，回滚backup/socket_runtime.py和backup/local.json。

用户随后确认床头正常，但餐桌排插仅页面显示跳变、实际供电不变。追加90秒只读抓取未见餐桌源状态改变或新增查询；所有餐桌上报on=1。记录中02:01:39有一条云端switch命令被集成执行，未包含方向，不推断其来源或用户操作；此前“观察命令0”仅限verification.json核验时点，不能扩大到全时段。临时查询日志级别已恢复info。已确认官方124U H5每个switch消息都会增加switchCount，HomeTimer以该值为key重建；这只证明定时区域重建，尚不能解释主开关翻转。等待用户确认具体跳动区域，不盲改状态方向、不删卡、不再次重启。

餐桌跳动位置已由用户确认为顶部开/关文字及大开关，排除仅定时区域闪动。用户使用HarmonyOS NEXT，并提出零功率导致误判假设。已核实餐桌无sensor功率实体，桥接仅按源switch状态生成on；已下载124U网页代码分别更新switchOn和power，不能据此断言纯鸿蒙实际实现。未填造假功率。电脑已找到DevEco的hdc工具，list targets为空；正询问用户连接USB调试以取得手机接收消息证据。未再次部署/重启，不能把餐桌问题记为修复。

用户选择暂不连接手机。当前缺少纯鸿蒙智慧生活接收侧事件日志，餐桌顶部状态跳变仍未解决；零功率因果关系未获证实。不要继续要求连接或声称已修复。床头功率与状态用户已验收正常。本轮未提交推送。


2026-10-18 餐桌显示跳变对照修正：本地选项deduplicate_delay_reports只对目标插座启用。只在每分钟心跳中省略已成功上报的delay，switch心跳保留；源状态变化及倒计时操作仍无条件发送delay，上次发送失败则心跳重试。最终实现不缓存快照去重，避免快速创建/取消时跳过需要发送的状态。当前属于待手机验收的对照修正，不将重复空倒计时与顶部开关跳变写成已证实的因果。40项测试、编译、配置验证、隐私检查通过。源码仅修改socket_runtime.py及回归测试，私有配置和回滚在项目temp/dining-display-fix；未切换电源、未重建云端卡、未改原生库、无提交推送。

2026-10-18 餐桌周期补报修正版已部署并观察两个周期：开关上报3次，均on=1、SDK返回0；delay仅初始化上报1次，不再周期重复。网关在线、SN集合不变，观察窗口内物理控制命令0。40项测试通过，实机证据temp/dining-display-fix/verification.json。手机端顶部跳变尚待用户验收，不能称根因已确认或已彻底修复。


2026-10-18 统一插座运行规则及资源精简：用户确认餐桌最终稳定开启后，要求合并设备分支和审查资源。socket_runtime统一所有插座的周期delay抑制规则，移除餐桌deduplicate_delay_reports私有配置；开关与功率仍保留每分钟心跳。源事件忽略仅属性变化，开关变化仅报switch、功率变化仅报power、电量变化仅检查对应SN。无倒计时任务时不再每秒dispatch工作线程；重复安装监听前注销旧监听。保留每秒轻量回调以维持倒计时精度，不更改SDK原生单线程队列或设备身份。当前四插座静态周期状态请求从9次/分钟降到6次/分钟（不含电量增量与实际事件），空闲倒计时工作线程调用60次/分钟降为0。41项测试、compileall、配置校验、隐私扫描、diff check通过。仅手术部署socket_runtime.py和删除过时本地开关；备份及运行证据在temp/socket-unified-optimization。不得整目录部署仓库燃气实验。手机验收待确认，无提交推送。

统一版部署后两周期实测通过：四张卡各switch上报3次、delay仅启动上报1次，SDK均0、网关在线、SN集合不变、无观察到物理命令，过时单设备配置已移除。证据temp/socket-unified-optimization/verification.json。用户反馈餐桌依旧先稳定关闭，过一会转为稳定开启；不能标记手机完整通过，初始显示延迟仍未解决。期间餐桌SDK查询及三次上报均on=1，无关闭消息。其余卡用户未逐项明确验收。优化已落盘并部署，无提交/推送。

2026-10-18 初始关闭显示继续排查：前两轮首报均switch→delay，后续switch-only心跳后用户反馈转为开启。此为相关性而非已证实因果。统一调整report顺序为delay→power→switch，让全量刷新最后提交真实开关；不增加请求、不加设备分支、不改SDK或卡片身份。41项测试、编译、配置、隐私、diff check通过。已单文件原子部署重启，备份和验证在temp/socket-report-order；手机初始显示待验收，未操作电源、无推送。

上报顺序实机核验完成：四卡首次分别为delay→switch或delay→power→switch，全部SDK0，SN集合不变、网关在线、观察到物理命令0。证据temp/socket-report-order/verification.json及initial.json。手机初始显示验证问题已发出，尚未收到结果；不能将顺序对照当作根因结论。

用户实测顺序对照仍先关闭后开启，因此顺序调整未解决问题，不能记为修复。下一步区分每次进入详情均复现与仅重启后首次复现；已发出一次针对性查看请求。暂不进行下一次部署或重启。

用户进一步纠正：顺序实验前开启恢复后重复进入一直正确；顺序实验后主页/详情均关闭，随后每分钟开关显示翻转。已立即撤销顺序实验，源码和NAS恢复统一优化版47f888bb417d031cae9ca722c5834e896620f1588a1aaaecc54a77345108a363，测试恢复对应断言并41项通过。仅回滚socket_runtime.py，保留统一/资源优化、本地配置、设备身份。已重启等待验证，证据temp/socket-report-order/rollback-deployed.json。不得再将原问题描述为每次进入都先关闭。

回滚后最终核验：四卡上线、SN集合不变，两个周期各switch上报3次均on=1且SDK0，delay仅1次、无控制命令，运行哈希47f888bb417d031cae9ca722c5834e896620f1588a1aaaecc54a77345108a363。用户明确确认餐桌“恢复开启后保持稳定”。上报顺序实验已撤回；统一插座逻辑及资源优化保留，初始显示延迟仍存在。不再尝试顺序调整，不把失败实验当作修复。证据temp/socket-report-order/rollback-observation/verification.json。无提交/推送。

2026-10-18 全量资源审查已形成docs/runtime-resource-audit.md：核对空调/温湿度/门磁/插座/基础router/原生队列/集成生命周期。本地修正service_router.sync_device_state按实体去重（四服务共实体避免全量同步四遍），native_async提交时统计等待任务并正确回收取消/异常/拒绝。新增tests/test_runtime_resource_audit.py，43项及编译/配置/隐私/diff检查通过。没有部署、重启或推送，当前HA保留已验稳定统一插座版；live与本地这两个文件哈希不同属预期。明确待办：卸载监听/任务清理必须配套重载恢复；队列无界需状态合并并保留注册顺序；315秒固定串行等待不能盲删；空调/门磁已有设备重复新增；事件去重与重连/失败重试；手机初始关闭根因未查明。私有验证temp/runtime-resource-audit/verification.json。

用户明确授权“从现在起一直做，做到需要验证”。已部署全量同步实体去重和原生任务计数修正，socket诊断新增native_queue；警告改为待完成请求数量，不单凭瞬时队列断言锁阻塞。43项测试/编译/配置/隐私/diff通过，3文件逐个原子部署备份于temp/resource-fixes-live，未改上报顺序、配置、库或身份。HA已重启，运行核验脚本进行中；无物理命令或推送。需核验身份集合、各扩展上报、两个周期队列回落及最终手机端一次验收。

本批运行核验通过：28次队列采样全部0；空调启动温度提交观察1次（此前全量同步会重复4次），四插座在线且状态开启，上报SDK均0；空调/温湿/门磁/插座各SN集合与部署前一致，网关在线，3个运行文件哈希匹配，无观察到物理控制。证据temp/resource-fixes-live/verification.json。到达手机验收节点：只读确认餐桌稳定、其他设备在线和温度/功率显示，无需切换设备。尚未取得手机反馈，不标全量实机验收完成。队列上限/卸载配套/初始显示延迟等剩余审查项仍在docs/runtime-resource-audit.md，未声称全部完成。无推送。

继续排查餐桌首次关闭：当前只读诊断native_queue=0；query_trace自启动仅餐桌一次全量查询，没有用户进入详情对应新查询；周期switch均on=1。证据temp/socket-query-investigation/current.json和summary.json。未改代码/重启，准备在用户页面显示关闭时调用现有socket_refresh_state（只上报、无开关动作），对照是否提前恢复；已询问页面当前状态，等待回复后才触发。不能把无新查询等同于已证明云缓存bug，也不能通过提高永久轮询掩盖原因。

最新餐桌取值排查：用户确认周期刚补报后退出重新进入仍显示关闭，不能再只当启动延迟。首次手动socket_refresh_state发送全部SDK0，但与周期仅5秒间隔且用户没看清，结论不确定。第二次时间隔离尝试因回复到达距周期10.68秒被保护断言拒绝，未发送。当前无代码/部署/重启。已下载124U H5默认switchOn=0，缓存/云首读与实时事件独立更新，证据temp/socket-query-investigation/card-load-evidence.json；不能据此断言纯鸿蒙实现相同。新查询仍未到Python，queue=0，周期均on1。findings.json保存已知/未知。停止重复手机计时问答，下一步应查SDK缓存/服务读取路径或准备独立非计量卡候选，不能改假功率、取反或再试已失败顺序。

用户纠正并非每次重新进入都关闭，只在AI询问期间返回重进出现关闭，怀疑AI触发。必须撤回“每次进入复现”结论。只读操作复核：09:46:15确实主动socket_refresh_state（含switch+空delay及其他卡），非纯读取；下一周期约5秒后，不能归因；第二次被断言取消未执行。diagnostics代码只读，无SDK调用。本轮只读既有文件，未联网/补报/部署/重启；证据temp/socket-query-investigation/operation-review.md，findings.json已纠正。后续先查代码与离线SDK读取路径，不再反复请用户计时配合补报。

离线SDK定义检查找到可证实的不一致：BrgDevSvcInfo首表st为服务类型，第二表svcId为服务ID；e270原生读取分别拷贝两表。旧socket构建器把serviceId写入两表，124U官方switch类型binarySwitch、update类型devOta，而旧库为switch/update。构建器已修正分别写入serviceType/serviceId，探针对新计划额外验证service_ids，旧计划兼容；新增test_socket_metadata.py验证两表及其他字节不变。44测试/编译/隐私/diff通过。真实124U候选与旧库差异仅slot0服务类型表，静态证据temp/socket-service-types/static-verification.json。未加载SDK、未部署/重启/补报；不能认定这就是餐桌显示错误根因。下一步需独立隔离Linux进程验证两表返回值，再考虑任何运行库替换；不可直接改共享库或重建卡。

2026-10-18 用户再次要求自主持续执行后，已完成候选隔离实测：独立Linux进程empty_network_namespace下，sdk_main_called/gateway_binding_read/device_registration_called均false；124U两表实际返回binarySwitch/switch和devOta/update，其他7槽一致。44测试/编译/配置/隐私/diff通过。已原子部署17字节类型表修正候选a7a51cf02f173cef7ff6a30c8e59c2101449210e93099608d5571d3a7f1217c3、socket_runtime哈希常量及匹配隔离计划/探针；未改SN/品类/配置，不删卡不重新绑定。HA已重启，后台验证进行中；备份清单temp/socket-service-types/deployment.json，隔离证据isolated-verification.json。无法将类型不一致直接归为显示根因，待一次手机验收。无推送。

服务类型候选运行核验通过：四插座在线、SDK上报均0；空调/温湿/门磁/插座SN集合不变，网关在线；28个队列采样全0；无观察到物理控制，部署各文件哈希匹配。证据temp/socket-service-types/verification.json。已到需要手机验证节点，仅观察详情首次状态/返回重进稳定性及其他设备在线；不手动补报、不切换电源，未推送。尚未取得手机结果，不声称根因已解决。

服务类型实机手机验收失败：仍先关闭，进入一分钟后开启。继续独立原生读取入口0xe930四项mock测试通过（单switch/全量×开/关，SDK0及正确JSON），无网络/绑定/注册/实际补报，stage脚本已恢复。证据temp/socket-service-types/state-read-verification.json、read-path-findings.md。尚缺手机首次缓存/云读取返回值，不能确认SDK缓存原因；Upload接口未导出，不能盲调内部地址。用户不连接手机偏好保留；不要重复顺序实验或提高永久轮询掩盖问题。本轮没有活动库修改/重启/控制/推送。

手机已由用户USB接入：HDC 3.2.0d正常识别OpenHarmony-7.0.0.105。定位智慧生活com.huawei.hmos.ailife及ailifesvc进程，按PID限定只读hilog采集180秒，已结束。用户确认无AI补报/重启/控制时仍先关闭后开启。手机10:15:26.777 getDeviceInfoAll、fromLocal:false，10:15:26.901云getDeviceProperty成功，收到1129字节IPC响应；10:15:56.317收到餐桌deviceDataChanged，HA10:15:55.960报on1成功（跨设备时钟未校准）。确认实际124U H5页面，但当前发布日志不输出初始属性/实时payload，不能声称云返回on0。未找到可用devtools socket。日志仅私有temp/phone-logs，timeline.json和ha-passive-after.json保存证据，不能推送原始日志。未改手机设置、清日志、主动补报或重启。

继续手机深查：智慧生活17.0.4.317、debug=false；日志全局W。首次试用0xD0DFFF/0xD0DFDF域被hilog Invalid domain拒绝，未生效；纠正为应用域0xDFFF/0xDFDF后成功设D，观察新增D/I日志，用户再复现先关后开，但首次属性/实时payload仍不打印。已明确恢复两域W成功，未改全局/private，不改HA/补报。HDC私有文件读取拒绝、未发现devtools端口；不绕过应用沙箱。temp/phone-logs/detailed-log-findings.json保留事实。确实需要用户查看应用是否支持本地诊断日志导出，已提问，不让用户对外提交反馈/发消息。该缺口阻止区分云端首读数据与H5解析，不再盲改生产。


2026-10-18 服务表 ABI 核验：用户确认智慧生活无本地日志导出，停止该路线。SDK 实际消费者以64项结构读取BrgDevSvcInfo（ID偏移0x800、记录0x1800），厂商回调却按20项输出（ID偏移0x280、记录0x780）。独立空网络namespace对照复现旧库单台10个ID全空、批量错位；3条输出布局指令修正后单台/连续三台正确。构建器和原生探针增加64项候选ABI及8槽双台服务表核验，44测试/编译/配置/隐私/diff通过。候选afbd689f2b9f10137428a51898cf83dad72de87a51cf9f9c09f493bbc9861a12已原子部署并重启，后台核验进行中。未改变SN/产品/上报频率、未删卡/切电源/推送。证据及回滚temp/socket-service-abi/。接口错误已证实，但与餐桌首次关闭的因果尚待手机验证，勿宣称已修好。

服务表ABI候选后台核验完成：4插座在线、所有观察到的上报SDK0，空调/温湿度/门磁/插座SN集合均不变，网关在线，27次队列采样全0，部署文件哈希一致，未观察到开关命令或倒计时动作。temp/socket-service-abi/live-verification.json保存结果；rollback.py可校验无后续变更后原子恢复7个文件，需另行重启，未执行回滚。当前到手机验收节点：餐桌实际保持开启时，进入详情是否立即正确/返回重进是否稳定。未手动补报、不删除卡片、不改变上报频率、无提交推送。

用户手机验收服务表ABI修正版：明确反馈“两次都立即显示开启”（餐桌首次进入、返回主页后重进），本次显示问题验收通过。live-verification.json已记录原话及范围，docs/socket-countdown.md更新。保留当前运行库和回滚备份；尚未覆盖长期/重连情形，不再称“手机待验收”。无提交推送。

2026-10-18 燃气继续：只读确认4个PID008全部在排除清单、当前燃气工作状态正常/浓度0。旧燃气候选槽0现被插座占用且服务类型写成ID，不可重用。新build_gas_candidate从已验收afbd基底仅替换已退役断路器槽7，服务类型/ID分开，保留64项ABI修正；候选efa49bee73df8a975fd4ce170d6e2d0b1aa927d91781c264424e9cb96f6d33a4只改121字节元数据，槽0至6独立隔离核验不变。共用contact_moisture运行代码，增加PID008冲突保护、可选gas_sensor_registered、gas安装失败停止启动而非回退错误库。46测试/编译/配置/隐私通过。手术部署6个Python、gas_test候选及同源cfg、本地gas开关和单独gas计划，已重启，后台验证中。未删卡/身份/绑定、未触发自检消音报警、未切电源、无提交推送。证据/回滚temp/gas-v2/，本轮完整文件清单见deployment.json；旧试验导致大面积离线的准确原因仍未查明。

燃气新候选运行核验完成：原有4类诊断SN集合全部保留、网关在线、4插座在线、15次队列采样全0；燃气实体正常，alarm/commonFaultDetection/gasSensor三项SDK0；部署文件哈希全部匹配。native_registration_events为空，仍无云端新增成功证据；只到手机验收节点，不声称接入完成。temp/gas-v2/live-verification.json已保存。下一步用户核实燃气设备是否出现且在线、正常及0%LEL，同时确认原有设备在线；未注册验收前gas_sensor_registered保持false。无物理命令/报警自检/消音，无提交推送。

燃气v2手机结果：列表完全没有，原有设备正常。只读/proc父进程mem（无attach/stop/write）核对SDK：本地燃气记录存在且有设备编号，最终requested_status=1；不等于云端绑定成功。基于已反汇编的994b0，独立空网络进程使用合成注册表实测status3后立即status1会把3覆盖成1，仅3保留3，证据temp/gas-v2/registration-overwrite-verification.json。燃气首次注册/重试改为仅3，已确认注册后仅1；新增gas注册future完成结果诊断。另修复候选校验失败恢复基底而非停整个桥接，48测试/编译/配置/隐私/diff通过，失败恢复的setup测试通过。仅原子部署__init__.py、contact_moisture_runtime.py并重启（原生库/配置不变），temp/gas-registration-fix/deployment.json及备份；后台核验中，无推送/物理控制。不能仅靠隔离覆盖实验断言燃气缺失的唯一根因。

燃气注册顺序修正后台完成：实际gas status3 future返回0，未提交紧随的status1；三项数据SDK0；捕获batch_bind_request count1及cloud_add_success_marker（无SN数值日志，不能单凭此认定燃气已在App）。原有全部SN集合保留、网关/4插座在线，15次队列全0；原生库和配置未改，两个Python部署哈希一致。只读SDK内存快照显示本地28/64条、燃气编号长度36且无重复、内部已转status1/infoqueue9，未attach/stop/write父进程。证据temp/gas-registration-fix/live-verification.json、sdk-memory-verification.json；到手机验收节点，须确认燃气出现且在线及旧设备正常，不重复补报或重试注册。无提交推送。

燃气注册顺序版手机仍完全没有，原有设备正常。继续新身份对照：SDK本地28/64、燃气设备编号唯一，不是本地容量满或ID重复；依据原HA device_id派生gas_identity_version2，预先只读SDK内存确认新SN从未存在，旧gas SN记录保留不删。气体型号专用register_device包装调用已有reuse_sn能力，默认version1保持原行为，其余型号身份不变；原生库/品类表不改。补充SDK注册阶段按设备index记录，51测试通过，编译/配置/隐私/diff通过。已原子部署aircon_settings.py、contact_moisture_runtime.py、native_log_probe.py以及仅本地identity_version2配置并重启，正在后台核验；证据/备份temp/gas-fresh-identity。原有非燃气身份须全保留，本次仅燃气SN按预案改变；未删除云端设备/网关身份/旧实验记录，未操作实际设备，无提交推送。

燃气新身份对照后台完成：新SN按预案注册，所有非燃气SN保留，网关/4插座在线，15次队列全0，部署文件哈希一致。新增future status3 SDK0，三项上报0。只读内存定位新燃气SDK index28，29/64条、设备编号36字节且无重复；对应数值日志确实出现index28的响应阶段14/17/8（队列阶段，不是云端错误码），另有单设备batchBind及cloud_add_success_marker。证据temp/gas-fresh-identity/live-verification.json和post-sdk-memory-verification.json。旧记录保留；无主动补报/物理命令/删除绑定。到手机确认节点，不能把SDK链路完成当作智慧生活卡片已出现。无提交推送。
