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

    /// <summary>生成桥显式开关：环境变量 RA3MT_SPAWN=1/true，或 exe 旁存在
    /// spawn-bridge.enable 标记文件。需要生成 wrapper、哈希查找、哈希表全局
    /// 三项全部严格校验通过才安装消费桩（复制选中/三阵营基地车/战场增援）。</summary>
    public bool EnableSpawnBridge { get; set; } =
        Environment.GetEnvironmentVariable("RA3MT_SPAWN") is "1" or "true"
        || File.Exists(Path.Combine(AppContext.BaseDirectory, "spawn-bridge.enable"));

    public bool SpawnBridgeActive => Attached && _mc is { SpawnBridgeEnabled: true, SpawnMailbox: not null };

    /// <summary>Whether one specific bridge is usable right now.</summary>
    private bool IsBridgeActive(Engine.BridgeId id) => id switch
    {
        Engine.BridgeId.Rank => RankBridgeActive,
        Engine.BridgeId.Capture => CaptureBridgeActive,
        Engine.BridgeId.Kill => KillBridgeActive,
        Engine.BridgeId.Spawn => SpawnBridgeActive,
        _ => false,
    };
    public string Version { get; private set; } = "";
    public int Pid { get; private set; }
    public string ProcessPath { get; private set; } = "";
    public nuint Base { get; private set; }
    public int ResolvedSites { get; private set; }
    public int TotalSites => _data.Hooks.Count;

    public event Action<string>? Log;
    public event Action? StateChanged;

    /// <summary>Owner of the on/off state for stub-flag features. Created eagerly so
    /// the UI can read it before the first attach; the flag writes themselves are
    /// routed through <see cref="WriteFeatureFlag"/> and need an installed block.</summary>
    private readonly SwitchBank _switches;
    private readonly FeatureRegistry _registry;
    private readonly Dictionary<string, IFeatureState> _featureStates = new(StringComparer.Ordinal);
    private FeatureServiceRegistry _services = new();

    public IReadOnlyDictionary<string, bool> ToggleState => _switches.Snapshot;
    public FeaturesData Data => _data;
    public FeatureRegistry Registry => _registry;

    public TrainerEngine()
    {
        _registry = LegacyFeatureCatalog.Build(_data, this, RunDiag);
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
        registry.Register<IBridgeGateway>(new EngineAdapters.BridgeGateway(
            IsBridgeActive,
            (id, name) => SubmitBridgeRequests(name, id)));
        registry.Register<ISpawnGateway>(new EngineAdapters.SpawnGateway(
            SpawnBridgeActive,
            CopyHolders,
            MouseGround,
            SelectionAnchor,
            SubmitSpawnRequests));
        return registry;
    }

    /// <summary>Template holders of the current selection (copy-selected path).</summary>
    private IReadOnlyList<uint> CopyHolders()
    {
        if (_mem is null) return [];
        return SpawnActions.EnumerateCopyTargets(_mem, _data, Version, Base)
            .Select(t => t.holder).ToList();
    }

    private (float x, float y, float z)? MouseGround()
    {
        if (_mem is null) return null;
        var mouse = SpawnActions.GetMouseWorldPosition(_mem, _data, Version, Base);
        return mouse is null ? null : (mouse.Value.x, mouse.Value.y, mouse.Value.z);
    }

    private (float x, float y, float z)? SelectionAnchor()
    {
        if (_mem is null) return null;
        return SpawnActions.GetSelectionAnchor(_mem, _data, Version, Base);
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
        nuint Rank, nuint Capture, nuint Kill, nuint KillDeathMarker,
        nuint SpawnWrapper, nuint HashLookup, nuint HashTableGlobal);

    /// <summary>Resolve every optional bridge capability. Each resolver is
    /// individually fenced: a contract mismatch downgrades that one bridge and is
    /// reported, instead of aborting the whole attach or installing something
    /// unverified. The feature switches only decide whether we bother resolving.</summary>
    private BridgeApis ResolveBridgeApis(string version, nuint imageBase, Target.IImageReader image)
    {
        nuint rank = 0, capture = 0, kill = 0, marker = 0;
        nuint spawnWrapper = 0, hashLookup = 0, hashTableGlobal = 0;

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
                    kill = resolved.adjust;
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
                    return (wrapper, support.TemplateHashLookup, support.HashTableOwnerGlobal);
                },
                resolved =>
                {
                    spawnWrapper = resolved.wrapper;
                    hashLookup = resolved.TemplateHashLookup;
                    hashTableGlobal = resolved.HashTableOwnerGlobal;
                },
                reason => Log?.Invoke($"生成桥：{reason}，功能不可用"));
        }

        if (rank != 0)
            Log?.Invoke($"晋级桥：晋级函数校验通过 0x{rank:X}（资金结算线程将安全调用）");
        if (capture != 0)
            Log?.Invoke($"俘虏桥：归属切换函数校验通过 0x{capture:X}");
        if (kill != 0)
            Log?.Invoke($"摧毁桥：HP 调整 0x{kill:X}，死亡标记 0x{marker:X}");
        if (spawnWrapper != 0)
            Log?.Invoke($"生成桥：生成 wrapper 校验通过 0x{spawnWrapper:X}，" +
                        $"哈希查找 0x{hashLookup:X}，模板表全局 0x{hashTableGlobal:X}");

        return new BridgeApis(rank, capture, kill, marker, spawnWrapper, hashLookup, hashTableGlobal);
    }

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
            var image = new Target.DelegateImageReader((rva, len) => mem.Read(baseAddr + rva, len));
            var text = mem.Read(baseAddr + 0x1000, 0x7D0000);
            var sites = HookResolver.ResolveAll(
                _data, found.version,
                readRva: image.Read,
                text,
                gameBase: baseAddr,
                log: Log);

            if (sites.Count != _data.Hooks.Count)
                throw new InvalidOperationException($"挂钩点校验不完整（{sites.Count}/{_data.Hooks.Count}），拒绝部分附加；请确认游戏版本且没有其他修改器挂钩");

            var rootRva = _data.Globals.PlayerRoot.RvaFor(found.version);
            var bridges = ResolveBridgeApis(found.version, baseAddr, image);

            var mc = new MasterCode(mem, baseAddr, baseAddr + rootRva, sites, _data.Hooks, Log,
                bridges.Rank, bridges.Capture, bridges.Kill, bridges.KillDeathMarker,
                bridges.SpawnWrapper, bridges.HashLookup, bridges.HashTableGlobal);
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
            _switches.ResetAll();
            CreateFeatureStates();

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
        // restore the free-build branch patch if the toggle was left on
        if (_buildAnywhereOn && _mem != null && Version != null)
        {
            try
            {
                var g = _data.Globals.BuildAnywherePatch;
                if (g != null && g.Rva.TryGetValue(Version, out var rvaStr))
                    _mem.Write(Base + Convert.ToUInt32(rvaStr, 16), new byte[] { 0x75, 0x0C });
            }
            catch { /* best-effort restore on detach */ }
            _buildAnywhereOn = false;
        }
        _mem?.Dispose();
        _mem = null;
        _mc = null;
        _actionState.Clear();
        _featureStates.Clear();
        _services = new FeatureServiceRegistry();
        Attached = false;
        RecoveryRequired = false;
        _switches.ResetAll();
        Log?.Invoke("已从游戏进程脱离，全部挂钩已还原。");
        StateChanged?.Invoke();
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
    // Historical implementations. These are the bodies the catalog currently
    // wraps as features; they disappear as features migrate (M5).
    // Every stub-flag toggle is already migrated to SwitchFeature, so only the
    // code-patch toggle is left here.
    // ---------------------------------------------------------------------

    internal (bool ok, string msg) SetFeatureToggle(string featureId, bool on)
    {
        if (_mc is null) return (false, "修改器未初始化");
        var f = _data.Features.FirstOrDefault(x => x.Id == featureId);
        if (f?.Kind != "toggle") return (false, "功能尚未可用或非开关型功能");
        try
        {
            // 随地建造 = FINAL3 同款 2 字节分支 patch（放置 gate 的"范围外返回 2"路径）
            if (f.Id == "build_anywhere")
            {
                var (vok, vmsg) = SetBuildAnywherePatch(on);
                if (!vok) return (vok, vmsg);
                Log?.Invoke($"{f.Name} = {(on ? "开" : "关")}{(vmsg.Length > 0 ? $"（{vmsg}）" : "")}");
                StateChanged?.Invoke();
                return (true, "");
            }
            return (false, "功能无开关标志");
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }

    private bool _buildAnywhereOn;

    /// <summary>随地建造 v3：FINAL3 同款 2 字节分支 patch（2026-10-12 实测验证）。
    /// 放置 gate 函数尾部的"全部候选失败 → 返回失败码 2（超出可建造范围）"分支：
    /// 75 0C (jne) ↔ EB 0C (jmp)——jmp 后永不返回 2，范围外照常通过。
    /// 效果与 FINAL3（EA 原版 0x4E7565）完全一致：格子仍显示灰色但可直接点击建造。
    /// 补丁点（VA）：1.13 0x511955 / 1.12 0x528DF5，磁盘字节级验证；该 gate 为
    /// 玩家放置与 AI 选址共用层。纯代码字节切换，对局切换不重置；脱离进程自动还原。</summary>
    private (bool, string) SetBuildAnywherePatch(bool on)
    {
        var global = _data.Globals.BuildAnywherePatch;
        if (global is null || !global.Rva.TryGetValue(Version!, out var rvaStr))
            return (false, "本版本暂不支持（补丁点未注册）");
        var site = Base + Convert.ToUInt32(rvaStr, 16);
        byte[] jne = { 0x75, 0x0C }, jmp = { 0xEB, 0x0C };
        var cur = _mem!.Read(site, 2);
        if (on && cur.SequenceEqual(jmp))
        { _buildAnywhereOn = true; return (true, "已在开启状态"); }
        if (!on && cur.SequenceEqual(jne))
        { _buildAnywhereOn = false; return (true, "已在关闭状态"); }
        if (!cur.SequenceEqual(jne) && !cur.SequenceEqual(jmp))
            return (false, $"补丁点字节异常（{Convert.ToHexString(cur)}），拒绝改写");
        _mem.Write(site, on ? jmp : jne);
        if (!_mem.Read(site, 2).SequenceEqual(on ? jmp : jne))
            return (false, "写入校验失败");
        _buildAnywhereOn = on;
        return (true, on ? "放置范围限制已解除" : "放置范围限制已恢复");
    }

    /// <summary>Last-resort action dispatch. The catalog covers every declared
    /// feature, so this only runs for an id that has no implementation (a typo or a
    /// stale UI). It is deliberately tiny: nothing may be added here — new actions
    /// become features.</summary>
    internal (bool ok, string msg) RunFeatureAction(string featureId, string? arg = null)
    {
        if (RecoveryRequired) return (false, "挂钩恢复未完成，禁止执行动作");
        if (!Attached || _mem == null) return (false, "未附加");
        return (false, $"功能 {featureId} 没有实现（catalog 未注册）");
    }

    // ---------------------------------------------------------------------
    // Bridge plumbing. Features reach this through IBridgeGateway /
    // ISpawnGateway; the waiting, logging and per-bridge wording live here.
    // ---------------------------------------------------------------------

    /// <summary>Diagnostics entry point for the feature catalog.</summary>
    private FeatureResult RunDiag()
    {
        var (ok, msg) = DiagDump();
        return ok ? FeatureResult.Succeeded(msg) : FeatureResult.Failure(msg);
    }

    /// <summary>Submit requests to a game-thread bridge one at a time, waiting for
    /// the settlement stub to consume each before sending the next (the mailbox
    /// allows a single outstanding request).</summary>
    private (bool, string) DrainBridge(string featureName, BridgeId id, IReadOnlyList<BridgeRequest> requests,
        int perTargetTimeoutMs, int totalBudgetMs)
    {
        if (_mc is null) return (false, "修改器未初始化");
        var mailbox = _mc.Mailbox(id);
        if (mailbox is null) return (false, $"{featureName}: 桥未启用");
        var consumer = _mc.Bridges[id];

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var applied = 0;
        var rejected = 0;
        var outstanding = 0;
        for (var i = 0; i < requests.Count; i++)
        {
            var request = requests[i];
            try
            {
                mailbox.Submit(request);
            }
            catch (InvalidOperationException ex)
            {
                Log?.Invoke($"{featureName}: 0x{request.Body:X} 未提交（邮箱状态 {mailbox.RawState}: {ex.Message}）");
                outstanding += requests.Count - i;
                break;
            }

            var deadline = System.Diagnostics.Stopwatch.StartNew();
            var outcome = BridgeOutcome.Pending;
            while (true)
            {
                outcome = mailbox.Outcome;
                if (outcome != BridgeOutcome.Pending) break;
                if (deadline.ElapsedMilliseconds > perTargetTimeoutMs ||
                    sw.ElapsedMilliseconds > totalBudgetMs) break;
                Thread.Sleep(25);
            }

            switch (outcome)
            {
                case BridgeOutcome.Applied:
                    applied++;
                    Log?.Invoke($"{featureName}: {DescribeRequest(consumer, mailbox, request)}");
                    break;
                case BridgeOutcome.Rejected:
                    rejected++;
                    Log?.Invoke($"{featureName}: {DescribeRejection(consumer, request)}");
                    break;
                default:
                    outstanding++;
                    break;
            }

            if (sw.ElapsedMilliseconds > totalBudgetMs)
            {
                outstanding += requests.Count - i - 1;
                break;
            }
        }

        var msg = applied > 0
            ? $"已作用于 {applied}/{requests.Count} 个目标"
            : "游戏线程未消费请求（资金未结算？稍后重试）";
        if (rejected > 0) msg += $"，{rejected} 个被校验拒绝";
        if (outstanding > 0) msg += $"，{outstanding} 个待处理（再次触发继续）";
        Log?.Invoke($"{featureName}: {msg}");
        StateChanged?.Invoke();
        return (applied > 0, applied > 0 ? "" : msg);
    }

    /// <summary>Per-bridge success line. Only the spawn bridge has a resolved
    /// holder / result body worth reporting.</summary>
    private static string DescribeRequest(IBridgeConsumer consumer, IBridgeMailbox mailbox, BridgeRequest request) =>
        mailbox is SpawnRequestMailbox spawn
            ? (request.Third != 0
                ? $"已生成 哈希 0x{request.Third:X8}（解析模板 0x{spawn.ReadResult().resolvedHolder:X}）" +
                  $" → 新单位 0x{spawn.ReadResult().resultBody:X}"
                : $"已生成 模板 0x{request.Fourth:X} → 新单位 0x{spawn.ReadResult().resultBody:X}")
            : $"{consumer.DisplayName}: 0x{request.Body:X} 已执行";

    /// <summary>Per-bridge rejection line.</summary>
    private static string DescribeRejection(IBridgeConsumer consumer, BridgeRequest request) =>
        consumer.Id == BridgeId.Spawn
            ? (request.Third != 0
                ? $"哈希 0x{request.Third:X8} 不在模板表，被拒绝"
                : $"模板 0x{request.Fourth:X} 校验失败，被拒绝")
            : $"{consumer.DisplayName}: 0x{request.Body:X} 校验未通过";

    /// <summary>Selected-unit bridges (rank/capture/kill) share this entry point.</summary>
    private (bool, string) SubmitBridgeRequests(string featureName, BridgeId kind)
    {
        var targets = kind switch
        {
            BridgeId.Rank => SelectionActions.EnumerateRankTargets(_mem!, _data, Version!, Base)
                .Select(t => BridgeRequest.For(t.body, t.drawable, t.tracker)).ToList(),
            BridgeId.Capture => SelectionActions.EnumerateCaptureTargets(_mem!, _data, Version!, Base)
                .Select(t => BridgeRequest.For(t.body, t.drawable)).ToList(),
            _ => SelectionActions.EnumerateKillTargets(_mem!, _data, Version!, Base)
                .Select(t => BridgeRequest.For(t.body, t.drawable, t.hp)).ToList(),
        };
        if (targets.Count == 0)
            return (false, _mc is not null && _mc.Bridges.TryGet(kind, out var consumer)
                ? consumer.NoTargetMessage
                : "桥未启用");
        return DrainBridge(featureName, kind, targets, perTargetTimeoutMs: 800, totalBudgetMs: 4000);
    }

    /// <summary>Spawn bridge entry point: every request carries a template hash or
    /// a template holder plus a world position.</summary>
    private (bool, string) SubmitSpawnRequests(string featureName,
        List<(uint hash, uint holder, float x, float y, float z)> requests)
    {
        var spawn = _mc?.SpawnMailbox;
        if (spawn is null) return (false, $"{featureName}: 生成桥未启用");

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var applied = 0;
        var rejected = 0;
        var outstanding = 0;
        for (var i = 0; i < requests.Count; i++)
        {
            var (hash, holder, x, y, z) = requests[i];
            try
            {
                spawn.Submit(hash, holder, x, y, z, 0);
            }
            catch (InvalidOperationException ex)
            {
                Log?.Invoke($"{featureName}: 第 {i + 1} 个未提交（邮箱状态 {spawn.State}: {ex.Message}）");
                outstanding += requests.Count - i;
                break;
            }

            var deadline = System.Diagnostics.Stopwatch.StartNew();
            (uint state, uint body, uint resolved) result;
            while (true)
            {
                result = spawn.ReadResult();
                if (result.state is 3 or 4) break;
                if (deadline.ElapsedMilliseconds > 1500 || sw.ElapsedMilliseconds > 6000) break;
                Thread.Sleep(25);
            }

            if (result.state == 3)
            {
                applied++;
                var describe = hash != 0
                    ? $"哈希 0x{hash:X8}（解析模板 0x{result.resolved:X}）"
                    : $"模板 0x{holder:X}";
                Log?.Invoke($"{featureName}: 已生成 {describe} → 新单位 0x{result.body:X}");
            }
            else if (result.state == 4)
            {
                rejected++;
                var reason = hash != 0 ? $"哈希 0x{hash:X8} 不在模板表" : $"模板 0x{holder:X} 校验失败";
                Log?.Invoke($"{featureName}: {reason}，被拒绝");
            }
            else outstanding++;

            if (sw.ElapsedMilliseconds > 6000)
            {
                outstanding += requests.Count - i - 1;
                break;
            }
        }
        var msg = applied > 0
            ? $"已生成 {applied}/{requests.Count} 个单位"
            : "游戏线程未消费生成请求（资金未结算？稍后重试）";
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
