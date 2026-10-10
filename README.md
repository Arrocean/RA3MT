# RA3MT — 红色警戒 3 现代修改器

以 Ken22265 的 24 项经典修改器（2009，EA 原版 1.12）为蓝本的重制版：
**C# / .NET 10 + WPF**，支持 **1.12 与 1.13（2024 终极合集版）**，24 项功能对齐原版并有新增。

> 仅限单机使用，联网对战不可用。仅供学习研究。

## 构建

- 需要 .NET 10 SDK（本机已装 10.0.401）+ WindowsDesktop 运行时
- `dotnet build RA3MT.slnx -c Release`
- **直接使用（推荐）**：`dotnet publish src/RA3MT.UI -c Release -r win-x86 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o publish`
  → `publish/RA3MT.UI.exe`（约 55MB，自包含 .NET 10 x86 运行时，**无需安装任何运行时**；
  同目录的 wpfgfx/PenImc/vcruntime/D3DCompiler 四个原生 DLL 需与 exe 同行）
- 产物为 **x86** 并要求管理员运行（manifest）——写 32 位游戏进程内存所必需

## 项目结构

```
assets/features.json      全部数据：26 项功能定义 + 16 个挂钩点（双版本 RVA、被替换字节、
                          AOB 特征码）+ 选中列表/玩家索引全局（Core 以嵌入资源引用）
src/RA3MT.Core            引擎：进程内存读写 / 挂钩解析（字节防呆 + 特征码后备）/
                          x86 桩生成 (StubGen) / MasterCode 安装器 / 选中单位遍历
src/RA3MT.SelfCheck       离线自检：在 ra3_1.12/1.13.game 上逐点验证；
                          `dotnet run --project src/RA3MT.SelfCheck -- stubdump <dir>`
                          导出全部桩字节码供反汇编审计
src/RA3MT.UI              WPF 主程序（WeMod 风格界面，MVVM，全局热键）
tools/analysis/*.py       逆向分析脚本（特征码生成、距离插值定位、反汇编验证）
artifacts/stubs/          桩导出产物（capstone 已验证）
```

## 自检结果（2026-10-10）

```
挂钩点校验: 32/32 通过（1.12 × 16 + 1.13 × 16，字节级）
AOB 特征码: 8 个跨版本唯一模式
桩反汇编:   16/16 全字节有效指令，跳转目标全部精确回站
```

## 运行

1. Steam 启动红警3（进入主菜单即可），右键管理员运行修改器
2. 修改器会自动找到 `ra3_1.12.game` / `ra3_1.13.game` 进程 → 点「附加进程」
3. 附加时逐点校验被替换的原始指令字节，不匹配即拒绝挂钩（防呆）
4. 开关型功能 = 翻转 MasterCode 标志字节（游戏线程执行桩）；动作型（选中单位类）= 遍历选中链表写对象字段
5. 「脱离进程」恢复全部原始字节

## 技术要点

- 游戏 32 位、ImageBase 0x400000、无 ASLR/无 NX；重打包版代码与 EA 原版**存在区域偏移**，
  老修改器脚本的绝对地址不可直接使用——本项目的 RVA 全部按「被替换字节搜索 + 函数内相对距离 +
  多锚点插值」在两个重打包版上重新定位（见 `tools/analysis/`）
- 每个 stub 以 `pushfd/popfd` 包裹（游戏 EFLAGS 不受影响）；两个特殊站点
  （`power_cool`、`zoom_unit_xp`）的游戏后续指令消费桩设置的 ZF，沿用原版 TMK 的分支控制技巧
- 协议/超武「立即就绪」「冻结敌方」需要本地玩家索引：`[root+0x28]`
  （root 为 `.data` 全局，1.12: `0x8DDE84` / 1.13: `0x8E21A4`，访问模式已在 .text 确认）

## 状态

| 分组 | 功能 | 状态 |
|---|---|---|
| 资源 | 无限资金/电力、协议点数、解锁协议 | ✅ 桩就绪 |
| 建造 | 快速建造、立即就绪、冻结敌方、瞬间完成 | ✅ 桩就绪（立即就绪/冻结的栈槽偏移需实测） |
| 视野 | 技能零冷却、地图全开 | ✅ 桩就绪（零冷却语义需实测） |
| 选中单位 | 经验999、无限弹药（钩子）＋ 等级/速度×2/冻结×2/血量×3/俘虏/摧毁（遍历） | ✅ 就绪（遍历字段偏移来自原版脚本，需实测） |
| 其他 | 威胁等级×3、矿脉恢复 | ⏳ 待逆向（对应全局未定位） |

原版作者：Ken22265（TMK 架构，2009-08-19 Final.2a）。
