using RA3MT.Core.Engine;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features;

/// <summary>Game-thread bridge orchestration: submitting requests into the
/// bridge mailboxes, waiting for the settlement stub to consume each one, and
/// the per-bridge logging and wording. The engine owns the attach lifecycle;
/// this class owns everything that happens after a feature says "submit
/// this". One instance per attached session (created after the block is
/// installed, dropped on detach), so the captured memory/version/base are
/// always valid while it exists.</summary>
public sealed class BridgeCoordinator
{
    private readonly MasterCode _master;
    private readonly ProcessMemory _mem;
    private readonly string _version;
    private readonly nuint _base;
    private readonly FeaturesData _data;
    private readonly Action<string> _log;
    private readonly Action _stateChanged;

    public BridgeCoordinator(MasterCode master, ProcessMemory mem, string version, nuint imageBase,
        FeaturesData data, Action<string> log, Action stateChanged)
    {
        _master = master;
        _mem = mem;
        _version = version;
        _base = imageBase;
        _data = data;
        _log = log;
        _stateChanged = stateChanged;
    }

    public bool IsActive(BridgeId id) => id switch
    {
        BridgeId.Rank => _master is { RankBridgeEnabled: true, RankMailbox: not null },
        BridgeId.Capture => _master is { CaptureBridgeEnabled: true, CaptureMailbox: not null },
        BridgeId.Kill => _master is { KillBridgeEnabled: true, KillMailbox: not null },
        BridgeId.Spawn => _master is { SpawnBridgeEnabled: true, SpawnMailbox: not null },
        _ => false,
    };

    /// <summary>Template holders of the current selection (copy-selected path).</summary>
    public IReadOnlyList<uint> CopyHolders() =>
        SpawnActions.EnumerateCopyTargets(_mem, _data, _version, _base)
            .Select(t => t.holder).ToList();

    public (float x, float y, float z)? MouseGround()
    {
        var mouse = SpawnActions.GetMouseWorldPosition(_mem, _data, _version, _base);
        return mouse is null ? null : (mouse.Value.x, mouse.Value.y, mouse.Value.z);
    }

    public (float x, float y, float z)? SelectionAnchor() =>
        SpawnActions.GetSelectionAnchor(_mem, _data, _version, _base);

    /// <summary>Submit requests to a game-thread bridge one at a time, waiting for
    /// the settlement stub to consume each before sending the next (the mailbox
    /// allows a single outstanding request).</summary>
    private (bool, string) DrainBridge(string featureName, BridgeId id, IReadOnlyList<BridgeRequest> requests,
        int perTargetTimeoutMs, int totalBudgetMs)
    {
        var mailbox = _master.Mailbox(id);
        if (mailbox is null) return (false, $"{featureName}: 桥未启用");
        var consumer = _master.Bridges[id];

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var applied = 0;
        var rejected = 0;
        var outstanding = 0;
        var skipped = 0;
        for (var i = 0; i < requests.Count; i++)
        {
            var request = requests[i];
            try
            {
                mailbox.Submit(request);
            }
            catch (InvalidOperationException ex)
            {
                _log($"{featureName}: 0x{request.Body:X} 未提交（邮箱状态 {mailbox.RawState}: {ex.Message}）");
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
                    _log($"{featureName}: {DescribeRequest(consumer, mailbox, request)}");
                    break;
                case BridgeOutcome.Rejected:
                    // Rank only: an award that did not move the rank value is the
                    // expected "already three-star" outcome — log it as a skip so
                    // it does not raise the error window.
                    if (mailbox is RankRequestMailbox rankBox && rankBox.RejectedBecauseAlreadyRanked())
                    {
                        skipped++;
                        _log($"{featureName}: 0x{request.Body:X} 未升星（多为已满星），跳过");
                    }
                    else
                    {
                        rejected++;
                        _log($"{featureName}: {DescribeRejection(consumer, request)}");
                    }
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

        var benignOnly = applied == 0 && skipped > 0 && rejected == 0 && outstanding == 0;
        var msg = applied > 0
            ? $"已作用于 {applied}/{requests.Count} 个目标"
            : benignOnly
                ? "全部目标已是满星，无需升星"
                : "游戏线程未消费请求（资金未结算？稍后重试）";
        if (skipped > 0) msg += $"，{skipped} 个未升星（多为已满星）";
        if (rejected > 0) msg += $"，{rejected} 个被校验拒绝";
        if (outstanding > 0) msg += $"，{outstanding} 个待处理（再次触发继续）";
        _log($"{featureName}: {msg}");
        _stateChanged();
        return (applied > 0 || benignOnly, applied > 0 ? "" : msg);
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

    /// <summary>Selected-unit bridges (rank/capture/kill) share this entry point.
    /// Destroy follows FINAL3's semantics (EA MustCode2+900 takes the single
    /// [root+0x54] entry): ONE target per invocation — queueing the whole
    /// selection keeps the mailbox busy across frames and later targets die
    /// while the player has already moved on (live-reported as stray kills).</summary>
    public (bool, string) SubmitSelected(string featureName, BridgeId kind)
    {
        var targets = kind switch
        {
            BridgeId.Rank => SelectionActions.EnumerateRankTargets(_mem, _data, _version, _base)
                .Select(t => BridgeRequest.For(t.body, t.drawable, t.tracker)).ToList(),
            BridgeId.Capture => SelectionActions.EnumerateCaptureTargets(_mem, _data, _version, _base)
                .Select(t => BridgeRequest.For(t.body, t.drawable)).ToList(),
            _ => SelectionActions.EnumerateKillTargets(_mem, _data, _version, _base)
                .Select(t => BridgeRequest.For(t.body, t.drawable, t.hp)).ToList(),
        };
        if (targets.Count == 0)
            return (false, _master.Bridges.TryGet(kind, out var consumer)
                ? consumer.NoTargetMessage
                : "桥未启用");
        if (kind == BridgeId.Kill && targets.Count > 1)
        {
            var total = targets.Count;
            targets = targets.GetRange(0, 1);
            _log($"{featureName}: 选中 {total} 个目标，按 FINAL3 语义一次只摧毁一个" +
                 $"（剩余 {total - 1} 个，再次执行继续）");
        }
        return DrainBridge(featureName, kind, targets, perTargetTimeoutMs: 800, totalBudgetMs: 4000);
    }

    /// <summary>FINAL3 "We need back": spawn <paramref name="count"/> units of the
    /// hash around the anchor, then rank every new body up through the rank
    /// bridge. FINAL3 spawns all eight at the same point; we spread them on a
    /// small circle because the engine will not separate a pile-up, and each
    /// reinforcement gets the same level-up FINAL3 applies.</summary>
    public (bool, string) SubmitReinforcement(string featureName, uint hash, float x, float y, float z, int count)
    {
        var spawn = _master.SpawnMailbox;
        if (spawn is null) return (false, $"{featureName}: 生成桥未启用");
        var bodies = new List<uint>();
        var rejected = 0;
        var sw = System.Diagnostics.Stopwatch.StartNew();
        for (var i = 0; i < count; i++)
        {
            var angle = i * 2f * MathF.PI / count;
            var px = x + 50f * MathF.Cos(angle);
            var pz = z + 50f * MathF.Sin(angle);
            try
            {
                spawn.SubmitAtMouse(hash, 0, px, y, pz, 0,
                    50f * MathF.Cos(angle), 50f * MathF.Sin(angle));
            }
            catch (InvalidOperationException ex)
            {
                _log($"{featureName}: 第 {i + 1} 个未提交（{ex.Message}）");
                break;
            }
            var deadline = System.Diagnostics.Stopwatch.StartNew();
            (uint state, uint body, uint resolved) result;
            while (true)
            {
                result = spawn.ReadResult();
                if (result.state is 3 or 4) break;
                if (deadline.ElapsedMilliseconds > 1500 || sw.ElapsedMilliseconds > 8000) break;
                Thread.Sleep(25);
            }
            if (result.state == 3) bodies.Add(result.body);
            else rejected++;
            if (sw.ElapsedMilliseconds > 8000) break;
        }
        if (bodies.Count == 0)
            return (false, $"{featureName}: 未生成任何单位" + (rejected > 0 ? $"（{rejected} 个被拒绝）" : ""));

        var ranked = 0;
        if (_master.Mailbox(BridgeId.Rank) is not null)
        {
            var requests = new List<BridgeRequest>();
            foreach (var body in bodies)
            {
                var drawable = _mem.ReadU32(body + GameLayout.For(_version).BodyDrawable);
                var tracker = _mem.ReadU32(body + GameLayout.For(_version).Tracker);
                if (drawable < 0x10000 || tracker < 0x10000) continue;
                requests.Add(BridgeRequest.For(body, drawable, tracker));
            }
            if (requests.Count > 0)
            {
                var (rok, _) = DrainBridge($"{featureName}·升星", BridgeId.Rank, requests, 800, 8000);
                if (rok) ranked = requests.Count;
            }
        }
        else
        {
            _log($"{featureName}: 晋级桥未启用，已生成但未升星");
        }
        var msg = $"已生成 {bodies.Count} 个单位" + (ranked > 0 ? "并升星" : "");
        _log($"{featureName}: {msg}");
        return (true, msg);
    }

    /// <summary>Spawn bridge entry point: every request carries a template hash or
    /// a template holder plus a world position.</summary>
    public (bool, string) SubmitSpawnRequests(string featureName,
        List<(uint hash, uint holder, float x, float y, float z)> requests, bool atMouse = false)
    {
        var spawn = _master.SpawnMailbox;
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
                if (atMouse) spawn.SubmitAtMouse(hash, holder, x, y, z, 0);
                else spawn.Submit(hash, holder, x, y, z, 0);
            }
            catch (InvalidOperationException ex)
            {
                _log($"{featureName}: 第 {i + 1} 个未提交（邮箱状态 {spawn.State}: {ex.Message}）");
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
                _log($"{featureName}: 已生成 {describe} → 新单位 0x{result.body:X}");
            }
            else if (result.state == 4)
            {
                rejected++;
                var reason = hash != 0 ? $"哈希 0x{hash:X8} 不在模板表" : $"模板 0x{holder:X} 校验失败";
                _log($"{featureName}: {reason}，被拒绝");
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
        _log($"{featureName}: {msg}");
        _stateChanged();
        return (applied > 0, applied > 0 ? "" : msg);
    }
}
