# 逆向笔记（重打包版 1.12/1.13）

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
