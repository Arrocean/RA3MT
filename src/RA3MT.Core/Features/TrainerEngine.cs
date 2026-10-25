using RA3MT.Core.Engine;
using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Host;
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
    private BridgeCoordinator? _bridges;   // session-bound, see Attach/Detach
    private readonly SelectionActionState _actionState = new();
    private FeaturesData _data = FeaturesData.LoadEmbedded();

    public bool Attached { get; private set; }
    public bool RecoveryRequired { get; private set; }

    /// <summary>晋级桥开关：默认开启（四桥已达 FINAL3 对等并多轮实测）。
    /// 设置环境变量 RA3MT_RANK_BRIDGE=0/false 可在排障时关闭。
    /// 开启后仍需 RankApiResolver 对晋级函数的严格字节校验通过才会安装消费桩。</summary>
    public bool EnableRankBridge { get; set; } =
        Environment.GetEnvironmentVariable("RA3MT_RANK_BRIDGE") is not ("0" or "false");

    public bool RankBridgeActive => _bridges is not null && _bridges.IsActive(BridgeId.Rank);

    /// <summary>俘虏/摧毁桥开关：默认开启；RA3MT_BRIDGES=0/false 可关闭。
    /// 附加时逐一严格校验，失败者不安装。</summary>
    public bool EnableCaptureKillBridges { get; set; } =
        Environment.GetEnvironmentVariable("RA3MT_BRIDGES") is not ("0" or "false");

    public bool CaptureBridgeActive => _bridges is not null && _bridges.IsActive(BridgeId.Capture);
    public bool KillBridgeActive => _bridges is not null && _bridges.IsActive(BridgeId.Kill);

    /// <summary>生成桥开关：默认开启；RA3MT_SPAWN=0/false 可关闭（复制选中/三阵营基地车/战场增援）。
    /// 需要生成 wrapper、哈希查找、哈希表全局三项全部严格校验通过才安装消费桩。</summary>
    public bool EnableSpawnBridge { get; set; } =
        Environment.GetEnvironmentVariable("RA3MT_SPAWN") is not ("0" or "false");

    public bool SpawnBridgeActive => _bridges is not null && _bridges.IsActive(BridgeId.Spawn);

    public string Version { get; private set; } = "";
    public int Pid { get; private set; }
    public string ProcessPath { get; private set; } = "";
    public nuint Base { get; private set; }
    public int ResolvedSites { get; private set; }
    public int TotalSites => _data.Hooks.Count;

    public event Action<string>? Log;
    public event Action? StateChanged;

    /// <summary>Raised once when the attached game process exits (thread-pool
    /// thread). The UI marshals this to its own thread and calls
    /// <see cref="Detach"/>, which takes the dead-process fast path.</summary>
    public event Action? GameExited;

    private System.Diagnostics.Process? _proc;   // liveness watcher (Exited event)
    private readonly object _detachGate = new(); // detach may race: UI click vs game exit

    /// <summary>Owner of the on/off state for stub-flag features. Created eagerly so
    /// the UI can read it before the first attach; the flag writes themselves are
    /// routed through <see cref="WriteFeatureFlag"/> and need an installed block.</summary>
    private SwitchBank _switches;
    private FeatureRegistry _registry;
    private readonly Dictionary<string, IFeatureState> _featureStates = new(StringComparer.Ordinal);
    private FeatureServiceRegistry _services = new();

    public IReadOnlyDictionary<string, bool> ToggleState => _switches.Snapshot;
    public FeaturesData Data => _data;
    public FeatureRegistry Registry => _registry;
    public GameDefinition Game { get; private set; } = GameCatalog.RedAlert3;

    public void SelectGame(GameId game)
    {
        if (Attached || RecoveryRequired) throw new InvalidOperationException("请先脱离当前游戏再切换");
        if (Game.Id == game) return;
        var definition = GameCatalog.Get(game);
        var data = FeaturesData.LoadEmbedded(game);
        var registry = FeatureCatalog.Build(data, this);
        _data = data;
        Game = definition;
        _registry = registry;
        _switches = new SwitchBank(_data,WriteFeatureFlag,m => Log?.Invoke(m));
        _featureStates.Clear();
        Version = ""; Pid = 0; ProcessPath = ""; Base = 0; ResolvedSites = 0;
        StateChanged?.Invoke();
    }

    public TrainerEngine()
    {
        _registry = FeatureCatalog.Build(_data, this);
        _switches = new SwitchBank(_data, WriteFeatureFlag, m => Log?.Invoke(m));
    }

    /// <summary>Create one state object per declared feature for this session.
    /// Failure to create one feature must not block the others.</summary>
    private void CreateFeatureStates()
    {
        _featureStates.Clear();
        _services = BuildServices();
        var context = new FeatureContext
        {
            Session = new SessionSnapshot
            {
                Memory = _mem!,
                Version = Version,
                ImageBase = Base,
                Pid = Pid,
                ProcessPath = ProcessPath,
                ResolvedSites = ResolvedSites,
                TotalSites = TotalSites,
            },
            Symbols = new SessionSymbols(_data, _mem!, Version, Base),
            Data = _data,
            Host = new FeatureHost
            {
                Log = m => Log?.Invoke(m),
                NotifyStateChanged = () => StateChanged?.Invoke(),
                Memory = _mem!,
                Services = _services,
                Symbols = new SessionSymbols(_data, _mem!, Version, Base),
            },
        };
        foreach (var feature in _registry.Features)
        {
            if (feature.Kind == FeatureKind.Pending) continue;
            try
            {
                _featureStates[feature.Id] = feature.CreateState(context);
            }
            catch (Exception ex)
            {
                Log?.Invoke($"⚠ 功能 {feature.Id} 初始化失败，已跳过: {ex.Message}");
            }
        }
    }

    /// <summary>Capabilities features may depend on for this session.</summary>
    private FeatureServiceRegistry BuildServices()
    {
        var registry = new FeatureServiceRegistry();
        registry.Register<IGameMemory>(new GameMemory(_mem!, Version, Base));
        registry.Register<ISwitchBank>(_switches);
        registry.Register<Actions.IFlagRequests>(new Actions.FlagRequests(WriteFeatureFlag));
        var bridges = _bridges ?? throw new InvalidOperationException("桥协调器需要已附加的会话");
        registry.Register<IBridgeGateway>(new EngineAdapters.BridgeGateway(
            bridges.IsActive, (id, name) => bridges.SubmitSelected(name, id)));
        registry.Register<ISpawnGateway>(new EngineAdapters.SpawnGateway(
            bridges.IsActive(BridgeId.Spawn),
            bridges.CopyHolders,
            bridges.MouseGround,
            bridges.SelectionAnchor,
            (name, reqs) => bridges.SubmitSpawnRequests(name, reqs, false),
            bridges.SubmitReinforcement,
            (name, reqs) => bridges.SubmitSpawnRequests(name, reqs, true)));
        return registry;
    }

    /// <summary>Write one stub flag through the installed block.</summary>
    private FeatureResult WriteFeatureFlag(string flag, bool on)
    {
        if (_mc is null) return FeatureResult.Failure("修改器未初始化");
        try
        {
            _mc.SetFlag(flag, on);
            return FeatureResult.Success;
        }
        catch (Exception ex)
        {
            return FeatureResult.Failure(ex.Message);
        }
    }

    /// <summary>API addresses a bridge needs, or 0 when the capability was not
    /// requested or its contract did not verify. A zero address means "bridge off",
    /// which is exactly how <see cref="MasterCode"/> decides what to install.</summary>
    private readonly record struct BridgeApis(
        nuint Rank, nuint Capture, nuint KillDamageEntry, nuint KillDeathMarker,
        nuint SpawnWrapper, nuint HashLookup, nuint HashTableGlobal,
        nuint MouseObjectGlobal, nuint MouseTransform);

    /// <summary>Resolve every optional bridge capability. Each resolver is
    /// individually fenced: a contract mismatch downgrades that one bridge and is
    /// reported, instead of aborting the whole attach or installing something
    /// unverified. The feature switches only decide whether we bother resolving.</summary>
    private BridgeApis ResolveBridgeApis(string version, nuint imageBase, Target.IImageReader image)
    {
        nuint rank = 0, capture = 0, kill = 0, marker = 0;
        nuint spawnWrapper = 0, hashLookup = 0, hashTableGlobal = 0;
        nuint mouseObjGlobal = 0, mouseTransform = 0;

        if (EnableRankBridge)
        {
            Target.ApiResolverCatalog.TryResolve("晋级桥",
                () => Target.RankApiResolver.Resolve(version, imageBase, image),
                resolved => rank = resolved.Value,
                reason => Log?.Invoke($"晋级桥：{reason}"));
        }

        if (EnableCaptureKillBridges)
        {
            Target.ApiResolverCatalog.TryResolve("俘虏桥",
                () => Target.CaptureApiResolver.Resolve(version, imageBase, image),
                resolved => capture = resolved.Value,
                reason => Log?.Invoke($"俘虏桥：{reason}，功能不可用"));
            Target.ApiResolverCatalog.TryResolve("摧毁桥",
                () => Target.KillApiResolver.Resolve(version, imageBase, image),
                resolved =>
                {
                    kill = resolved.damageEntry;
                    marker = resolved.deathMarker;
                },
                reason => Log?.Invoke($"摧毁桥：{reason}，功能不可用"));
        }

        if (EnableSpawnBridge)
        {
            Target.ApiResolverCatalog.TryResolve("生成桥",
                () =>
                {
                    var wrapper = Target.SpawnApiResolver.Resolve(version, imageBase, image);
                    var support = Target.SpawnSupportApiResolver.Resolve(version, imageBase, image);
                    return (wrapper, support.TemplateHashLookup, support.HashTableOwnerGlobal,
                        support.MouseObjectGlobal, support.MouseScreenToWorld);
                },
                resolved =>
                {
                    spawnWrapper = resolved.wrapper;
                    hashLookup = resolved.TemplateHashLookup;
                    hashTableGlobal = resolved.HashTableOwnerGlobal;
                    mouseObjGlobal = resolved.MouseObjectGlobal;
                    mouseTransform = resolved.MouseScreenToWorld;
                },
                reason => Log?.Invoke($"生成桥：{reason}，功能不可用"));
        }

        if (rank != 0)
            Log?.Invoke($"晋级桥：晋级函数校验通过 0x{rank:X}（资金结算线程将安全调用）");
        if (capture != 0)
            Log?.Invoke($"俘虏桥：归属切换函数校验通过 0x{capture:X}");
        if (kill != 0)
            Log?.Invoke($"摧毁桥：完整伤害入口 0x{kill:X}，死亡标记 0x{marker:X}");
        if (spawnWrapper != 0)
            Log?.Invoke($"生成桥：生成 wrapper 校验通过 0x{spawnWrapper:X}，" +
                        $"哈希查找 0x{hashLookup:X}，模板表全局 0x{hashTableGlobal:X}");

        return new BridgeApis(rank, capture, kill, marker, spawnWrapper, hashLookup, hashTableGlobal,
            mouseObjGlobal, mouseTransform);
    }

    /// <summary>Quiet process probe for the start-and-auto-attach flow: true
    /// when a supported game process exists. Never throws or logs, so the UI
    /// can poll it while waiting for the player to launch the game.</summary>
    public bool ProbeGameRunning() =>
        !Attached && ProcessMemory.FindGame(_data.Game.ModuleNames) is not null;

    public void Attach(int? preferredPid = null)
    {
        if (Attached) throw new InvalidOperationException("已附加");
        var found = ProcessMemory.FindGame(_data.Game.ModuleNames, preferredPid)
                    ?? throw new InvalidOperationException($"未找到运行中的{Game.Name}进程（{string.Join('/', Game.ModuleNames)}）");
        var mem = new ProcessMemory(found.pid);
        MasterCode? pendingMaster = null;
        var version = found.version;
        try
        {
            var proc = System.Diagnostics.Process.GetProcessById(found.pid);
            var main = proc.MainModule
                       ?? throw new InvalidOperationException("无法读取主模块");
            var baseAddr = (nuint)main.BaseAddress;

            // ra3_1.12.game is the module name of both the Steam repack and the
            // EA original; classify by content before resolving any hook.
            if (Game.Id == GameId.Uprising)
            {
                version = GameBuildClassifier.ClassifyUprising(
                    new DelegateImageReader((rva,len) => mem.Read(baseAddr+rva,len)), version, _data);
                // Validate both globals independently of the optional spawn bridge.
                UprisingTarget.Build(version).Verify("selectionRegister",baseAddr,
                    new DelegateImageReader((rva,len) => mem.Read(baseAddr+rva,len)));
                foreach (var contract in UprisingTarget.Build(version).Contracts.Keys.Where(k=>k.StartsWith("layout",StringComparison.Ordinal)))
                    UprisingTarget.Build(version).Verify(contract,baseAddr,
                        new DelegateImageReader((rva,len) => mem.Read(baseAddr+rva,len)));
            }
            else if (version == "1.12")
            {
                version = Target.GameBuildClassifier.Classify(mem, baseAddr, _data);
                if (version != found.version)
                    Log?.Invoke($"识别为 EA 原版 1.12（{found.modulePath}）");
            }

            Log?.Invoke($"附加 {found.modulePath} (PID {found.pid}) 基址 0x{baseAddr:X}");
            var image = new Target.DelegateImageReader((rva, len) => mem.Read(baseAddr + rva, len));
            var text = PeTextSection.Read(image);
            var sites = HookResolver.ResolveAll(
                _data, version,
                readRva: image.Read,
                text,
                gameBase: baseAddr,
                log: Log);

            if (sites.Count != _data.Hooks.Count)
                throw new InvalidOperationException($"挂钩点校验不完整（{sites.Count}/{_data.Hooks.Count}），拒绝部分附加；请确认游戏版本且没有其他修改器挂钩");

            var rootRva = _data.Globals.PlayerRoot.RvaFor(version);
            var bridges = ResolveBridgeApis(version, baseAddr, image);

            var mc = new MasterCode(mem, baseAddr, baseAddr + rootRva, sites, _data.Hooks, Log,
                bridges.Rank, bridges.Capture, bridges.KillDamageEntry, bridges.KillDeathMarker,
                bridges.SpawnWrapper, bridges.HashLookup, bridges.HashTableGlobal,
                bridges.MouseObjectGlobal, bridges.MouseTransform, GameLayout.For(version));
            pendingMaster = mc;
            mc.Install();

            _mem = mem;
            _mc = mc;
            _actionState.Clear();
            Attached = true;
            RecoveryRequired = false;
            Version = version;
            Pid = found.pid;
            ProcessPath = found.modulePath;
            Base = baseAddr;
            ResolvedSites = sites.Count;
            _switches.ResetAll();
            _bridges = new BridgeCoordinator(mc, mem, version, baseAddr, _data,
                m => Log?.Invoke(m), () => StateChanged?.Invoke());
            CreateFeatureStates();
            WatchGameProcess(proc);

            Log?.Invoke($"修改器已就绪：{sites.Count}/{_data.Hooks.Count} 挂钩点全部通过原始字节校验 ✓");
            StateChanged?.Invoke();
        }
        catch (Exception installError)
        {
            // If the game died mid-attach there is nothing to roll back — the
            // writes would fail one by one. Just drop the half-open session.
            if (!mem.IsProcessAlive)
            {
                mem.Dispose();
                Log?.Invoke($"附加中断：游戏进程已退出（{installError.Message}）");
                throw;
            }
            try { pendingMaster?.Uninstall(); }
            catch (Exception rollbackError)
            {
                _mem = mem;
                _mc = pendingMaster;
                Attached = true;
                RecoveryRequired = true;
                Version = version;
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
        lock (_detachGate)
        {
            if (!Attached) return;

            // The game exited before the detach click (or the auto-detach raced
            // the manual one): its memory died with it. There is nothing to
            // restore — attempting the writes would spam one failure per hook
            // site and wedge the session in RecoveryRequired forever.
            if (_mem is { IsProcessAlive: false })
            {
                ReleaseSession();
                Log?.Invoke("游戏进程已退出，直接脱离（进程内存已随之消失，无需恢复挂钩）。");
                StateChanged?.Invoke();
                return;
            }

            try { _mc?.Uninstall(); }
            catch (Exception ex)
            {
                RecoveryRequired = true;
                StateChanged?.Invoke();
                Log?.Invoke("卸载失败，功能已禁用；请重试脱离或重启游戏: " + ex.Message);
                return;
            }
            // Restore the build-anywhere branch patch if its toggle is still on. The
            // patch belongs to the feature, so ask the feature state for both the
            // "is it on" question and the restore; the raw address is only a fallback
            // for when no state exists.
            if (_featureStates.TryGetValue(Patches.BuildAnywhereFeature.FeatureId, out var ba)
                && ba.IsOn && _mem != null && Version != null)
            {
                try
                {
                    if (!ba.SetOn(false).Ok)
                    {
                        var siteRva = PrivateOffsets.RvaFor(_data, Version,
                            Patches.BuildAnywhereFeature.FeatureId, "site");
                        if (siteRva != 0)
                            _mem.Write(Base + siteRva, new byte[] { 0x75, 0x0C });
                    }
                }
                catch { /* best-effort restore on detach */ }
            }
            ReleaseSession();
            Log?.Invoke("已从游戏进程脱离，全部挂钩已还原。");
            StateChanged?.Invoke();
        }
    }

    /// <summary>Drop every session-scoped object. Shared by the normal detach
    /// (after byte restoration) and the dead-process fast path (nothing to
    /// restore). Leaves the engine ready for a fresh attach.</summary>
    private void ReleaseSession()
    {
        if (_proc is not null)
        {
            _proc.Exited -= OnGameExited;
            _proc.Dispose();
            _proc = null;
        }
        _mem?.Dispose();
        _mem = null;
        _mc = null;
        _bridges = null;
        _actionState.Clear();
        _featureStates.Clear();
        _services = new FeatureServiceRegistry();
        Attached = false;
        RecoveryRequired = false;
        _switches.ResetAll();
    }

    /// <summary>Watch the attached process so the UI can auto-detach the moment
    /// the game exits (clean close or crash), instead of waiting for the user
    /// to notice features stopped working.</summary>
    private void WatchGameProcess(System.Diagnostics.Process proc)
    {
        _proc = proc;
        proc.EnableRaisingEvents = true;
        proc.Exited += OnGameExited;
    }

    private void OnGameExited(object? sender, EventArgs e)
    {
        try { GameExited?.Invoke(); }
        catch { /* never take down the thread-pool thread */ }
    }

    // ---------------------------------------------------------------------
    // Public dispatch. The engine no longer switches on feature ids: every
    // request is routed to the feature instance the catalog produced.
    // ---------------------------------------------------------------------

    public (bool ok, string msg) SetToggle(string featureId, bool on)
    {
        if (RecoveryRequired) return (false, "挂钩恢复未完成，禁止启用功能");
        if (!Attached || _mc == null) return (false, "未附加");
        if (_featureStates.TryGetValue(featureId, out var state))
        {
            var (ok, msg) = state.SetOn(on);
            return (ok, msg);
        }
        return SetFeatureToggle(featureId, on);
    }

    public (bool ok, string msg) ExecuteAction(string featureId, string? arg = null)
    {
        if (!Attached || _mem == null) return (false, "未附加");
        if (_featureStates.TryGetValue(featureId, out var state))
        {
            var (ok, msg) = state.Execute(arg);
            return (ok, msg);
        }
        return RunFeatureAction(featureId, arg);
    }

    // ---------------------------------------------------------------------
    // Unimplemented-feature fallbacks. M5 is complete: every declared feature
    // has a catalog implementation (SwitchFeature / code-patch / bridge /
    // spawn / selection actions), so these only answer for a stale UI copy
    // showing an id the catalog no longer knows. Nothing may be added here —
    // new features get their own IFeature.
    // ---------------------------------------------------------------------

    /// <summary>Fallback toggle dispatch. Every toggle is a catalog feature, so this
    /// only runs for an id with no implementation (typo or stale UI). Nothing may be
    /// added here — new toggles become features.</summary>
    internal (bool ok, string msg) SetFeatureToggle(string featureId, bool on) =>
        (false, $"功能 {featureId} 没有实现（catalog 未注册）");

    internal (bool ok, string msg) RunFeatureAction(string featureId, string? arg = null)
    {
        if (RecoveryRequired) return (false, "挂钩恢复未完成，禁止执行动作");
        if (!Attached || _mem == null) return (false, "未附加");
        return (false, $"功能 {featureId} 没有实现（catalog 未注册）");
    }

    public bool IsOn(string featureId) => _switches.IsOn(featureId);

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
