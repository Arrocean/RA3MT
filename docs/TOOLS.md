# 工具与检查入口

本文对应 **v261025-8**，2026-10-25 完成脚本整理。所有命令从仓库根目录执行。当前保留 **5 个证据/数据工具、14 个离线审计/回归脚本或共享模块**；游戏修改逻辑由 C# Core 维护，Python 不再保留第二套修改器实现。

`artifacts` 不参与修改器的构建、发布或运行。版本控制只保留 `baseline_stubs/` 回归基线及 `final3/`、`uprising-final/` 原件脚本归档；`stubs_semantic/` 等当前导出、日志、截图与临时镜像均不提交，检查前按下文命令生成。

## 环境与镜像

需要 Windows、.NET 10 SDK（含 Windows Desktop 支持）和 Python。离线 Python 依赖已按本次实际检查环境固定：

```powershell
py -m pip install -r tools/requirements.txt
```

`requirements.txt` 包含 pefile 2024.8.26、capstone 5.0.9、unicorn 2.1.4。无需通过运行旧修改器提取脚本。

三构建审计需要 EA 1.0、Steam 1.0 和 Steam 1.01 的原始游戏程序：

| 构建键 | 模块名 | Python 镜像别名 |
|---|---|---|
| `uprising-1.0ea` | EA `ra3ep1_1.0.game` | `ea` |
| `uprising-1.0` | Steam `ra3ep1_1.0.game` | `s0` |
| `uprising-1.01` | Steam `ra3ep1_1.1.game` | `s1` |

C# `uprisingtest` 可使用 `RA3MT_UPRISING_EA_IMAGE`、`RA3MT_UPRISING_10_IMAGE`、`RA3MT_UPRISING_101_IMAGE` 指定程序文件。Python 工具从 `tools/analysis/uprising_probe.py` 的 `PATHS` 表取路径；更换安装位置需要同步该表，C# 环境变量不会自动覆盖 Python 路径。

原版检查自动寻找 Steam `Data` 目录；EA 原版可通过 `RA3MT_EA_DIR` 指定包含 `ra3_1.12.game` 的 `Data` 目录。

## 常用离线检查

### 起义时刻三个构建

```powershell
py tools/harness/run_uprising_audit.py
```

此入口构建解决方案、运行只读磁盘审计和 C# `uprisingtest`，分别导出三个构建的机器码并运行十套离线检查，最后执行 WPF 检查。它不发现、附加或写入游戏进程。

输出：

- `artifacts/uprising/static-audit.json`：镜像哈希、挂钩、契约及控制流检查结果。
- `artifacts/audit/<构建>/`：该构建实际导出的机器码和元数据。
- `artifacts/audit/<构建>.log`、`results.json`：各套件结果。
- `artifacts/uprising/ui-preview*.png`：WPF 检查预览。

当前结果为每构建 903 个执行用例，共 2,709 个；另有 84 处挂钩、63 段契约和 10,302 项字节篡改拒绝检查。结果的实战边界见 [UPRISING.md](UPRISING.md)。

仅重跑磁盘契约/控制流检查可使用：

```powershell
py tools/analysis/audit_uprising.py
```

它读取当前预期字节，不更新 `assets/uprising.json`。

### 原版与通用机制

```powershell
dotnet build RA3MT.slnx -c Release
py tools/harness/stub_regression.py
dotnet run --project src/RA3MT.SelfCheck -c Release --no-build -- stubdump artifacts/stubs_semantic 1.13
```

基线检查重新导出并比较 `artifacts/baseline_stubs/` 当前 34 份原版桩；`stubdump` 为随后执行的原版 Python 套件准备当前字节。

C# 离线模式按改动选择：

```powershell
$checks = @('bridgetest','rankmailboxtest','ranktest','actiontest','installertest','resolvertest','asmtest','selectiontest','featuretest','layouttest','spawntest','reinforcetest','processtest','identitytest')
foreach ($check in $checks) {
    dotnet run --project src/RA3MT.SelfCheck -c Release --no-build -- $check
    if ($LASTEXITCODE) { throw "SelfCheck failed: $check" }
}
```

不指定模式时，`SelfCheck` 检查原版游戏镜像的挂钩地址。`processtest` 只检查本机进程句柄/退出状态，不访问游戏。

`identitytest` 的 157 项检查覆盖永久常量、标准 FNV 向量、标记格式、损坏拒绝、块布局、清单一致性，以及自建辅助进程中的真实跨进程读取、命名对象发现及退出清理；不访问游戏。`identity-child` 是它内部启动的辅助入口，无需手工运行。该检查也包含在起义时刻一键审计中。平台接入规则见 [DETECTION.md](DETECTION.md)。

原版 Python 套件可单独运行：

```powershell
py tools/harness/test_disabled_stubs.py
py tools/harness/test_execution_stubs.py
py tools/harness/test_rank_dispatcher.py
py tools/harness/test_bridge_dispatchers.py
py tools/harness/test_rank_money_bridge.py
py tools/harness/test_semantic_stubs.py
py tools/harness/test_unpack_schedule.py
py tools/harness/test_spawn_dispatcher.py artifacts/stubs_semantic
```

`game_fixture.py` 默认使用原版 1.13 和 `artifacts/stubs_semantic`。批量审计会设置 `RA3MT_GAME_BUILD` 与 `RA3MT_STUBS_DIR` 来选择独立起义构建；手动设置后应清除，避免后续误用其他构建的数据。

纯界面检查：

```powershell
dotnet run --project src/RA3MT.UI.SelfCheck -c Release
```

只有审阅并解释了有意的机器码变更后，才能更新基线；`stub_regression.py --freeze` 会重建预期结果，不是修复未知回归的办法。

## 保留脚本清单

### `tools/analysis/`（5 个）

| 文件 | 用途 | 写入范围 |
|---|---|---|
| `extract_final3.py` | 从原版或起义时刻 FINAL 原件提取滚动 XOR 的 CE 脚本及来源哈希 | 指定输出目录 |
| `gen_reinforce_table.py` | 从游戏 BIG/manifest/语言包生成对应产品增援目录 | 指定 JSON |
| `uprising_probe.py` | 读取磁盘 PE、扫描和反汇编；也被审计、契约生成及原生指令回归导入 | 无；不打开进程 |
| `build_uprising_contracts.py` | 从三个已确认镜像重建地址与精确契约，保留手工 `features` | `assets/uprising.json` |
| `audit_uprising.py` | 独立核对预期字节、完整指令、调用/清栈、分支和布局证据 | `artifacts/uprising/static-audit.json` |

数据生成命令示例（引号中的路径换成本机路径）：

```powershell
py tools/analysis/extract_final3.py "原修改器.exe" "artifacts/提取目录"
py tools/analysis/gen_reinforce_table.py --game-dir "原版安装根目录" -o assets/reinforcement_codes.json
py tools/analysis/gen_reinforce_table.py --game-dir "起义时刻安装根目录" -o assets/uprising_reinforcement_codes.json
py tools/analysis/build_uprising_contracts.py
```

后三个命令会更新项目数据；不应作为普通检查例行运行。检查当前元数据用 `audit_uprising.py`，不要用生成器覆盖它来掩盖失配。

### `tools/harness/`（14 个）

| 文件 | 覆盖范围 |
|---|---|
| `run_uprising_audit.py` | 三构建审计编排入口 |
| `stub_regression.py` | 原版导出桩基线比较 |
| `game_fixture.py` | 构建、桩目录与独立对象字段的共享测试配置，不直接运行 |
| `test_disabled_stubs.py` | 关闭功能时与原始指令的寄存器/数据/栈/浮点状态对照 |
| `test_execution_stubs.py` | 功能开关、所有者、空指针、弹药等实际机器码执行 |
| `test_rank_dispatcher.py` | 晋级认领、资格校验、调用与上下文保存 |
| `test_bridge_dispatchers.py` | 俘虏/摧毁调用、校验及 ABI/FX 保存 |
| `test_rank_money_bridge.py` | 结算入口与晋级桥组合 |
| `test_spawn_dispatcher.py` | 模板/所有者、鼠标转换失败回退、增援间距及 ABI/FX |
| `test_semantic_stubs.py` | 原版导出桩的反汇编结构检查 |
| `test_unpack_schedule.py` | 苏军展开开始帧与事件句柄混用的已知回归 |
| `test_uprising_stubs.py` | 挑战资金单次请求/溢出、挑战时间、电力 UI |
| `test_uprising_continuations.py` | 真实 PE 的视野继承与相机后续分支 |
| `test_uprising_resource_forks.py` | 真实 PE 的电力/协议空分支和电力桥栈行为 |

这些套件消费 C# 实际导出字节，不维护第二套 Python 修改桩。

## 显式实机诊断

以下入口不包含在离线批量检查中：

| SelfCheck 参数 | 行为 |
|---|---|
| `livetest` | 只读解析运行中原版的构建、挂钩和桥；不安装 |
| `livetest uprising [PID]` | 对起义时刻执行相同只读检查 |
| `uprising-selectiontest [PID]` | 只读选中链、升星/摧毁/复制目标；需要选中普通可晋级作战单位，可在修改器已附加时使用 |
| `uprisingattachtest [PID]` | **会安装全部挂钩**，保持功能关闭，一秒后脱离并检查原始字节恢复；需要游戏无其他修改器附加 |

前两项用未改写的站点识别构建，适用于尚未附加修改器的游戏。选中链诊断从磁盘判别构建，可在已附加时执行。只读诊断仍需操作系统允许打开对应游戏进程。

## 已删除的 12 个旧脚本

| 文件 | 清理原因与替代方式 |
|---|---|
| `analysis/_layout_probe.csx` | 临时布局草稿，使用失效 API；由 C# `layouttest` 替代 |
| `analysis/patchtest_buildanywhere.py` | 随地建造定案前的临时写入实验；结论已进入正式功能 |
| `analysis/trace_trampoline.py` | 仅服务旧原版地址的实验跳板/放置采样器；当前解析与离线检查使用 Core |
| `analysis/watch_text_diff.py` | 旧修改器对照实验的一次性 `.text` 差分监视器；定位结论已保存 |
| `analysis/check_trace_sites.py` | 仅检查已删除跳板的旧 1.13 站点 |
| `analysis/verify_tramp_v2.py` | 已删除实验跳板的配套检查 |
| `harness/test_trampoline.py` | 已删除实验跳板的配套检查，非当前生产桩回归 |
| `harness/attach.py` | 早期 1.13 Python 修改器，地址/功能集已过时 |
| `harness/pystubs.py` | 早期 Python 桩副本，仍包含旧对象判断；Core 为唯一实现 |
| `harness/check_stubs.py` | 比较过时 Python 副本；由当前 C# 导出与基线比较替代 |
| `harness/gclick.py` | 固定 PID 和缩放比例的旧点击脚本，无当前消费者 |
| `harness/memutil.py` | 无当前消费者的早期进程扫描/写入辅助模块 |

历史文档中的旧名称和实验命令作为证据过程保留，不能继续当作当前运行指南。原件提取脚本、CE 原文、来源 manifest、生产桩基线及有实际覆盖范围的离线检查继续保留。
