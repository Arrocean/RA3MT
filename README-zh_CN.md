# RA3MT — Red Alert 3 Modern Trainer（红色警戒 3 现代修改器）

[English](README.md) | 简体中文

以 Ken22265 的 FINAL3 修改器（2009，EA 原版 1.12，31 项功能）为蓝本的现代重制版：
**C# / .NET 10 + WPF**。FINAL3 31 项功能已全部对等移植并多轮实测，本修改器共 **34 项功能**、
四大游戏线程桥架构，UI 由 WhiteSprite 主理。

**一份修改器支持三个游戏构建（附加时自动识别）：**

| 构建 | 说明 |
|---|---|
| Steam 终极合集 **1.13** | 主力实测平台 |
| Steam 终极合集 **1.12** | 同样字节级校验支持 |
| **EA 原版 1.12** | 经典零售布局（FINAL3 的原生目标），v261013-2 起 |

> 仅限单机使用，联网对战不可用。仅供学习研究。

## 当前版本 v261013-9（2026-10-13）

版本号规则：`vYYMMDD-N`（日期 + 当日第 N 次发布）。发布产物为**单文件 exe**：
`Red Alert 3 Modern Trainer v<版本号>.exe`（约 58MB，x86，自带图标，**无需任何附带文件**）。

近期亮点（详见 docs/NOTES.md v261013 节）：

- **内置增援单位表**：125 个常用单位（盟军 36 / 苏军 40 / 升阳 42 / 中立趣味箱 7），
  带繁体中文名和可搜索选择器（增援卡片上的 📋），数据从游戏自身文件自动提取，
  并与实测验证过的代码逐个核对；也可手动输入十六进制代码或单位内部名
- **WeMod 式单键启动**：点「开始游戏」自动拉起游戏并在进程出现后附加；
  游戏已在运行则直接附加；等待期间可取消
- 四个游戏线程桥（晋级 / 俘虏+摧毁 / 生成）**默认开启**；排障时可用环境变量
  `RA3MT_RANK_BRIDGE=0`、`RA3MT_BRIDGES=0`、`RA3MT_SPAWN=0` 单独关闭
- 首次启动自动清理旧版本运行缓存（%TEMP%），不随版本更替累积占用
- 7 个用户分组、34 条玩家向功能描述、日期版本号、应用图标

## 构建

- 需要 .NET 10 SDK + Windows Desktop 运行时
- `dotnet build RA3MT.slnx -c Release`
- 发布：`dotnet publish src/RA3MT.UI -c Release -r win-x86 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o publish-v<版本>`
  （Git Bash 下必须用 `-p:` 而不是 `/p:`；每发一版同步改两处版本串：
  `MainVM.AppVersion` 与 UI csproj 的 `AssemblyName`）
- 产物为 **x86** 单文件 exe，要求管理员运行（manifest）——写 32 位游戏进程内存所必需

## 项目结构

```
assets/features.json             手工维护的源数据：34 功能 + 26 挂钩（三版本 RVA、被替换
                                 字节、AOB 特征码）+ 全局/功能私有偏移（嵌入资源）
assets/reinforcement_codes.json  内置增援单位表（gen_reinforce_table.py 从游戏文件生成）
src/RA3MT.Core                   分层引擎（见 docs/ARCHITECTURE.md）：
                                 Model（数据形状+ISymbols）/ Target（字节契约解析器）/
                                 Engine（MasterCode 生命周期、StubGen 桩工厂、四桥分派器）/
                                 Features（FeatureCatalog 注册、34 个功能实现、
                                 BridgeCoordinator 桥编排、TrainerEngine 编排器）
src/RA3MT.SelfCheck              离线自检 12 套件 + stubdump + livetest（活体只读验证）
src/RA3MT.UI                     WPF 主程序（元数据驱动卡片、单键启动、增援选择器）
tools/harness/                   Unicorn 桩执行套件 + 桩基线回归（artifacts/baseline_stubs）
tools/analysis/                  常驻逆向工具（跳板 tracer、.text diff、FINAL3 提取器、
                                 增援表生成器等 7 项）；探索脚本用完即删，结论在 NOTES
docs/NOTES.md                    逆向笔记——所有功能的定位过程、契约、教训（知识主载体）
docs/ARCHITECTURE.md             分层与扩展指南（含"哪些数据手工维护/哪些生成"清单）
docs/FINAL3_*.md                 FINAL3 解构与对照审计（历史交付物，结论以 NOTES 为准）
artifacts/final3/                FINAL3 全部 13 个 CE 脚本原文（.cea）+ manifest
```

## 验证（每次改动全跑）

```
挂钩点      78/78（1.12 + 1.13 + EA 1.12 三个镜像，逐字节 displaced 校验）
SelfCheck   12 套件全过（featuretest 108 / installertest 162 / actiontest 24 /
            bridgetest / ranktest / spawntest 69 / selectiontest / layouttest /
            rankmailboxtest / asmtest / resolvertest / reinforcetest）
livetest    对运行中游戏的只读全链路验证（构建判别 + 全钩子 + 四桥解析，不挂钩）
桩门禁      33 桩逐字节零回归（py tools/harness/stub_regression.py）
Unicorn     Python 侧桩语义执行套件（tools/harness/）
```

## 运行

1. 双击单文件 exe（管理员）；点「开始游戏」——Steam 版经 Steam 拉起后自动附加，
   EA 原版权请自行启动游戏后点击（一样自动附加）
2. 附加时自动识别游戏构建（Steam 与 EA 的 1.12 模块同名，靠内存指纹判别），
   逐点校验原始指令字节，不匹配即拒绝挂钩（防呆）
3. 开关型功能 = MasterCode 标志字节（游戏线程执行桩）或纯字节补丁（随地建造）；
   动作型 = 选中链遍历或游戏线程桥
4. 「脱离进程」恢复全部原始字节（随地建造补丁也会还原）

## 技术要点

- 游戏 32 位、ImageBase 0x400000、无 ASLR；三个构建两两之间存在区域偏移，
  所有 RVA 按字节契约在各自镜像重新定位并防篡改校验——**接入新游戏构建 =
  解析器加一行 + features.json 加一列键，零代码分叉**（EA 1.12 即此方式接入）
- 同名双构建判别：`ra3_1.12.game` 既是 Steam 重打包也是 EA 原版的模块名，
  附加时读两个独立锚点共 14 字节内存指纹判定；判错即字节校验大声失败
- **四桥架构**：资金/电力结算点为游戏线程入口，按序 CALL 各桥分派器；每个桥独立邮箱
  （payload 先写、state 最后发布的原子认领），跨线程调用游戏函数全程在游戏线程执行
- **随地建造补丁**：放置 gate 的"范围外→失败码"分支 `75 0C→EB 0C`
  （EA 0x4E7565 ↔ 1.13 0x511955 ↔ 1.12 0x528DF5，三版同字节，玩家与 AI 选址共用层）
- **增援代码 = WB 字符串哈希**：游戏自带档案（WBStringHashes.big/Core*.big/语言包）
  可程序化提取完整"单位→代码"对照，无需手工解包
- 站点定位铁律：静态地址必须先经活体证实才可 patch；VA/RVA 差 0x400000，
  引用笔记地址前先确认口径（历史三次误诊皆源于此，见 NOTES v18o）
- 旧 EA 地址的语义对应用**指令特征 + 结构同构**定位（可运行的参照实现优先于推理——
  盗版 1.12 上的 FINAL3 是 ground truth）

## 功能一览（34 项 / 7 组）

| 分组 | 功能 | 状态 |
|---|---|---|
| 资源（4） | 资金 / 电力 / 协议点数 / 解锁协议 | ✅ 实测通过 |
| 建造与生产（3） | 快速建造 / 随地建造 / 禁止电脑建造 | ✅ 实测通过 |
| 战斗（4） | 玩家无敌 / 一击必杀 / 冻结敌方技能 / 协议立即就绪 | ✅ 实测通过 |
| 视野与镜头（2） | 地图全开 / 无限缩放 | ✅ 实测通过 |
| 选中单位（13） | 三星 / 弹药 / 速度×2 / 冻结 / 血量×3 / 治疗 / 俘虏 / 摧毁 / 复制 等 | ✅ 实测通过 |
| 战场增援（4） | 三阵营基地车 / 增援代码（📋 内置单位表） | ✅ 实测通过 |
| 其他（4） | 威胁×3 / 矿脉恢复 | ✅ 实测通过 |

以上均在 Steam 1.13 实测收官（FINAL3 31/31 对等 + 3 项扩展）；
**EA 原版 1.12** 于 v261013-2 接入，地址层已三重验证（离线契约 + 78/78 静态 + livetest 活体），
功能实机测试进行中。

原版作者：Ken22265（FINAL3，2009）。本项目是其功能的现代重制与扩展，by WhiteSprite。
