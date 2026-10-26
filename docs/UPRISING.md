# 《起义时刻》接入记录（2026-10-25）

当前说明对应 **v261026-1**。v8 新增修改器/游戏公开进程身份，游戏标记放在注入块的独立保留区，脱离后保留到进程退出；接入见 [DETECTION.md](DETECTION.md)。v7 仅更新挑战功能说明与版本号；三个构建各 36 份导出桩均与 v6 逐字节一致。常用命令和保留脚本清单见 [TOOLS.md](TOOLS.md)，历史勘误见 [NOTES.md](NOTES.md)。

## 范围与验证边界

左侧选择游戏；原版保留现有 34 项功能，《起义时刻》复用这些功能并增加挑战资金、挑战时限两项，共 36 项。附加或等待启动期间锁定选择，脱离后可切换。启动按钮按产品使用 Steam appid：原版 17480，起义时刻 24800；已运行的 EA 版直接附加。

| 构建键 | 游戏文件 | 当前离线验证 | 旧版本真实进程记录 |
|---|---|---|---|
| `uprising-1.0ea` | 旧 EA `ra3ep1_1.0.game` | 28 个挂钩、21 个 API/全局/结构契约，903 项执行用例 | 28/28、四桥解析、安装与原始字节完整恢复通过 |
| `uprising-1.0` | Steam `ra3ep1_1.0.game` | 同上 | 尚未执行 |
| `uprising-1.01` | Steam `ra3ep1_1.1.game` | 同上 | 28/28、四桥解析、安装与原始字节完整恢复通过 |

Steam 文件名 `1.1` 的版本资源为 `1.01.0.0`。旧 EA 原版这里只接入实际提供的 1.0，没有臆造 EA 1.01 地址。两个同名 1.0 构建通过两处独立指令指纹区分；未知或歧义构建拒绝附加。上表实机附加记录来自之前版本，不能替代 v6 调整挂钩后的逐项实测。用户已确认挑战资金生效，但**尚未完成三个构建全部 36 项功能的逐项实战验收**。全面审计及工具整理只访问磁盘镜像和模拟内存，不写入当前游戏。

## 可重复证据

参照原件：`RedAlert3_Uprising_Trainer_FINAL.exe`，1,423,199 字节，SHA256：
`00203e87eb11f3f2a72b88dfff381cf2a11bc02a303d298a3aa574a8e04943b4`。

沿用 `extract_final3.py` 的滚动 XOR 提取方法，未执行旧修改器，得到 15 段脚本，保存在 `artifacts/uprising-final/`。主脚本明确标注游戏 `1.0.3313.38400`、Ken22265、December 2009。脚本中的地址均为 **RVA**；本次所有表格也使用 RVA，加载基址 `0x400000`。

`assets/uprising.json` 保存三个构建的独立地址和精确字节契约。`tools/analysis/build_uprising_contracts.py` 对本地三个 PE 重新核对并生成地址、函数快照及结构证据；保留 JSON 内手工维护的专属功能元数据。`uprising_probe.py` 提供只读 PE 扫描与反汇编。

| 入口 / 全局 | EA 1.0 | Steam 1.0 | Steam 1.01 |
|---|---:|---:|---:|
| 资金结算 | 0x6E7C0A | 0x67C7FA | 0x664A3A |
| 电力结算完整分支（v6） | 0x6E7AFF | 0x67C6EF | 0x66492F |
| 协议点完整分支（v6） | 0x6E7C70 | 0x67C860 | 0x664AA0 |
| 晋级 | 0x371C60 | 0x3B0680 | 0x3985C0 |
| 俘虏 | 0x3A3440 | 0x3E2060 | 0x3C9DE0 |
| 完整伤害入口 | 0x3E4E40 | 0x423A90 | 0x40B690 |
| 生成 wrapper | 0x2111F0 | 0x2510B0 | 0x238220 |
| 模板哈希查找 | 0x2D9470 | 0x318070 | 0x2FFFE0 |
| 玩家根全局 | 0x8FC734 | 0x9009C4 | 0x905DD4 |
| 游戏逻辑全局（与玩家根不同） | 0x8EC568 | 0x8F0808 | 0x8F5C18 |
| 选中列表全局 | 0x8EEFE4 | 0x8F3284 | 0x8F8694 |
| 模板表全局 | 0x8F9138 | 0x8FD3C8 | 0x9027D8 |
| 鼠标对象全局 | 0x8EE78C | 0x8F2A2C | 0x8F7E3C |
| 鼠标屏幕到世界 | 0x1F1CB0 | 0x231730 | 0x218680 |
| 随地建造 gate | 0xEECB5 | 0x130CD5 | 0x116BC5 |

生成 wrapper 为 308 字节，内部栈空间及 descriptor 字段发生变化，但对调用者仍是 cdecl 五参数、调用者清栈。晋级、俘虏、摧毁继续使用原有独立邮箱和游戏线程桥。EA 鼠标变换入口是原生 SecuROM `FF25` 跳板，严格校验其原有字节及后续指令；不改动保护跳板。

## 对象结构差异

禁止对所有指针统一加偏移。差异集中在 `GameLayout`，由桩、桥和宿主读取逻辑共同使用。Uprising 的分支修正单独选择；v6 的鼠标失败回退与增援间距修复适用于两个游戏，原版其余 32 个历史桩不变。

| 字段 | 红警 3 | 起义时刻 |
|---|---:|---:|
| Body 指回 Drawable（v261025-4 修正） | +0xF4 | +0xF8 |
| GenericUnpackUpdate 开始帧（v261025-5 修正） | +0x3C | +0x34 |
| Body 健康组件 | +0x33C | +0x34C |
| Body 属主 | +0x418 | +0x428 |
| Body 经验 tracker | +0x3CC | +0x3DC |
| Body 移动 AI | +0x374 | +0x384 |
| Body 矿脉状态 | +0x398 | +0x3A8 |
| 模板可晋级资格 | +0x245 | +0x24D |
| 选中管理器链表头 / 计数 | +0x50 / +0x5C | +0x54 / +0x60 |
| AI 当前 locomotor / vector | +0x21C / +0x1FC | +0x228 / +0x208 |
| 武器模板弹夹容量 | +0x70 | +0x78 |
| 电力界面成员 | +0x3B0 | +0x3E0 |
| 视野写入字段 | +0x260 | +0x264 |

特别注意：起义时刻的矿脉剩余量计算是 `state+0x28 - state+0x14`（FINAL 的 EA `0x2E3D70`），而原版通过 `state+4 → container+8` 读取总量。矿脉恢复必须按实例写 `+0x28=100000`、`+0x14=0`。已通过独立调用者 `0x72F890` 证明 Body+0x3A8 的类型。

移动当前实例的变化由同构指令证明，例如原版 EA `0x2908C7` 对应 Steam 1.01 `0x2B8537`：同时读取 `AI+0x228`、`Body+0x384`，不能仅用旧修改器的数组首项替代当前实例。选中列表全局也必须使用原脚本的 `0x8EEFE4`；另一组相似 setter 会指向 `0x8EF048`，短 setter 签名不足以证明选中列表。

### v261025-4：修复选中目标被全部过滤

用户反馈升星、摧毁等选中功能无效。对当前 Steam 1.01 战场只读检查：选中管理器 count=1、node+8 的 Drawable 有选中位、Drawable+0x138 能取得 Body，但 Body+0xF4=0；Body+0xF8 才指回同一 Drawable。此前错误地沿用了原版的 +0xF4，宿主侧交叉引用检查因此过滤掉全部目标，游戏线程桥中同样存在这项错误校验。之前模拟数据也错误地在 +0xF4 放入 Drawable，因此未能发现这个遗漏。

现在将 `BodyDrawable` 纳入布局，起义时刻使用 +0xF8；同步覆盖选中列表读取、执行前复核、晋级/俘虏/摧毁消费桩、选中弹药、复制和增援后升星。保持双向指针与选中位校验，没有通过移除安全检查或尝试两个偏移来掩盖错误。新增模拟用例要求旧 +0xF4 失败，并保证 +0xF8 失效时即使 +0xF4 看似有效也拒绝。

独立静态证据：Steam 1.01 RVA `0x66B0DA` 先读取 Drawable+0x138，再在 `0x66B0F9` 读取 Body+0xF8。该 48 字节上下文在三个镜像独立唯一匹配，加入 `layoutBodyDrawable` 契约。真实选中单位对比结果：`selected=1, legacy-F4=0, rank=1, destroy=1, copy=1`。这项检查没有安装挂钩、提交请求或写入游戏内存；实际升星/死亡动作效果仍需使用新版验证。

### v261025-5：修复苏军建筑卡在建造状态

用户在挑战模式选中一个卡住的反应炉，当前开启快速建造、没有其他修改器。只读检查 Steam 1.01 PID 44744：生命当前值/上限均为 1000；选中 Body 为 `0x06215AA0`，其 `StructureUnpackUpdate` 实例为 `0x0635B758`。游戏当前帧 2092，模块开始帧 `+0x34=1891`、持续帧数 `+0x30=150`，但下次更新 `+0x14=10438`；`+0x3C=10437` 是事件句柄。

此前 `power` 桩仍沿用原版 `+0x3C`，快速建造开启时执行 `module+0x14 = module+0x3C + 1`，将事件句柄当成帧数，使更新被推迟到未来。这也解释了关闭功能或脱离后仍卡住：错误值已写入游戏对象。该问题与快速建造的苏军展开路径有关，不能据此判断所有挑战功能均不可用，也不能把此前的附加冒烟测试当作功能实战验收。

修复将 `UnpackStartFrame` 纳入 `GameLayout`，起义时刻使用 `+0x34`，原版保留 `+0x3C`。原件主脚本也明确读取 `[edi+34]`。新增 `layoutUnpackSchedule` 契约：Steam 1.01 RVA `0x32A366` 的 28 字节上下文包含游戏自身读取 `[edi+34]` 并传给计时计算；三个镜像均独立匹配。未移除关闭开关与 `ebp==1` 的保护，也未加入自动扫描或修复游戏对象的写入。

`test_unpack_schedule.py` 使用实际导出的机器码复现旧版错误，并检查正确帧字段、关闭开关、分支保护、事件句柄及寄存器/浮点状态，共 24 例。`test_disabled_stubs.py` 逐一对照全部挂钩与原始被覆盖指令：起义时刻 168 例、原版 156 例，比较游戏数据、寄存器、标志、有效栈和浮点状态。此次排查未附加新挂钩、未写入用户当前游戏；新版能否恢复已经卡住的建筑仍待实机观察。

## 挑战模式与单位表

- 挑战资金：一次请求在游戏线程执行 `+50000` 并清除请求位。在战局中执行后，按 Esc 进入菜单页刷新一次生效；用户已确认修改成功。连续刷新不会反复加钱，整数接近上限时拒绝溢出。快捷键 `Ctrl+Shift+F11`。
- 挑战时限：v7 按用户确认的操作说明显示“将挑战平均时间设置为 9999：99；同样需要按 Esc 进入菜单页刷新生效”。底层沿用原脚本的 `599999.0f`（`0x49127BF0`），关闭后停止设置，当前关卡已写入的时限保留。快捷键 `Ctrl+Shift+F12`。
- 两个新快捷键避开原版 F11/F12 被占用时使用的 Ctrl 回退键。
- 起义时刻使用自己的 137 条增援表（盟军 38、苏军 45、升阳 47、中立 7）；原版保留 125 条。名称解析、输入代码和选择器都按当前产品选择目录。
- 起义时刻没有 `WBStringHashes.big`：从 `Misc.big` 的编译 `stringhashes.bin` 解析 54,571 条哈希，12 字节记录的字符串偏移相对 8 字节资产头，再结合 `StaticStream.big/static.manifest` 和 `ChineseT.big`。三阵营 MCV 哈希逐项复核一致。

## v261025-6 全面静态审计

### 本次确认并修复的问题

| 问题 | 独立证据 | 修复 |
|---|---|---|
| 电力/协议点挂钩有外部分支跳入中间，功能关闭也存在风险 | 三个 `.text` 全段直接分支扫描。Steam 1.01 `0x664936→0x66493B`；协议点 `0x664A98/0x664AA6→0x664AAB`，目标均位于旧覆盖范围内部 | 电力移至 `0x66492F` 覆盖完整 12 字节分支，协议点移至 `0x664AA0` 覆盖 11 字节分支；用标签重新生成内部跳转。共享 `MOV ECX` 留在原游戏中，缺失玩家/资源组件的分支仍可正常跳过 |
| 地图全开写入会被继承视野分支覆盖 | 原生 `JP +0C; FLD [ebp+25C]; FSTP [ebp+264]`，模板视野 `-1.0f` 时进入继承路径 | 开启时跳过这段经过校验的 14 字节后续指令；关闭完全保留游戏分支与标志 |
| 批量增援会全部堆在鼠标点 | 宿主计算了圆周位置，但游戏线程随后将位置全部替换为同一个鼠标转换结果 | 请求额外携带 X/Z 偏移，转换成功后再应用；失败时使用原先已带偏移的备用位置 |
| 鼠标转换失败时备用位置可能被部分输出破坏 | 原生函数只定义 AL 返回值；旧桩把输出指向正式位置，失败跳转与成功路径实际汇合，未保护备用值 | 输出先放入栈上临时 float3，检查 AL；仅成功时提交位置，保留寄存器/栈/FX 状态 |

另修正 `SpawnSupportApis.OwnerKindGlobal` 元数据：它应为游戏逻辑全局，原先误填了玩家根全局；当前生成消费桩未使用该返回字段，不能把它称为已发生的生成故障。哈希查找契约由 56 补全至 57 字节、哈希表搜索由 80 补全至 93 字节，覆盖全部返回和匹配分支；两段结构上下文补齐指令边界。鼠标契约扩至完整 1,150 字节，EA 入口的 6 字节保护跳板保持原样，后续 1,144 字节与 Steam 对应结构一致。

### 检查范围与结果

- 三个 PE 单独读取、记录 SHA-256，分别验证 x86/基址、84 处挂钩边界/上下文、63 段函数/全局/布局契约、调用边、返回清栈、放置补丁分支和全段直接入边。
- 比较主体指令时只屏蔽可重定位地址/调用目标，**保留条件跳转距离**；EA 邻接函数保护跳板在当前函数结束之后，单独限定上下文，未忽略挂钩所在函数内部差异。
- 字段核对包括 Body 的健康/属主/经验/移动/矿脉/Drawable、选中链、模板晋级资格、当前 locomotor、弹夹容量、电力 UI、视野与苏军展开计时；资源、建造、战斗、选中动作、生成、挑战两项均覆盖相应桩/桥/宿主路径。36 项注册和依赖检查通过。
- 每个构建独立导出桩，运行 10 套、903 项离线执行用例，共 2,709 项；包括实际 PE 的视野/相机后续指令和资源空分支。另通过 10,302 项字节篡改拒绝用例、安装失败/恢复检查和 WPF 切换检查。
- 原版完整 SelfCheck、离线执行/ABI 检查通过。33 个旧基线仅 `spawn_dispatcher.bin` 因共用生成修复由 370 改为 436 字节，其余 32 个不变；增加电力桥测试导出。新旧哈希记录在 `artifacts/uprising/spawn-baseline-change.json`，仅更新这两项基线，未整体重建来掩盖差异。

当前验证边界：v6 新挂钩在三个实际进程的完整附加/脱离及逐功能验收、EA 保护入口实际执行、已卡住反应炉的恢复均未取得完整记录。用户在后续实测中已确认挑战资金修改成功，并要求按“战局中执行 → Esc 菜单刷新”说明操作；该确认不能外推到所有构建和其余功能。生成请求在没有任何备用锚点且鼠标转换失败时，仍沿用现有的零坐标备用约定；本次只修正备用值被破坏，没有将该路径当作有效地图位置的实测证明。

## 检查入口

一键复现三构建全面离线审计（不打开游戏进程）：

```powershell
py tools/harness/run_uprising_audit.py
```

生成 `artifacts/uprising/static-audit.json`、`artifacts/audit/results.json` 与每个构建的独立日志。单独静态审计可运行 `py tools/analysis/audit_uprising.py`，它只读取预期契约，**不会像地址生成器那样更新预期字节**。

```powershell
dotnet build RA3MT.slnx -c Release
dotnet run --project src/RA3MT.SelfCheck -c Release -- uprisingtest
dotnet run --project src/RA3MT.UI.SelfCheck -c Release
dotnet run --project src/RA3MT.SelfCheck -c Release -- uprising-stubdump artifacts/uprising_stubs
$env:RA3MT_TEST_UPRISING='1'
py tools/harness/test_execution_stubs.py
py tools/harness/test_rank_dispatcher.py
py tools/harness/test_bridge_dispatchers.py
py tools/harness/test_rank_money_bridge.py
py tools/harness/test_spawn_dispatcher.py artifacts/uprising_stubs
py tools/harness/test_uprising_stubs.py
py tools/harness/test_unpack_schedule.py
py tools/harness/test_disabled_stubs.py
py tools/harness/test_uprising_continuations.py
py tools/harness/test_uprising_resource_forks.py
Remove-Item Env:RA3MT_TEST_UPRISING
py tools/harness/stub_regression.py
```

`uprisingtest` 当前为 84/84 三构建挂钩、63 个函数/全局/结构契约、10,302 个字节篡改拒绝用例，另含四桥布局安装/恢复、功能注册、选中列表、速度、生命、复制、矿脉与游戏切换检查。v261025-5 的历史结果为 57 个契约、6,513 个篡改拒绝用例、原版 33 桩零变化；v6 的新增结果与唯一有意更新的原版生成桩见上节。

只读选中链诊断：`SelfCheck uprising-selectiontest [PID]`。保持选中一个可晋级的普通作战单位，输出修正布局与旧 +0xF4 的目标数量，以及升星、摧毁、复制的可用目标数。可在修改器已附加时使用：构建从磁盘原始镜像判别，检查期间不提交任何游戏动作。

只读实机：`SelfCheck livetest uprising [PID]`。安装/恢复冒烟：`SelfCheck uprisingattachtest [PID]`，会安装所有挂钩且保持功能关闭，一秒后脱离并逐点检查原始字节。后者应在正常运行且没有其他修改器的游戏进程中执行。

C# `uprisingtest` 可用环境变量指定三个离线镜像：`RA3MT_UPRISING_EA_IMAGE`、`RA3MT_UPRISING_10_IMAGE`、`RA3MT_UPRISING_101_IMAGE`。Python 审计和生成工具使用 `uprising_probe.py` 的 `PATHS` 表；更换安装目录时需要同步该表。工具的输入、输出和写入边界见 [TOOLS.md](TOOLS.md)。
