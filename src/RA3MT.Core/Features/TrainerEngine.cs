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
    private FeaturesData _data = FeaturesData.LoadEmbedded();

    public bool Attached { get; private set; }
    public bool RecoveryRequired { get; private set; }
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
            var mc = new MasterCode(mem, baseAddr, baseAddr + rootRva, sites, _data.Hooks, Log);
            pendingMaster = mc;
            mc.Install();

            _mem = mem;
            _mc = mc;
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

            var n = SelectionActions.Apply(_mem, _data, Version!, f.Action, Base);
            Log?.Invoke($"{f.Name}: 作用于 {n} 个选中目标");
            return (n > 0, n > 0 ? "" : "没有可处理的选中目标（未选中或目标不支持此功能）");
        }
        catch (Exception ex)
        {
            Log?.Invoke($"{f.Name} 失败: {ex.Message}");
            return (false, ex.Message);
        }
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
