using RA3MT.Core.Engine;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;
using RA3MT.Core.Target;

namespace RA3MT.Core.Features;

/// <summary>High-level trainer orchestration: attach → verify → install detours →
/// toggle flags / run selection actions.</summary>
public sealed class TrainerEngine : IDisposable
{
    public static TrainerEngine? Instance { get; private set; }

    private ProcessMemory? _mem;
    private MasterCode? _mc;
    private readonly SelectionActionState _actionState = new();
    private FeaturesData _data = FeaturesData.LoadEmbedded();

    public bool Attached { get; private set; }
    public bool RecoveryRequired { get; private set; }

    /// <summary>晋级桥显式开关：环境变量 RA3MT_RANK_BRIDGE=1/true，或 exe 旁存在
    /// rank-bridge.enable 标记文件（对用户可见可切换的持久开关）。
    /// 开启后仍需 RankApiResolver 对晋级函数的严格字节校验通过才会安装消费桩。</summary>
    public bool EnableRankBridge { get; set; } =
        Environment.GetEnvironmentVariable("RA3MT_RANK_BRIDGE") is "1" or "true"
        || File.Exists(Path.Combine(AppContext.BaseDirectory, "rank-bridge.enable"));

    public bool RankBridgeActive => Attached && _mc is { RankBridgeEnabled: true, RankMailbox: not null };

    /// <summary>俘虏/摧毁桥显式开关：环境变量 RA3MT_BRIDGES=1/true，或 exe 旁存在
    /// bridges.enable 标记文件。附加时逐一严格校验，失败者不安装。</summary>
    public bool EnableCaptureKillBridges { get; set; } =
        Environment.GetEnvironmentVariable("RA3MT_BRIDGES") is "1" or "true"
        || File.Exists(Path.Combine(AppContext.BaseDirectory, "bridges.enable"));

    public bool CaptureBridgeActive => Attached && _mc is { CaptureBridgeEnabled: true, CaptureMailbox: not null };
    public bool KillBridgeActive => Attached && _mc is { KillBridgeEnabled: true, KillMailbox: not null };
    public string Version { get; private set; } = "";
    public int Pid { get; private set; }
    public string ProcessPath { get; private set; } = "";
    public nuint Base { get; private set; }
    public int ResolvedSites { get; private set; }
    public int TotalSites => _data.Hooks.Count;

    public event Action<string>? Log;
    public event Action? StateChanged;

    private readonly Dictionary<string, bool> _toggleState = new();

    public IReadOnlyDictionary<string, bool> ToggleState => _toggleState;
    public FeaturesData Data => _data;

    public void Attach()
    {
        if (Attached) throw new InvalidOperationException("已附加");
        var found = ProcessMemory.FindGame(_data.Game.ModuleNames)
                    ?? throw new InvalidOperationException("未找到运行中的红警3进程（ra3_1.12/1.13.game）");

        var mem = new ProcessMemory(found.pid);
        MasterCode? pendingMaster = null;
        try
        {
            var main = System.Diagnostics.Process.GetProcessById(found.pid).MainModule
                       ?? throw new InvalidOperationException("无法读取主模块");
            var baseAddr = (nuint)main.BaseAddress;

            Log?.Invoke($"附加 {Path.GetFileName(found.modulePath)} (PID {found.pid}) 基址 0x{baseAddr:X}");
            var text = mem.Read(baseAddr + 0x1000, 0x7D0000);
            var sites = HookResolver.ResolveAll(
                _data, found.version,
                readRva: (rva, len) => mem.Read(baseAddr + rva, len),
                text,
                gameBase: baseAddr,
                log: Log);

            if (sites.Count != _data.Hooks.Count)
                throw new InvalidOperationException($"挂钩点校验不完整（{sites.Count}/{_data.Hooks.Count}），拒绝部分附加；请确认游戏版本且没有其他修改器挂钩");

            var rootRva = _data.Globals.PlayerRoot.RvaFor(found.version);

            // 游戏线程桥：显式开启且各 API 严格校验通过才接入；
            // 校验失败只降级为普通资金桩并告警，绝不带病安装消费桩。
            nuint rankApi = 0;
            if (EnableRankBridge)
            {
                try
                {
                    rankApi = Target.RankApiResolver.Resolve(found.version, baseAddr,
                        (rva, len) => mem.Read(baseAddr + rva, len));
                    Log?.Invoke($"晋级桥：晋级函数校验通过 0x{rankApi:X}（资金结算线程将安全调用）");
                }
                catch (Exception ex)
                {
                    Log?.Invoke($"晋级桥：校验失败，已保持默认资金桩（{ex.Message}）");
                }
            }
            nuint captureApi = 0, killApi = 0;
            if (EnableCaptureKillBridges)
            {
                try
                {
                    captureApi = Target.CaptureApiResolver.Resolve(found.version, baseAddr,
                        (rva, len) => mem.Read(baseAddr + rva, len));
                    Log?.Invoke($"俘虏桥：归属切换函数校验通过 0x{captureApi:X}");
                }
                catch (Exception ex)
                {
                    Log?.Invoke($"俘虏桥：校验失败，功能不可用（{ex.Message}）");
                }
                try
                {
                    killApi = Target.KillApiResolver.Resolve(found.version, baseAddr,
                        (rva, len) => mem.Read(baseAddr + rva, len));
                    Log?.Invoke($"摧毁桥：HP 调整函数校验通过 0x{killApi:X}");
                }
                catch (Exception ex)
                {
                    Log?.Invoke($"摧毁桥：校验失败，功能不可用（{ex.Message}）");
                }
            }

            var mc = new MasterCode(mem, baseAddr, baseAddr + rootRva, sites, _data.Hooks, Log,
                rankApi, captureApi, killApi);
            pendingMaster = mc;
            mc.Install();

            _mem = mem;
            _mc = mc;
            _actionState.Clear();
            Attached = true;
            RecoveryRequired = false;
            Version = found.version;
            Pid = found.pid;
            ProcessPath = found.modulePath;
            Base = baseAddr;
            ResolvedSites = sites.Count;
            foreach (var f in _data.Features)
                if (f.Kind == "toggle") _toggleState[f.Id] = false;

            Log?.Invoke($"修改器已就绪：{sites.Count}/{_data.Hooks.Count} 挂钩点全部通过原始字节校验 ✓");
            StateChanged?.Invoke();
        }
        catch (Exception installError)
        {
            try { pendingMaster?.Uninstall(); }
            catch (Exception rollbackError)
            {
                _mem = mem;
                _mc = pendingMaster;
                Attached = true;
                RecoveryRequired = true;
                Version = found.version;
                Pid = found.pid;
                ProcessPath = found.modulePath;
                StateChanged?.Invoke();
                throw new AggregateException("附加失败且恢复不完整，功能已禁用；请重试脱离或重启游戏", installError, rollbackError);
            }
            mem.Dispose();
            throw;
        }
    }

    public void Detach()
    {
        if (!Attached) return;
        try { _mc?.Uninstall(); }
        catch (Exception ex)
        {
            RecoveryRequired = true;
            StateChanged?.Invoke();
            Log?.Invoke("卸载失败，功能已禁用；请重试脱离或重启游戏: " + ex.Message);
            return;
        }
        _mem?.Dispose();
        _mem = null;
        _mc = null;
        _actionState.Clear();
        Attached = false;
        RecoveryRequired = false;
        foreach (var k in _toggleState.Keys.ToList()) _toggleState[k] = false;
        Log?.Invoke("已从游戏进程脱离，全部挂钩已还原。");
        StateChanged?.Invoke();
    }

    public (bool ok, string msg) SetToggle(string featureId, bool on)
    {
        if (RecoveryRequired) return (false, "挂钩恢复未完成，禁止启用功能");
        if (!Attached || _mc == null) return (false, "未附加");
        var f = _data.Features.FirstOrDefault(x => x.Id == featureId);
        if (f?.Kind != "toggle" || f.Flag == null) return (false, "功能尚未可用或无开关标志");
        try
        {
            _mc.SetFlag(f.Flag, on);
            _toggleState[featureId] = on;
            Log?.Invoke($"{f.Name} = {(on ? "开" : "关")}");
            StateChanged?.Invoke();
            return (true, "");
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }

    public (bool ok, string msg) ExecuteAction(string featureId)
    {
        if (RecoveryRequired) return (false, "挂钩恢复未完成，禁止执行动作");
        if (!Attached || _mem == null) return (false, "未附加");
        var f = _data.Features.FirstOrDefault(x => x.Id == featureId);
        if (f?.Kind != "action" || f.Action == null) return (false, "功能尚未可用或非动作型功能");
        try
        {
            if (f.Action == "diag")
                return DiagDump();
            if (_mc == null)
                return (false, "修改器未初始化");

            // 威胁等级恢复 = 关闭两个覆盖开关（FINAL3 Normal 语义：不保存旧值）
            if (f.Action == "threatnormal")
            {
                _mc.SetFlag("threatmax", false);
                _mc.SetFlag("threatzero", false);
                _toggleState["threat_max"] = false;
                _toggleState["threat_zero"] = false;
                Log?.Invoke("威胁等级恢复：覆盖已关闭，交还游戏自然重算");
                StateChanged?.Invoke();
                return (true, "");
            }

            // 晋级桥路径：请求经资金结算（游戏线程）分派到已配对的晋级函数
            if (f.Action == "lv" && RankBridgeActive)
                return SubmitBridgeRequests(f.Name, BridgeKind.Rank);
            if (f.Action == "capture")
            {
                if (CaptureBridgeActive) return SubmitBridgeRequests(f.Name, BridgeKind.Capture);
                return (false, "需要 bridges.enable 启用俘虏桥并通过校验（直接改属主指针不安全，已禁用）");
            }
            if (f.Action == "destroy")
            {
                if (KillBridgeActive) return SubmitBridgeRequests(f.Name, BridgeKind.Kill);
                return (false, "需要 bridges.enable 启用摧毁桥并通过校验（直接清血量绕过死亡流程，已禁用）");
            }

            var n = SelectionActions.Apply(_mem, _data, Version!, f.Action, Base, _actionState);
            Log?.Invoke($"{f.Name}: 作用于 {n} 个选中目标");
            return (n > 0, n > 0 ? "" : "没有可处理的选中目标（未选中或目标不支持此功能）");
        }
        catch (Exception ex)
        {
            Log?.Invoke($"{f.Name} 失败: {ex.Message}");
            return (false, ex.Message);
        }
    }

    private enum BridgeKind { Rank, Capture, Kill }

    /// <summary>向游戏线程桥逐个提交选中目标：每次提交后等待资金结算消费（限时），
    /// 再提交下一个。邮箱同时只允许一个未完成请求。</summary>
    private (bool, string) SubmitBridgeRequests(string featureName, BridgeKind kind)
    {
        var mailbox = _mc!;
        uint MailState() => kind switch
        {
            BridgeKind.Rank => mailbox.RankMailbox!.State,
            BridgeKind.Capture => mailbox.CaptureMailbox!.State,
            _ => mailbox.KillMailbox!.State,
        };
        void SubmitOne(uint body, uint drawable, uint third)
        {
            switch (kind)
            {
                case BridgeKind.Rank: mailbox.RankMailbox!.Submit(body, drawable, third); break;
                case BridgeKind.Capture: mailbox.CaptureMailbox!.Submit(body, drawable); break;
                default: mailbox.KillMailbox!.Submit(body, drawable, third); break;
            }
        }

        var targets = kind switch
        {
            BridgeKind.Rank => SelectionActions.EnumerateRankTargets(_mem!, _data, Version!, Base)
                .Select(t => (t.body, t.drawable, t.tracker)).ToList(),
            BridgeKind.Capture => SelectionActions.EnumerateCaptureTargets(_mem!, _data, Version!, Base)
                .Select(t => (t.body, t.drawable, 0u)).ToList(),
            _ => SelectionActions.EnumerateKillTargets(_mem!, _data, Version!, Base)
                .Select(t => (t.body, t.drawable, t.hp)).ToList(),
        };
        if (targets.Count == 0)
            return (false, kind switch
            {
                BridgeKind.Rank => "没有可晋级目标（未选中或不支持经验）",
                BridgeKind.Capture => "没有可俘虏目标（未选中或目标已属己方）",
                _ => "没有可摧毁目标（未选中或无生命组件）",
            });

        const int perTargetTimeoutMs = 800;
        const int totalBudgetMs = 4000;
        var sw = System.Diagnostics.Stopwatch.StartNew();
        var applied = 0;
        var rejected = 0;
        var outstanding = 0;
        for (var i = 0; i < targets.Count; i++)
        {
            var (body, drawable, third) = targets[i];
            try
            {
                SubmitOne(body, drawable, third);
            }
            catch (InvalidOperationException ex)
            {
                var busyState = MailState();
                Log?.Invoke($"{featureName}: 0x{body:X} 未提交（邮箱状态 {busyState}: {ex.Message}）");
                outstanding += targets.Count - i;
                break;
            }
            // 等待游戏线程消费（资金结算频率约一次/秒内）
            var deadline = System.Diagnostics.Stopwatch.StartNew();
            uint state;
            while (true)
            {
                state = MailState();
                if (state is 3 or 4) break;
                if (deadline.ElapsedMilliseconds > perTargetTimeoutMs ||
                    sw.ElapsedMilliseconds > totalBudgetMs) break;
                Thread.Sleep(25);
            }
            if (state == 3) applied++;
            else if (state == 4) rejected++;
            else outstanding++;
            if (sw.ElapsedMilliseconds > totalBudgetMs)
            {
                outstanding += targets.Count - i - 1;
                break;
            }
        }
        var msg = applied > 0
            ? $"已作用于 {applied}/{targets.Count} 个目标"
            : "游戏线程未消费请求（资金未结算？稍后重试）";
        if (rejected > 0) msg += $"，{rejected} 个被校验拒绝";
        if (outstanding > 0) msg += $"，{outstanding} 个待处理（再次触发继续）";
        Log?.Invoke($"{featureName}: {msg}");
        StateChanged?.Invoke();
        return (applied > 0, applied > 0 ? "" : msg);
    }

    private (bool, string) DiagDump()
    {
        if (_mc == null || _mem == null) return (false, "未附加");
        var diag = _mc.ReadDiagnostics();
        if (diag == null)
            return (false, "诊断区不可用");
        var (esi, prodEax, prodEsi, owner, selEntry, selArr, selIdx, weaponEax) = diag.Value;
        var rootRva = _data.Globals.PlayerRoot.RvaFor(Version!);
        var root = _mem.ReadU32(Base + rootRva);
        Log?.Invoke("──── 诊断采集 ────");
        Log?.Invoke($"MasterCode块=0x{_mc.Block:X}  controller=0x{root:X}  本地阵营={(root >= 0x10000 ? SafeRead(root + 0x28) : "<无上下文>")}");
        var selected = SelectionActions.ReadSelection(_mem.ReadU32,
            address => _mem.Read(address, 1)[0], Base + _data.Globals.SelectionList.RvaFor(Version));
        Log?.Invoke($"真实选中目标={selected.Length}: {string.Join(", ", selected.Select(body => $"0x{body:X}"))}");
        Log?.Invoke($"money_h1.esi=0x{esi:X}   build_power.eax=0x{prodEax:X} esi=0x{prodEsi:X} [eax+418]={owner}");
        Log?.Invoke($"UI.weaponEntry=0x{selEntry:X} weaponArray=0x{selArr:X} index={selIdx}");
        Log?.Invoke($"legacyAccessor.threatComponent=0x{weaponEax:X}");
        if (prodEax > 0x10000)
        {
            Log?.Invoke($"  [prod+0x20]={_mem.ReadU32(prodEax + 0x20)} [prod+0x418]={SafeRead(prodEax + 0x418)}");
        }
        if (weaponEax > 0x10000)
        {
            Log?.Invoke($"  威胁组件（非弹药）: [+4]={SafeRead(weaponEax + 4)} [+8]={SafeRead(weaponEax + 8)} " +
                        $"[+0xC]={SafeRead(weaponEax + 0xC)} [+0x10]={SafeRead(weaponEax + 0x10)} [+0x1C]byte={SafeReadByte(weaponEax + 0x1C)}");
        }
        if (selEntry > 0x10000)
        {
            Log?.Invoke($"  UI武器弹夹[+0x1C]={SafeRead(selEntry + 0x1C)} slot[+8]={SafeRead(selEntry + 8)}");
        }
        Log?.Invoke("──────────────");
        return (true, "");
    }

    private string SafeReadByte(nuint addr)
    {
        try { return $"0x{_mem!.Read(addr, 1)[0]:X2}"; }
        catch { return "<不可读>"; }
    }

    private string SafeRead(nuint addr)
    {
        try { return $"0x{_mem!.ReadU32(addr):X}"; }
        catch { return "<不可读>"; }
    }

    public bool IsOn(string featureId) => _toggleState.TryGetValue(featureId, out var v) && v;

    public void Dispose() => Detach();

    /// <summary>Locate the game's Data directory on disk (Steam layout).</summary>
    public static string? FindGameDataDir()
    {
        var candidates = new List<string>();
        var pf86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
        var vdf = Path.Combine(pf86, "Steam", "steamapps", "libraryfolders.vdf");
        if (File.Exists(vdf))
        {
            foreach (var line in File.ReadAllLines(vdf))
            {
                var t = line.Trim();
                if (t.StartsWith("\"path\""))
                {
                    var p = t.Split('"')[3].Replace(@"\\", "/");
                    candidates.Add(p);
                }
            }
        }
        candidates.Add(Path.Combine(pf86, "Steam"));
        candidates.Add(@"D:\Steam");
        candidates.Add(@"E:\Steam");
        foreach (var c in candidates)
        {
            var data = Path.Combine(c, "steamapps", "common", "Command and Conquer Red Alert 3", "Data");
            if (Directory.Exists(data) && File.Exists(Path.Combine(data, "ra3_1.13.game")))
                return data;
        }
        return null;
    }
}
