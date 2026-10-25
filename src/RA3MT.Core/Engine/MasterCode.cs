using RA3MT.Core.Memory;
using RA3MT.Core.Model;
using RA3MT.Core.Target;

namespace RA3MT.Core.Engine;

/// <summary>
/// The injected MasterCode block: flag bytes + one stub per hook site, faithfully
/// ported from the original TMK trainer's scripts (with flag handling cleaned up —
/// every stub preserves EFLAGS via pushfd/popfd, except the two sites whose game
/// continuation deliberately consumes stub-controlled flags).
///
/// Block layout: [0x00..0x20) flags — [0x40..) stubs (16-byte aligned).
/// Stub emission is a pure static function so SelfCheck can dump &amp; verify
/// the bytes without a live process.
/// </summary>
public sealed class MasterCode
{
    // flag offsets inside the block
    public static readonly Dictionary<string, byte> Flags = new()
    {
        ["money"] = 0x00,
        ["power"] = 0x01,
        ["scpoints"] = 0x02,
        ["allproto"] = 0x03,
        ["fastbuild"] = 0x04,
        ["instantready"] = 0x05,
        ["freezeenemy"] = 0x06,
        ["zoom"] = 0x07,
        ["revealmap"] = 0x08,
        ["xp999"] = 0x09,
        ["ammo"] = 0x0A,
        ["aiblock"] = 0x0B,
        ["threatmax"] = 0x0D,
        ["threatzero"] = 0x0E,
        ["godmode"] = 0x0F,
        ["onekill"] = 0x38,   // 0x00-0x0F 已占满；0x38 在数据区末尾（<0x40）
        ["challenge_money"] = 0x39,
        ["challenge_time"] = 0x3A,
            };

    public const uint BlockSize = BlockLayoutCatalog.BlockSize;
    public const uint StubArea = BlockLayoutCatalog.StubAreaStart;

    // ---- 数据区布局 ----
    // [0x00..0x0C) 功能标志；0x0C 选中捕获 armed；[0x10..0x30) 诊断捕获；0x40 起桩代码。
    // ⚠ 数据区严禁越过 0x40（曾因覆盖桩代码导致游戏闪退，Install 有断言）。
    public const uint FlagCaptureSel = 0x0C;   // 选中条目捕获开关（1=armed）
    public const uint CaptureCount = 0xFFC;    // dword：捕获到的条目数
    public const uint CaptureArray = 0x1000;   // dword 数组（最多 64）
    public const uint SideFieldOff = 0x1188;   // [玩家对象+0x1188] = 己方阵营对象（实测）

    // 诊断捕获槽（诊断桩无条件写入，供“诊断采集”动作读取）
    public const uint DiagPlayerEsi = 0x10;   // money_h1 的 esi（玩家上下文候选）
    public const uint DiagProdEax = 0x14;     // build_power 的 eax（生产对象）
    public const uint DiagProdEsi = 0x18;     // build_power 的 esi
    public const uint DiagOwner = 0x1C;       // build_power 的 [eax+0x418]
    public const uint DiagSelEntry = 0x20;    // zoom_unit_xp 的 ecx（遍历中的选中条目）
    public const uint DiagSelArr = 0x24;      // zoom_unit_xp 的 edx（数组基址）
    public const uint DiagSelIdx = 0x28;      // zoom_unit_xp 的 edi（下标）
    public const uint DiagWeaponEax = 0x2C;   // ammo 的 eax（武器对象）

    // 一击必杀（F12）：两个数据钩子捕获"正在被处理的 body/健康模块"，
    // 主钩子在 HP 写入点比对捕获值后清零敌方 HP。0x30..0x3C 在数据区末尾（<0x40）。
    public const uint OneKillBody = 0x30;     // 数据钩子捕获的 body
    public const uint OneKillHealth = 0x34;   // 数据钩子捕获的健康模块
    public const uint OneKillZero = 0x3C;     // 0.0f 常量（块内存零初始化保证）
    // onekill 功能标志在 Flags["onekill"]=0x38
    // 诊断计数（桩区与捕获区之间的空闲区，0x600..0xF00）：区分"站点没跑/
    // 捕获不匹配/门失败"各级卡点（v30 主基地不能秒杀的调查工具）
    public const uint OneKillSiteHits = 0x900;
    public const uint OneKillKills = 0x904;

    public nuint Block { get; private set; }
    public bool Installed { get; private set; }

    private readonly IInjectionMemory _mem;
    private readonly nuint _rankApi;
    private readonly nuint _captureApi;
    private readonly nuint _killApi;
    private readonly nuint _killDeathMarkerApi;
    private readonly nuint _spawnWrapperApi;
    private readonly nuint _hashLookupApi;
    private readonly nuint _hashTableGlobalVa;
    private readonly nuint _mouseObjGlobalVa;
    private readonly nuint _mouseTransformApi;
    public bool RankBridgeEnabled => _rankApi != 0;
    public bool CaptureBridgeEnabled => _captureApi != 0;
    public bool KillBridgeEnabled => _killApi != 0 && _killDeathMarkerApi != 0;
    public bool SpawnBridgeEnabled => _spawnWrapperApi != 0 && _hashLookupApi != 0 && _hashTableGlobalVa != 0;

    /// <summary>Bridges that passed resolution and will be installed. The engine
    /// drives submit/wait through this set instead of switching on a bridge kind.</summary>
    public BridgeConsumerSet Bridges { get; private set; } = new([]);

    private readonly Dictionary<BridgeId, IBridgeMailbox> _mailboxes = new();

    /// <summary>The installed mailbox for a bridge, or null when the bridge is off.</summary>
    public IBridgeMailbox? Mailbox(BridgeId id) => _mailboxes.GetValueOrDefault(id);

    // Typed views kept for the feature code and the mailbox tests.
    public RankRequestMailbox? RankMailbox => Mailbox(BridgeId.Rank) as RankRequestMailbox;
    public CaptureRequestMailbox? CaptureMailbox => Mailbox(BridgeId.Capture) as CaptureRequestMailbox;
    public KillRequestMailbox? KillMailbox => Mailbox(BridgeId.Kill) as KillRequestMailbox;
    public SpawnRequestMailbox? SpawnMailbox => Mailbox(BridgeId.Spawn) as SpawnRequestMailbox;

    private readonly nuint _rootVa;             // player-context root global
    private readonly Dictionary<string, HookResolution> _sites;
    private readonly Dictionary<string, string> _stubBySite;   // site id -> stub id
    private readonly List<(string hookId, byte[] original, nuint va)> _patched = new();
    private readonly Action<string>? _log;
    private BlockLayout? _layout;
    private readonly GameLayout _gameLayout;

    public MasterCode(IInjectionMemory mem, nuint imageBase, nuint playerRootVa,
        Dictionary<string, HookResolution> sites, IReadOnlyDictionary<string, HookDef> defs, Action<string>? log,
        nuint rankApi = 0, nuint captureApi = 0, nuint killApi = 0,
        nuint killDeathMarkerApi = 0,
        nuint spawnWrapperApi = 0, nuint hashLookupApi = 0, nuint hashTableGlobalVa = 0,
        nuint mouseObjGlobalVa = 0, nuint mouseTransformApi = 0, GameLayout? gameLayout = null)
    {
        _gameLayout = gameLayout ?? GameLayout.RedAlert3;
        _mem = mem;
        _rankApi = rankApi;
        _captureApi = captureApi;
        _killApi = killApi;
        _killDeathMarkerApi = killDeathMarkerApi;
        _spawnWrapperApi = spawnWrapperApi;
        _hashLookupApi = hashLookupApi;
        _hashTableGlobalVa = hashTableGlobalVa;
        _mouseObjGlobalVa = mouseObjGlobalVa;
        _mouseTransformApi = mouseTransformApi;
        _rootVa = playerRootVa;
        _sites = sites;
        _stubBySite = defs.ToDictionary(kv => kv.Key, kv => kv.Value.Stub ?? kv.Key);
        _log = log;
    }

    /// <summary>Build the consumers for every bridge whose API resolution passed.
    /// Adding a bridge means adding one consumer here, not a new branch in
    /// Install/Submit/uninstall.</summary>
    private BridgeConsumerSet BuildBridgeConsumers()
    {
        var consumers = new List<IBridgeConsumer>();
        if (RankBridgeEnabled) consumers.Add(new RankBridgeConsumer(_rankApi, _rootVa, _gameLayout));
        if (CaptureBridgeEnabled) consumers.Add(new CaptureBridgeConsumer(_captureApi, _rootVa, _gameLayout));
        if (KillBridgeEnabled) consumers.Add(new KillBridgeConsumer(_killApi, _rootVa, _gameLayout));
        if (SpawnBridgeEnabled)
            consumers.Add(new SpawnBridgeConsumer(_spawnWrapperApi, _hashLookupApi, _hashTableGlobalVa, _rootVa,
            _mouseObjGlobalVa, _mouseTransformApi));
        return new BridgeConsumerSet(consumers);
    }

    public void Install()
    {
        if (Installed) return;
        if (_patched.Count != 0) throw new InvalidOperationException("残留挂钩尚未恢复，拒绝重新安装");
        Block = _mem.Alloc(BlockSize);
        _mem.Write(Block, new byte[BlockSize]); // zero
        _layout = BlockLayoutCatalog.Create();
        Bridges = BuildBridgeConsumers();
        foreach (var consumer in Bridges.Consumers) consumer.Declare(_layout);

        var layouts = new List<(string id, byte[] code)>();
        uint off = StubArea;
        foreach (var (id, site) in _sites.OrderBy(kv => kv.Key))
        {
            if (!_stubBySite.TryGetValue(id, out var stubId) || !StubGen.Handles(stubId)) continue;
            var siteEnd = site.Va + (nuint)site.Displaced.Length;
            var bridgeOffsets = Bridges.Consumers
                .Select(c => _layout.OffsetOf($"{c.BlockSlot.Owner}Dispatcher"))
                .ToArray();
            // Bridge consumers ride both settlement sites: money_h2 (cash settle)
            // and money_h1 (power settle). With infinite cash enabled the cash
            // settlement can go quiet for long stretches, but the power settle
            // keeps ticking, so mailbox requests get consumed either way.
            var code = bridgeOffsets.Length != 0 && (stubId == "money_h2" || stubId == "money_h1")
                ? RankDispatcher.EmitMoneyBridge(_gameLayout, Block + off, siteEnd, Block, _rootVa, stubId, bridgeOffsets)
                : StubGen.Emit(stubId, Block + off, siteEnd, Block, _rootVa, site.Displaced, _gameLayout);
            var next = checked(off + (uint)((code.Length + 15) & ~15));
            if (next > CaptureCount)
                throw new InvalidOperationException($"Stub area overlaps capture data at hook '{id}'");
            layouts.Add((id, code));
            off = next;
        }

        // One loop for every bridge: declare was done above, so this only emits,
        // measures (AmendSize) and installs the mailbox facade.
        foreach (var consumer in Bridges.Consumers)
        {
            if (!_sites.ContainsKey("money_h2"))
                throw new InvalidOperationException($"{consumer.DisplayName} requires money_h2");
            var region = _layout.OffsetOf($"{consumer.BlockSlot.Owner}Dispatcher");
            var dispatcher = consumer.EmitDispatcher(Block + region, Block);
            _layout.AmendSize($"{consumer.BlockSlot.Owner}Dispatcher", dispatcher.Length);
            _mem.Write(Block + region, dispatcher);
            _mailboxes[consumer.Id] = consumer.CreateMailbox(_mem, Block);
        }

        // Stub arena size is known from the emitted code before anything is
        // written, so the whole layout is proven before the first byte lands.
        var stubArenaSize = layouts.Aggregate(0u, (acc, item) => acc + (uint)((item.code.Length + 15) & ~15));
        _layout.Declare("StubArena", StubArea, stubArenaSize, "stubs");
        _layout.Validate();

        off = StubArea;
        foreach (var (_, code) in layouts)
        {
            _mem.Write(Block + off, code);
            off += (uint)((code.Length + 15) & ~15);
        }

        off = StubArea;
        foreach (var (id, code) in layouts)
        {
            var site = _sites[id];
            var stubVa = Block + off;
            var siteVa = site.Va;
            var patch = new byte[site.Displaced.Length];
            patch[0] = 0xE9;
            BitConverter.GetBytes((int)(stubVa - (siteVa + 5))).CopyTo(patch, 1);
            for (var i = 5; i < patch.Length; i++) patch[i] = 0x90;

            _patched.Add((id, site.Displaced, siteVa));
            _mem.Write(siteVa, patch);
            _log?.Invoke($"[mastercode] {id}: 0x{siteVa:X} -> 桩 0x{stubVa:X} ({code.Length}B)");
            off += (uint)((code.Length + 15) & ~15);
        }
        Installed = true;
        _log?.Invoke($"[mastercode] 安装完成，块基址 0x{Block:X}");
    }

    public void Uninstall()
    {
        if (_patched.Count == 0) { Installed = false; return; }
        var failures = new List<Exception>();
        foreach (var patch in _patched.ToArray().Reverse())
        {
            var (id, original, va) = patch;
            try
            {
                _mem.Write(va, original);
                _patched.Remove(patch);
                _log?.Invoke($"[mastercode] {id}: 恢复原始字节 0x{va:X}");
            }
            catch (Exception ex) { failures.Add(ex); }
        }
        Installed = _patched.Count != 0;
        if (failures.Count != 0)
            throw new AggregateException("部分挂钩恢复失败", failures);
    }

    public void SetFlag(string name, bool on)
    {
        if (!Flags.TryGetValue(name, out var off))
            throw new ArgumentException($"unknown flag '{name}'");
        _mem.Write(Block + off, new[] { on ? (byte)1 : (byte)0 });
    }

    public bool GetFlag(string name) => _mem.Read(Block + Flags[name], 1)[0] != 0;

    /// <summary>武装选中条目捕获（zoom 桩把每次迭代的条目抄进块内数组）。</summary>
    public void ArmSelectionCapture(bool armed)
    {
        _mem.Write(Block + FlagCaptureSel, new[] { armed ? (byte)1 : (byte)0 });
        if (armed) _mem.Write(Block + CaptureCount, new byte[4]);
    }

    /// <summary>读取捕获到的选中条目（并解除武装）。</summary>
    public nuint[] ReadCapturedSelection()
    {
        var count = BitConverter.ToUInt32(_mem.Read(Block + CaptureCount, 4), 0);
        ArmSelectionCapture(false);
        if (count == 0) return Array.Empty<nuint>();
        if (count > 64) count = 64;
        var raw = _mem.Read(Block + CaptureArray, (int)(count * 4));
        var outp = new nuint[count];
        for (var i = 0; i < count; i++) outp[i] = BitConverter.ToUInt32(raw, i * 4);
        return outp;
    }

}
