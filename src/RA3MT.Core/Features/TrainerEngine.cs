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

    /// <summary>生成桥显式开关：环境变量 RA3MT_SPAWN=1/true，或 exe 旁存在
    /// spawn-bridge.enable 标记文件。需要生成 wrapper、哈希查找、哈希表全局
    /// 三项全部严格校验通过才安装消费桩（复制选中/三阵营基地车/战场增援）。</summary>
    public bool EnableSpawnBridge { get; set; } =
        Environment.GetEnvironmentVariable("RA3MT_SPAWN") is "1" or "true"
        || File.Exists(Path.Combine(AppContext.BaseDirectory, "spawn-bridge.enable"));

    public bool SpawnBridgeActive => Attached && _mc is { SpawnBridgeEnabled: true, SpawnMailbox: not null };
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
            nuint captureApi = 0, killApi = 0, killDeathMarkerApi = 0;
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
                    var (adjust, marker) = Target.KillApiResolver.Resolve(found.version, baseAddr,
                        (rva, len) => mem.Read(baseAddr + rva, len));
                    killApi = adjust;
                    killDeathMarkerApi = marker;
                    Log?.Invoke($"摧毁桥：HP 调整 0x{adjust:X}，死亡标记 0x{marker:X}");
                }
                catch (Exception ex)
                {
                    Log?.Invoke($"摧毁桥：校验失败，功能不可用（{ex.Message}）");
                }
            }

            nuint spawnWrapperApi = 0, hashLookupApi = 0, hashTableGlobalVa = 0;
            if (EnableSpawnBridge)
            {
                try
                {
                    spawnWrapperApi = Target.SpawnApiResolver.Resolve(found.version, baseAddr,
                        (rva, len) => mem.Read(baseAddr + rva, len));
                    var support = Target.SpawnSupportApiResolver.Resolve(found.version, baseAddr,
                        (rva, len) => mem.Read(baseAddr + rva, len));
                    hashLookupApi = support.TemplateHashLookup;
                    hashTableGlobalVa = support.HashTableOwnerGlobal;
                    Log?.Invoke($"生成桥：生成 wrapper 校验通过 0x{spawnWrapperApi:X}，" +
                                $"哈希查找 0x{hashLookupApi:X}，模板表全局 0x{hashTableGlobalVa:X}");
                }
                catch (Exception ex)
                {
                    spawnWrapperApi = hashLookupApi = hashTableGlobalVa = 0;
                    Log?.Invoke($"生成桥：校验失败，功能不可用（{ex.Message}）");
                }
            }

            var mc = new MasterCode(mem, baseAddr, baseAddr + rootRva, sites, _data.Hooks, Log,
                rankApi, captureApi, killApi, killDeathMarkerApi,
                spawnWrapperApi, hashLookupApi, hashTableGlobalVa);
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
        if (f?.Kind != "toggle") return (false, "功能尚未可用或非开关型功能");
        try
        {
            // 随地建造 = FINAL3 同款 2 字节分支 patch（放置 gate 的"范围外返回 2"路径）
            if (f.Id == "build_anywhere")
            {
                var (vok, vmsg) = SetBuildAnywherePatch(on);
                if (!vok) return (vok, vmsg);
                _toggleState[featureId] = on;
                Log?.Invoke($"{f.Name} = {(on ? "开" : "关")}{(vmsg.Length > 0 ? $"（{vmsg}）" : "")}");
                StateChanged?.Invoke();
                return (true, "");
            }
            if (f.Flag == null) return (false, "功能无开关标志");
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

    public (bool ok, string msg) ExecuteAction(string featureId, string? arg = null)
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

            // 生成桥路径：复制选中（直接模板持有者）/ 基地车 / 战场增援代码（哈希）
            if (f.Action == "selcopy")
            {
                if (!SpawnBridgeActive)
                    return (false, "需要 spawn-bridge.enable 启用生成桥并通过校验");
                var targets = SpawnActions.EnumerateCopyTargets(_mem, _data, Version!, Base);
                if (targets.Count == 0)
                    return (false, "没有可复制的选中目标（未选中或目标缺少模板链）");
                var mouse = SpawnActions.GetMouseWorldPosition(_mem, _data, Version!, Base);
                if (mouse != null)
                    return SubmitSpawnRequests(f.Name,
                        targets.Select(t => (0u, t.holder, mouse.Value.x, mouse.Value.y, mouse.Value.z)).ToList());
                return SubmitSpawnRequests(f.Name,
                    targets.Select(t => (0u, t.holder, t.x, t.y, t.z)).ToList());
            }
            if (f.Action == "spawnhash")
            {
                if (!SpawnBridgeActive)
                    return (false, "需要 spawn-bridge.enable 启用生成桥并通过校验");
                uint hash;
                if (arg is "allied" or "soviet" or "japan")
                {
                    if (!SpawnActions.McvHashes.TryGetValue(arg, out hash))
                        return (false, "未知阵营");
                }
                else if (!SpawnActions.TryParseHash(arg ?? "", out hash) || hash == 0)
                {
                    return (false, "无效的增援代码（应为 8 位十六进制，如 6586A5A0）");
                }
                // spawn at the mouse ground point (world x/z, always live);
                // fall back to the selected unit's position when unavailable
                var mouse = SpawnActions.GetMouseWorldPosition(_mem, _data, Version!, Base);
                if (mouse != null)
                    Log?.Invoke($"生成位置=鼠标地面 0x({mouse.Value.x:F0}, {mouse.Value.z:F0})");
                var anchor = mouse ?? SpawnActions.GetSelectionAnchor(_mem, _data, Version!, Base);
                if (anchor == null)
                    return (false, "鼠标位置不可用：请把鼠标移到游戏画面上，或选中一个己方单位作锚点");
                var (x, y, z) = anchor.Value;
                return SubmitSpawnRequests(f.Name, [(hash, 0u, x, y, z)]);
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

    /// <summary>向生成桥逐个提交请求（每次等待游戏线程消费后再提交下一个）。
    /// owner 传 0：消费桩在游戏线程用 playerRoot 全局补齐本地阵营。</summary>
    private (bool, string) SubmitSpawnRequests(string featureName,
        List<(uint hash, uint holder, float x, float y, float z)> requests)
    {
        var mailbox = _mc!.SpawnMailbox!;
        const int perTargetTimeoutMs = 1500;
        const int totalBudgetMs = 6000;
        var sw = System.Diagnostics.Stopwatch.StartNew();
        var spawned = 0;
        var rejected = 0;
        var outstanding = 0;
        for (var i = 0; i < requests.Count; i++)
        {
            var (hash, holder, x, y, z) = requests[i];
            try
            {
                mailbox.Submit(hash, holder, x, y, z, 0);
            }
            catch (InvalidOperationException ex)
            {
                Log?.Invoke($"{featureName}: 第 {i + 1} 个未提交（邮箱状态 {mailbox.State}: {ex.Message}）");
                outstanding += requests.Count - i;
                break;
            }
            var deadline = System.Diagnostics.Stopwatch.StartNew();
            (uint state, uint body, uint resolved) result;
            while (true)
            {
                result = mailbox.ReadResult();
                if (result.state is 3 or 4) break;
                if (deadline.ElapsedMilliseconds > perTargetTimeoutMs ||
                    sw.ElapsedMilliseconds > totalBudgetMs) break;
                Thread.Sleep(25);
            }
            if (result.state == 3)
            {
                spawned++;
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
            if (sw.ElapsedMilliseconds > totalBudgetMs)
            {
                outstanding += requests.Count - i - 1;
                break;
            }
        }
        var msg = spawned > 0
            ? $"已生成 {spawned}/{requests.Count} 个单位"
            : "游戏线程未消费生成请求（资金未结算？稍后重试）";
        if (rejected > 0) msg += $"，{rejected} 个被校验拒绝";
        if (outstanding > 0) msg += $"，{outstanding} 个待处理（再次触发继续）";
        Log?.Invoke($"{featureName}: {msg}");
        StateChanged?.Invoke();
        return (spawned > 0, spawned > 0 ? "" : msg);
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
