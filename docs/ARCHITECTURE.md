# 架构

本文件描述当前分层与扩展方式（M1–M7 解耦 + v261013-8/9 收尾抛光后的稳态）。
设计目标是**解耦、模块化、功能之间互相影响最小**，
每步都以"桩字节零回归 + SelfCheck 全模式 + Unicorn 全套件"为闸门。

## 分层

```
RA3MT.UI ──► RA3MT.Core ──► RA3MT.SelfCheck（离线验证，引用 Core）

UI 只做渲染：卡片来自 features.json 元数据（icon / arg），不再认识任何 feature id。
Core 分层（依赖严格向下，无环）：
  Model          数据形状（FeaturesData / ReinforcementCatalog）+ ISymbols 契约
  Target         字节契约解析器（三构建布局表 + ImageScan 校验原语 + 构建判别器）
  Engine         机制层：MasterCode 生命周期、StubGen 桩工厂（分文件）、
                 块布局、四桥分派器、邮箱
  Features       FeatureCatalog（唯一注册点）→ 34 个功能实现（Toggles / Selection /
                 Actions / Patches）；BridgeCoordinator 会话级桥编排（提交/等待/措辞）；
                 TrainerEngine 编排器（附加/脱离/判别/服务装配，447 行）
  Host           功能可用的能力（服务按类型查找，不是宽接口）
  Abstractions   功能契约与上下文（IFeature / IFeatureState / FeatureContext）
```

## 扩展一个新功能

只需三步，**不需要改引擎**：

1. `assets/features.json` 加一条 `features[]`（含 `icon`，需要参数就加 `arg`；
   功能私有地址放 `private`）。
2. `src/RA3MT.Core/Features/<目录>/` 加一个 `IFeature` 实现。
3. `Features/FeatureCatalog.cs`（唯一注册点）把 id 接到该实现。

> **`features.json` 是手工维护的源数据**（34 功能+26 挂钩+三版本地址表）。
> 旧生成器（build_features.py / gen_features.py）停留在 24 功能时代且会覆盖
> 现有数据，已于 v261013-8 删除；hookdata.json 是其历史输入，无消费者。
> 仍由工具生成的数据只有两个：`reinforcement_codes.json`
> （tools/analysis/gen_reinforce_table.py，从游戏文件提取）和桩字节
> （SelfCheck stubdump）。

`SelfCheck featuretest` 会校验：声明与实现一一对应、id 唯一、kind/flag/action 自洽、
**每个可运行功能都 `IsMigrated`（不得回落到引擎旧分支）**、卡片有图标、参数声明合法、
未附加时功能必须 fail-closed。

## 关键抽象

| 抽象 | 位置 | 作用 |
|---|---|---|
| `IFeature` / `IFeatureState` | `Features/Abstractions` | 功能契约：Kind、Availability、per-session 状态、`IsMigrated` |
| `FeatureContext` | 同上 | 会话快照 + `ISymbols` + `FeaturesData` + `FeatureHost` |
| `ISymbols` | `Model` | 共享全局按 `GameGlobalId` 枚举解析，版本化取址唯一入口（Engine/Features 共同向下依赖） |
| `FeatureServiceRegistry` | `Features/Host` | 能力按**类型**查找；加能力=加服务类，不撑大所有功能 |
| `IGameMemory` | 同上 | 受保护的读写（指针 < 0x10000 视为 null） |
| `ISwitchBank` | 同上 | **开关状态的唯一所有者**，功能只请求翻转 |
| `IBridgeGateway` / `ISpawnGateway` | 同上 | 游戏线程桥的提交入口，功能看不到邮箱细节 |
| `BridgeCoordinator` | `Features/` | 会话级桥编排：邮箱提交/等待/重试/日志措辞；附加时创建、脱离时销毁 |
| `BlockLayout` / `BlockLayoutCatalog` | `Engine` | 块内区域的唯一声明处，`Validate()` 一次证明不重叠 |
| `IBridgeConsumer` / `RequestMailbox` | `Engine` | 一个桥=一个对象；邮箱状态机只写一次 |
| `IApiResolver` / `IImageReader` / `ImageScan` | `Target` | 严格字节契约与校验原语 |
| `GameBuildClassifier` | `Target` | 同名双构建（Steam/EA 1.12）的内存指纹判别，只读 |

## 不变量（改动时勿破）

1. `TrainerEngine` 里**不得**出现按 feature id 的分支；发现即应做成功能。
2. 功能之间不直接依赖：只通过 `FeatureContext.Host` 与服务交互。
3. 块内偏移只在 `BlockLayoutCatalog` 声明；`MasterCode` 不再手写偏移。
4. 每次改动的验收：`py tools/harness/stub_regression.py`（桩字节逐字节）+ SelfCheck 全模式 + Unicorn 全套件。

## 验证入口

```
dotnet build RA3MT.slnx -c Release
py tools/harness/stub_regression.py                 # 桩字节零回归闸门
dotnet run --project src/RA3MT.SelfCheck -c Release -- <mode>
   bridgetest rankmailboxtest ranktest actiontest installertest resolvertest
   asmtest selectiontest featuretest layouttest spawntest reinforcetest
   livetest   # 只读活体验证：对运行中的游戏做判别+全钩子/桥解析（不挂钩）
py tools/harness/test_execution_stubs.py            # 及其余 Unicorn 套件
```
