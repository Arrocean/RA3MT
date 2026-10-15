# 逆向笔记（重打包版 1.12/1.13）

## v33（体验整理：去诊断功能；日志转后台静默，仅错误时自动弹窗，publish-v33，待实测）

- **删除"诊断采集"功能**（34 功能）：features.json 条目 + DiagnosticsFeature +
  目录 diag 分支 + TrainerEngine RunDiag/DiagDump/ReadDiagnostics/诊断辅助全链
  拆除；诊断捕获桩（money_h1 等 diag 槽写入）保留无害（块内自写自弃）。
- **日志后台化**：主窗口移除日志抽屉与"运行日志"导航项；缓冲只在内存
  （上限 400→2000 行），随程序退出清空，不落盘。MainVM.IsErrorLine() 分类：
  ⚠/✗ 前缀或含 失败/未通过/异常/找不到/未找到/不可用/被校验拒绝/无法附加/未消费。
- **错误自动弹窗**：ErrorLogged 事件 → LogWindow（Owner=主窗口，随修改器关闭；
  完整日志+复制全部+自动滚到底；重复错误只激活已开窗口不重复弹）。
  触发场景覆盖用户要求：地址修改与预期不符（resolver"字节校验未通过"/桥拒绝）、
  找不到进程等。正常运行全程无日志窗口。
- 34 功能/26 挂钩；桩零变化（纯 UI/目录改动）。

## v32（★FINAL3 全量移植收官：P 三星对齐，31 项功能全覆盖，publish-v32，待实测）

- **P 三星本已存在**：`sel_lv`（Alt+P，action "lv"）即 BridgeActionFeature→
  晋级桥→rank(3,1,0)——与 FINAL3 P 键（MustCode+800 SelectUnitLevelUp）完全同款，
  v18g 多目标 3/3 实测、增援升星同管线。差距只在文案与遗留条目。
- 收尾：`sel_lv` 更名"选中单位瞬升三星"+desc 对齐（旧文案还写着"不等同FINAL3
  直接晋级"——过时）；**删除死条目 `xp999`**（pending 状态，其钩子 zoom_unit_xp
  实为选中捕获/诊断桩，继续独立安装不受影响，flag 0x09 恒 0 走透传）。
  热键保持 Alt+P（裸字母 P 做全局热键会拦截系统所有 P 按键）。
- 35 功能/26 挂钩。桩零变化（纯 features.json 文案/条目改动）。

### ★FINAL3 31 项对照终局（v19b 审计 → v32 全部闭环）

24 项早期覆盖 + L 随地建造(v19) + J 增援批量升星(v23/v26) + F10 禁电脑建造
(v27/v28) + F11 无敌(v29) + F12 一击必杀(v30/v31) + P 三星(v32 文案对齐，
功能 v18g 起) = **31/31 全覆盖**。MT 另有 9 项超出 FINAL3 的增强（治疗/威胁
分级/真实弹药容量/诊断/任意哈希增援等）。两次记录在案的故意偏离：摧毁
DeathType CATALYST→NORMAL（不溅射友军）、F12 门控换伤害符号（FINAL3 原门
挡主基地，对照实验定案）。

## v31（F12 修复：门控换伤害符号 + 诊断计数器，publish-v31，待实测）

### 勘误（用户实测反例推翻 v30 诊断）

- 用户补充实测：**矿场、发电厂（同样无武装）都能正常一击必杀，唯独主基地不行**
  ——v31 首版"无武装建筑被门挡住"的推断错误。四个门字段是**会变化的瞬时状态**
  （征召兵 +0x3AC=0x3F7793EE≈0.97f，非指针非模块表），v30 的探测在战斗结束数分钟后
  进行，读到主基地全零无法证明受击时刻也是零——探测时机无效。
- v31 的修复方向仍然有效：伤害符号门（comiss xmm1<0）**完全不依赖那四个字段**。
  若主基地卡点真在门上 → 修复；若卡在别处（如主基地伤害路径未经捕获钩子）→ 无效。
- **实测通过（2026-10-12 深夜）**：主基地一发摧毁，其余照旧。v30/v31 对照实验
  （两桩仅差门控）证明 FINAL3 原门就是主基地失效的元凶——**原门不回加**
  （回加即复现）；伤害符号门为最终方案。F12 收官。诊断计数器保留（无害）。
- **诊断计数器**（块+0x900 真伤害到达数 / +0x904 击杀执行数，桩内 IncM32Abs）：
  下次实测主基地仍不秒杀时，打几枪后读计数即可分层定位——0x900 不涨=HP 调整
  未到站点；涨而 0x904 不涨=捕获不匹配或属主/符号检查挂；两计数同涨=击杀执行了
  但建筑没死（死亡判定层另有逻辑）。桩 104→116B。

### v30 实测反馈与活体定位

- **实测**：大部分单位一击必杀 ✓，但征召兵打**敌方主基地**不能一次摧毁；日志另见
  F12 热键注册失败（被占用）。
- **活体探针**（游戏运行中直读）：敌方主基地 body 0x688D370 的门字段
  **[0x390..0x3AC] 全零**，征召兵 0x68A4070 在 +0x3AC 有非零（0x3F7793EE）——
  FINAL3 的"任一非零"门把无武装建筑全挡了。双方健康模块 **vtable 同为 0xC418F8**
  （同一条 HP adjust 路径，钩子没问题，纯粹门太严）。
- **修复（对 FINAL3 的第二次故意偏离）**：门控换成 `comiss xmm1,[块+0x3C(0.0f)];
  jae 放行`——HP adjust 的**增量在站点时位于 xmm1**（函数头 `movss xmm1,[esp+4]`
  装载后无人改动），负增量=真伤害才杀、正增量（治疗/修理/纳米维修）跳过。
  语义比 FINAL3 的不名门更准，且覆盖建筑。块内存 VirtualAlloc 零初始化保证
  0x3C 处恒为 0.0f（OneKillZero 常量）。
- **热键回退**：裸功能键被占用时（如 F12 调试保留位）自动改注册 Ctrl+原键并
  日志提示（MainWindow.RegisterHotkeys 通用逻辑）。
- 测试：onekill 矩阵 5 态中 'gate_zero'→'heal'（xmm1 装载 +12.0f）；273 用例绿；
  桩 121B→104B 基线刷新；publish-v31。

## v30（F12 一击必杀实装：三钩子协作，publish-v30，待实测）

### FINAL3 架构（script_00 全解）与双版定位

- **主钩**（EA 0x3651AE，displaced `F3 0F 11 46 04`=movss [esi+4],xmm0）=
  健康模块 HP adjust 方法的"写当前血"处。**EA ≡ 1.13 0x38CB4E ≡ 1.12
  0x3A366E**——正是 kill 桥早已验证的 HP adjust（0x38CB30/0x3A3650）+0x1E，
  交叉自洽。站点后紧跟 `je`（消费函数头 `test eax,eax` 的标志）→ 桩必须
  pushfd 保护。
- **数据钩 A**（EA 0x3FE714，displaced `8B 8E 3C 03 00 00`=mov ecx,[esi+33C]，
  esi=body）：捕获"正在被处理的 body/健康模块"到块槽 0x30/0x34。双版
  1.13 0x427B34 / 1.12 0x43C964。
- **数据钩 B**（EA 0x2E24E3，displaced `8B 89 3C 03 00 00`=mov ecx,[ecx+33C]，
  ecx=body）：同捕获。1.13 0x30B6C3 / 1.12 0x320963。
- **主桩逻辑**（FINAL3 MustCode+461）：esi==捕获的健康模块 → body 过
  [390/394/3A0/3AC] 任一非零门（战斗相关）→ 属主槽位≠本地槽位（v28 链）→
  **当前/上限 HP 双清零 + xorps xmm0**（重放 movss 写入 0）= 敌方单位受到
  任何伤害即刻死亡。FINAL3 的 [esi-8] 反查 body 以捕获槽替代（同一对象）。
  FINAL3 尾部多余的 `test eax,eax`（clobber 标志）与 [ID+8] 死存储不抄。
- 模式：主钩 20 字节（movss xmm0,[esi+4]; [esi+8]=xmm0; addss; push edi;
  站点; je）、数据钩 A 加 `mov edx,[ebp+0x80]`、数据钩 B 加前导
  `mov ecx,[esp+0xC]`——三模式在 EA/1.13/1.12 各唯一命中。

### 实装

- StubGen `onekill`(121B,flag 0x38——0x00-0x0F 标志区已满，扩展到数据区末尾
  <0x40) + `onekill_a`(23B) + `onekill_b`(23B)。数据钩无 pushfd/pushad
  （指令只写 ecx，与 displaced 同款，标志零扰动）。功能 no.36/热键 **F12**，
  挂钩点 23→26、功能 35→36。
- 工程坑：**手写 modrm 算错 reg 字段**（`39 E0`=cmp eax,**esp**，本意
  cmp eax,esi=0xF0）——Unicorn 矩阵用例当场逮住（杀敌分支永不触发），修正后过。

### 验证

SelfCheck 52/52（26 挂钩双版）+ featuretest 112 + 全套件 + Unicorn execution
273（onekill 家族 32 例：数据钩双形态捕获、主桩 flag×受害者匹配×属主×门×
空态矩阵、xmm0 置零路径、重放语义）+ 桥 60/25/217。基线 33 桩（纯新增）。
publish-v30（62MB x86 + 三 .enable）。

### 待实测

F12 开 → 打敌方任意单位一下立刻死亡（含盟友单位也一击死）；己方单位互相
无伤；与 F10/F11 同开互不干扰；关 F12 恢复正常伤害。FINAL3 19b 遗留观察项：
门字段 [390..3AC] 的确切语义未深究（照抄 FINAL3）。

## v29（F11 玩家无敌实装，publish-v29，待实测）

### 定位（EA 原版直接反汇编，一击定案）

- FINAL3 EA 0x12EEDF 的包含函数 **0x12EEA0 与重打包 1.13 0x1588C0 / 1.12
  0x1705A0 逐指令同构**：this=ebx=drawable → [ebx+0x138]=body →
  esi=[body+0x33C] 健康模块 → vt+0x48(上限)/vt+0x3C(当前)（血条渲染读取，每帧跑）
  → [ebx+0x3A4]-[ebx+0x39C] 屏幕坐标数学。站点即 vt+0x3C 装载处：
  **1.13 0x1588FF / 1.12 0x1705DF**，displaced `8B 50 3C 8B CE`（`mov edx,[eax+3C];
  mov ecx,esi`）三版同字节。
- 5 字节模式在重打包有 22 个命中（vtable 调用惯用语），全不可靠；改用
  `D9 5C 24 08 8B 06 | 8B 50 3C 8B CE`（fstp+mov eax,[esi]+站点）11 字节模式
  在 1.13/1.12/EA 三镜像各唯一命中，EA 侧正好落在 FINAL3 钩子地址上。
- **机制（FINAL3 F11）**：血条读取函数每帧运行时，把健康模块的**真实 HP 字段**
  +4(当前)/+0xC(上限) 重置 1000000.0f（vt getter 读的就是这两个字段）——
  掉血一帧内被刷回满 = 无敌。属主 [body+0x418] vs [[root]+0x28]（阵营指针
  编码，与 aiblock 的槽位号编码不同——v28 教训的又一例证）。

### 实装

- StubGen `godmode` 桩 78B（flag 0x0F）：pushad 内重走 [ebx+0x138]→[+0x418]
  属主链（FINAL3 原样）+ root 链本地阵营比对 + body/health/root/side 四重判空
  （FINAL3 一重不查，防御性补齐）→ 钉 [esi+4]/[esi+0xC]=0x497423F0 → 重放
  两指令。features.json：hook godmode + 功能 no.35（toggle，热键 **F11**，
  建造组）。
- 工程坑：**链接式 EmbeddedResource（assets/features.json）改动不被增量构建
  跟踪**——改 JSON 后必须 `dotnet build src/RA3MT.Core --no-incremental`
  （否则 SelfCheck 仍读旧资源，v29 首轮"44/44"假象）。另：Asm 无 JbShort/
  CmpRegReg，判空用 TestRegReg+JeShort、reg-reg 比较用裸字节 `39 D7`。

### 验证

SelfCheck 46/46（双版 displaced+11 字节特征码唯一命中）+ featuretest 107
（35 功能/23 挂钩）+ 全套件 + Unicorn execution 221→**241**（godmode 20 例：
flag×属主×5 种空态；断言双字段钉值+重放寄存器 edx=[vt+0x3C]/ecx=esi 不失真）
+ 桥 60/25/217。基线 30 桩（纯新增）。publish-v29（62MB x86 + 三 .enable）。

### 待实测

F11 开 → 己方单位/建筑被打血条闪一下立刻回满、永远打不死；敌方正常掉血；
F10/F11 同开互不干扰；关 F11 后恢复正常掉血（血条刷新时不再重置）。

## v28（F10 修复：条目属主是槽位号非阵营指针，publish-v28，待实测）

### v27 实测翻车与根因

- **实测**：F10 把**己方**生产也钉死了——比较永远不相等 → 所有人都被钉。
- **根因（静态三重实锤）**：
  ① 条目方法 0x4761A0（`call 0x4652B0; mov ecx,eax; call 0x4761A0`）：
  `mov ecx,[entry+0xC]; mov eax,[root+ecx*4+0x30]`——**[entry+0xC] 是玩家
  槽位号（小整数）**，root 对象 +0x30 起是玩家指针数组（15 处同型解析）；
  ② 游戏自己的"是否本地玩家"判定（1.13 24 处 / 1.12 32 处，如 0x11F4BE、
  0x547B10）= `mov edx,[root]; mov eax/edx,[edx+0x28]; cmp X,[side+0x20]`——
  **本地玩家槽位号=[[[root]+0x28]+0x20]**；
  ③ FINAL3 在 EA 上的链 `[[x+0x28]+0x20]` 与②完全同形——它比的就是槽位号。
- **修复**：AiBlock 桩比较改为 `[side+0x20] == [entry+0xC]`（side=[[root]+0x28]；
  只对 root/side 空跳过，槽位值 0 合法不做判空）。55B→58B。
- **教训（升星/生成桥的类比失效警告）**：`[[root]+0x28]` 在 Body+0x418 的属主
  比较里=阵营对象，但**生产条目的属主字段存的是槽位号**——同一游戏里"属主"
  有两种编码，新对象的属主字段必须先看它的消费者怎么解析，不能沿用旧惯例。
- 测试：execution 209→**221**（aiblock 12→24 例：+槽位号语义、槽位 0 边界、
  local_slot 0/2 两态）；44/44+104+14+asmtest 绿；基线刷新（aiblock 58B）。
  publish-v28。

## v27（F10 禁止电脑建造实装，publish-v27，实测翻车见 v28）

### 定位与语义（全部静态+磁盘双版验证）

- **FINAL3 原版（script_00 MustCode+3D0）**：钩子 EA 0x30F530，displaced
  `add edx,[eax+4]; cmp edx,edi`（5 字节）。script_09（该开关的 ENABLER）设
  iEnable+15=1 → 生效档=把属主≠本地的生产条目增量 [eax+4] 钉 **1**（每拍只付 1，
  任何东西都造不完）。它还有个 flag=0 的默认档钉 5000（=瞬间完成，全局分配零初始化
  的残留，不抄——"禁止建造"的真身就是钉 1 档）。
- **Steam 双版对称点**：模式 `03 50 04 3B D7` 各 .text **唯一命中**——
  1.13 RVA 0x3387D0 / 1.12 RVA 0x34D920（老线索"1.13 0x3387D0 已定位未挂钩"落实）。
  站点环境逐指令同构：`call 0x4652B0(1.13)/0x479EC0(1.12)`（[ebp+0xE4] 生产条目数组
  第 0 项）→ `mov edx,[eax+0x14]`（已付）→ 站点 → `jb 累加路径 / 落空=完成路径`
  （完成路径调 0x472910 扣款、`[esi+0x68]+=实际扣除`、ret al=1；未完成路径带疑似
  "资金不足"提示音）。eax=生产条目，[eax+0xC]=属主，edi=剩余预算。
- **属主判定**：FINAL3 用 EA 的 ID 链（[x+0x28]+0x20）；MT 用活体验证过的
  `[[playerRoot]+0x28]` 本地侧（build_power/rank/spawn 同款）。若极性判断错，
  症状=己方生产被钉慢（可逆：关开关即恢复），实测即知。

### 实装

- StubGen 新增 `aiblock` 桩（55B）：pushfd/pushad → flag 0x0B → root 链取本地侧 →
  `[entry+0xC]==本地侧` 跳过 → 否则 `[eax+4]=1` → popad/popfd → 重放
  `add edx,[eax+4]; cmp edx,edi`（cmp 的 CF/ZF 供原代码随后的 jb 消费）→ 跳回。
- features.json：hook `aiblock`（双版 RVA+5 字节 displaced+pattern）+ 功能条目
  （no.34，toggle，flag aiblock，热键 **F10**，建造组，34 功能/22 挂钩）。
  LegacyFeatureCatalog 对 toggle+flag 自动注册 SwitchFeature，零代码。
- 顺手：UI 启动横幅陈年的 "v2.0" 改为与发布号同步（v27）。

### 验证

SelfCheck 44/44（双版字节+5 字节模式唯一命中交叉验证）+ featuretest 104
（34 功能/22 挂钩）+ installertest 138 + layouttest 14 + asmtest（桩区 0x530 < 0xFFC）
+ Unicorn：execution 197→**209**（aiblock 12 例：flag×属主×root 缺失 3 态；
  断言钉值、重放 add 的 edx、重放 cmp 的 CF 必须与真实比较一致——jb 决策不失真）
+ 桥三套 60/25/217 全绿。基线 28→29 桩（纯新增，存量 0 变化）。publish-v27
（62MB 自包含 x86 + 三 .enable）。

### 待实测

进对局开 F10 → 电脑（含盟友）生产进度条几乎不动、永远造不出新单位；己方生产不受
影响；关 F10 恢复。注意与 [05] 快速建造互不干扰（己方路径跳过钉值）。

## v26（增援位置+升星双修：整数像素变换 ABI、去选中门禁，publish-v26，待实测）

### v25 实测反馈（2026-10-12）

- 增援**仍跟镜头**且有固定偏移（镜头置 0,0 → 落点右上 ~28°、约 1/3 图边长）；
  日志同时暴露 8 个升星请求全被桩拒绝（"晋级桥: 0x… 校验未通过"×8 每轮）。

### 根因一：位置——v25 鼠标段桩两处错

1. **读回指针错位**：像素写在 [esp+0x204/0x208]，`lea eax,[esp+0x14]`（压 3 栈后）
   实指 [esp+0x8] = fxsave 保存区内的 x87 残渣 → 变换吃进**随镜头变化的游戏线程浮点
   垃圾**，正好解释"跟镜头+固定偏移"。活体证据：用户选中的增援兵 0x68A0970 实际落点
   (4930,190,2010)（对象 +0x220/+0x720 双份记录），当时训练器侧鼠标地面 (348,5077)。
2. **照抄 FINAL3 的输入格式错了**：FINAL3 在 EA 上是 fild 转 float + 转发鼠标对象
   +0x44 深度到缓冲 +0xC（Mustcode+1120 原文核对）。但活体反汇编重打包 1.13 的
   13 个真调用者（find_transform_callers.py：整段 .text 线性扫 + int3 定函数头）证明
   **Steam 0x60ECF0 吃裸整数像素**：游戏自己的屏幕中心调用者 0x528500 把
   `call [vtbl+0x44/0x48]` 返回的宽高 `shr 1` 后**直接以 int 存缓冲**，+8/+0xC 不填；
   0x613B3F 调用后 `fld dword` 证明输出仍是 float3；arg3/arg4=0/0 与 FINAL3 一致。
   鼠标对象 +0x44=0x25890091（非深度非像素，活体读取）→ 弃用。

修法：`mov [esp+0x204/0x208]`（**disp32 编码** 89 84 24 xx 02 00 00——初版 disp8
错写 [esp+4/8] 穿了 fxsave 的 x87 标记字，Unicorn FX 镜像校验当场逮住）+
`lea eax,[esp+0x210]`（压 3 栈后正确回指像素缓冲）；变换失败不再整体拒绝，
落回邮箱里训练器侧预置的兜底坐标；空鼠标对象改走 FxReject 出口——v25 起的潜伏雷：
旧路径跳 Rejected 出口会**跳过 fxrstor 与 [esp+0x200] 的 ESP 恢复**（帧已 sub 0x214），
popad 弹垃圾即崩溃（加载屏等清空 0xCE43BC 的时机会触发）。

### 根因二：升星——RankDispatcher 的"必须选中"门禁

`test byte [drawable+0x13D],0x40; jz reject`（v14 为 P 键加的安全门）把所有刚生成、
未入选区的增援单位挡掉。活体验证 0x68A0970（用户手动选中的那只）：
反链 [draw+0x138]✓ / 归属 [body+0x418]=本地✓ / tracker 资格链✓——**唯一挂点就是选中位**。
移除该门禁（FINAL3 的 MustCode+800 无此检查，可作用于任意己方单位）；
SelectionActions 客户端的选中过滤（血量恢复等）不受影响。

### 验证

Unicorn：spawn 21→**25** 用例（新增鼠标模式 4 例：变换入参必须等于鼠标对象原始
整数像素、out 指针=邮箱位置槽、双栈奇偶、变换失败落兜底、空鼠标走 FX 恢复出口）；
rank **217** 用例（拒绝用例 16→15，选中位两处 fixture 同步删除；假 transform 改为
cdecl 约定只砸 EAX/ECX/EDX/XMM——桩在调用前后持有 EDI/EBP）。SelfCheck 12 套件绿
（42 挂钩+30 桥邮箱+46 生成+24 动作+132 安装+14 布局[生成桩 370B]+101 目录）；
基线刷新（spawn 344→370B、rank 340→327B）；publish-v26（三 .enable）。

### v25（存档：鼠标三步架构定位，00b7739）

鼠标对象全局 1.13 VA 0xCE43BC / 1.12 0xCE009C（注册点 mov [global],esi+[esi+0x8C]
能力检查为唯一签名）；对象 +0x3C/+0x40 为**整数屏幕像素**（OS GetCursorPos 对照 1:1，
失焦冻结；与 EA 的 float 布局不同构）；屏幕→世界变换 cdecl(in*,out*,0,0; ret al)
1.13 0x60ECF0 / 1.12 0x62C500。0xCE15B8=屏幕中心地面投影（随镜头，v24 增援"固定
南侧"的元凶）。SpawnDispatcher 邮箱 +0x24 鼠标模式位，SubmitAtMouse 全链路。

## v20（摧毁 v3 实装：kill 桥改走完整伤害入口，publish-v20，待实测）

- **KillDispatcher 全重写**：从"底层 HP adjust(0x38CB30) + 手工 Die 镜像（vt[0x270] kick + 死亡标记）"改为**调完整伤害入口**（FINAL3 同款 thiscall Body + push 6/0x13/0，ret 0xC 被调方清栈）——死亡决策/动画分发/模型回收全部走游戏自己的管线。旧 Die 镜像序列与邮箱静态 DamageInfo（+0x10/+0x18/+0x1C）全部删除（类型常量直接进桩指令），新桩 236B（旧 283B，仍 <0x180 槽）。
- **KillApiResolver 三值契约**：(adjust, deathMarker, **damageEntry**)。damageEntry=1.13 RVA 0x3C7190 / 1.12 RVA 0x3DCDF0（EA 0x39EA50 对称，两段字节契约跳过版本化标签/call + ret 0xC@+0xB7 验证）。adjust/marker 契约保留（身份交叉验证+marker 仍参与 KillBridgeEnabled 判定）。bridgetest 增加 kill-adjust 篡改拒绝用例（共 4 契约）。
- **调用链更新**：BridgeApis.Kill→KillDamageEntry；KillBridgeConsumer(damageEntryVa, rootVa)（marker 不再进 consumer）；TrainerEngine 日志改"完整伤害入口"。
- **测试**：test_bridge_dispatchers.py run_kill 重写（mock 断言 ecx=Body、栈参 6/0x13/0、(sp+16)%16==0、ret 0xC；删 marker/death-seq fake——60 用例过）；BridgeMailboxChecks 邮箱发布序去掉类型字段；stubdump 重新生成+同步 stubs 目录+**baseline_stubs 刷新**（kill 桩 283B→236B 为预期变化，--freeze 后 28 桩 0 差异）。全套：42/42+13 套件+Unicorn 全绿。
- **publish-v20 已发布**。待实测：摧毁选中敌兵应见**死亡动画+模型消失**（对比之前"实体死但模型残留"）。若对局内崩溃→伤害入口有前置条件未满足（回退方案：git revert 本节，保留旧 kill 桩）。
- 施工队列（v19c 排序）：①摧毁 ✓→②J 增援批量 8+升级→③F10/F11/F12→④P 三星接桥。

## v19c（FINAL3 行为级全量复核 + 摧毁修复定位完成）

- **复核方法**：盗版 EA 1.12（FINAL3 可正常运行）+ script_00 全解读 = 行为级对照。结论：MT 多 9 项增强、缺 4 项、1 项重大实现偏差（摧毁）、2 项行为差异、1 项伪差异。
- **★摧毁偏差根因与修复定位（用户点名）**：FINAL3 Delete 调 **EA 0x79EA50 完整伤害入口**（thiscall ecx=Body + push 6/19/0：伤害类型 6、死亡类型 0x13；函数开头 sub esp,0x9C 构造 DamageInfo→[Body+0x33C] HP 对象完整管线→死亡决策→动画+模型回收）。MT kill 桥=底层 adjust(0x38CB30)+手工 Die 镜像=无上游管线=无动画。**Steam 对称已定位（三特征+逐指令同构验证）：1.13=VA 0x7C7190（RVA 0x3C7190）、1.12=VA 0x7DCDF0（RVA 0x3DCDF0）**——与 EA 逐指令同构（仅 .rdata 标签 0xBF3138/0xBF276C 与构造 callee 0x500FD0 随版本不同；兄弟函数 0x7D49B0 写死 6/8 不是它）。**修复方案：KillDispatcher 改调伤害入口（ecx=Body, push 6/0x13/0），DamageInfo 邮箱可简化；FINAL3 实测此路径有完整死亡动画**。v18i"push 0/0x13/6 call 模式静态穷尽无命中"的结论作废——当时没有 EA 映像，现在有了。
- **缺 4 项**（同 v19b 审计）：F10 禁电脑建造（EA 0x30F530/1.13 0x3387D0 已定位）、F11 玩家无敌（EA 0x12EEDF）、F12 一击必杀敌方（EA 0x3651AE+3FE714+2E24E3）、P 三星（FINAL3=call 晋级(3,1,0)，MT rank 桥有等价能力未接）。
- **行为差异 2 项**：①J 增援——FINAL3 一次生成 **8 个**+每个升一级（MustCode2+B00 循环），MT 生成 1 个；②F1 资金——FINAL3 一次性 +100000 可连按（另钉上限 99999999），MT 持续开关制（更强，无需改）。
- **伪差异澄清**：①sel_copy 位置——当前代码已是鼠标优先（回退选中锚点），与 FINAL3 一致（v18h 时期"叠放"已被 v18g/v18j 修复）；②F9 迷雾——桩值与 FINAL3 完全相同（[ebp+260]=100000.0），用户报告的"高度迷雾残留"非实现差异，待实机对比（可能是版本渲染差异）。
- **俘虏六 hash**（95D6E965/FD87E82A/856C9DD6/D20552E1/1AFC9A6E/D6D22475，FINAL3 俘虏时对六种模板跳过裸改属主）在 WBStringHashes.big 的十进制/十六进制两查均无命中=非标准模板哈希空间，身份未识别；不影响 MT（capture 桥走完整归属函数+context 校验）。
- **MT 增强清单（FINAL3 无）**：资金防爆上限、弹药回填真实容量（vs 钉 21 亿）、俘虏完整归属切换（vs 裸改字段）、任意 hash 增援、治疗/经验动作、威胁分离开关、诊断采集、现代化 UI/热键/脱离自动还原/对局切换保持。
- **优先级建议**：①摧毁修复实装（定位已完成）→②J 增援批量+升级→③F10/F11/F12→④P 三星接桥。

## v19（★随地建造正式落地：实测成功 → 修改器开关实现，publish-v19）

- **用户实测成功（2026-10-12，Steam 1.13）**：patchtest 0x511955 `75 0C→EB 0C` 后灰色格子直接点击放置成功——v18s 的 patch 点定案无误，FINAL3 随地建造语义完整复刻。
- **build_anywhere v3 实装（TrainerEngine.SetBuildAnywherePatch）**：纯 2 字节分支 toggle（75 0C↔EB 0C），开关幂等（重复开/关安全）、字节异常拒绝改写、写入校验、**脱离进程自动还原**（Detach 段）；对局切换不重置（.text 补丁，比旧数值方案稳）。补丁点经 features.json globals.buildAnywherePatch（RVA 1.13 0x111955 / 1.12 0x128DF5）注入。**旧数值方案全链删除**（SetPlacementDistance/placementDistance 全局/_savedPlacementDistance——该值是 AI/收集层搜索半径，与放置范围无关）。
- **版本规则切换（用户拍板）**：UI 关于栏 v2.0→v19，发布目录纯数字 publish-v19 起（不再 v18m 字母后缀）。
- SelfCheck 42/42 通过（无回归），Release build 0 警告 0 错误。**publish-v19 已发布**。
- 剩余待办：①v19 实测（建议顺带验热键 Alt+B、对局中开关、切对局不重开、修改器脱离自动还原）②摧毁死亡管线深抓（差一次 60s kill 采样）③1.12 侧 patch 点 0x528DF5 实测（磁盘已验证，未实机）。
- 复盘要点（v18n→v19 全程）：三次方向反转的根因都是**信息不全时过早收敛**——v18m 把 RVA 当 VA（链错位）、v18q 把"未变绿"当失败（判读标准错）、v18p 怀疑 AI 链（归因不完整）。终局解法是用户提议的"找参照系实测"（盗版 1.12+FINAL3 磁盘对照），一次拿到 ground truth。**以后凡有可运行的参照实现，先对照再推理。**

## v18s（★破案：FINAL3 随地建造全链路定案，Steam 双版 patch 点字节级确认）

- **用户盗版 1.12 实验**：FINAL3 在 Steam 重打包 1.12 无效且闪退——直接写 0x4E7565（Steam 版那里是 fstp 指令中间）→ 执行乱码崩溃。确认 FINAL3 为直接地址写入（无 AOB 保护）、EA 原版布局专用。盗版 1.12 磁盘验证 **0x4E7565 = `75 0C` 实锤**——MustCode+1201 imm32 常量表解读成立。
- **用户关键洞察**：FINAL3 的随地建造效果=**灰色格子也能建造**（"在目前有效范围外正常建造"），不是把格子变绿——v18q patchtest 的"没变绿=失败"判读标准本身错了（当时没测点击）。0xB322EA 格状态 patch 可能本来就有效但未验证（保留为备选，不作数）。
- **EA gate 函数全解（盗版=EA 原版 1.12 的 0x4E74B0..0x4E7580，ret 0x10 thiscall+4 栈参）**：开头 test edx,0x10000 早退返回 0 / `shr edx,0xB; and bl,1`（bl 初值=参数 bit11）/ 空容器直落 test bl,bl / 主循环遍历容器（[eax+8] 链表项）：预筛（[esi+0xC]≠0→标记找到、[esi+0x20]、test edx,0x8000、edi、[esi+8]）→ playerRoot（EA 全局 0xCE8C9C）+ 查询 0x838F60/0x4DFF50 → "找到"标志 [esp+0x13] → **主判定 0x4E4120（bl==0 才调用，任一成功锁定 bl=1）** → 循环到容器尾。尾：`test bl,bl; jne +0xC`——bl 全败 → **mov eax,2（失败码）**；否则 setne [esp+7] 返回 bool。**FINAL3 patch：jne→jmp = 永不返回 2 = 范围外照常通过**。
- **★ Steam 双版对应函数定位（三特征唯一定案）**：EA 函数体的 `test edx,0x8000`（F7 C2 00 80 00 00）在两版 .text 各**唯一命中**，且 `test al,al; sete al; test al,al` 三连与 `mov eax,2; pop ebx; add esp,0xC; ret 0x10` 失败码尾巴聚集同一函数，逐指令同构验证：
  - **Steam 1.13：gate 函数 0x511870（主判定 callee 0x50E140，查询 0x862350/0x509C70，playerRoot 0xCF214C）→ patch 点 0x511955：`75 0C`→`EB 0C`**（磁盘验证 ✓）
  - **Steam 1.12：gate 函数 ≈0x528770 → patch 点 0x528DF5：`75 0C`→`EB 0C`**（磁盘验证 ✓）
  - 三版（EA 0x4E7565 / Steam 0x528DF5 / Steam 0x511955）**完全相同的 2 字节 patch**。
- **gate 函数与 AI 的关系（修正 v18f）**：gate 紧邻 v18f 分析的 AI 选址 worker（1.13 VA 0x511980，GetAIStructurePlacementLocation 路径）——**玩家放置与 AI 选址共用此 gate**（AI worker 是其调用者之一），这解释了 FINAL3 patch 单点全效（预览+提交+AI 三路）。v18f"该区域=AI 专用、不能当玩家 permission"的结论不准确——它是共用判定层。此前 placehunt 链（validator 0xA42450→worker 0x520780→percell 0xA2A1E0）是另一条更上层的放置准备链（候选收集/足迹），与本 gate 是上下游关系。
- **patchtest_buildanywhere.py v2**：双版本自动检测（进程名/tasklist；显式 PID 时按补丁点字节探测版本），patch 点按版本选择，提示文案改为"灰格直接点击"判读。待用户实测：放下成功=v3 定案（改造成 StubGen toggle 或纯字节 toggle 开关）；仍被拒=提交层另有检查（追 gate 的调用者中非 AI 的那条）。

## v18r（patchtest 阴性 + FINAL3 script_12 语义定案 + 分层模型修正 → 1.12 实况 diff 实验）

- **patchtest 阴性（0xB322EA 75 05→EB 05 空格返回 1）：虚影没变绿**。格状态（buildability 覆盖）层不是绿色判定层。
- **FINAL3 script_12（Free Build）原文只有 4 行**：`[MustCode+1201]: db eb 0c` / disable 还原 `75 0c`。结合 script_00 的 `MustCode+1200: mov eax,[Ra3_1.12.game+e7565]; ret`——**MustCode+1201 处躺的 4 字节正是该 mov 的 imm32=0x004E7565**，FINAL3 用"mov 桩 imm32"当补丁目标常量表（`[label]`=解引用语义）。**随地建造 = EA 1.12 模块 RVA 0xE7565 处 `75 0C`（jne +0xC）→ `EB 0C`（jmp）**。v18f 的 hypothesis 精确化成立。
- **FINAL3 全部地址在 Steam 重打包 1.12 上对不上**（实测：RVA 0xE7565→VA 0x4E7565 是 `fstp [eax]` 指令中间；CreateUnit RVA 0x205240→0x605240 是 `mov eax,edx; shr` 非 cdecl 入口；变换 0x1ED4A0 亦非独立函数）——FINAL3 是 EA 原版/3DM 1.12 布局专用（来源 3DMGAME-Com1.12 包），只能映射语义不能映射地址。
- **分层模型修正（解释阴性结果）**：worker 0x520780 在 **PlacementGrid（[0xCE21CC]，0xB281E0 访问器，0x28 字节/项数组）**上收集候选格——**候选集合=虚影绿色的来源**；followup/percell 查的是**另一个网格**（[0xCEC450]+0x28→0xB336E0，[ecx+0x44] 基址 0x34 字节/项）=buildability 覆盖层（第二阶段/提交用）。patch buildability 层不影响颜色 ✓ 与实测吻合。**两个网格系统是不同数组**（0x28/项 vs 0x34/项）。下一站=worker 内部的收集谓词（0x51A9E0→0x5149F0，worker 有 3 处调 0x51A9E0：0x5208C9/0x5209DB/0x520AB4），EA 0xE7565 的 jne 对应物应在其中——dump_worker_full.py 已备（未跑完）。
- **vf48 在两局扫图中全程零命中**（placehunt 挂了但 hits=0）——UI 谓词 0x707880→vf48 路径在放置预览中未被调用，v18g 的"UI 谓词两层检查"模型对预览颜色不成立（至少不经 vf48）。
- **★ 下一步实验（用户提议，正确路线）：1.12 + FINAL3 实况 diff**。放弃在 1.13 硬猜 EA 地址的语义对应，改为：游戏切 1.12 → 先开 `tools/analysis/watch_text_diff.py`（基线快照+每 3s 对比 .text，任何字节改动实时打印 VA/旧/新，含还原检测）→ 运行 FINAL3 开随地建造 → 监控直接打印它 patch 的真实地址和字节。三种结果都有定案价值：①Steam 1.12 上 FINAL3 有效 → 拿到真实 patch 点 → 反汇编语义 → 1.13 对称复刻；②FINAL3 无效但监控显示它写了某处 → 看写哪了（可能崩游戏，崩溃也无妨）；③FINAL3 无效且什么都没写（如 AOB 扫描失败拒绝 patch）→ 确认 EA 原版专用，转 worker 收集谓词静态路线。FINAL3 本体=C:\Users\14560\Downloads\3DMGAME-Com1.12.ken22265.160913\RedAlert3_Trainer_1.12_FINAL3.exe（无游戏本体，实验用 Steam 1.12）。
- 操作顺序铁律：**先开监控再开 FINAL3**（基线必须干净）。

## v18q（两局活体实验定案：玩家预览路径实锤 + 格状态 gate 确认 + 2 字节 patch 点定案）

- **两局 placehunt 数据（tools/txt/hai.txt 有AI / noai.txt 无AI，各 90s 扫图）全部定案**：
  1. **链归属=玩家预览路径实锤**：无 AI 局整条链照样高频活跃（validator +15/0.5s=30/s=逻辑帧率、percell/格状态 +900/0.5s=1800/s），鼠标扫图即触发无需点击。v18p 的"可能是 AI 选址链"质疑被数据否定——两局频率几乎一致，若为 AI 链无 AI 局应归零。
  2. **AABB=世界包围盒死刑**：两局扫图全程 [mgr] allowed-zone records 恒为 1 条 (0,0,500,560)（全图），粗筛-FAIL 仅开场一次性 60 次。EB 46 预案正式废弃。
  3. **格状态=真 gate**：无 AI 局样本 eax 全 1（扫图起点=自己基地旁，格子有建造许可覆盖）；有 AI 局样本 eax 全 0（起点无覆盖）。格记录地址两局不同区（0x656xxxx vs 0x5CAxxxx）。
  4. **频率结构：30fps × ~60 格/帧**——候选格围绕建筑虚影（不是围绕基地的 90 半径圈），patch 后构造成本有界（≤60 足迹对象/帧）✓；**距离 90 不限制"建多远"，数值线正式关闭**（v18j 的 300 数值开关退休）。
  5. **采样注意**：中部桩（函数内地址如 0xA2A2A6/0xA2A2C5）样本的"ret"字段是栈内数据（保存的 ebx，显示 0x7DB7C20/0x7259CD0=两局 manager 堆地址）不是调用者；eax 观测仍有效。样本 cap=8 冻结太早，只覆盖扫图最初 8 格——若需全程分布须让 widx 周期清零。
- **格状态机 0xB322D0 完整逻辑（含 0xB322F1 尾段）**：byte[rec+0x32]≠0→3(阻止，保留)；word[rec+idx*2+4]==0→0(无覆盖=THE gate)；0xB322F1: cmp ax,0xFFFF / mov eax,1 / jne ret → 0xFFFF 时改取全局默认 [0xD233DC]，其余返回 1(被许可圆覆盖)。idx=[side+0x20]（放置类型，≤19；每格 0x34B 含 ~20 个 16 位状态槽）。
- **★ patch 点定案：0xB322EA `75 05`→`EB 05`**（jne→jmp）：无覆盖格(word==0)不再走 xor eax,eax 返回 0，改走 ax≠0 路径→cmp 0xFFFF 不等→mov eax,1→返回"已覆盖"。阻止态(3)与真覆盖(1)语义不变，地形/占用全保留。**FINAL3 `75 0C→EB 0C` 的精确等价物（连 jne→jmp rel8 指令形式都一致）**。影响面：0xB322D0 仅 2 个直接 caller（0xB3373D=0xB336E0 内部、0xB32B9B 待查），0xB34740 thunk 有 22 caller 共享此查询（含 AI 选址——单机可接受：AI 也会全图选址）。
- **tools/analysis/patchtest_buildanywhere.py 就绪**：120 秒临时 patch 实验（冻结整写 EB 05→倒计时→try/finally 自动还原 75 05+还原校验）。判读：虚影远处变绿可放=v3 定案（走 StubGen 通道做成正式开关）；仍被拒=提交层另有验证（追 0xA424E0/0xAA891C 上游）。
- 版本号规则（用户拍板）：v19 起纯数字递增；UI 关于栏已从 v2.0 改 v19；find_game() 重写为 tasklist 解析（Process32First 在本机 Python 3.14 x64 报 ERROR_BAD_LENGTH，线程快照正常进程快照不行——勿用 toolhelp 枚举进程）。

## v18p（SDK/RA1 源码调研核实：格状态机定案 + 链归属质疑——0xA42450 链可能是 AI 选址链）

- **DeepSeek 的 SDK 引用全部属实**（SDK 位于 `D:\RiderProject\CnC_Modding_Support\Red Alert 3\`）：`Xml\Allied\Structures\AlliedConstructionYard.xml:632` 确有 `ProjectedBuildabilityInfo`（ConYard Radius=600，第二处带 HeightVariation）；schema `AssetTypeGameObject.xsd:365-371`（Radius/RadiusY 椭圆/BuildPlacementTypes/注释"In RA3 no structures provide buildability until fully unpacked"）；**`BuildingPlacementDistance` 全 SDK 只出现在 `Xml\SkirmishAI\AITargetHeuristicLibrary.xml:1072-1076`，值为 200/500/1000/3000/7000**——没有任何地方是 90。机制模型：建筑落成后向周围投射 Radius=600 的可建造圆，写进格状态位；"只能建在基地附近"= 圆并集。
- **格状态机判读核实准确并补细节**：`0xB336E0`（世界→格：减原点 [ecx+4/8]、乘缩放 [ecx+0x38]、行宽 [ecx+0x3C]、**imul 0x34**=每格记录 0x34 字节、基址 [ecx+0x44]）→ `0xB322D0`：`byte[rec+0x32]!=0→3(阻止)`；`word[rec+idx*2+4]==0→0(该类型无覆盖)`；`0xFFFF→[0xD233DC] 全局默认`；`其它→1(被覆盖)`。**关键细节：idx=arg1=[side+0x20]（阵营相关放置类型索引，cmp 0x13=最多 20 种）——每格 0x34B 记录里有 ~20 个 16 位状态槽，每个 BuildPlacementType 一个**，与 SDK 枚举对上。消费点 `0xA2A2C5: cmp eax,1`。
- **cl 语义分歧未定案**：DeepSeek 判读"cmp eax,1/2/3 决定接受/拒绝"，本方判读"cl 只选 esi+0x10/esi+0x24 两组字段=足迹对象类型，不产生拒绝"（两条路径都继续构造）。且它说 0xA2A2D4 的 `cmp eax,2/3` 比较的是查询返回值——实际比较的是 [esp+0x50]=候选条目+0xC 字段（arg3）。静态不能定案 → tracer 挂 0xA2A2C5 直接采 eax/arg3 分布。
- **★链归属质疑（比 DeepSeek 更进一步）**：既然 SDK 说 BuildingPlacementDistance 是 AI 字段（且值域不含 90），而验证器 0xA42450 静态确实消费 [0xCF2CAC]+0xC=90.0——两个事实可以统一为：**0xA42450 整条链可能是 AI 建筑选址链，不是玩家放置路径**。v18m 的深栈样本在"用户做放置动作时"抓到，但用户放置时 AI 也在建造（并发），"用户动作时被调用"≠"在玩家路径上"；v18n 的"90→100000 巨卡"同样可被"AI 每帧全图选址扫描"解释。堆块内容（3.0/4.0/90.0/2/0.142857/...与 .rdata 0xBED828 同串）像 GameData 里的 AI/全局配置记录副本。90 与矿场 RestrictedAreaShape Offset x=90.0 同值大概率巧合。**判别实验：无 AI 研究局 + 放置模式扫图看链是否亮**（v18b 教训：研究局本来就该无 AI；对照有 AI 正常局）。
- **RA1 源码（Westwood 非 SAGE）方向性启示**（无直接符号可用，零命中确认）：`Passes_Proximity_Check()`（DISPLAY.CPP:666）与 `Legal_Placement()`（TECHNO.CPP:6323）分工——邻近/距离许可 vs 地基干净——与 RA3 的 buildability 判定 vs grid/footprint 检查同构；`Debug_Map` 短路证明此类规则是官方允许旁路的单点；RA2 注释（BG 署名）证明"放宽放置限制"是官方常规改动。客户端谓词（0x707880→vt+0x48=0x5F0930）与服务器判定分离也由 RA1 模型解释（v18h vf48 恒真无效的必然性）。
- **tracer v3 站点已换**（全部 displaced MATCH、边界干净、Unicorn 复验通过）：validator 0xA42450（链入口/距离消费）、percell 0xA2A1E0、粗筛-FAIL 0xA2A283、粗筛-PASS 0xA2A2A6（AABB 站点改标签为粗筛=世界包围盒 5000×5600，不再当 gate）、**★格状态 0xA2A2C5（displaced `83 F8 01 B1 01` 恰好 5 字节整窗，样本 eax=格状态 0/1/3/默认、栈 arg3=候选条目）**、vf48 0x5F0930（UI 谓词对照，vt+0x48 本体）。去掉了 top（validator 唯一 caller 即 top，频率等价）。[mgr] 每 2s 记录数组快照保留。
- **判读矩阵 v2**（placehunt 一局定案）：
  1. **无 AI 局**放置模式扫图：链高频 → 玩家路径；此时基地内格状态 eax=1 高频、远处空地 eax=0/3 → 格状态=真 gate → v3 方向=格状态字改写（数据侧，把空格 word 改成覆盖值——需先单格验证语义+弄清游戏何时重写）或 0xA2A2C5 分支 patch；
  2. 无 AI 局全零、有 AI 局活跃 → 0xA42450 链=AI 选址链 → 玩家 gate 另寻（第二阶段 0xA424E0 anchor search / 顶层之上 0xAA891C / UI 链 0x707880 的调用者）；
  3. 粗筛 FAIL 应极少（仅地图边缘）、PASS 高频——确认粗筛恒真假设后 EB 46 patch 彻底放弃；
  4. 格状态查询与鼠标位置无关/全零 → 不在逐帧预览 → 点击瞬间采样。
- 90→91 差分实验（DeepSeek 提议）采纳为低风险判别项，但需用户在场观察预览变化，归入下次会话（placehunt 的验证器样本也能侧面回答距离的传递路径）。

## v18o 补遗（DeepSeek 反馈核实 + 活体盒=全图重大降级证据 + 判读矩阵）

- **DeepSeek"8 字节 displaced 坑"核实：结构警告正确，字节描述有误**。0xA2A25E 起：`76 23`（jbe）+ `F3 0F 10 4C 24 38`（movss xmm1,[esp+0x38]，完整 6 字节）——**正确 8 字节窗口 = `76 23 F3 0F 10 4C 24 38`**（DeepSeek 写的 "F3 0F 10 44 24" 是 0xA2A253 处 movss 的字节且少一位）。E9 跳板在此站点需要 8 字节 displaced；2 字节直接 patch（76 23→EB 46）本身无 displaced 问题，坑只在跳板式/toggle 还原式实现。整窗 toggle 方案定案：开=`EB 46 90 90 90 90 90 90`、关=原 8 字节、冻结整写原子（1.13 0xA2A25E→0xA2A2A6、1.12 0xA2535E→0xA253A6，EB 46 两版同字节）。
- **DeepSeek"PASS 路径构造成本"核实：正确且已细化**。PASS=每候选格构造足迹对象（0x8627D0=playerRoot+0x28 side 微访问器 → [side+0x20] → 0xB34740=[0xCEC450] manager +0x28 thunk→0xB336E0 查询 → cl=足迹类型选择 → lock xadd 引用计数 + 0xA236E0 + 0x54DA20/0x545DD0）。**确认 PASS 无第二个权限拒绝出口**（cl 只选 esi+0x10/esi+0x24 两组字段=对象类型，不产生拒绝）——percell 的唯一剔除出口就是 AABB。最坏组合（gate patch+距离 100000+每帧预览）=全图×每帧构造=必然卡死。**开关合并决策（采纳）：v3=单开关，只做 EB 46 整窗 patch 且不碰距离值（保持 90），SetPlacementDistance 数值开关退休**——待活体确认后一并实施。
- **★ 活体盒=全图（AABB gate 假设重大降级）**：manager vt+0x38 实现已定位并独立验证（活体 [0xCF2410]=0x52B6090 → vtable 0xC13A10 → **+0x38=0x5F07D0、+0x48=0x5F0930=vf48——同一 manager 类的两个虚方法**，v18g 的 UI 层记录与本轮 percell 分析由此统一）。0x5F07D0 全函数语义闭合：遍历 [mgr+0x54,+0x58) 的 16 字节记录（minx,minz,maxx,maxz 格子坐标），×10（[0xBED704]=10.0 格尺寸）归并外接盒，附高度窗口 [0x1438]/[0x143C]；percell 只比较 X/Z（Y 写出但不比）。**活体当前记录数组只有 1 条 = (0,0,500,560) 格 = 整张地图**——若这是放置时的稳定状态，AABB 只是地图边界裁剪，EB 46 patch 将是 no-op，"基地附近"的真限制在别处：候选收集锚点（worker 以锚点为中心 r=90 收集——锚点=基地则 r 就是离基地距离）或第二阶段 0xA424E0→0x3A14B0 anchor search（v18f 记录的锚点查找，hash 0x9590538A）。未排除：记录数组在放置流程执行期间动态收缩（当前读的是非放置时刻状态）。
- **placehunt 已升级**：轮询循环每 2s 打印 `[mgr] allowed-zone records=N first=...` 快照（manager 记录数组），扫图期间记录数/内容变化=动态盒实锤。read_manager_predicate.py 已修复 DeepSeek 版的分块解码 bug（按 0x80 分块导致 0x5F0850 后乱码）并补全活体记录读取。
- **判读矩阵（placehunt 一局定案）**：
  1. 远拖时 AABB-FAIL 高频、近基地 AABB-PASS 出现 → 盒动态收缩、AABB 是真 gate → EB 46 patch 有效，实施 v3；
  2. FAIL/PASS 都命中且频率与鼠标远近无关 → AABB=地图裁剪、patch 无效 → 转向锚点链（dump 0xA424E0 第二阶段 + 0x3A14B0 anchor search + worker 锚点参数流）；
  3. FAIL/PASS 全零 → percell 不在预览路径（仅点击提交时跑）→ 改点击瞬间采样；
  4. `[mgr]` 记录在扫图期间变化 → 无论分支 1/2 都要重新评估盒语义。
- v2 站点 AABB-FAIL 0xA2A283（displaced `8B 74 24 48 8B 4E 04` 7B）与 AABB-PASS 0xA2A2A6（`8B 0D 4C 21 CF 00` 6B）边界干净、与 8 字节 patch 窗口（0xA2A25E）互不重叠，tracer 挂点与 patch 点无冲突。
- DeepSeek pre-flight 与我上轮只读检查一致（PID 38552 活、站点 MATCH、距离 90.0、manager/grid/playerRoot 活、修改器已脱离）。

## v18o（"死装置"报告复核：三个地址口径误诊全部推翻；percell AABB gate 静态定位）

- **上一轮探测报告的核心结论（placementDistance 是死装置）是扫描口径错误产生的假阴性，已推翻**。`find_gamedata_refs.py` 用 `struct.pack('<I', 0x8F2CAC)`（RVA 字节 `AC 2C 8F 00`）扫 .text，而指令编码的是 VA `0xCF2CAC`（`AC 2C CF 00`）；对照组 `0xCF30F0` 恰好是 VA 口径，一真一假不可比。正确口径扫描 `0xCF2CAC` 有 **4 处真引用**（`0x802A37 / 0xA1B80F / 0xA42457 / 0xA44A0D`，其中 `0xA42457` 就是验证器本体的 `mov edx,[0xCF2CAC]`）。逻辑上该结论也自相矛盾：v18n 实测写 100000 会让游戏巨卡（全图逐格扫描），没人读的值不可能引起巨卡。
- **报告的三个"勘误"也全是把 v18m 的 RVA 记录当 VA 反汇编的误诊**：v18m 链 `0x647300→0x642450→0x120780` 全程 RVA 记法（与 PLACEHUNT 标签 `0x63AAB0`=VA `0xA3AAB0` 同风格）。`0x642450` 加基址=VA `0xA42450`，它本身就是函数入口（`sub esp,0x14` 开头），不是"落在 mov eax,edi 和 ret 0x10 中间"（那是误把 RVA 0x242450 处的无关代码当成了它）；`0x120780`=VA `0x520780` 在 .text 内有效（`0x120780<0x400000` 根本不可能是 VA，这个异常本身就该触发口径警觉）；`0x647300`=VA `0xA47300` 是顶层函数入口。
- **整条玩家放置链静态复核完成（指纹一锤定音）**：全 1.13 .text 中 `or ecx,0xC4020` 唯一命中 VA `0xA42496`（=RVA 0x642496，紧邻 v18m 记录的 0x642484）→ 验证器 VA `0xA42450`：`mov edx,[0xCF2CAC]; fld [edx+0xC]`（距离 90.0）+ 碰撞掩码 + `mov ecx,[ThePlacementGrid 0xCE21CC]` + `call 0x520780`（worker，逐格收集候选）+ `call 0xA41510`（followup）。验证器唯一 caller VA `0xA47326`（顶层 `0xA47300` 内）；顶层唯一 caller `0xAA891C`。顶层紧接着调第二阶段 `0xA424E0`（hash `0x9590538A` 查找）——v18l 说它是"另一条路径（疑生产完成/AI）"也是误判，同参数连续调用=同一放置流程两阶段。1.12 全同构：顶层 `0xA42840`/验证器 `0xA3D8E0`（`mov edx,[0xCEE98C]; fld [edx+0xC]; or ecx,0xC4020; mov ecx,[0xCDDEAC]; call 0x538250`）/followup `0xA3C9A0`。
- **★ 真正的区域 gate 静态定位：percell `0xA2A1E0`（RVA 0x62A1E0）的 AABB 包围盒剔除**。followup `0xA41510`（arg2=0 时）对 worker 收集的每个候选格调 `0xA2A1E0`：① gridquery `0x5065A0`（PlacementGrid 格坐标→世界 float3，含矩阵变换）；② **`[0xCF2410` 放置权限 manager] vt+0x38 虚调用返回包围盒**（该 manager 正是 v18g 记录的 UI 谓词两层检查里的 manager，1.12=VA `0xCEE0F0`）；③ 4×comiss AABB 测试（格世界坐标 X/Z 必须落在盒内）；**出盒→`0xA2A283` 剔除该候选格**（销毁足迹对象+从容器移除）；入盒→`0xA2A2A6` 走 playerRoot（`0xCF214C`）+ `0xB34740` 权限查询→创建放置足迹。这就是"只能建在基地附近"的服务器侧几何 gate——与 v18n"候选格收集空=放置失败"的推断吻合：距离只是收集半径，远处候选格全部被 AABB 剔除，扩半径（300/100000）永远不解决区域限制。
- **1.12 对称到字节级**：percell `0xA252E0`，AABB 四分支 `0xA2535E 76 23 / 0xA25369 76 18 / 0xA25376 76 0B / 0xA25381 77 23`，FAIL=`0xA25383`、PASS=`0xA253A6`——**rel8 与 1.13（`0xA2A25E/0xA2A269/0xA2A276/0xA2A281`）完全相同**。patch 预案（待活体验证后实施，等价 FINAL3 75 0C→EB 0C 语义）：首 jbe 改 `EB 46` 无条件跳 PASS（1.13 `0xA2A25E`、1.12 `0xA2535E`，两版同字节）。只跳过包围盒测试，地形/占用/碰撞（worker 的 0xC4020 掩码与 16 项 bounds 检查）全部保留。这不是裸签名扫描（Round 3 已证明裸 `75 0C` 有 1193 假命中）——是活体链+语义定位的单点指令。
- **与 v18f AI 链的区分（两代结论不冲突）**：v18f 确认的 AI 放置搜索链 worker 是 RVA `0x111980`（VA 0x511980，GetAIStructurePlacementLocation.cpp 路径）；本链 worker 是 RVA `0x120780`（VA 0x520780）——不同函数。v18m 深栈样本来自玩家实际放置动作，证明 0xA42450 链是玩家路径。Round 3"玩家 permission 站点尚未定位"的结论由本轮推进到"AABB gate 候选，差活体分支频率证实"。
- **PLACEHUNT 旧六点判读修正**：`0x64C970`（sixiter）= 懒初始化+6 玩家槽遍历+模板表宿主 0xCF0108 引用，是玩家/规则更新器不是放置谓词；`0x818A00` 转发器/`0xA3AAB0` 容器 resize 维护（确在放置路径上但语义太泛）；`0x5F0930`（vf48）无直接 caller（纯虚调用）+ v18h 实测恒真无效=UI 层非 gate，仅留作对照；regionline `0x90FD60`（=v18g 记录的 RVA 0x50FD60，当年挂桩误用 VA 0x50FD60 所以无效）唯一 xref 在 vf48 内。上一轮报告对 tracer"count 满后仍每次复制 120 字节"的批评不成立——`jge skip` 目标在 inc 之后，满后 imul/复制/inc 全部跳过（重读代码确认）；"缺频率观测"批评成立，已修。
- **trace_trampoline.py v2**：PLACEHUNT 换成真链六站点（顶层/验证器/percell/**AABB-FAIL 0xA2A283**/**AABB-PASS 0xA2A2A6**/vf48 对照），displaced 全部字节级核对 MATCH 且指令边界干净；数据片头部改为 +0 hit count（永续递增，Python 0.5s 轮询差分=每站点调用频率）/+4 written idx（cap 冻结）/+0x10 样本区，slice 0x400×8 样本（旧 0x200×6 实际装不下 724B，从未跑通过）；样本布局澄清：30 dwords=8 pushad+**1 pushfd eflags**+21 栈（打印约定 eflags=stack[0]/ret=stack[1]/arg1=stack[2]）。Unicorn 语义验证 12 项全过（verify_tramp_v2.py：hit/widx 冻结、寄存器+DF+esp 恢复、cap 后样本区零写入、displaced 栈效果 0x40）。新增单站点模式 top/validator/percell。
- **活体只读确认（PID 38552，1.13 对局中）**：[0xCF2CAC]=0x133CC3D0、[obj+0xC]=90.0（v18j 的 300 已还原或对局重建）；全部新站点字节=磁盘原样（无桩无 patch）；manager 0xCF2410=0x52B6090、TheXXX 0xCCFC90、playerRoot、ThePlacementGrid 全部非空活跃。
- **下一步（需用户配合一局）**：跑 `py tools/analysis/trace_trampoline.py placehunt 90 38552`，游戏内进入放置模式**用鼠标扫过地图**（预览每帧重算，无需点击）。判读：远处拖动时 AABB-FAIL 分支高频命中而 AABB-PASS 零命中、近基地处 PASS 出现 → gate 实锤 → 实施 2 字节 patch（build_anywhere v3 代码桩，走 StubGen replay 通道）。若 FAIL/PASS 都不命中则 percell 不在预览路径（可能仅在点击提交时跑），改在放置点击瞬间采样。
- 工具：verify_distance_chain.py / verify_distance_chain2.py / dump_validator.py / dump_placement_funcs.py（链路复核与全函数 dump，artifacts/placement_chain_113.txt 1174 行）/ verify_tramp_v2.py（Unicorn 桩验证）。

## Round 3 收口（离线核验；仅以下新增事实）

- 新增严格 `src/RA3MT.Core/Target/SpawnApiResolver.cs`：双版本重建并比对 304B wrapper 完整字节、12 个 rel32 CALL 目标及 manager VA（按 imageBase + RVA）；仅返回地址，不调用、不安装、不连接生产桥。SelfCheck `spawntest` 通过两版真实磁盘映像并拒绝 38 项改动（函数体、call displacement、manager operand、短读）；Release build 0 warning/0 error。该身份解析不能证明运行时线程/生命周期/单位适配安全。
- 双版本核对实际由 wrapper 调用的 owner resolver：1.13 RVA `0x4647A0` / 1.12 RVA `0x4793B0` 为 thiscall(ECX=owner-record)，无栈参数、`ret`。它向 global VA `0xCE21A4` / `0xCDDE84` 的 helper `0xFF4A0` / `0x1175D0` 查类别（helper 读 global object+`0x148`，类别 5/6/7/8 返回 true）；global 与 owner ECX 在解引用前都无 null guard。helper 为 true 且 owner+`0x8C` 非空时返回 `[owner+0x8C]+0x10`（该最终指针不验证，可能为 null）；否则——包括 helper false 或 owner+`0x8C` 为空——直接返回 `[owner+0xAC]`，也不验证，可能为 null。字段名义类型及 enum 业务含义未证；这是 map startup owner-record 路径，不能当作任意 `Side*` API。另有独立构造器 fallback：1.13 RVA `0x3EB718` 在 request+4 为空时读取 `[0xCF214C]+0x30` 写入 Body+`0x418`；1.12 对应 global VA 为 `0xCEDE2C`。这不是 resolver 的 null/有效性保证。
- startup hash→template 链两版均已核对：1.13 caller RVA `0x22E5A3` 先调 key getter `0x4629C0`（返回 `[*arg+0x34]`），取 `[*result]` hash，再以全局 VA `0xCF0108` 为 hash-table owner 调查找器 `0x40D5B0`；1.12 配对 RVA `0x2442B3`、getter `0x477760`、全局 VA `0xCEBDE8`、查找器 `0x422510`。两查找器分别调通用 map finder `0x40D2C0` / `0x11F110`，map header 为 owner+`0x28`。1.12 finder 的调用 ECX=`map+0x28`，通过栈上传入 key/out 参数；helper 以 key 指针取 uint hash，按 bucket count 取模、索引 buckets 并沿 node+8 链比较 node[0]，以 out 参数返回 iterator/value 指针（`ret 8`）。外层 hash lookup 检查 bucket/key，命中返回 node+4 的 value，未找到/sentinel 返回 null（`ret 4`）。startup caller 将结果直接当 wrapper arg2；其模板-like类型由后续 Body 构造器处理验证，但名义类型和任意运行时 hash 的合法性仍不能单由这一条路径推出。全局/桶数的 null/零保护不足。
- startup caller 参数源进一步配对：1.13 outer helper `0x22E510` / 1.12 `0x244220`；其 direct caller 分别 `0x240232` / `0x255EA2`。在 inner wrapper call `0x22E64E` / `0x24435E` 处 arg2 是上述 hash lookup 返回项，arg3 是 waypoint记录 `+0xC/+0x10/+0x14` 填出的局部 Coord3D（经 terrain manager 高度转换），arg4 来自 startup side/name object，arg5 来自 outer arg3，arg1 来自 outer arg1；wrapper 自己忽略 arg1/arg5，所以不必假设它们为0或 `[side+0x10]`。第二个 caller `0x22EACD` / `0x2447DD` 也显式推入五个值、`add ESP,0x14`。Direct CALL byte candidates each version exactly two;都属于 startup/map path而非可复用的 match-time spawn contract。
- hash lookup 配对：1.13 `0x40D5B0` / 1.12 `0x422510` 接收 ECX=hash-table owner、栈 arg1=uint hash、RET4；table header 在 owner+28，分别调用通用 map-find `0x40D2C0` / `0x11F110` 执行 bucket/chained-node 查找。找不到结果时返回 NULL；找到时比较 hash，并返回 `foundRecord+4` 所指内容。地图 caller `0x22E5A3` 先调 `0x4629C0` 返回 hash-record `+34`，然后该值作为 hash 传给 helper；此 startup path 结果在 wrapper中直接当 template pointer，但不能推论所有哈希输入都返回 `ObjectTemplate*`。另一路 startup hash 有 237 个CALL-byte候选，须按指令边界分类，不能当唯一模板 lookup。
- 1.13 caller `0x22E64E` / `0x22EACD`、1.12 `0x24435E` / `0x2447DD` 为 wrapper 唯二 rel32 CALL 候选（字节扫描，前后皆验证）；地点值来自 caller 堆栈 waypoint/记录结构，并经过 terrain manager vfunc `+0x20` 和高度处理，不是屏幕XY。wrapper arg4 实为 startup side/name owner-record；owner resolver按上段继续取 owner context。map startup path既不能代表 match-time外部线程合同，也未验证所有单位模板接受该路径。
- Body 构造器开头 request+0 被当作 pointer 解引用，后续复制模板列出的组件、写 Body+310组件表；Body+4 被解析器提取后作为创建上下文域之一，但其名义类型仍不明。组件部分失败、后期 factory setup 没有完整事务回滚。
- 两版位姿 helper的 disk disassembly复核与已有 note一致：1.13 `0x40CFC0/0x40C430/0x3D6A30`、1.12 `0x421FE0/0x421450/0x3EC240`（Coord3D*、yaw按值、矩阵指针）；位置是 world/engine-space，不含屏幕转换。
- 随地建造玩家路径审查完成但未找到安全移植点：1.13 StructurePlacementBehavior ctor RVA `0x30EBA0` 设两张接口表（VA `0xC2CF48/0xC2CE18`），已查非默认槽多为getter/默认实现而非 permission validator；AssistedPlacementInfoBehavior ctor `0x309880`、method `0x3098F0`（RET `0x10`）查 global hash table、遍历 stride `0x14` 记录并调用 template/component predicate `0x109C70`，唯一直接 CALL `0x63CCFA`，没有证据连到玩家 UI/command/free-build/radius permission。1.12 两组件对应 ctor/vtable 尚未独立配对。已知 PlacementGrid worker/iterator/retry 全为 AI candidate search 并含占格、碰撞和 16 项 footprint/bounds 检查；EA `0xE7565` 不可映射，也禁止以裸 `75 0C/EB 0C` 签名改分支。当前结论：玩家 permission站点尚未定位，保留验证/碰撞/bounds，不做跳过。

## Round 2 收口（以下结论优先于历史猜测）

- 确认地图开局 spawn wrapper RVA：1.13 `0x22E3E0`，1.12 `0x2440F0`，长度 304B。cdecl：`Body* spawn(unused, ObjectTemplate*, Coord3D*, Side/Player*, unused)`。第 1/5 参数全函数未读；位置是第 **3** 参数，不是历史 note 的 arg5。严格栈证据：entry ESP=S；局部0x3C+三个push后ESP=S-0x48，owner `[esp+0x58]`=S+0x10；再push EBP保留、angle helper RET4后ESP=S-0x4C，位置 `[esp+0x58]`=S+0xC，模板 `[esp+0x54]`=S+8。与 FINAL3 `(0,template,&pos,side,[side+10])` 调用合同一致（ignored slots 不必解引用旧 side+10）。
- 直接调用者仅两处/版：1.13 `0x22E64E/0x22EACD`、1.12 `0x24435E/0x2447DD`，均 push5/addESP0x14；都在地图开局 `Player_%d_Start` / `Player_%d_Rally` / `BASE_FLAG_%d` 流程。模板来自 side startup hash → global lookup（1.13 VA `0xCF0108`、helper RVA `0x40D5B0`）；位置来自 waypoint XYZ 并经 terrain manager 调整高度。可以否定历史“附近候选只是链表遍历”的一概判断，但不代表证明任意 match-time 外部请求安全。
- wrapper 调用 owner resolver、通用 factory、默认 yaw setter、Coord3D setter、模板属性查询、Body 激活/注册与可选 locomotor setup。null template 能安全早退；owner/position 未guard，必须有效；factory 自身 OOM 分支仍可能解引用null，后期 setup/组件失败未见完整rollback。不以外部WPF/remote thread调用；任何后续生产实现必须走游戏线程并校验当前match模板/side/manager存活。
- 新增 `tools/analysis/verify_spawn_wrapper.py`：双版本**全304B**精确指令+12相对call+manager全局匹配，每版18篡改拒绝；Unicorn 12 mock用例验证模板/位置/side参数读取、ignored参数、request blob构造、null模板/null工厂结果、callee保存寄存器及cdecl栈不清理、初始化调用顺序。全部通过；mock不验证真实构造/回调、可选locomotor分支、线程或游戏效果。
- 新增 `tools/analysis/inspect_creation.py` 只读磁盘，显示统一RVA并用rel32字节扫描列出factory每版55个candidate xref；避免整段linear disasm提前停止误报0个caller，也避免混用VA/RVA。
- 变换契约：request+14=engine-space三float位置，+18=float* radians yaw，+1C=48B矩阵优先；1.13 helpers `0x40CFC0/0x40C430/0x3D6A30` 配对1.12 `0x421FE0/0x421450/0x3EC240`。角度helper规范到(-π,π]，不能误称XYZ规范；request+8=28B opaque blob原样复制至Body+80..9B，不是栈局部。
- 随地建造：此前网格iterator向上链已由 `GetAIStructurePlacementLocation.cpp` 确认为AI候选放置搜索，不能当玩家permission bypass。下一玩家组件线索：1.13 StructurePlacementBehavior ctor `0x30EBA0` 设置VA方法表`0xC2CF48/0xC2CE18`，已查非默认槽为interface getter，不是validator；AssistedPlacementInfoBehavior ctor`0x309880`、方法`0x3098F0`遍历0x14字节记录并调用`0x109C70`。尚无安全FreeBuild branch；保留碰撞与bounds检查。
- 下一轮具体可实现方向：制作严格C# spawn API resolver（暂不自动安装）及fake-only mailbox/dispatcher回归；同时配对hash lookup与确认Body+4模板包装链、side→context；追玩家组件permission而非AI grid，坐标先复用选中目标world XYZ，不依赖鼠标转换。四功能仍未完成，保持目标active。

## v18f 离线静态续查（遵守不操作运行中游戏）

- 本轮只分析了磁盘上的 1.12/1.13 映像、现有脚本和源码；未附加、读取或写入运行中游戏，未模拟点击、调试或启停游戏。无意间查看到的进程清单信息不用于逆向，也未对该进程做任何操作。
- PlacementGrid 静态配对确认：网格 worker 1.13 RVA `0x111980` / 1.12 `0x128E20` 访问 `[this+0x24]` 网格，入口后调用 cell-test，再检查邻格和 16 个 footprint/bounds float 条件；返回小状态码（RET 0x14），属于**占格/放置验证**而不是创建对象。range iterator 1.13 `0x111C60` / 1.12 `0x129100` 对格子调用该 worker，允许时向虚回调传计算的 X/Y；唯一直接 caller 为 1.13 `0x4E8C26` / 1.12 `0x500848`。进一步向上追到 1.13 `0x4E8710` / 1.12 `0x500330` 的 5 次重试路径；其中 1.13 `0x4E87DB` 的源码字符串是 `GetAIStructurePlacementLocation.cpp`，确认这条 iterator/candidate 路径属于 **Skirmish AI 放置搜索**，不是玩家 FreeBuild/radius 权限。worker 的候选早期门是 `test eax,eax; je +0x17`（1.13 `0x1119CE-0x1119D0` / 1.12 `0x128E6E-0x128E70`），不是 EA Free Build `75 0C` 的直接等价；拒绝路径仍有 16 项边界检查，不能安全单点跳过。字节 `75 0C` 在 .text 中 1.12/1.13 分别约 1193/1173 命中，`EB 0C` 约 494/496 命中，裸签名不具辨识度。EA RVA `0xE7565` 在重打包版本也不等价。因此仍未找到可用的随地建造 production patch；下一静态方向是 StructurePlacementBehavior/AssistedPlacementInfo 的玩家组件虚函数表，而不是 AI 路径。
- Free Build script #12 `[MustCode+1201] db EB 0C` 的最合理静态读法：主脚本 `globalalloc(MustCode,0x3000)` 且 `MustCode+1200` 为 `mov eax,[game+E7565]; ret`，其机器码为 `A1 imm32`，imm32 正位于 +1201；因此脚本较可能解引用该 operand 再把 EA 地址 `0x4E7565` 的分支从 `75 0C` 改成 `EB 0C`。CE5.5 解析语义未用 CE parser 独立验证，故仍标 hypothesis；不能映射到重打包版。
- `GenericObjectCreationNugget.cpp` 源码名字符串 xref（1.13 `push 0xC29AE8`@`0x3E919E` / 1.12 `push 0xC27360`@`0x3FE24E`）位于较大调用者中，该调用者 RVA 约 1.13 `0x3E98F0`，不是早先误指的 `0x3E85C0`。1.13 `0x3E9E1D` 调真实 RVA `0x102410`（1.12 `0x11A210`），传入局部 request/descriptor；深入追踪表明这是强 Object/Body factory 候选，不是单纯 manager accessor：1.13 `0x10241F` push `0x4FC` 后调用 freelist 分配器 RVA `0x3062E0`，随后 push 1 / push request 并以 ECX=分配指针调用 constructor RVA `0x3EAF30`（1.12 `0x3FFFE0`）；constructor 在 1.13 `0x3EAF98` 写 Body 标签 `0xC57340`（1.12 `0xC54BB0`）并初始化字段/接口表。返回的对象具有组件列表 `+0x310`、Drawable `+0xF4`、HP `+0x33C`、XP `+0x3CC`、side `+0x418` 等布局。之后调用者写 `[result+0x418]` 并调用注册/初始化 helper；仍未完整确认 factory request 字段、生命周期/失败合同，不能连接生产。目标 `0x3E85C0`（近似配对 1.12 `0x3FD670`）反而是 8 个栈参数的 thiscall 处理函数：ECX=context、首栈参数来自 ESI/EDI，入口读 `[arg+0x308]` 等既有对象字段；三个直接调用者分别在 1.13 `0x3EA128/0x3EA167/0x3EA511` 与 1.12 `0x3FF1D8/0x3FF217/0x3FF5C1`，函数 epilogue `ret 0x20`，调用者不消费 EAX。更像更新/处理已有对象，不能当 CreateUnit。邻近 RVA `0x502420` 同样不构成新对象 factory 证据。
- factory constructor 的 request 至少 0x20 字节（当前只读静态推导）：`+0` 为必需 ObjectTemplate 指针（较早就解引用，晚期 null check 不能当保护）；`+4` owner/context（有全局 fallback）；`+8` 可选七 DWORD 初始化/变换数据；`+C` 注册/context ID；`+10` 写 Body+E4 的 metadata；`+14` 候选位置指针；`+18` 候选朝向 float*；`+1C` 候选完整变换，优先于 `+18`。位置/变换名义类型仍须进一步证明。constructor 从模板 `+194/+1A8/+1AC` 的组件记录数组构造 `Body+310` 的 null-terminated 组件列表并注册；部分组件失败不会统一回滚，后续可能在首个 null 截断；分配失败路径也未证明可安全拒绝。因此仅确认 factory 身份，不能暴露可调用 spawn API。
- 新工具 `tools/analysis/verify_object_factory.py` 只读磁盘确认两版 factory 指令、分配 0x4FC、三个 CALL edge、constructor Body tag，并逐版拒绝六种锚点篡改（通过）；`tools/analysis/verify_spawn_hashes.py` 只读 BIG4/XML 校验四个 hash 无歧义名称（通过）。均未调用 API 或安装钩子。
- 结论：旧 FINAL3 的 EA RVA `0x205240` 是参考脚本中唯一直接 CreateUnit 调用，但不是重打包版 1.12/1.13 的已配对 ABI。已识别的 generic factory 使用单 request 指针 + constructor thiscall，而非已确认的旧五栈参数入口。owner/template/position 名义类型、线程/manager 约束、对象生命周期和失败回滚仍未完整证实；复制/MCV/增援不能连接生产桥。随地建造属于另一条 placement permission 分支，不能假设 CreateUnit 成功即已解决。
- Free Build 脚本的更正见下方本节第 4 项：EA 老脚本更像通过指针把游戏 RVA `0xE7565` 的两字节分支 `75 0C` 改为 `EB 0C`；这仍不是当前两版本的已定位摆放限制站点。
- FINAL3 模板 hash 的离线名称映射已确认：`0x28DA574E`=`AlliedMCV`，`0xAF4C0DA5`=`SovietMCV`，`0x1C2EF767`=`JapanMCV`；WeNeedBack 默认 `0x6586A5A0`=`JapanCommandoTech1`（日本武士，不是基地车）。证据为 `Data/WBStringHashes.big` 的 `data\stringhashes.xml` 条目（偏移 `0x772300` / 7,807,744，长度 4,308,927），XML 原始行分别 6,935 / 29,831 / 4,815 / 17,146，后段存在重复记录。这只确认标识符，不证明生成 ABI/归属/合法性。
- FINAL3 动作契约仍有安全缺口：GetMeBase 将 `[ID]` 写入创建上下文后按 Allied/Soviet/Japan 顺序查询并生成；GetUnitData2 用 EAX=hash、ECX=`[game+0x8E6C58]` 调旧 EA `+0x3E4230`；CreateUnit 读取上下文 `+0x10` owner、位置指针与 template ECX，再调用旧 EA `+0x205240`，caller 清栈 `0x14`。位置 helper 读取 `[game+0x8DAEFC]` 的 `+0x3C/+0x40/+0x44`，调用旧 EA `+0x1ED4A0` 做鼠标到地图坐标转换，不是直接屏幕 XY。WeNeedBack 从 `iEnable+24` 取 hash 循环 8 次，并对结果直接调 `SetUnitState`/晋级，缺乏现代边界/有效性/所有权验证；Copy For Me 取旧全局 `0x8E9838` 做模板查询，只创建同模板对象，不复制生命/经验/武器等状态。三者均不能当成已准备好的安全现代参数合同。
- WBStatic manifest 新证据：未压缩 manifest 的 header 48 字节，LE@12=count=12123，记录每项 48 字节（12 个 LE uint32）；实例 hash 在 field1，name offset 在 field6，source offset 在 field7。name buffer base=48+count*48+header[32]+header[36]=`0xD7D51`，source buffer base=`0x1518E2`，末尾与文件大小 1,566,871 精确一致。记录 10969/11123/11282/11104 独立把 MCV/默认增援 hash 配到 `GameObject:AlliedMCV/JapanMCV/SovietMCV/JapanCommandoTech1` 及 `DATA:allied/units/alliedmcv.xml` / 对应 japan、soviet source。field0=`0x942FFF2D` 是共享 GameObject 资源类型，与旧笔记误称为类型 hash 的字段应区分；不代表每个单位都具有同一个实例 hash。下一步可核对记录 field8/9 与 bin/relo 的累计偏移，但含义尚未证明。
- request 变换字段已静态确认（1.13，双版本构造器相对调用可配对）：`+14` 是三浮点 Coord3D*，调用 `0x40CFC0`（RET4），写 Body 矩阵平移并同步缓存 `+38/+3C/+40`，随后触发变换通知；`+18` 是单 float* yaw/radians，调用 `0x40C430`（RET4），用 FSINCOS 构造方向矩阵并保留平移；`+1C` 是 12-float/48-byte 完整变换矩阵，调用 `0x3D6A30`（RET4），复制矩阵并从矩阵平移列导出缓存坐标/角度，优先于 `+18`，随后 `+14` 独立覆盖平移。位置契约因此不再是未知，但仍不能从外部安全构造 request，因为 template/owner/context、线程和部分失败生命周期未满足。
- request 变换 setters 和世界坐标含义双版本确认：1.13 `0x40CFC0` ↔ 1.12 `0x421FE0` 为 Coord3D* setter，写 Body translation matrix `[+0x14,+0x24,+0x34]` 与缓存 `[+0x38,+0x3C,+0x40]`，不是屏幕坐标转换；1.13 `0x40C430` ↔ 1.12 `0x421450` 接收标量 yaw/angle（调用者先解引用 request+18 的 float* 再按值传递），对当前方向矩阵做 FSINCOS；1.13 `0x3D6A30` ↔ 1.12 `0x3EC240` 收 12-float/48B 矩阵指针，从其平移列生成缓存坐标与角度。构造器顺序为 +1C full matrix 优先，若无则 +18 yaw，最后 +14 平移独立覆盖；全部 `thiscall ECX=Body, RET4`。这确认 Request 的变换表示和坐标是 engine-space，但没有说明鼠标 XY→world conversion。
- request+8 具体是可选 28B blob 指针：构造器在 `0x3EAF3D` 设置 EBP=Body，`0x3EAFD3` 设置 EDI=Body+0x80，`0x3EB456` 取得 request+8 的源指针，非空后 `rep movsd ECX=7` 原样复制到 Body+0x80..+0x9B；不是栈局部 staging。在构造器 `0x3EAF30..0x3EB7C5` 的静态扫描中未发现该区间的后续直接读取，不能排除虚调用/后续初始化或引擎使用；其目的语义尚未标名，不推测。request+0 模板为空会在 constructor 早段被解引用，硬性必需；不要依赖晚期 null test。组件按 ObjectTemplate 记录列表创建，单个 component 创建失败可能留下未完整 Body，未见原子 rollback。
- factory 1.13 `0x102410` / 1.12 `0x11A210` 的直接 E8 xref 各 55 处，广泛用于资源/对象生命周期，而非专用生成入口。1.13 `0x22E3E0` / 候选配对 1.12 `0x2440F0` 是更像 GameObject spawn 的 wrapper：签名是 caller-cleaned 五参数，模板在栈 `arg2`，owner/context 来自 `arg4`，位置来自 `arg3`（完整栈追踪确认，arg1/arg5 未读取）；内部构造单请求并调用通用 factory，再执行 angle/position setter、算 owner 相关属性和 locomotor/部署类 setup。这个 wrapper 在例 `0x22E451` 中返回 Body/null，但尚未证明足以匹配所有单位类型或可从 WPF 线程外调；失败后发现 Body 的某些 setup 校验失败并无 rollback。旧 FINAL3五参数与此 wrapper 有表面相似性，但参数1/3的真实语义、owner 来源、地图动作线程上下文仍未配对，禁止直接调用。
- 1.13 factory direct E8 xref 共 55 个，1.12 同样 55 个，大多数是对象/资源生命周期路径；无唯一 safe external spawn entry。
- 下一轮具体方向：追 factory request `+0` 的 ObjectTemplate 来源与包装类型（不能直接用 XP wrapper 推导即当相同类型）；确认 `0x22E451` 双版本对应函数是否是 GenericObjectCreationNugget 的高层路径；随地建造继续沿网格 caller 向上追建造权限与距离限制，保留碰撞/地图边界检查，不按短分支裸签名强改。
- BIG 归档离线解析：磁盘 BIG4 索引可直接读取（16 字节 header，条目为 BE offset/size + NUL ASCII 路径），不是加密；上述 XML payload 是直接 UTF-8 BOM 文本。Core `.manifest` 的 `10 FB` + 3-byte BE 解压长度是 EA RefPack/QFS 压缩，不是加密（例 Core12 `static.12.manifest` 压缩 457,537 字节，预期解压 `0x17E8AB`）。进一步 asset manifest/stream 分析可在内存解压后进行；本轮未提取归档文件，也未操作游戏。
- 离线回归（当前源码）通过：Release build 0 warning/0 error；hook bytes 42/42；selectiontest/actiontest 18/24/24 相应项通过；rank/capture/kill API 双版本解析与篡改拒绝、installer 132、asm 5；Unicorn 套件 197/218/8/60。语义反汇编测试曾因旧断言不识别威胁桩而失败，本轮已按实际指令语义更新并重跑通过。均为磁盘/合成对象验证，不是游戏实效证明。

## v18 研究（2026-10-11 /goal：四新功能依赖攻坚——重大进展但未完成）

### v18c 补充（第三局：机制疑团定位，需下会话收口）

- **同一进程内重开局（離開遭遇戰→再開始）后选中全局 0x8E4BFC 变死数据**：
  match2/3 的 root=0x4909920（同址、count 恒 0、守其页零事件零读取）——重开局不刷新该全局，
  真选中根在别处。match1（全新进程启动）时该全局是活的（矿节点点选 count=1 真实生效）。
  **结论：研究必须全新进程开局，绝不进程内重开局。**
- **点击选择疑团**：全部三局中，己方单位/建筑的点选从未生效（count=0），
  唯一中立矿节点可点选（match1 三点全中）。推测 D3D 代理转发的合成点击带某种
  观战/中立标志。**下会话试验：PostMessage 拖框选择（DOWN→MOVE→UP）走不同代码路径。**
- **PAGE_GUARD 机制状态**：OS 层生效（保护查询 0x104 ✓、远端写被挡 ✓、游戏不崩），
  但守"必写页"（选中根页/矿容器页/模板名页）全部零事件——因为 match2/3 里这些页
  本就是死数据（重开局后遗症）+ 矿量可能仅悬停显示时更新。**机制本身未在活数据上验证过，
  下会话在全新进程内用矿节点点选+守真选中根页做首次有效验证。**
- watch_guard.py / watch_spawn.py（WOW64 修正版）就绪；整局 UI 自动化坐标链完备
  （NOTES v18b）；败局教训（去 AI/先补电）已记录。
- 名字块 0xFEA8A68 在同进程多局间稳定（地图模板池复用堆分配）；生成不写模板数据页。

### v18b 补充（第二局自动化研究会话，被 AI 推平终止）

- **整局自动化打通**：steam://rungameid/17480 → 遭遇戰 → 開始 → MCV(560,470)选中→展开(1155,620)
  →反應爐(1165,300 排队→完成后点图标→放置 700,560)→兵營(1165,390→820,560)→征召兵(1165,295)。
- **败局教训**：电力 50/100 时生产被拖慢（队列堆 8 个不动）；无人防守基地 ~15 分钟被简单 AI
  推平。**研究局应去掉 AI（大厅删掉电脑玩家）避免败局**，且先补电再生产。
- **WOW64 实锤**：Wow64SetThreadContext 返回 TRUE 但 DR 回读全 0——**64 位 Python 对 32 位
  游戏硬件监视点彻底不可用**（系统忽略 DR 写入），非挂起问题。
- **PAGE_GUARD 替代方案**（watch_guard.py）：VirtualProtectEx+GUARD+TF 单步跨指令恢复。
  堆页保护成功（RW 页），机制事件链未验证完（守 0xFEA8000 模板名页 40s 零事件——
  生成不写模板数据页，**活体类型状态对象与模板数据分离**，上局的 wrapper+descriptor
  结构在本局未再现/未找到）。
- **本局堆布局差异**：side 对象地址会漂移（0x486FEE0→0x730BB0 两次读取不同），
  全堆 [+0x418]==side 扫描全为噪声；BFS 也找不到单位——**side 锚点不稳定是本局新问题**
  （上局稳定）。名字扫描定位征召兵模板数据块成功（0xFEA8A68，Name:/Type:/Desc: 三连）。
- 下局计划：**无 AI 观战局**（不会败）→ 先建电→兵营→兵；用"双击选同类型"选中征召兵
  （免去逐个盲点）；guard 选中根页验证机制 → guard 征召兵 tracker/wrapper 页在生成时抓写。

目标功能：随地建造/三阵营基地车/战场增援代码/复制选中。共同依赖 CreateUnit（EA 0x205240 重打包对应）。

### 已验证（活体，PID 49100 对局，游戏已关闭）

- **部队发现（无需点击）**：side=[playerRoot]+0x28 → BFS ≤3 跳（≤0x600/节点，≤4000 节点）
  → 所有 [obj+0x418]==side 且 +0x3CC 有效的对象=己方全部单位/建筑。实测 523 节点 25 个己方对象。
- **模板链（真单位验证 ✓）**：body+0x3CC→tracker；tracker+4→wrapper（同类型共享，征召兵×5 共享 0xFE7E6D0）；
  wrapper+0x14→template。模板前 ~0x300 内有完整定义串：
  `Name:SovietAntiInfantryInfantry` / `Type:` / `Desc:`（征召兵）、`SovietRefinery`（精炼厂）。
  **复制选中的模板提取已解决。**
- **wrapper 结构**（ThingTemplateCountMap）：+0=静态描述符指针（描述符=8 个函数指针+类型名串，
  征召兵在 0xC58BD0；方法[1]=0x80E640 读 template+0x94 用全局 RVA 0x8E21C0）；
  +4/+8=类型哈希（0x942FFF2D 等——与模板池条目哈希同族）；+0xC/+0x10=池指针；+0x14=template。
- **模板池条目**（矿节点样例）：名字串@条目+8（"auto_cp"）、哈希@+0x18、条目体@+0x30、template@体+0x14。
  → 基地车/增援可运行时扫池按名/哈希取模板（不需 lookup 函数）。
- **鼠标状态对象**：0x19323A0（int XY，随光标实时更新；光标差分法找到）。持有者未定位
  （仅 0x5D00744→+1 内部指针），疑为 D3D 代理层输入态。鼠标→世界坐标转换未找到。
- **分发表分析**（.rdaa RVA 0x7F6808，63×13 槽，281 去重处理器）：跨处理器调用频度 TOP 全是
  运行时基础设施（0x4169C0=free、0x4CB350=release 等），未暴露 spawn。
- **硬件监视点追踪器已就绪**（tools/analysis/watch_spawn.py）：附加调试器→58-62 线程设
  DR 写监视→泵事件→干净脱离（4 次运行零事故）。**关键坑已修：64 位 Python 调试 32 位游戏
  必须用 Wow64Get/SetThreadContext**（普通版本写的是 64 位上下文，DR 永不生效）。
  修正后机制验证被游戏退出打断——下轮先盯鼠标 X（0x19323A0，动光标必触发）验证回路，
  再盯 wrapper 计数字段（候选 +0x2C/+0x34/+0x38/+0x3C 区）+ 排征召兵抓 spawn 写点 →
  栈内 .text 返回地址即 CreateUnit 调用链。

### 死路（勿重复）

- vtable 0xC57340（单位 body 首 dword）=类型标签非 vtable，构造器不写它。
- EA CreateUnit 窗口插值（≈0x22F000）扫 cdecl-5arg 调用点：仅 1 命中且是链表遍历。
- proto_cool_a/b 是 vtable 访问器 thunk，.text 零引用（仅 vtable 挂载）。
- 磁盘无 EA 原版二进制（Steam 全 1.0-1.13 均重打包）→ 无法提取 EA CreateUnit 字节做 AOB。
- 字典根全局：.data 两跳可达性搜索 3 候选零代码引用（字典走共享 wrapper，根全局路线放弃）。

### 下轮计划（按优先级）

1. 开对局 → watch_spawn.py（WOW64 修正版）机制验证（鼠标X）→ 盯 wrapper 计数 →
   排兵触发 → 抓 #DB EIP+调用栈 → 定位 CreateUnit → SpawnDispatcher 第四桥
   （模板+side+位置，位置先用选中单位坐标，绕开鼠标世界坐标）。
2. 基地车×3：扫模板池名字（MCV 族：SovietMCV/AlliedMCV/JapanMCV 待确认实际命名）。
3. 增援代码：UI 输入哈希 → 扫池条目哈希 → 模板 → spawn。
4. 随地建造：未移植。静态复核 FINAL3 `script_12` 的 `[MustCode+1201]: db EB 0C` / disable `75 0C`，与主脚本 `MustCode+1200` 的 `mov eax,[ra3+E7565]; ret` 配合，较可能是通过该指针把 EA RVA `0xE7565` 的短条件跳转改为无条件跳转；旧注“改自身 MustCode 双字节”不可靠。CE5.5 间接地址语法及该分支的摆放语义仍待确认；即使 EA 语义成立，也不能迁移旧 RVA，必须在重打包 1.12/1.13 的磁盘映像中独立定位并交叉验证摆放限制路径后再考虑实现。

## v17（2026-10-11 /goal 续：实测反馈修复 + 俘虏/摧毁桥 + 矿脉动作化）

- **实测确认**：晋级桥在真实对局中生效（用户报告：提高选中单位经验成功）。
  v16 矿脉开关也曾实际生效（矿量被回满到 100000 的痕迹在活体调研中观察到）。
- **修复：框选多单位只升一个**——SubmitBridgeRequests 循环提交全部目标
  （每目标限 800ms 等资金结算消费，总预算 4s；未消费/拒绝/待续均有计数反馈）。
- **矿脉动作化**（用户要求"恢复选中的矿脉"）：移除 oremine 钩子与开关，
  改为动作 oreminerestore。活体验证链：body+0x398→采集状态C，[C+4]→容器O，
  [O+8]=矿量、[C+0x14]=已采（与 FINAL3 矿量访问器语义一致）。BFS(≤2跳/64节点)
  清零所有指向该容器的采集状态并回填 100000。
- **俘虏桥（v17 新）**：CaptureApiResolver 严格校验归属切换函数
  （1.13 RVA 0x3B5DF0 / 1.12 0x3CBF50；prologue 19B + 双 helper call 0x2FDBC0/0x166340 +
  playerRoot 全局 + RET8@+0x285 四锚点，双版本 + 篡改拒绝全过）。
  CaptureDispatcher（块+0x1300，邮箱 0x1840）：认领后校验选中位/互指/属主≠己方/
  本地 context 链 [[side+AC]+4]→+8==side，然后 game-thread 调用
  transition(Body, [side+0xAC], 0)；成功判据=属主变为己方。
- **摧毁桥（v17 新）**：KillApiResolver 校验 HP adjust（1.13 0x38CB30/1.12 0x3A3650，
  入口 0x24 字节双版本一致 + RET8）。KillDispatcher（块+0x1400，邮箱 0x1880）：
  调 adjust(hp, -3.4e38f, null) 走完整钳制+死亡通知；成功判据=[hp+4]==0。
  这是 EA+39EA50（未配对）的现代重推导。
- 资金桥前 CALL 现在按启用情况串行调用最多三个派发器（rank→capture→kill）。
  开关：rank-bridge.enable（晋级）/ bridges.enable（俘虏+摧毁），环境变量
  RA3MT_RANK_BRIDGE / RA3MT_BRIDGES 等效。publish-v17 已带两个标记文件。
- 工程教训：disp8 装不下 0xAC；FXSAVE 需 16 对齐（垫字节要在 fxsave 之后）；
  被调函数可打爆所有 GPR——call 后必须从邮箱重载指针（rank 桩原有设计，照抄）。
- 验证：42/42 站点、bridgetest（3 API×双版本+篡改拒绝+17 邮箱例）、
  新 test_bridge_dispatchers.py 60 例、其余全套（197/218/8/24/132/…）全绿。
  发布 publish-v17。**俘虏/摧毁/多目标晋级/矿脉动作均未实战复测。**
- FINAL3 剩余四功能（随地建造/给基地车×3/战场增援代码/复制选中）依赖未定位：
  模板字典（EA 0x8E6C58+0x3E4230）、造单位（EA 0x205240）、鼠标地图坐标
  （EA 0x8DAEFC+0x1ED4A0）。无 EA 二进制可比对，需活体调用链追踪或
  从已锚定函数的交叉引用推导；三桥模式（严格校验+邮箱+游戏线程）已就绪可复用。

## v16（2026-10-11 /goal 会话：FINAL3 全量对照审计 + 矿脉移植 + 6 站点定位）

- **docs/FINAL3_CROSSREF.md**：FINAL3 全部 22 站点/13 分派动作 ↔ Final2a ↔ RA3MT 的完整对照
  审计表（验证等级 L1-L4）、7 条误分类校正、不可安全移植清单、未实测清单。
- 本轮定位（locate_final3_sites.py，唯一命中 + 运行中 1.13 进程字节比对 ✓）：
  矿脉 EA 0x2D4933 → 1.12 0x312EB3 / 1.13 0x2FDBB3（**勘误：旧 NOTES 此站点误标 fast_build**）；
  敌方禁产 EA 0x30F530 → 1.12 0x34D920 / 1.13 0x3387D0（[eax+0xC] 属主语义待活体验证再移植）。
- 无敌/一击必杀：EA 字节序列在重打包中不存在 → 从 HP adjust（1.13 0x38CB30/1.12 0x3A3650，
  双版本逐指令一致）的血量写点 0x38CB4E/0x3A366E 重设计（写点字节活体确认 F30F114604）；
  EA OneKillData/Data2 三点捕获链（1.13 0x427B34/0x30B6C3 候选）不再需要。
- v16 移植矿脉：oremine 桩（持续回满 100000+清已采，flag 0x0F）+ 功能开关 + Unicorn 4 例。
  站点 44/44，桩执行 201 例，actiontest24/installertest138 全过。发布 publish-v16。
- 下一步优先级：①用户实战复测（v15/v16 全部未实测功能，晋级桥需 RA3MT_RANK_BRIDGE=1）；
  ②敌方禁产属主字段活体验证；③无敌/一击必杀在 adjust 写点的重设计桩；
  ④摧毁函数（EA+39EA50）配对定位；⑤俘虏复用晋级桥模式。

## v15（2026-10-11 接手会话：威胁等级落地 + 晋级桥接入生产）

- 威胁等级完成（sol 半成品收尾）：Ammo 桩条件写入 [分量+8]=50000(threatmax 0x0D)/0(threatzero 0x0E)，
  同开最大优先；features 21/22/23 → 开关/开关/动作(threatnormal=双关，FINAL3 不保存旧值)。
  Unicorn ammo 矩阵 6站点×组件×标志 = 48 例，桩执行套件增至 197 例。
- 晋级桥接入生产：环境变量 RA3MT_RANK_BRIDGE=1 显式开启（TrainerEngine.EnableRankBridge），
  附加时 RankApiResolver 严格校验（99字节签名+context全局+两个helper call 目标），
  通过才以 rankApi 构造 MasterCode（装消费桩 0x1200 + 邮箱 0x1800 + 资金桩前 CALL 桥）；
  校验失败降级默认资金桩并告警。sel_lv 在桥激活时走邮箱路径（EnumerateRankTargets 同
  消费桩校验门；单未决请求，一次触发提交一个目标，资金结算时游戏线程执行）。
- test_rank_money_bridge.py 两处断言修正（测试自身 bug，dispatcher 行为与其 218 例套件一致）：
  ① 认领尝试无条件发生，断言改为 claims==[state]（每次结算恰好一次、观察到提交态）；
  ② state=1 被校验拒绝的终态是 4 不是原 state。
- 清理 SelfCheck 死 stackalloc（发布构建 0 警告）。发布 publish-v15（自包含单文件 x86）。
- 仍然未做：全量实战复测（威胁/缩放方向/速度/生命/弹药/立即就绪/晋级桥——本版全部仅离线验证）；
  xp999 仍 pending（桥稳定后可由其驱动）；俘虏/摧毁/矿脉未动。

## FINAL3补充勘误（优先于下文历史）

新主要参考见 docs/FINAL3_ANALYSIS.md 与 artifacts/final3/script_00_0008D05B.cea。
FINAL3明确定义NormalHP为读取健康组件+10，恢复当前+4与有效上限+C；
这是撤销生命上限作弊，不是仅治疗，不能将此原版语义误判为字段错误。
v13恢复NormalHP原意，并新增独立heal动作只回填当前有效+C，保留原上限。
actiontest现13例分别验证两种写入范围、非法float和禁用动作拒绝。
FINAL3三参数晋级对应已配对：1.13 VA0x785600/RVA0x385600，1.12 VA0x79A840/RVA0x39A840。
99字节函数RET0xC，参数1为正晋级增量次数；原push0/1/3最多尝试3次而非绝对等级3。
两个helper模拟的Unicorn160例验证配对字节、参数顺序、栈清理与循环提前停止，详见rank_pair.json。
尚未接入游戏线程请求桥，不以自然经验刷新RET4函数0x705F60代替。
v14将协议点数由99改为FINAL3的15，速度操作对应500/10/0/恢复；
备份仅在本会话且模板和最近写入速度仍一致时恢复，游戏已改变值则拒绝覆盖。
构建0警告/0错误，actiontest24例、现有桩执行161例通过；无实机注入或效果验证。

## 此前勘误与修复（与上节矛盾时以上节为准）

历史会话中的推测并不可靠，尤其是选中列表、玩家锚点、经验与弹药的定性。
本轮只读实机检查 PID 43776，加上双版本反汇编，确认以下结论：

- 真正选中全局 RVA：1.12 `0x8E08DC`，1.13 `0x8E4BFC`。
  root+0x50 为循环链表哨兵，root+0x5C 为计数；node+8 为 Drawable，
  Drawable+0x138 为 Body。Drawable+0x13D 的 bit 0x40 为选中标志，Body+0xF4 反向指回 Drawable。
  已替换 SelectionActions 的临时 UI 捕获机制，加入计数/循环/反向引用/变化校验。
- 本地阵营上下文全局 RVA：1.12 `0x8EDE2C`，1.13 `0x8F214C`；[root]+0x28 为阵营对象。
  旧 money_h1.esi+0x1188 锚点会取到 vtable，不能用于归属检查。
- 协议冷却 HpA 站点在游戏查找匹配节点之前；必须按 node+8 的协议键查询，
  只能改匹配节点+0xC 截止时刻，不能修改首节点或哨兵。
  JMP 没有旧 CALL 的额外返回地址，保存属主栈槽应为 pushfd/pushad 后 esp+0x28。
  已加入 4096 节点搜索上限；立即就绪设置截止时刻为当前游戏时钟。
- BuildPower 在钩子之前缓存 EDI 冷却截止值；修改内存后必须重新加载 EDI。
  无属主判定的 HpB/Sidebar 增量写入已移除，避免冻结本地或无关记录。
- 缩放桩旧 push 0/popfd 实际清除 ZF，与 JE 绕过钳制的需求相反。
  已改为保存的 EFLAGS OR 0x40 后 popfd，保留其他标志。
- zoom_unit_xp 遍历的是 Weapon：Weapon+8->WeaponSlot，slot+0x10->Body。
  Weapon+0x1C 是弹夹数量，不是经验！旧 xp999 写入已移除，该功能暂不可用。
- 旧六个 ammo 站点读取 Body+0x1278 的 RedAlert 威胁组件，+8 是威胁值。
  已停止错误50000写入；v9改用真实Weapon开火扣弹站点（见下）。
  真弹药链候选：Body+0x37C WeaponSetUpdate，+0x34/+0x38 为武器数组 begin/end，
  Weapon+0x1C 当前弹夹，[[Weapon+4]+4]+0x70 容量；未完成开火持续性测试。
  弹药调查补充：1.13 VA 0x7E7200 为 reload，0x7E724D/0x7E7302 写容量到 Weapon+0x1C，
  增加时调用0x727AB0通知；0x727AA0仅返回类型名称常量。
  勘误：前次代理递减候选的版本地址对调。当前1.13 VA 0x7DABAD 才是
  83 43 1C FF 83 7B 1C 00，0x7EFFDD 实为6A 01 57 E8...调用序列。
  0x7DABAD 周围用 EBX-0x2C 子对象、EBX+0x24 时间链表，递减归零后按游戏时间重设计数，
  不能证明是Weapon弹夹，已排除直接挂钩。
  真消耗已确认：1.13函数VA0x7B9020，1.12函数VA0x7CF120，entry ECX->ESI 为Weapon，
  两个发射分支汇合到1.13 RVA0x3B9171 / 1.12 RVA0x3CF271，
  重放6字节83 C8 FF 01 46 1C（OR EAX,-1；ADD [ESI+1C],EAX），15字节AOB双版本唯一。
  v9桩先重放真实扣弹，保存全部寄存器/算术标志，再仅对本地且Drawable选中bit40的武器
  回填已解析的弹夹容量（正值且<=100万），不修改+24/+2C连发计数。
  owner链采用前次活体确认Weapon+8->slot+10->Body；Body+F4为Drawable。
  已空弹时前置guard阻止进入开火钩子，需正常装填一次，不声称解除任何装填/射击间隔。
  双版本挂钩42/42；Unicorn148执行用例通过，容量边界与本地/选中组合覆盖。
  尚未由代理进行实战连续开火复测。
  新增 tools/analysis/inspect_selection.py，只以VM_READ|QUERY打开自动发现的当前游戏，
  输出选中Body/生命/经验rank/当前Locomotor速度上限/Weapon弹夹容量JSON，
  使用标准ctypes显式Win32签名，关闭快照与进程句柄，无游戏内存写入。
  本机运行成功返回PID35440、1.13、selectionCount0；单选详细输出仍待下一次目标选中。
- 真经验组件 Body+0x3CC 的 +0xC 为经验浮点值，+0x24 为等级。
  直接写经验不会立即晋级，游戏 setter 1.13 VA 0x76E080 会调用 0x705F60 刷新。
  当前经验动作只声称设置经验，立即三星暂禁用。
  增加setter同款晋级资格检查：tracker+4->wrapper+0x14->template，byte+0x245非零。
  自然award函数1.13 VA0x76DF90，在0x76E06D写XP后0x76E072调用0x705F60；
  该路径仅在奖励经验事件发生，不是每帧callback，不能作为可靠立即晋级实现。
  未实现任意远程线程调用游戏setter，避免绕开游戏线程/锁的要求。
  弹药Unicorn回归扩展到155例，7条缺失slot/body/drawable/controller/side/template链均不回填。
  v10包含经验资格检查；selectiontest扩展到13项，新增支持/不支持晋级与缺组件/模板4例。
  发布构建通过，无游戏写入，实战效果仍待复测。
- 移动组件+0x1FC 是嵌入 vector 的 vtable，不得解引用后写游戏代码！
  begin/end 为 +0x200/+0x204；当前模式实例为 AI+0x21C，实例+8 为基础速度。
  已按双版本 getter（1.13 VA 0x77EC70 / 1.12 VA 0x793E90）证据改为操作当前实例，
  第二组动作操作当前 LocomotorSet 全部实例，而非固定第二项。
  +0x238 是懒生成的18模式聚合集，不是当前模式备份，不能用于持久修改。
  实例+0x20 是游戏可更新的减速上限，修改动作保留它，不能统一恢复到构造默认99999。
  编队速度 query3 可覆盖基础速度；模式重建会销毁实例，一次性冻结不能声称持久生效。
  effective speed 1.13 VA 0x785D10 / 1.12 VA 0x79AF00，分配 ctor 0x73E3D0/0x753550，
  实例0xC4字节，+4模板/+8基础速度/+20上限一致；无跨单位共享模板写入。
  selectiontest 扩展为9项，包括当前实例非第一项、集合去重、空数组和异常边界。
- 生命勘误：HP+4当前，HP+8前值，HP+0xC有效最大生命（比例分母），+0x10基准最大生命。
  ratio getter1.13 VA0x6FEEA0 /1.12 VA0x714140使用+4/+C，+C不是显示当前生命。
  hpnormal现只写当前值为有效+C，不覆盖上限；拒绝NaN/Inf/非正上限。
  adjust vtable+0x94：1.13 VA0x78CB30 /1.12 VA0x7A3650，thiscall(delta, nullableContext)RET8，
  更新前值/当前、钳制上限、行为回调并调用死亡状态通知0x7513F0/0x765C90。
  通知设置Body+0x471 bit0及其他死亡流程，直接HP+4=0绕过这些副作用，故v12禁用摧毁动作。
  factor setter+0x80=0x6FEDB0/0x714040；max setter+0x84=0x6FEDF0/0x714080，均走adjust回调。
  当前其他生命动作仍是实验性直接数值写入，不能宣称行为/死亡状态完整刷新。
  选中动作写前重新验证Body+F4<->Drawable+138与选中位；selectiontest扩展18例，
  拒绝提前哨兵（count比链长大）及枚举中计数改变。
  SelectionActions复用IInjectionMemory，actiontest8例实际断言写入范围：
  有效+C恢复仅写+4、保留基准+10；NaN/Inf/非正上限无写入；取消选择无写入；
  capture/destroy拒绝无写入。假内存测试不证明游戏行为回调。
- 俘虏必须走完整归属切换流程，已禁止仅覆盖 Body+0x418。
  新归属切换候选commit：1.12 RVA0x3CC0D8 / 1.13 RVA0x3B5F78，
  MOV [ESI+0x418],EDI 后 MOV [ESI+0x414],EBP，前后有旧属主判断、管理器与通知调用，RET8。
  新EDI从EBP相关结构或controller+0x30解析；参数/入口与捕获调用上下文尚未完整证明。
  inspected slice起点1.12 RVA0x3CBF58 / 1.13 RVA0x3B5DF8在函数内部，不是已证明入口。
  EBP与旧Body+0x414比较并替换该字段，EDI为解析出的Body+0x418；
  后续已证明完整入口：1.13 RVA0x3B5DF0 / 1.12 RVA0x3CBF50，前有CC边界，
  函数长0x288，RET8位于RVA0x3B6075/0x3CC1D5。
  prologue PUSH ECX; PUSH EBP; MOV EBP,[ESP+0xC]; PUSH ESI; MOV ESI,ECX：
  ECX=Body，第1参数entryESP+4是写入Body+0x414的可空指针，第2参数entryESP+8低字节bool。
  helper1.13RVA0x2FDBC0 /1.12RVA0x166340返回[[arg1+4]+8]派生owner，
  owner无效或arg1空回退controller+0x30；同旧+414直接返回。
  +414指针名义类型仍未完全证明，不用于远程调用。
  调用者追踪：1.13 VA0x7C6710正常wrapper调用0x7B5DF0（arg2=0），
  序列化0x7B7C0A传arg2=1；1.12正常wrapper0x7DC370、序列化0x7CDD6A。
  实际capture组件0x7E5870调用captor Body的getter0x7073F0，结果传0x7D6D40(target,newContext)。
  getter返回Body+414（其+1F8非零）或owner+AC默认context；默认本地context=[localSide+AC]，
  应验证[[context+4]+8]==localSide。调用为游戏组件同步路径，仍缺外部动作的安全游戏线程队列。
  不能只跳到commit位置，不能以不明线程的远程调用冒充完整俘虏功能；下轮核实契约。
- UI 附加/脱离共用按钮已改为双向命令，修复附加后脱离按钮禁用。

验证：双版本 40/40 挂钩字节通过；selectiontest 5 项通过；
C# 桩导出 + capstone 编码/跳转检查通过；新选中链只读实机解析 1 个单位通过。
新增 Unicorn x86 执行回归 `tools/harness/test_execution_stubs.py`：100 个用例通过，
覆盖本地/非本地、开关组合、空上下文、协议匹配/缺失/空表/异常循环，
断言只修改匹配节点且哨兵与不匹配记录不变；校验栈/寄存器/EFLAGS 恢复、
缩放 ZF、UI 武器 TEST 的空路径、六个威胁访问器无写入及两个冷却谓词纯重放。
这是合成对象执行测试，不代替实际游戏效果验证。
运行命令：先 `dotnet run --project src/RA3MT.SelfCheck -c Release -- stubdump artifacts/stubs_semantic`，
再 `py tools/harness/test_execution_stubs.py`（依赖 unicorn 2.1.4）。
新增 Asm rel8 范围与未定义标签拒绝检查，`SelfCheck asmtest` 5 个边界用例通过；
当前 20 桩按 16 字节对齐后的末端为 0x3B0，小于捕获数据起点 0xFFC。
Install 同步加入桩区/捕获区重叠拒绝检查。
v11注入防护：附加要求全部21站点通过校验，不允许缺关键站点仍显示就绪。
取消仅凭原始短字节/最近兄弟距离猜测重定位，只保留精确RVA或唯一上下文AOB。
SelfCheck resolvertest4例覆盖原始字节拒绝、唯一特征通过、多候选拒绝和精确RVA通过。
ProcessMemory检查实际写入长度及FlushInstructionCache结果。
安装先写全量桩，再写跳板；写跳板前记录原始字节，以覆盖短写/刷新失败的回滚。
附加失败尝试逆序恢复所有已记录站点，卸载逐点尝试并保留失败条目用于重试，
卸载失败不再报告全部已还原。附加回滚失败保留内存句柄和MasterCode恢复记录，
RecoveryRequired禁用全部功能/动作并保留脱离重试入口，UI明确显示恢复失败；
重试仍失败时要求用户重启游戏。线程并发patch风险未完全解决。
新增IInjectionMemory窄接口用于InstallerChecks假内存故障注入，不改变生产Win32调用。
SelfCheck installertest132例通过：所有43写入点的写前/部分写后/完整写后失败129例，
加3个卸载首/中/尾故障、逆序全量尝试、只重试残留、原始字节恢复断言。
这是安装器离线故障测试；未对当前游戏注入错误，未证明Win32系统调用故障或线程安全。
TrainerEngine附加回滚失败的UI/句柄保留路径仍未以假native端到端测试。
发布 v8 包含当前 Locomotor 基础速度操作与真实选中数量诊断，
发布构建0警告/0错误，9项选中/移动容器回归及100项x86执行回归通过。
本轮过程中用户已重启游戏，当前 PID 为35440（此前43776已退出），
只读检查选中计数为0，禁止复用前局堆地址。新版仍未由代理执行实战操作。
未向正在运行的游戏注入本轮代码，未执行生命/摧毁等破坏性动作。
所以协议/缩放、速度、生命动作的实战效果仍须复测；冻结敌方包含所有非本地阵营（包括盟友）。
下文历史记录保留供溯源，但与本节矛盾时以本节为准。


日期：2026-10-10。前置分析见 `D:\RA3TrainerWork\NOTES.md`（EA 原版 1.12 的老修改器分析）。

## 关键发现：重打包版 ≠ EA 原版

老修改器（Ken22265 Final.2a）的脚本是针对 **EA 官方 1.12** 的绝对地址。
本机 Steam 库里的 `ra3_1.12.game` / `ra3_1.13.game` 是 2024 终极合集**重打包版**，
代码有**区域性偏移**（非全局常数，也不同符号）：

| 区域 | EA 1.12 锚点 | 重打包 1.12 偏移 | 重打包 1.13 偏移 |
|---|---|---|---|
| zoom/xp 函数 | 0x128735 | +0x41650 | +0x299E0 |
| 建造进度区 | 0x2D4933~0x30F42E | +0x3E3B0~+0x3E580 | +0x291B0~+0x292A0 |
| 资金函数区 | 0x6CFD0D~0x6CFEB5 | **-0x6AF60**（被搬到别处） | -0x66430 |
| 单位/弹药/血量区 | 0x3C226C~0x43ECA6 | +0x3DF70~+0x3E350 | +0x292A0~+0x29430 |
| power_cool | 0x1EC7CD | +0x3F060 | +0x2A4B0 |

同函数内部相对距离在重打包中保持不变（资金链 h1→h2→h3→h4 的 +0xF1/+0x6E/+0x49 完全一致），
跨函数距离不可靠 → 用「多锚点距离插值 + 字节相似度」定位。

## 定位方法（tools/analysis/）

1. **find_true_sites.py**：老脚本 [DISABLE] 段记录了每个钩子被替换的原始指令 →
   在重打包 1.12 上字节搜索 = 真实站点（16 个中 10 个唯一命中）。
2. **fix_stragglers.py / final_resolver.py / final_clean.py**：
   - 同函数兄弟点位距离预测（money_h3/build_hp_a）
   - 站点后继上下文锁定（power_cool：`movss [esi+44],xmm0` 后跟 `je`，且 [esi+26fc] 虚调用）
   - 多锚点插值裁决歧义候选（power/ammo/build_power）
3. **gen_features.py**：跨版本 AOB（E8/E9 rel32、0F8x rel32、映像地址 imm32 掩码）。

## 最终挂钩点表（详见 assets/features.json）

| id | 1.12 RVA | 1.13 RVA | 被替换字节 | 功能 |
|---|---|---|---|---|
| zoom_unit_xp | 0x169D85 | 0x152115 | 8B 0C BA 85 C9 | 选中单位经验999（+无敌视口迭代） |
| power_cool | 0x22B82D | 0x216C7D | F3 0F 11 46 44 | 技能零冷却（je 分支控制） |
| fast_build | 0x312EB3 | 0x2FDBB3 | 8B 40 08 2B 41 14 | 瞬间完成生产 |
| build_power | 0x329F19 | 0x314D19 | 8B 98 18 04 00 00 | 秒就绪/冻结敌方 |
| power | 0x33511F | 0x31FEDF | D9 86 BC 01 00 00 | 快速建造不断电 |
| sidebar_pts | 0x348A06 | 0x333886 | 8B 48 50 3B 4E 20 | 冻结敌方侧栏 |
| proto_cool_a | 0x34D77C | 0x33862C | D9 46 1C 89 46 5C | 快速建造 |
| proto_cool_b | 0x34D81E | 0x3386CE | F3 0F 2C 46 1C | 快速建造 |
| unit_lv | 0x4005BC | 0x3EB50C | F3 0F 11 85 60 02 00 00 | 地图全开 |
| ammo | 0x4770B0 | 0x462300 | 8B 81 78 12 00 00 | 无限弹药 |
| build_hp_a | 0x47CB89 | 0x467FC9 | 8B 70 50 8B 01 | 秒就绪/冻结（栈槽 [esp+8]） |
| build_hp_b | 0x47CC16 | 0x468056 | 8B 51 50 3B 50 0C | 冻结 |
| money_h1 | 0x664DAD | 0x6698DD | 8B 40 04 8B 8E B0 03 00 00 | 无限电力 |
| money_h2 | 0x664E9E | 0x6699CE | 03 78 04 8B 11 | 无限资金 |
| money_h3 | 0x664F0C | 0x669A3C | 8B 78 34 8B 4E 3C | 协议点数 |
| money_h4 | 0x664F55 | 0x669A85 | F3 0F 10 47 2C | 解锁协议 |

## 新解出的全局（老修改器未公开的部分）

- **选中单位列表**：`[root]`，root 全局 1.12 RVA `0x8E0940` / 1.13 `0x8E4C60`。
  `[root+4]`=begin、`[root+8]`=end（vector of 选中条目）；条目 `+8` → `+0x138` → 单位对象。
  发现途径：zoom/xp 函数头 `mov eax,[0xCE0940]; ... test eax,eax` 的字节签名跨版本唯一。
- **玩家上下文 root**：1.12 `0x8DDE84` / 1.13 `0x8E21A4`；`[root+0x28]` = 本地玩家索引。
  发现途径：全 .text 扫描 `mov reg,[root]; mov reg2,[reg+28]` 模式，两版各恰好 1 处。
  root 还被 3331 处引用（电力 [x+0x1BC]、资金对象 [x+0x3B0] 等走它）。

## 桩设计（src/RA3MT.Core/Engine/MasterCode.cs）

- E9 跳板 + 桩内 `pushfd/popfd` 保护标志位（原版用 call 天然保标志，我们的 jmp 结构必须手动保护）
- **两个例外**（游戏站点后续指令消费 ZF，故意让桩控制标志）：
  - `power_cool`：`movss [esi+44],xmm0` 后是 `je` → 桩以 `cmp [flag],1` 设置 ZF；
    开=ZF1（popf 0），关=popfd 还原
  - `zoom_unit_xp`：`test ecx,ecx` 后是 `je` → 桩重放后 pushfd/popfd 还原 test 的 ZF
- `build_hp_a` 的属主比较用 `[esp+0x2C]`（pushfd+pushad 后 = 原始 esp+8 的游戏栈槽）——
  沿用原版脚本，**需进游戏验证该槽在重打包版中语义一致**

## 待办（下次会话）

1. **进游戏实测**：资金+10万、电力、快速建造、地图全开、经验999、弹药 —— 逐个开关验证；
   任何崩溃先检查 SelfCheck 输出与附加日志。
2. `build_hp_a` 栈槽 [esp+8] 验证：秒就绪/冻结敌方两功能依赖它。
3. 威胁等级 ×3 与矿脉恢复：需在游戏运行时搜索（老版走 TMK freezer 表，逻辑未完全还原）。
4. 老版[08]「无限缩放」与新[08]「技能零冷却」共用 power_cool 站点——实测确认语义后改名。
5. UI 热键冲突检查（Ctrl+P 等在游戏内是否被吞）；考虑加"启动修改器"一次性确认按钮（老版 Ctrl+`）。


---

# 2026-10-10 实测与诊断会话补充

## 已证实
- 机制层全部工作：附加/防呆/20 桩/标志开关（快速建造生效即为证明）。
- **弹药簇**：两版本各 6 个同源 thunk（1/6/1/1/1/1 调用者分布），老版钩的是 6-caller 主 thunk
  （1.12=0x477090 / 1.13=0x4622E0）。现全部 6 点挂钩（features.json: ammo + ammo_2..6）。
- **power_cool 站点 = 老版[08]无限缩放**（相机对象上下文），不是技能冷却。已改名 zoomlimit。
- **玩家对象**：资金钩 (money_h1) 运行时的 esi = 真实玩家上下文（vtable 0xC81A40，
  [esi+0x3B0]→资金对象→+4=资金值 ✓）。诊断槽 DiagPlayerEsi 持续捕获它。
- **root 全局 (0x8DDE84/0x8E21A4) 的 [root+0x28] 不是本地玩家索引**（对局中恒 0）——
  instantready/freezeenemy/capture 的敌我判定需要换锚点（用 DiagPlayerEsi 的 esi）。
- **0x8E0940/0x8E4C60 不是选中列表**（原定性错误）：节点内容与选中无关（+0xC 恒 0x56626220），
  是常驻对象列表；zoom_unit_xp 钩子的"类型2过滤"遍历的是它。
- **unit body 候选**（真实单位，+33C→血量对象 +4/+C/+10 浮点）在 entry BFS 可达范围外 3+ 跳，
  未找到 entry→body 短链。body+0x418 在重打包版疑似为属主**对象指针**（多单位共享同一值），
  不再是老版的属主索引。

## 诊断桩布局（MasterCode 块，数据区 0x10..0x2C，桩区 0x40 起）
+0x10 money_h1.esi（玩家） | +0x14/+0x18 build_power.eax/esi | +0x1C [eax+0x418]
+0x20/+0x24/+0x28 zoom 的 ecx/edx/edi
⚠ 数据区严禁越过 0x40（Install 有断言）；曾因写在 0x40 覆盖桩代码导致选中即闪退（已修）。

## 下次会话计划
1. **选中链正攻**：trace 点击→selectObject 调用链（UI 命令处理），或对 [player+X] 结构做
   选择/取消差异扫描；拿到 entry→body 后重写 SelectionActions 的 10 项。
2. **立即就绪/冻结敌方**：让用户排队生产后点诊断（captured eax≠0），验证 [eax+418] 与 [esi+20]
   语义；敌我判定改用 DiagPlayerEsi。
3. **无限缩放**：A/B 分支方向实测（当前=ON 时强制 je 成立，与老版 13/14 双 flag 行为一致）。
4. 待用户复测：无限弹药（6 thunk 版）、协议点数、解锁协议。
5. 威胁等级×3 / 矿脉恢复：仍待定位。


---

# 2026-10-10 深夜探查会话（游戏挂后台 + 屏幕自动化）

## 方法论突破
- 屏幕自动化（CUA + Win32 SendInput，注意 SetProcessDPIAware）可以操作 RA3 菜单，
  配合内存读写实现了无人闭环验证。RA3 窗口前台化需 ALT+SetForegroundWindow 技巧。
- RA3 的 ESC 战场选单**不暂停模拟**（资金在菜单里继续跳）。
- MasterCode 块地址可从任意挂钓站点的 E9 rel32 反推；桩按站点 id 字典序排列，
  第一个（ammo）在 Block+0x40。

## 活体证实
- **无限资金溢出事故**：资金桩每跳 +100000 无上限，挂机数小时 int32 溢出变负
  （屏幕实测 -2,014,021,676）。已在 MoneyH2 桩加 1000 万上限（cmp/jae 跳过 add）。
- **阵营指针**：[玩家对象+0x1188] = 己方阵营对象（0x47D95A0），与单位体/生产对象的
  +0x418 值一致 → 敌我判定链：`esi=[块+0x10] → ebx=[esi+0x1188] → cmp [eax+418],ebx`。
  重打包版 +0x418 是阵营**对象指针**（EA 时代是索引）。
- **单位体链**：`选中条目+8 → A → A+0x10 → body`；body+0x33C→血量对象
  （+4 当前/+C 显示/+10 上限，实测 500/500/500 与 2500 全军单位）。12 个全军单位
  全部通过 body+0x418==己方阵营验证。
- **选中条目类**：vtable 0xC37C84，+0C=单位 ID（每单位不同），+1C 观察值 2/3
  （写 999 未确认星级变化，xp999 仍属实验）。
- 0x8E0940/0x8E4C60 节点内容跨选择**不变** → 确认不是选中列表（原定性错误，已纠正两次）。

## v5 变更
- MoneyH2 加上限；BuildPower/BuildHpA 敌我判定改用 [esi+0x1188]（带空指针守卫）。
- zoom 桩加捕获数组：FlagCaptureSel(0x0C) armed 时 entries[count++]=ecx（上限 64，
  数组在块+0x1000，计数在 +0xFFC）。
- SelectionActions 全面重写：枚举走捕获数组，链走 entry+8→+0x10→body；
  capture 写 [body+0x418]=[[esi+0x1188]]。
- 自检 40/40 + 20 桩反汇编全过。发布 publish-v5。

## 明日（10号晚）测试清单
1. 无限资金：开着打一局，确认资金涨到 1000 万封顶不再溢出。
2. 立即就绪/冻结敌方：验证敌我判定（若无效点诊断采集，比对 [eax+418] 与 esi+0x1188）。
3. 选中类 10 项：单选测一遍（捕获数组保证单选必中）；再群组选测试多选。
4. 无限弹药：开着让米格打完弹 → 诊断采集看武器对象 +4/+8/+1C 哪个是弹药计数。
5. 若有崩溃：把修改器运行日志发来（桩布局防呆已内置）。


---

# 2026-10-10 凌晨自主测试会话（屏幕自动化 + python 训练师）

## 完成的闭环
- 关 QQ 通话（CUA 点击退出通话 ✓）
- 从修改器「启动游戏」同款机制拉起游戏（steam://rungameid/17480）
- **python 训练师全套实现**（tools/harness/）：pystubs.py（StubGen 的 python 移植，
  与 C# 输出 20/20 逐字节一致）+ attach.py（站点校验/分配块/装桩/幂等重装）+ memutil.py
  （VirtualQueryEx 区域遍历 + 差分扫描）+ gclick.py（DPI 感知真实点击）
- UI 自动化走通：主菜单 → 對決 → 遭遇戰大厅 → 开始 → 对局（Battlebase Beta vs 簡單AI）

## 屏幕级验证 ✓
- **无限资金**：资金 9200 → 标志置位后每跳 +90 万 → **10,010,000 封顶**（截图确认，
  上限桩工作正常）。旧版无上限的溢出事故（-20.1 亿）根因确认并修复。
- 无限电力：左上电力条满格绿色（截图确认）。

## 关键教训（都是真金白银的坑）
1. **标志写到旧块**：重装新块后忘迁移标志 → 一切"无效"的假象。_attach 后必须重新置位。
2. **幂等安装的槽位覆盖**：第二次安装偏移从头算，把已有桩覆盖成弹药桩（会崩溃）→
   改为每次全新块 + 全量重装（旧块泄漏 8KB 无害）。
3. **python Asm.build 的 rel32 负数**：& 0xFFFFFFFF 掩码破坏向后跳转 → 直接 pack signed。
4. **zoom 捕获桩两 bug**（je 反向 + [edx] 解引用比较）→ jne + cmp edx,imm64 修复
   （python 与 C# 同步修）。

## zoom_site(0x552115 函数) 的最终认知
- 该函数 = 相机缩放/视野处理（内部 [esi+4] 平滑、[ebp+0x3A4]/[ebp+0x39C] 缩放范围 clamp）。
- **只响应真实物理输入**：触发计数器 3 秒 = 0（合成滚轮 mouse_event 不被 RA3 原始输入接受）。
  用户实际游玩时每帧触发（昨晚实测）。
- 捕获数组桩逻辑已修复且字节验证正确；其枚举的是"视野内对象"（非选中单位）——
  明日由真人滚屏 + 点击选中，观察数组内容即可确定其真实语义，进而决定
  选中类功能是走本钩子还是另找选中存储。

## 明日测试指引（v5 = publish-v5）
1. 无限资金/电力：✅ 已屏幕级验证，可直接玩。
2. 立即就绪/冻结敌方：敌我判定锚已实现（esi+0x1188），进游戏造超级武器实测；
   若无效点诊断采集（诊断槽会打出 [eax+418] 与 esi 值）。
3. 选中类 10 项：需要真人操作（滚轮缩放/点击选中驱动 zoom 钩子）；
   点「诊断采集」前先滚一下鼠标滚轮、选中部队，再点按钮 → 日志/捕获数组立刻有数据。
4. 无限弹药：让米格参战后诊断槽 ammo.weaponEax 会有值，看 +8 是否=50000。
5. 威胁等级×3 / 矿脉：仍待逆向。


---

# 2026-10-10 追加：选中列表语义的最终确认（回应"功能搞混"质疑）

用户质疑无限缩放与选中类可能搞混 → 深挖 [0xCE4C60] 的写入者：
- 设置器/清除器（0x145F80/0x145F90/0x145FA0）无直接 E8 调用者，而是以连续函数指针
  出现在 .rdata+0x7F6808 的 **63 槽网络消息处理器分发表**（13 个一组重复注册），
  占每组第 5/6/7 槽 = "选中对象消息 / 清除选中 / 组选中" 三个消息处理器。
- SAGE 引擎选中变化走命令网络（单机同样）→ **[0xCE4C60] 就是选中列表，原判定正确**。
- zoom_unit_xp 函数只在选中非空时运行（空列表 → 表头判空 early-out → 桩永不到达）
  → 解释了夜间无人会话 selEntry=0/捕获=0 的全部观察；昨晚用户游玩时每帧触发也自洽。
- 旧脚本 ebp==1 守卫 = 条目记录里的"被选中"位（EA 时代语义），重打包版寄存器含义待实测。
- 结论：功能↔站点映射无混淆；zoomlimit(无限缩放)=0x216C7D 站点维持 [08] 归属；
  选中类功能(v5 捕获数组+链)在真人选中部队后即可用。


---

# 2026-10-10 复查：老脚本仍未理解内容清单（应用户要求系统性复查）

## 已从二进制记录新解码
- TMK 热键记录结构（文本+二进制混合）：名称/VK码/动作，引用训练师表单元用
  **dword 与 ASCII 双份**（如 1a 0a 01 00 + "00010a1A"）。
- **LM MAX/MIN/NORMAL = 威胁等级最大/归零/恢复**（VK 0xBC','=0xBE'.',0xBF'/' 与 README 21-23 对上）：
  热键写威胁值字符到 0x10a1A（'1'=最大/'2'=归零/'0'=恢复），Ore Mine 写 '1' 到 0x10a1C。
- 机制 = TMK Freezer 计时器：反复把 0x10a1A 的值写到 0x10a06 存的目标游戏地址。
  **目标地址的填充环节不在文本转储里**（训练师 .text 无 .data 立即数）→ 威胁/矿脉的
  游戏地址是最后的盲区。方案：下会话跑原版修改器 + 活体观察 0x10a06 被写入的值，
  或在对应功能点击瞬间抓地址。

## 其余未解/存疑清单
1. [entry+0x1C]=999 → 三星？（实测观察值 2/3，写 999 未确认星级——需截图对照）
2. ebp==1 守卫 = 条目"被选中"位的推测（逻辑自洽但未实测）
3. [06]/[07]/[08] 三功能的站点语义重叠（0x216C7D 的 je 控制到底是缩放还是别的）
4. Freezer 目标地址填充环节（上述）
5. 老脚本 `mov [eax],ra3+8DB73C` 的 [eax]（疑为 TMK 表 0x10a34 的文本歧义，
   EA .data 0x8DB73C = 金钱全局地址，重打包版等价物 = [esi+0x3B0]，已不需要）
6. zoom 函数内部 [eax+0x70] vs call 0x145fe0 结果的 jle 比较细节（未分析）
7. 老训练师 0x10a0c 选中指针的填充者（TMK 内部机制，已被我的捕获数组方案取代，仅存档）

## 明确已理解/已移植 ✓
全部 16 个代码钩子的语义与重放字节、MasterCode 标志布局、选中链
（entry+8→+0x10→body→+33C/+418）、[玩家+0x1188]=阵营、消息分发表证实选中列表、
24 项功能的 README 对照与按键映射。


---

# 2026-10-10 自主对局测试会话（自动化进对局实测）

## 屏幕级验证结果（Battlebase Beta vs 簡單AI，全自动进对局）
- ✓ 无限资金：10,010,000 封顶（花钱时持续回补到上限，消费中资金 10,009,994 实测）
- ✓ 无限电力：电力条满格
- ✓ 快速建造：反应炉 4 秒接近完工（正常 10 秒）——画面可见建造光效
- ✓ 地图全开：小地图全亮（与旗标开关联动）
- ✓ 19 钩子（无 zoom）经历完整对局周期（加载→运行→结束→大厅→再开局）无崩溃
- ⏳ 立即就绪 A/B：无法在无超级武器/协议技能时判定（其语义本来就是协议/超武冷却，
  对普通建筑无声称效果）——需要真人对局到超级武器阶段
- ✗ zoom 钩子（0x152115）在合成输入下不触发（真实硬件输入才响应），
  xp999/选中类/无限缩放的最终验证需真人操作

## 关键工程成果
- gclick.py/memutil.py/pystubs.py/attach.py 构成可复用 python 训练师
- 真实点击可选中游戏内单位（侧栏生产面板出现）；但统计界面会因坐标偏移误触
  （點生產圖標時若面板未開，點到 (1135,318) 会开统计——需先确认面板可见）

## 游戏现状（交接给用户）
- 对局运行中（Battlebase Beta vs 簡單 歐列格），己方：MCV + 反應爐×2 + 3 征召兵
- 旗标全开：资金 1001 万、电力满格、快速建造、地图全开、scpoints、allproto、instantready
- 修改器 UI（diag 版）仍挂着但未附着本局——点其「附加进程」会因站点已被 python 钩住而失败
  （无损害）。接管方式：直接玩（旗标持续生效），或让 python 卸载钩子后再用训练师 UI。

### v18d 补充（第四局·无AI单人居，无人自动化路线穷尽）

- 后台 capture_spawn.py 等待真实点击 300s 超时（用户不在机前）。
- 无人路线全部穷尽：新进程名字块=0xFE3DA68（逐进程漂移）；模板池指针宿主 2368 个
  在活跃生成 25 秒内**零变化**（生成状态不持模板指针，按哈希/ID 引用）；
  新分配堆区=零填充预留（分配器复用）；HP 三连浮点假设不成立；资金对象差分定位成功
  （0x491A268 +5/tick）但 +0x3B0 持有者链断（无任何指针指向资金对象头）。
- **解锁只差一步用户动作**：游戏窗口前台时用真鼠标点任意一个征召兵（capture_spawn.py
  自动完成剩余全链：读 wrapper→排兵→守页→抓 EIP+栈）。或批准 UAC 启动修改器
  （money 桩诊断槽给出玩家上下文锚）。
- 结论固化：RA3 地图交互只认 Raw Input（合成输入全拒）；选中/生成状态对象按需发现，
  静态锚点每局漂移，必须靠一次性真实输入或运行时桩建立锚。

### v18e（收尾：矿态→地图对象系统确认；捕获守护进程常驻）

- 运行时矿态（[C+4]→容器、[O+8]=矿量）特征扫描成功（本局 C=0x48C93E8 矿量2404/已采65，
  双采集者共享容器）；但持有者是**地图对象**（含 "...\Red Alert 3 Data\Maps..." 路径串、
  共享类型对象 0x4804C90）——矿节点走地图对象系统，与单位 body 系统（+0x33C/+0xF4）不同轨，
  不能由此学单位 drawable。
- capture_spawn.py 升级为 30 分钟双通道守护（真实点击 OR 修改器进程任一触发）后台常驻。
- 全部自主路线确认穷尽；解锁需要用户在场。

### v18f（接手 sol：第四桥"生成桥"完成——复制选中/三阵营基地车/战场增援代码）

**sol 阶段成果（commit 76165d2 + 本次修复）**：
- `SpawnApiResolver`：重打包地图开局生成 wrapper 全字节契约（304B，1.13 RVA 0x22E3E0 /
  1.12 0x2440F0，12 个 CALL 边 + manager global 1.13 0x8F1DB8）。cdecl(忽略, 模板持有者,
  float3* 位置, 属主side, 忽略) → eax=新 body；mock ABI 验证（null 模板/null body 安全早退）。
- `SpawnSupportApiResolver`：模板哈希查找 TemplateHashLookup（1.13 0x40D5B0/1.12 0x422510，
  thiscall ret4：ecx=表宿主, 栈参=哈希）+ OwnerResolver + 调用锚。
- `verify_spawn_hashes.py`：增援代码=WB 字符串哈希，从游戏自带 WBStringHashes.big 的
  stringhashes.xml 证实：AlliedMCV=0x28DA574E、SovietMCV=0xAF4C0DA5、JapanMCV=0x1C2EF767、
  0x6586A5A0=JapanCommandoTech1（FINAL3 增援示例代码）。
- **本次修复 sol 的 bug**：SpawnSupportApiResolver 把表宿主 VA 错误写进 HashLookup 契约
  +0x05（该函数是 thiscall 无 imm32 全局，+0x05 是 lea esi,[ecx+0x28] 中段）→ spawntest
  1.12 崩。改为用**wrapper+0x1CA 调用现场**锚定表宿主全局（两版完全对称：
  `8B 0D <表宿主VA> 52 E8 <→lookup>`；1.13 现场 0x22E5AA / 1.12 0x2442BA）。

**离线逆向补充（本次新增证据）**：
- map-start caller（1.13 0x22E510，紧邻 wrapper 之后）完整闭环确认：
  `mov ecx,[0xCF0108]; push hash; call 0x40D5B0`（哈希→模板持有者）→
  读出生点坐标 → `push arg5; push owner; push pos; push holder; push arg1; call wrapper` →
  `add esp,0x14`（cdecl）→ eax=新 body。wrapper 的 wrapper+0x1CA 处即该调用序列。
- **单位坐标**：position-set（1.13 0x40CFC0/1.12 0x421FE0，wrapper 内部第 4 个 CALL）
  把 float3 写入 body+0x38/0x3C/0x40（整数镜像）与 +0x14/0x24/0x34（float 副本）。
  复制选中的生成位置直接读选中单位 body+0x38 三连。
- 选中链与 wrapper 参数完全同构：tracker+4 的"wrapper"对象就是 wrapper 的 arg2 模板持有者
  （+0x14→descriptor，+0x64 yaw）——复制选中无需任何新链。

**第四桥架构（SpawnDispatcher @0x1500，邮箱 @0x18C0）**：
- 邮箱：state/+4 hash(0=直接持有者)/+8 holder/+C..+14 float3/+18 owner(0=playerRoot补齐)/
  +1C resultBody/+20 resolvedHolder。
- 消费桩：cmpxchg 领取 → hash≠0 时游戏线程查表（ecx=[表宿主全局]; push hash; call lookup，
  ret4 thiscall）→ 直接路径门禁 holder≥0x10000 且 [holder+0x14]≥0x10000（wrapper 必读）→
  owner 补齐 [playerRoot]+0x28 → cdecl 调 wrapper（5 参 + FXSAVE + pad8 入口对齐 esp%16==0，
  callee-cleans=false caller add esp,0x14）→ eax≠0 → state 3 + resultBody。
- TrainerEngine：`spawn-bridge.enable` 标记/RA3MT_SPAWN 环境变量显式开启，附加时
  SpawnApiResolver+SpawnSupportApiResolver 全过才装桩；`ExecuteAction(id, arg)` 新签名。
- 功能：selcopy（复制选中，每目标自身坐标+散布偏移）/ mcv_allied|soviet|japan（哈希常量）/
  reinforce_code（UI 输入 8 位十六进制 → 哈希路径；无选中单位时提示先选中锚点单位）。

**验证**：Unicorn 20 用例（领取门禁/哈希路径/直接路径/owner 补齐/5 参 ABI/入口栈对齐
esp%16==0/全 GPR+XMM+EFLAGS clobber 恢复/FX 保存/全拒绝门禁/4 种 caller 对齐/payload 不突变）；
C# 邮箱 30 用例（生命周期/发布顺序/非法参数/结果回读）。SelfCheck 9 模式全过、
Unicorn 6 套件全过（197+semantic+60+218+8+20）。publish-v18（含三个 .enable 标记）。

**遗留**：生成 wrapper 运行中调用的线程/生命周期风险由桥缓解（资金结算=游戏线程），
效果待实机验证；wrapper 可选分支（locomotor 初始化 calls[9..11]）未在 mock 覆盖。
随地建造未开始。

### v18g（实测反馈轮：升星多目标修复✓；摧毁动画与鼠标坐标攻坚记录）

- **升星多目标已修复并实测确认**（3/3）：桥消费只挂 money_h2（资金结算），无限资金下资金结算
  长时间不跑 → 邮箱无人消费。现在 money_h1（电力结算，持续跑）也装桥 CALL 链
  （EmitMoneyBridge 参数化 stubId），原子邮箱认领保证双站点安全。
- **摧毁（v18d ctx 修复后仍无动画）**：活体桩反汇编确认 ctx=邮箱+0x10（含 6/0x13）已正确传入。
  adjust→0x3513F0 死亡标记链完整跑通（用户实测"无法选中"=标志生效），但模型残留/无动画。
  结论：**死亡动画分发在伤害管线层**（FINAL3 调的 EA 0x39EA50(6,19,0)=完整伤害入口），
  不在底层 HP 函数。等价函数静态寻找穷尽：RTTI 剥离、线性平移无效（晋级锚 Δ+0x3E640 映射
  0x3DD090 非指令边界）、push 6/13/0 模式无直接命中、死亡标记 8 调用者全为内部清理路径、
  0x324710（[Body+0x4EC] 链表+全局 0xCEED48）是 356-xref 高频基础操作非死亡队列。
  **下一步=活体断点抓正常击杀的 0x3513F0(al=1) 调用链对比**。
- **FINAL3 逻辑全解**（script_00 原文）：CreateUnit EA 0x205240 cdecl(0,模板,位置float3*,
  side,**[side+0x10]**)——第 5 参非 0（我们传 0 实测也能生成）；复制选中模板=**Body+4 直取**
  （我们走 0x3CC→tracker+4 链，等价）；位置=Body+0x38/3C/40 **与我们的偏移完全一致**；
  鼠标世界坐标=[EA 8DAEFC 对象]{+0x3C=X,+0x40=Y,+0x44=Z 屏幕 float} + cdecl(in*,out*,0,0)
  变换 EA 0x1ED4A0。**待重打包定位**（find_mouse_object.py 已就绪：SetCursorPos 两次+
  堆扫描找跟随光标的 +0x3C/40 对，再反查 .data 全局；需游戏窗口前台，本轮扫描时游戏最小化失败）。
- 随地建造失效未诊断（需活体：开关开着+放置模式鼠标停在远处空地读 UI 状态差分）。

## v261013 系列（2026-10-13，产品化 + EA 支持大日子，9 个发布）

**版本规则变更：`vYYMMDD-N`（日期+当日序号）取代 v19 起纯数字制。**
**发布产物变更：单文件正式名 exe `Red Alert 3 Modern Trainer v<版本>.exe`（~58MB x86，图标内嵌，
无任何附带文件；.enable/dll/pdb 全部退役）。**
每发一版同步两处版本串：MainVM.AppVersion + UI csproj 的 AssemblyName（PublishSingleFile 条件下覆盖）。

### 内置增援单位表（v34 引入）
- **增援代码=WB 字符串哈希彻底定案**：B 站教程（opus/383217795565387307）的 Instance ID 就是同一套
  （JapanEmperorMecha=0xCC023E30 与 FINAL3 文档/我们的哈希表三方一致；AlliedMCV=0x28DA574E 同）。
- **数据提取全程序化**（tools/analysis/gen_reinforce_table.py → assets/reinforcement_codes.json，
  125 条=盟军36/苏军40/升阳42/中立箱7）：
  ① WBStringHashes.big→stringhashes.xml **明文 XML** 58573 条（name→hash）；
  ② **真实单位清单必须用 Core12.big 的 data\static.12.manifest（RefPack 压缩，507 GameObject）**
  ——WBData 的 worldbuilder.manifest 只有 19 个阵营物件+环境道具，不是战斗单位表；
  ③ ChineseT.big→gamestrings.csf（RefPack+CSF：` LBL`/` RTS` ASCII 操作码、值=XOR 0xFF 的
  UTF-16LE）→ `NAME:<大写名>` 繁中显示名 542 条，**"有中文名"=真实单位过滤条件**（游戏不给
  弹药/坍塌态这类 helper 对象做本地化）。
- **格式规范**：BIG4 头=4B magic+LE 文件长+**BE** 条目数+**BE** 索引长，表项=BE offset+BE size+名字；
  RefPack 解压按 Niotso wiki 公有领域实现（四类命令字）。CSF 头 24B。
- 接入：ReinforcementCatalog（Core/Model 嵌入资源——**链接资源增量坑同 features.json，改后
  必须_Core --no-incremental**）；TryResolve 三路=十六进制/内部名/繁中名；UI 卡片 📋
  （Views/ReinforcePickerWindow 搜索+分组）；`arg.suggest` 元数据驱动（FeatureVM 保持零功能知识）。
  SelfCheck reinforcetest 8 例。**内部名是语义名**（天啟坦克=SovietAntiVehicleVehicleTech3），
  英文社区俗名搜不到——已知局限。

### EA 原版 1.12 支持（v261013-2/3/4，用户拍板的特征码哲学落地）
- **EA 本体=D:\BaiduNetdiskDownload\Red Alert 3（5D 简中盗版）；与重打包同模块名 ra3_1.12.game
  但布局不同**。版本维度="1.12ea"：features.json 26 钩子加第三列 RVA（displaced 逐字节相同，
  零 displacedByVersion）；ImageScan.Layout 加 params 多版本重载；五个解析器加 EA 行。
- **EA 地址总表**（离线定位+契约验证+FINAL3 文档值三方交叉）：
  钩子 money_h1..h4=0x6CFD0D/DFE/E6C/EB5（链距+F1/+6E/+49 同 repack）、proto_cool_a/b=0x30F38C/42E、
  aiblock=0x30F530、godmode=0x12EEDF、onekill=0x3651AE、onekill_a/b=0x3FE714/0x2E24E3、
  build_hp_a/b=0x43EC19/0x43ECA6、zoom=0x128735、sidebar_pts=0x30A5F6、unit_lv=0x3C226C、
  power_cool=0x1EC7CD、build_power=0x2EBB69、power=0x2F6CFF、weapon_clip=0x390ED1、
  **ammo 簇=0x438ED0/0x438EF0/0x438F10/0x43BD10/30/50**（六胞胎函数 0x20 间距）。
  全局：selectionList=0x8DB7A0、playerRoot=0x8E8C9C、鼠标对象=0x8DAEFC（.rdata，13 引用簇）、
  hash 表宿主=0x8E6C58、owner-kind=0x8D8CE4、生成 manager=0x8E8908。
  桥：rank=0x35C200（99B 契约原样成立，threshold=0xF7680/award=0x343920/root=0x8D8CDC）、
  capture=0x38DBB0（helper 0x124C60 同三偏移）、kill=0x365190/0x327890/**0x39EA50**、
  **spawn wrapper=0x205240：304B canonical 完美吻合**（第三目标集）；support lookup=0x3E4230/
  hashfind=0x104E10/owner=0x43B300/predicate=0xD5400/transform=0x1ED4A0。
  随地建造 EA patch 点=0xE7565（FINAL3 文档值，v19 盗版实测 75 0C）。
- **同名双构建判别**：GameBuildClassifier（Core/Target）——双锚点（money_h1 9B + zoom 5B）
  全中才判 1.12ea；重打包在 EA 槽位是完全无关字节（实测零巧合）。判错则字节校验大声失败。
- **v261013-3 防错乱加固**（用户质疑触发）：①ammo 的 AOB 从一开始就锚错六胞胎兄弟
  （repack 上也错，被"RVA 字节校验通过，特征码仅供参考"掩盖）——重写为"函数体+15CC+下函数前缀"
  36B 模式，三镜像唯一命中正确地址，特征码回退路径也安全；②回滚路径版本一致；③附加日志全路径。
- **livetest**（SelfCheck 新模式）：对运行中游戏只读做判别+26 钩子+四桥活体验证（零挂钩零写入）。
  **双构建活体结果：EA→1.12ea 全过（桥 rank 0x75C200/capture 0x78DBB0/kill 0x765190/spawn 0x605240）；
  Steam 1.12→1.12 未误判全过（老地址集）——同一份修改器把两个同模块名构建各自路由正确。**
- 方法论沉淀：①Python 通配符模式解析器把 ?? 字节从数组丢掉=后续字节错位、带通配扫描静默失效
  （纯字节扫描不受影响）；②六胞胎函数族消解=0x60 窗口差分掩码；③"displaced 全族命中"≠定位成功；
  ④FINAL3 的 EA 地址按 RVA 理解（鼠标对象 0x8DAEFC 在 .rdata）。

### 单 exe 分发与缓存治理（v261013-5/6/7）
- 四桥默认开启（.enable 标记退役；env=0 关闭；字节校验仍把守安装）。
- IncludeNativeLibrariesForSelfExtract + DebugType=none（PublishSingleFile 条件，**Core/UI 两个
  csproj 都要加**否则 Core.pdb 残留）→ 发布目录只剩一个 exe。
- **v261013-7 自解缓存清理**：.NET 单文件宿主从不删 %TEMP%\.net\<AssemblyName>\；版本入名→
  每版泄漏 ~7MB（实测一天 34MB）。App.OnStartup→SingleFileCache.CleanStale() 清家族内非当前
  版本目录。**★翻车：当前版本目录碰都不能碰**——启动早期 D3DCompiler 等未 LoadLibrary 没锁，
  被清掉后 WPF 首渲染崩溃（bundle 6 文件只剩锁住的 1 个，活体诊断实锤后改为完全跳过当前目录）。
- 正式名带空格：tasklist/taskkill IMAGENAME 过滤不可靠，用 PowerShell Get-Process -like。

### 架构两轮（v261013-8 收尾 + v261013-9 抛光）
- StubGen 拆分（MasterCode 877→279+598 两文件，桩门禁 33/33 零字节）；**M5 定案完成**
  （"四成未迁"评估过时：16 开关=15 SwitchFeature+build_anywhere 独立功能，全部动作走 catalog）；
  build_features.py/gen_features.py 删除（会覆盖手工数据），features.json 手工维护写入 ARCHITECTURE.md。
- 抛光：LegacyFeatureCatalog→FeatureCatalog+FeatureRegistry.cs 归位；ISymbols→Model（消除
  Engine 实现接口倒挂）；BridgeCoordinator 拆出（TrainerEngine 736→447 行）。
- 二次评估结论：稳态维护，无结构性欠账；观察项=功能>50 或版本>4 时把版本地址表数据化。

### 其余（v261013-1）
WhiteSprite 署名入 UI；RA3MT=Red Alert 3 Modern Trainer（用户命名确认）。

## v261015 系列（2026-10-15，两个实测反馈修复，均已实测通过并推送）

### 1.12 系鼠标生成被功能层门禁卡死（v261015-2 前半，commit d639174）
- **用户报告：1.12 上鼠标放空地、未选中单位，按基地车热键无反应**。根因不在桩：
  SpawnActionFeature（MCV/增援/复制）提交前硬性要求 `MouseGround ?? SelectionAnchor` 非空；
  **mouseGround 静态副本只有 1.13 有 RVA**（0x8e15b8，v18g 定位；1.12/1.12ea 运行时指针
  访问，静态无引用从未定位）→ 1.12 上 MouseGround 恒 null → 空地+未选中 → 功能层直接
  拒绝提交（"鼠标位置不可用"）。**桩内实时鼠标机制三版本全有**（鼠标对象全局+屏幕→世界
  变换，SpawnSupportApiResolver 三 Layouts 契约校验）——v261013-2 备忘"鼠标生成走桩内
  EA 鼠标全局不受影响"漏算了功能层这道门。**教训：备忘里的"不受影响"要核对整条链的
  每一道门，不是只看最终执行件。**
- 修复：锚点降级为"变换失败兜底"——无任何锚点也照常 SubmitAtMouse（兜底坐标原点，
  变换成功=实时鼠标位置，失败=被游戏拒绝，桩本就 null-safe）；复制/增援同放宽；无锚点
  时日志明说"无回退锚点"。1.13 行为零变化（有 mouseGround 时照旧）。actiontest +5
  anchor-gate（无锚点提交/选中兜底/鼠标地面兜底/增援同放宽/桥关闭 fail-closed）。
- features.json mouseGround note 修正为**屏幕中心地面投影**（随镜头不随鼠标，v24a 活体
  定案）——旧"任意时刻跟随鼠标"是 v18g 被推翻的结论；该全局现仅作日志显示与兜底锚点，
  真实位置全靠桩内游戏线程实时求值。

### 升星"已满星"误报错误窗（v261015-2 后半，commit e021f80）
- **用户报告：框选混入已三星单位，升星弹错误日志窗**。RankDispatcher 桩调升星函数前后
  各写一次 tracker+0x24 对比，值没动=Reject——这是"证明升星确实发生"的防呆，已满星单位
  必走此路，**属预期结果**；但 DrainBridge 统一措辞"校验未通过/被校验拒绝"命中
  IsErrorLine 关键词→弹窗。
- **分类法（精确零歧义）**：邮箱提交时把 before/after 两槽清零；校验拒绝路径在写槽
  **之前**就退出（两槽 0/0=真校验失败）；"奖不动"路径两槽相等且非零=已满星。
  `RankRequestMailbox.RejectedBecauseAlreadyRanked()` 实现；bridgetest +8 锁定。
- DrainBridge 拒绝分两计数：benign→"未升星（多为已满星），跳过"（无错误关键词不弹窗）；
  真校验失败措辞不变照弹。汇总行分开计数；**全部已满星（applied=0 仅 skipped）返回
  成功**，FeatureVM 成功行改为带消息（"全部目标已是满星，无需升星"）。仅升星桥分类，
  俘虏/摧毁/生成桥零变化。
- 发布链说明：v261015-1 只含第一修复、未实测即被 v261015-2 取代（两修复一起实测）。
