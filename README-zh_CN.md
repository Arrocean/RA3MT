# RA3MT — 红色警戒 3 现代修改器

[English](README.md) | 简体中文

以 Ken22265 的 FINAL3 修改器（2009，EA 原版 1.12，31 项功能）为蓝本的现代重制版：
**C# / .NET 10 + WPF**，支持 **1.12 与 1.13（2024 终极合集版）**，33 项功能，四大游戏线程桥架构。

> 仅限单机使用，联网对战不可用。仅供学习研究。

## 当前版本 v20（2026-10-12）

- **已实测通过**：无限资金/电力/协议点数、解锁协议、快速建造、地图全开、
  晋级桥（含多目标）、俘虏桥、生成桥（三 MCV/复制/任意哈希增援）、**随地建造**（FINAL3 同款 2 字节分支补丁，灰格直放实测成功）
- **v20 新增待实测**：摧毁 v3 —— kill 桥改走游戏完整伤害入口（FINAL3 同款调用），
  死亡动画与模型回收由游戏自己的管线完成（此前为底层 HP 写入，无动画）
- **对照 FINAL3 全量审计已完成**：31 项功能行为级对照，缺 4 项（禁止电脑建造 / 玩家无敌 /
  一击必杀敌方 / 三星升级直调）待移植，路线见 docs/NOTES.md v19c

## 构建

- 需要 .NET 10 SDK + WindowsDesktop 运行时
- `dotnet build RA3MT.slnx -c Release`
- 发布：`dotnet publish src/RA3MT.UI -c Release -r win-x86 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o publish-vN`
  （Git Bash 下必须用 `-p:` 而不是 `/p:`；版本号 v19 起纯数字递增）
- 产物为 **x86** 并要求管理员运行（manifest）——写 32 位游戏进程内存所必需

## 项目结构

```
assets/features.json      全部数据：33 项功能定义 + 21 个挂钩点（双版本 RVA、被替换字节、
                          AOB 特征码）+ 全局/功能私有偏移（Core 以嵌入资源引用）
src/RA3MT.Core            分层引擎（见 docs/ARCHITECTURE.md）：
                          Abstractions（功能契约）/ Host（能力服务）/ 功能目录（每功能一类）/
                          Engine（附加、挂钩、块布局、四桥、API 解析器字节契约）
src/RA3MT.SelfCheck       离线自检 13 套件（挂钩点字节 / 动作写 / 安装恢复 / 汇编边界 /
                          选中链 / 桥邮箱 / 生成契约 / 功能目录 / 块布局 / 解析器）
src/RA3MT.UI              WPF 主程序（元数据驱动卡片，MVVM，全局热键）
tools/harness/            Unicorn 桩执行套件 + 桩基线回归（基线在 artifacts/baseline_stubs）
tools/analysis/           常驻逆向工具（跳板 tracer、代码段 diff 监控、临时补丁实验模板、
                          FINAL3 提取器、features 生成器）；探索脚本用完即删，结论在 NOTES
docs/NOTES.md             逆向笔记——所有功能的定位过程、契约、教训（知识主载体）
docs/ARCHITECTURE.md      M1–M7 重构后的分层与扩展指南
docs/FINAL3_*.md          FINAL3 解构与对照审计（历史交付物，结论以 NOTES 为准）
artifacts/final3/         FINAL3 全部 13 个 CE 脚本原文（.cea）+ manifest
```

## 验证（每次改动全跑）

```
挂钩点校验  42/42（1.12+1.13 字节级）
SelfCheck   13 套件全过（actiontest 24 / installertest 132 / bridgetest 30 / spawntest 46 /
            featuretest 101 / layouttest 14 / ranktest / selectiontest / asmtest / resolvertest …）
Unicorn     桩执行 197+197 / 桥分发 60+218+20 / 桩基线回归 28 桩零差异
```

## 运行

1. Steam 启动红警3（进主菜单即可），右键管理员运行修改器
2. 「附加进程」：逐点校验原始指令字节，不匹配即拒绝挂钩（防呆）；三个游戏线程桥
   （晋级/俘虏+摧毁/生成）默认开启；排障时可用环境变量 RA3MT_RANK_BRIDGE=0、
   RA3MT_BRIDGES=0、RA3MT_SPAWN=0 单独关闭
3. 开关型功能 = MasterCode 标志字节（游戏线程执行桩）或纯字节补丁（随地建造）；
   动作型 = 选中链遍历或游戏线程桥
4. 「脱离进程」恢复全部原始字节（随地建造补丁也会还原）

## 技术要点

- 游戏 32 位、ImageBase 0x400000、无 ASLR；重打包版与 EA 原版**存在区域偏移**，
  FINAL3 的绝对地址不可直接使用——所有 RVA 按字节契约在双版本重新定位并防篡改校验
- **四桥架构**：资金/电力结算点为游戏线程入口，按序 CALL 各桥分派器；每个桥有独立邮箱
  （payload 先写、state 最后发布的原子认领），跨线程调用游戏函数全程在游戏线程执行
- **就地建造补丁**：放置 gate 函数"范围外返回失败码"分支 `75 0C→EB 0C`
  （EA 0x4E7565 ↔ 1.13 0x511955 ↔ 1.12 0x528DF5，三版同字节，玩家与 AI 选址共用层）
- 站点定位铁律：静态地址必须先经跳板活体证实才可 patch；VA/RVA 差 0x400000，
  笔记地址引用前先确认口径（历史三次误诊皆源于此，详见 NOTES v18o）
- 旧 EA 地址的语义对应用**指令特征 + 结构同构**定位（可运行的参照实现优先于推理——
  盗版 1.12 上的 FINAL3 是 ground truth）

## 功能状态速览

| 分组 | 功能 | 状态 |
|---|---|---|
| 资源 | 资金/电力/协议点数/解锁协议 | ✅ 实测通过 |
| 建造 | 快速建造/立即就绪/冻结敌方/无限缩放 | ✅ 桩就绪（立即就绪/冻结待复测） |
| 视野 | 地图全开 | ✅ 实测通过 |
| 选中单位 | 三星/弹药/经验/速度×2/冻结/血量×3/治疗/俘虏/摧毁/复制（14 项） | ✅ 实测通过（摧毁动画 v20 待验） |
| 其他 | 威胁×3/矿脉恢复/诊断（5 项） | ✅ 实测通过 |
| 战场增援 | 三 MCV/任意哈希增援/随地建造（5 项） | ✅ 实测通过 |
| 对照 FINAL3 缺失 | 禁止电脑建造/玩家无敌/一击必杀敌方/三星直调 | ⏳ 已定位待移植（NOTES v19c） |

原版作者：Ken22265（FINAL3，2009）。本项目为其功能的现代重制与扩展。
