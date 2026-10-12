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

    public MasterCode(IInjectionMemory mem, nuint imageBase, nuint playerRootVa,
        Dictionary<string, HookResolution> sites, IReadOnlyDictionary<string, HookDef> defs, Action<string>? log,
        nuint rankApi = 0, nuint captureApi = 0, nuint killApi = 0,
        nuint killDeathMarkerApi = 0,
        nuint spawnWrapperApi = 0, nuint hashLookupApi = 0, nuint hashTableGlobalVa = 0,
        nuint mouseObjGlobalVa = 0, nuint mouseTransformApi = 0)
    {
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
        if (RankBridgeEnabled) consumers.Add(new RankBridgeConsumer(_rankApi, _rootVa));
        if (CaptureBridgeEnabled) consumers.Add(new CaptureBridgeConsumer(_captureApi, _rootVa));
        if (KillBridgeEnabled) consumers.Add(new KillBridgeConsumer(_killApi, _rootVa));
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
                ? RankDispatcher.EmitMoneyBridge(Block + off, siteEnd, Block, _rootVa, stubId, bridgeOffsets)
                : StubGen.Emit(stubId, Block + off, siteEnd, Block, _rootVa, site.Displaced);
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

/// <summary>Pure x86 stub factory — byte-exact ports of the original TMK
/// MasterCode scripts. Pure functions so SelfCheck can dump &amp; verify every
/// stub without a live process.</summary>
public static class StubGen
{
    public static bool Handles(string id) => id switch
    {
        "money_h2" or "money_h1" or "money_h3" or "money_h4" or
        "proto_cool_a" or "proto_cool_b" or "power" or
        "build_power" or "build_hp_a" or "build_hp_b" or "sidebar_pts" or
        "power_cool" or "unit_lv" or "zoom_unit_xp" or "ammo" or "weapon_clip" or
        "aiblock" or "godmode" or "onekill" or "onekill_a" or "onekill_b" => true,
        _ => false,
    };

    /// <param name="stubVa">VA the emitted bytes will sit at (rel32 fixups)</param>
    /// <param name="siteEnd">VA right after the displaced bytes (jump-back target)</param>
    /// <param name="block">VA of the MasterCode block (flag bytes)</param>
    /// <param name="rootVa">VA of the player-context root global</param>
    /// <param name="replay">displaced bytes to replay verbatim (position-independent sites only)</param>
    public static byte[] Emit(string id, nuint stubVa, nuint siteEnd, nuint block, nuint rootVa,
        byte[]? replay = null) => id switch
    {
        "money_h2" => MoneyH2(stubVa, siteEnd, block),
        "money_h1" => MoneyH1(stubVa, siteEnd, block),
        "money_h3" => MoneyH3(stubVa, siteEnd, block),
        "money_h4" => MoneyH4(stubVa, siteEnd, block),
        "proto_cool_a" => ProtoCoolA(stubVa, siteEnd, block),
        "proto_cool_b" => ProtoCoolB(stubVa, siteEnd, block),
        "power" => Power(stubVa, siteEnd, block),
        "build_power" => BuildPower(stubVa, siteEnd, block, rootVa),
        "build_hp_a" => BuildHpA(stubVa, siteEnd, block, rootVa),
        "build_hp_b" => BuildHpB(stubVa, siteEnd, block),
        "sidebar_pts" => SidebarPts(stubVa, siteEnd, block),
        "power_cool" => PowerCool(stubVa, siteEnd, block),
        "unit_lv" => UnitLv(stubVa, siteEnd, block),
        "zoom_unit_xp" => ZoomUnitXp(stubVa, siteEnd, block),
        "ammo" => Ammo(stubVa, siteEnd, block),
        "weapon_clip" => WeaponClip(stubVa, siteEnd, block, rootVa),
        "aiblock" => AiBlock(stubVa, siteEnd, block, rootVa),
        "godmode" => GodMode(stubVa, siteEnd, block, rootVa),
        "onekill" => OneKill(stubVa, siteEnd, block, rootVa),
        "onekill_a" => OneKillA(stubVa, siteEnd, block),
        "onekill_b" => OneKillB(stubVa, siteEnd, block),
        _ => throw new NotImplementedException(id),
    };

    private sealed class C
    {
        public readonly Asm A = new();
        public readonly nuint StubVa;
        public readonly nuint SiteEnd;
        public readonly nuint Block;

        public C(nuint stubVa, nuint siteEnd, nuint block)
        {
            StubVa = stubVa;
            SiteEnd = siteEnd;
            Block = block;
        }

        public void Flag(string name) => A.CmpM8Abs((uint)(Block + MasterCode.Flags[name]), 1);
        public void FlagCaptureSel() => A.CmpM8Abs((uint)(Block + MasterCode.FlagCaptureSel), 1);

        public byte[] Fin()
        {
            A.JmpTo((uint)SiteEnd);
            return A.Build((uint)StubVa);
        }
    }

    // [01] 无限资金 — money_h2: add edi,[eax+4]; mov edx,[ecx]
    // 带 1000 万上限：长时间挂机时反复 +100000 会把 int32 加爆成负数（实测）
    private static byte[] MoneyH2(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("money");
        a.JneShort(1);
        a.CmpM32RegDisp8Imm32(R.Eax, 0x04, 10000000);     // 资金 ≥ 1000 万 → 不再加
        a.JaeShort(6);
        a.AddM32RegDisp8Imm32(R.Eax, 0x04, 0x186A0);      // [eax+4] += 100000
        a.Label(6);
        a.MovM32RegDisp8Imm32(R.Eax, 0x08, 0x05F5E0FF);   // [eax+8] = 99999999
        a.Label(1);
        a.Popfd();
        a.Db(0x03, 0x78, 0x04);                           // add edi,[eax+04]
        a.Db(0x8B, 0x11);                                 // mov edx,[ecx]
        return c.Fin();
    }

    // [02] 无限电力 — money_h1: mov eax,[eax+4]; mov ecx,[esi+3B0]
    private static byte[] MoneyH1(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        a.MovM32AbsReg(R.Esi, (uint)(block + MasterCode.DiagPlayerEsi)); // 诊断：捕获 esi
        c.Flag("power");
        a.JneShort(1);
        a.MovM32RegDisp8Imm32(R.Eax, 0x04, 0x186A0);      // [eax+4] = 100000
        a.MovM32RegDisp8Imm32(R.Eax, 0x08, 0);            // [eax+8] = 0（零耗电）
        a.Label(1);
        a.Popfd();
        a.Db(0x8B, 0x40, 0x04);                           // mov eax,[eax+04]
        a.Db(0x8B, 0x8E, 0xB0, 0x03, 0x00, 0x00);         // mov ecx,[esi+3B0]
        return c.Fin();
    }

    // [03] 无限协议点数 — money_h3: mov edi,[eax+34]; mov ecx,[esi+3C]
    private static byte[] MoneyH3(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("scpoints");
        a.JneShort(1);
        a.MovM32RegDisp8Imm32(R.Eax, 0x34, 15);
        a.Label(1);
        a.Popfd();
        a.Db(0x8B, 0x78, 0x34);                           // mov edi,[eax+34]
        a.Db(0x8B, 0x4E, 0x3C);                           // mov ecx,[esi+3C]
        return c.Fin();
    }

    // [04] 解锁全部协议 — money_h4: movss xmm0,[edi+2C]
    private static byte[] MoneyH4(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("allproto");
        a.JneShort(1);
        a.MovM32RegDisp8Imm32(R.Edi, 0x2C, 0x43C78000);   // [edi+2C] = 250.0f
        a.Label(1);
        a.Popfd();
        a.Db(0xF3, 0x0F, 0x10, 0x47, 0x2C);               // movss xmm0,[edi+2C]
        return c.Fin();
    }

    // [05] 快速建造 — proto_cool_a: fld [esi+1C]; mov [esi+5C],eax
    private static byte[] ProtoCoolA(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("fastbuild");
        a.JneShort(1);
        a.MovM32RegDisp8Imm32(R.Esi, 0x1C, 0x42C80000);   // [esi+1C] = 100.0f
        a.Label(1);
        a.Popfd();
        a.Db(0xD9, 0x46, 0x1C);                           // fld dword [esi+1C]
        a.Db(0x89, 0x46, 0x5C);                           // mov [esi+5C],eax
        return c.Fin();
    }

    // [05] 快速建造 — proto_cool_b: cvttss2si eax,[esi+1C]
    private static byte[] ProtoCoolB(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("fastbuild");
        a.JneShort(1);
        a.MovM32RegDisp8Imm32(R.Esi, 0x1C, 0x42C80000);
        a.Label(1);
        a.Popfd();
        a.Db(0xF3, 0x0F, 0x2C, 0x46, 0x1C);               // cvttss2si eax,[esi+1C]
        return c.Fin();
    }

    // [05] 快速建造（不断电） — power: fld [esi+1BC]
    private static byte[] Power(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("fastbuild");
        a.JneShort(1);
        a.Db(0x83, 0xFD, 0x01);                           // cmp ebp,1
        a.JeShort(1);
        a.Pushad();
        a.MovRegRegDisp8(R.Eax, R.Edi, 0x3C);             // eax=[edi+3C]
        a.IncReg(R.Eax);
        a.Db(0x89, 0x47, 0x14);                           // mov [edi+14],eax
        a.Popad();
        a.Label(1);
        a.Popfd();
        a.Db(0xD9, 0x86, 0xBC, 0x01, 0x00, 0x00);         // fld dword [esi+1BC]
        return c.Fin();
    }

    // [06]+[07] — build_power: mov ebx,[eax+418]
    private static byte[] BuildPower(nuint stubVa, nuint siteEnd, nuint block, nuint rootVa)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        a.Pushad();
        // 诊断：捕获 eax(生产对象) / esi / [eax+0x418](属主)
        a.MovM32AbsReg(R.Eax, (uint)(block + MasterCode.DiagProdEax));
        a.MovM32AbsReg(R.Esi, (uint)(block + MasterCode.DiagProdEsi));
        a.MovRegRegDisp32(R.Edx, R.Eax, 0x418);
        a.MovM32AbsReg(R.Edx, (uint)(block + MasterCode.DiagOwner));
        // [06] 协议/超武立即就绪：属主==己方 → [esi+20]=0
        // The global contains the local controller; controller+0x28 is the
        // side pointer compared with body+0x418 (verified in both game images).
        c.Flag("instantready");
        a.JneShort(2);
        a.MovRegAbs(R.Ebx, (uint)rootVa);
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(2);                                     // 尚未捕获玩家 → 跳过
        a.MovRegRegDisp8(R.Ecx, R.Ebx, 0x28);
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(3);                                     // local side unavailable: no mutation
        a.CmpRegMRegDisp32(R.Ecx, R.Eax, 0x418);          // cmp ecx,[eax+418]
        a.JneShort(2);
        a.MovM32RegDisp8Imm32(R.Esi, 0x20, 0);
        // [07] 冻结敌方：属主!=己方 → [esi+20]+=1
        a.Label(2);
        c.Flag("freezeenemy");
        a.JneShort(3);
        a.MovRegAbs(R.Ebx, (uint)rootVa);
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(3);
        a.MovRegRegDisp8(R.Ecx, R.Ebx, 0x28);
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(3);                                     // local side unavailable: no mutation
        a.CmpRegMRegDisp32(R.Ecx, R.Eax, 0x418);
        a.JeShort(3);                                     // 属主==己方 → 跳过
        a.AddM32RegDisp8Imm8(R.Esi, 0x20, 1);
        a.Label(3);
        a.Popad();
        a.Popfd();
        a.Db(0x8B, 0x7E, 0x20);                           // reload deadline: game cached EDI before hook
        a.Db(0x8B, 0x98, 0x18, 0x04, 0x00, 0x00);         // mov ebx,[eax+418]
        return c.Fin();
    }

    // [06]+[07] — build_hp_a: mov esi,[eax+50]; mov eax,[ecx]（先重放，逻辑用 eax）
    private static byte[] BuildHpA(nuint stubVa, nuint siteEnd, nuint block, nuint rootVa)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Db(0x8B, 0x70, 0x50);                           // mov esi,[eax+50]
        a.Db(0x8B, 0x01);                                 // mov eax,[ecx]
        a.Pushfd();
        a.Pushad();
        // Mirror the game's search: ECX=sentinel, EDX=power key, EAX=head.
        // JMP detour has no extra CALL return: saved side is [esp+0x28].
        a.Db(0x8B, 0xF9);                                 // mov edi,ecx
        a.Db(0xBB, 0x00, 0x10, 0x00, 0x00);               // bounded 4096 nodes
        a.Label(7);
        a.Db(0x3B, 0xC7);                                 // cmp eax,edi
        a.JeShort(3);
        a.TestRegReg(R.Eax, R.Eax);
        a.JeShort(3);
        a.Db(0x39, 0x50, 0x08);                           // cmp [eax+8],edx
        a.JeShort(8);
        a.MovRegRegInd(R.Eax, R.Eax);
        a.Db(0x4B);                                       // dec ebx
        a.JneShort(7);
        a.JmpShort(3);
        a.Label(8);
        a.MovRegAbs(R.Ebx, (uint)rootVa);
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(3);
        a.MovRegRegDisp8(R.Ecx, R.Ebx, 0x28);
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(3);
        a.CmpRegMEspDisp32(R.Ecx, 0x28);
        a.JneShort(9);
        c.Flag("instantready");
        a.JneShort(3);
        a.Db(0x89, 0x70, 0x0C);                           // matched deadline=current clock ESI
        a.JmpShort(3);
        a.Label(9);
        c.Flag("freezeenemy");
        a.JneShort(3);
        a.AddM32RegDisp8Imm8(R.Eax, 0x0C, 1);
        a.Label(3);
        a.Popad();
        a.Popfd();
        return c.Fin();
    }

    // Completion predicate: replay only; no owner survives at this site.
    private static byte[] BuildHpB(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        c.A.Db(0x8B, 0x51, 0x50, 0x3B, 0x50, 0x0C);
        return c.Fin();
    }

    // Completion predicate fallback: replay only, never freeze unrelated owners.
    private static byte[] SidebarPts(nuint stubVA, nuint siteEnd, nuint block)
    {
        var c = new C(stubVA, siteEnd, block);
        c.A.Db(0x8B, 0x48, 0x50, 0x3B, 0x4E, 0x20);
        return c.Fin();
    }

    // [F10] 禁止电脑建造 — aiblock: add edx,[eax+4]; cmp edx,edi
    // 生产付款点：eax=生产队列条目（[ebp+0xE4] 数组第 0 项），[eax+4]=每拍进度
    // 增量、[eax+0x14]=已付、edi=剩余预算；edx≥edi 走完成路径。FINAL3 的启用档
    // （script_09 → iEnable+15=1）把非本地条目的增量钉 1——每拍只付 1，任何
    // 单位/建筑都造不完（它默认的 5000 档=瞬间完成，不抄）。
    // 属主：条目 [eax+0xC] 是玩家槽位号（int，游戏经 [root+idx*4+0x30] 解析玩家
    // ——0x4761A0），本地槽位号=[[[root]+0x28]+0x20]（游戏自己的本地判定链，
    // 双版 24/32 处同型，如 0x11F4BE/0x547B10）。v27 曾拿条目槽位跟 side 指针
    // 本身比（永远不等）→ 连己方一起钉，实测翻车后改链。
    private static byte[] AiBlock(nuint stubVA, nuint siteEnd, nuint block, nuint rootVA)
    {
        var c = new C(stubVA, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        a.Pushad();                                       // edx/edi hold live progress state
        c.Flag("aiblock");
        a.JneShort(1);
        a.MovRegAbs(R.Ebx, (uint)rootVA);
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(1);                                     // 尚未捕获玩家 → 跳过
        a.MovRegRegDisp8(R.Ecx, R.Ebx, 0x28);             // ecx = side
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(1);                                     // local side unavailable: no mutation
        a.MovRegRegDisp8(R.Ecx, R.Ecx, 0x20);             // ecx = [side+0x20] 本地玩家槽位号（0 合法，不做 test）
        a.CmpRegMRegDisp32(R.Ecx, R.Eax, 0xC);            // cmp localSlot,[entry+0xC]
        a.JeShort(1);                                     // 属主==己方 → 跳过
        a.MovM32RegDisp8Imm32(R.Eax, 0x04, 1);            // 敌方增量钉 1
        a.Label(1);
        a.Popad();
        a.Popfd();
        a.Db(0x03, 0x50, 0x04);                           // add edx,[eax+04]
        a.Db(0x3B, 0xD7);                                 // cmp edx,edi（标志供随后的 jb 消费）
        return c.Fin();
    }

    // [F11] 玩家无敌 — godmode: mov edx,[eax+3C]; mov ecx,esi
    // FINAL3 EA 0x12EEDF 的包含函数（0x12EEA0）与重打包 1.13 0x1588C0 / 1.12
    // 0x1705A0 逐指令同构：this=ebx=drawable → [ebx+0x138]=body → esi=[body+0x33C]
    // 健康模块 → vt+0x48(上限)/vt+0x3C(当前) 读取（血条渲染，每帧跑）。
    // FINAL3 机制：读取时把健康模块的**真实 HP 字段** +4(当前)/+0xC(上限) 重置
    // 1000000.0——掉血一帧内被刷回满，相当于无敌。属主 [body+0x418] 与
    // [[root]+0x28] 比（阵营指针编码，rank/spawn 桥同款）。
    private static byte[] GodMode(nuint stubVA, nuint siteEnd, nuint block, nuint rootVA)
    {
        var c = new C(stubVA, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        a.Pushad();                                       // ebx/esi/eax live at the site
        c.Flag("godmode");
        a.JneShort(1);
        a.MovRegRegDisp32(R.Ecx, R.Ebx, 0x138);           // ecx = [drawable+0x138] body
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(1);                                     // 防御：无 body 跳过（FINAL3 不查）
        a.MovRegRegDisp32(R.Edi, R.Ecx, 0x418);           // edi = 属主
        a.TestRegReg(R.Esi, R.Esi);
        a.JeShort(1);                                     // 防御：健康模块空跳过
        a.MovRegAbs(R.Ebx, (uint)rootVA);
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(1);                                     // 尚未捕获玩家 → 跳过
        a.MovRegRegDisp8(R.Edx, R.Ebx, 0x28);             // edx = side
        a.TestRegReg(R.Edx, R.Edx);
        a.JeShort(1);                                     // local side unavailable: no mutation
        a.Db(0x39, 0xD7);                                 // cmp edi,edx（属主 vs 本地阵营）
        a.JneShort(1);                                    // 属主!=己方 → 跳过
        a.MovM32RegDisp8Imm32(R.Esi, 0x04, 0x497423F0);   // [health+4]  = 1000000.0f
        a.MovM32RegDisp8Imm32(R.Esi, 0x0C, 0x497423F0);   // [health+0xC] = 1000000.0f
        a.Label(1);
        a.Popad();
        a.Popfd();
        a.Db(0x8B, 0x50, 0x3C);                           // mov edx,[eax+3C]
        a.Db(0x8B, 0xCE);                                 // mov ecx,esi
        return c.Fin();
    }

    // [F12] 一击必杀 — 主钩 onekill: movss [esi+4],xmm0
    // EA 0x3651AE ≡ 1.13 0x38CB4E ≡ 1.12 0x3A366E（HP adjust 方法，kill 桥
    // 早已验证的 0x38CB30/0x3A3650 +0x1E）。FINAL3 语义：esi 是刚被数据钩子
    // 捕获的健康模块、属主槽位≠本地槽位 → 当前/上限 HP 双清零 + xmm0 置 0
    // （重放写入 0）= 该单位即刻死亡。FINAL3 的 [esi-8] 反查 body 以捕获槽
    // 替代（数据钩子存的就是同一 body）。
    // 门控偏离说明：FINAL3 用 [body+390|394|3A0|3AC] 任一非零做门——实测
    // （v30）敌方主基地等无武装建筑全零被挡，无法一击必杀；换成"本次增量
    // xmm1<0"（真伤害才杀，治疗/修理跳过），语义更准且覆盖建筑。
    private static byte[] OneKill(nuint stubVA, nuint siteEnd, nuint block, nuint rootVA)
    {
        var c = new C(stubVA, siteEnd, block);
        var a = c.A;
        a.Pushfd();                                       // 站点后的 je 消费函数头 test 的标志
        a.Pushad();
        c.Flag("onekill");
        a.JneShort(1);
        a.Db(0x0F, 0x2F, 0x0D);                           // comiss xmm1,[block+0x3C]（0.0f）
        a.Db(BitConverter.GetBytes((uint)(block + MasterCode.OneKillZero)));
        a.JaeShort(1);                                    // 增量≥0（治疗/修理）→ 放行
        a.IncM32Abs((uint)(block + MasterCode.OneKillSiteHits));  // 诊断：真伤害到达计数
        a.MovRegAbs(R.Eax, (uint)(block + MasterCode.OneKillHealth));
        a.Db(0x39, 0xF0);                                 // cmp eax,esi（≠刚捕获的受害者 → 放行）
        a.JneShort(1);
        a.MovRegAbs(R.Eax, (uint)(block + MasterCode.OneKillBody));
        a.TestRegReg(R.Eax, R.Eax);
        a.JeShort(1);
        a.MovRegRegDisp32(R.Ecx, R.Eax, 0x418);           // 属主
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(1);
        a.MovRegRegDisp8(R.Eax, R.Ecx, 0x20);             // 属主槽位号
        a.MovRegAbs(R.Ebx, (uint)rootVA);                 // [root global] → root 对象
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(1);
        a.MovRegRegDisp8(R.Edx, R.Ebx, 0x28);             // side
        a.TestRegReg(R.Edx, R.Edx);
        a.JeShort(1);
        a.MovRegRegDisp8(R.Edx, R.Edx, 0x20);             // 本地槽位号
        a.Db(0x39, 0xD0);                                 // cmp eax,edx
        a.JeShort(1);                                     // 己方单位 → 放行
        a.IncM32Abs((uint)(block + MasterCode.OneKillKills));      // 诊断：击杀分支计数
        a.Db(0x0F, 0x57, 0xC0);                           // xorps xmm0,xmm0（重放将写 0）
        a.MovM32RegDisp8Imm32(R.Esi, 0x04, 0);            // 当前 HP = 0
        a.MovM32RegDisp8Imm32(R.Esi, 0x0C, 0);            // 上限 HP = 0
        a.Label(1);
        a.Popad();
        a.Popfd();
        a.Db(0xF3, 0x0F, 0x11, 0x46, 0x04);               // movss [esi+4],xmm0
        return c.Fin();
    }

    // [F12] 数据钩 A — onekill_a: mov ecx,[esi+0x33C]
    // EA 0x3FE714 ≡ 1.13 0x427B34 ≡ 1.12 0x43C964（esi=body 的伤害处理路径）。
    // 无 pushfd/pushad：指令本身只写 ecx（重放同款），标志零扰动。
    private static byte[] OneKillA(nuint stubVA, nuint siteEnd, nuint block)
    {
        var c = new C(stubVA, siteEnd, block);
        var a = c.A;
        a.Db(0x8B, 0x8E, 0x3C, 0x03, 0x00, 0x00);         // mov ecx,[esi+0x33C]（重放）
        a.MovM32AbsReg(R.Esi, (uint)(block + MasterCode.OneKillBody));
        a.MovM32AbsReg(R.Ecx, (uint)(block + MasterCode.OneKillHealth));
        return c.Fin();
    }

    // [F12] 数据钩 B — onekill_b: mov ecx,[ecx+0x33C]
    // EA 0x2E24E3 ≡ 1.13 0x30B6C3 ≡ 1.12 0x320963（ecx=body 的另一条路径）。
    private static byte[] OneKillB(nuint stubVA, nuint siteEnd, nuint block)
    {
        var c = new C(stubVA, siteEnd, block);
        var a = c.A;
        a.MovM32AbsReg(R.Ecx, (uint)(block + MasterCode.OneKillBody)); // 捕获 body（重放前，ecx 尚是 body）
        a.Db(0x8B, 0x89, 0x3C, 0x03, 0x00, 0x00);         // mov ecx,[ecx+0x33C]（重放）
        a.MovM32AbsReg(R.Ecx, (uint)(block + MasterCode.OneKillHealth));
        return c.Fin();
    }


    // [08] Camera zoom limit — power_cool: movss [esi+44],xmm0
    // 特殊：游戏后续指令是 je（消费桩设置的 ZF）——沿用原版 TMK 技巧：
    // 开 → ZF=1（分支成立）；关 → 还原原始标志。
    private static byte[] PowerCool(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        a.Db(0xF3, 0x0F, 0x11, 0x46, 0x44);               // movss [esi+44],xmm0
        c.Flag("zoom");                                   // 设置 ZF=(flag==1)
        a.JeShort(1);
        a.Popfd();                                        // 关：还原原始标志
        a.JmpTo((uint)siteEnd);
        a.Label(1);
        a.Db(0x83, 0x0C, 0x24, 0x40);                     // or dword [esp],0x40: force ZF, preserve other EFLAGS
        a.Popfd();
        a.JmpTo((uint)siteEnd);
        return a.Build((uint)stubVa);
    }

    // [09] 地图全开 — unit_lv: movss [ebp+260],xmm0
    private static byte[] UnitLv(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("revealmap");
        a.JneShort(1);
        a.MovM32RegDisp32Imm32(R.Ebp, 0x260, 0x47C35000); // [ebp+260]=100000.0f
        a.Popfd();
        a.JmpTo((uint)siteEnd);                           // 开：跳过原始写入
        a.Label(1);
        a.Popfd();
        a.Db(0xF3, 0x0F, 0x11, 0x85, 0x60, 0x02, 0x00, 0x00); // movss [ebp+260],xmm0
        return c.Fin();
    }

    // [10] 经验999 — zoom_unit_xp: mov ecx,[edx+edi*4]; test ecx,ecx（先重放，ZF 需还原）
    private static byte[] ZoomUnitXp(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Db(0x8B, 0x0C, 0xBA);                           // mov ecx,[edx+edi*4]
        a.Db(0x85, 0xC9);                                 // test ecx,ecx
        a.Pushfd();                                       // preserve TEST before capture's CMP/INC
        // 诊断：捕获 ecx(选中条目) / edx(数组) / edi(下标)
        a.MovM32AbsReg(R.Ecx, (uint)(block + MasterCode.DiagSelEntry));
        a.MovM32AbsReg(R.Edx, (uint)(block + MasterCode.DiagSelArr));
        a.MovM32AbsReg(R.Edi, (uint)(block + MasterCode.DiagSelIdx));
        // 选中条目捕获数组：armed 时 entries[count++] = ecx（上限 64）
        c.FlagCaptureSel();
        a.JneShort(5);
        a.Pushad();
        a.MovRegAbs(R.Edx, (uint)(block + MasterCode.CaptureCount));
        a.CmpR32Imm32(R.Edx, 64);
        a.JaeShort(6);
        // mov [block+CaptureArray + edx*4], ecx
        byte sib = (byte)((2 << 6) | ((int)R.Edx << 3) | 5);
        a.Db(0x89, Asm.Modrm(0, R.Ecx, R.Esp), sib);
        a.Db(BitConverter.GetBytes((uint)(block + MasterCode.CaptureArray)));
        a.IncM32Abs((uint)(block + MasterCode.CaptureCount));
        a.Label(6);
        a.Popad();
        a.Label(5);
        // These are Weapon entries, not selected Drawables. Weapon+0x1C
        // is clip ammo, not experience; selected actions use the real list.
        a.Popfd();                                        // restore original TEST flags
        return c.Fin();
    }

    private static byte[] WeaponClip(nuint stubVa, nuint siteEnd, nuint block, nuint rootVa)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Db(0x83, 0xC8, 0xFF, 0x01, 0x46, 0x1C);       // original shot consumption
        a.Pushfd();
        a.Pushad();
        c.Flag("ammo");
        a.JneShort(1);
        a.MovRegRegDisp8(R.Ebx, R.Esi, 8);                // WeaponSlot
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(1);
        a.MovRegRegDisp8(R.Ebx, R.Ebx, 0x10);             // Body
        a.TestRegReg(R.Ebx, R.Ebx);
        a.JeShort(1);
        a.MovRegRegDisp32(R.Edx, R.Ebx, 0xF4);            // Drawable
        a.TestRegReg(R.Edx, R.Edx);
        a.JeShort(1);
        a.Db(0xF6, 0x82, 0x3D, 0x01, 0x00, 0x00, 0x40); // selected bit
        a.JeShort(1);
        a.MovRegAbs(R.Ecx, (uint)rootVa);
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(1);
        a.MovRegRegDisp8(R.Ecx, R.Ecx, 0x28);
        a.TestRegReg(R.Ecx, R.Ecx);
        a.JeShort(1);
        a.CmpRegMRegDisp32(R.Ecx, R.Ebx, 0x418);
        a.JneShort(1);
        a.MovRegRegDisp8(R.Eax, R.Esi, 4);                // weapon template wrapper
        a.TestRegReg(R.Eax, R.Eax);
        a.JeShort(1);
        a.MovRegRegDisp8(R.Eax, R.Eax, 4);
        a.TestRegReg(R.Eax, R.Eax);
        a.JeShort(1);
        a.MovRegRegDisp8(R.Eax, R.Eax, 0x70);             // clip capacity
        a.Db(0x48);                                      // dec eax: reject zero/negative capacity
        a.CmpR32Imm32(R.Eax, 1000000);
        a.JaeShort(1);
        a.IncReg(R.Eax);
        a.Db(0x89, 0x46, 0x1C);                          // refill only clip; preserve burst counters
        a.Label(1);
        a.Popad();
        a.Popfd();
        return c.Fin();
    }


    // 威胁等级访问器（旧名 ammo 站点族）：eax=[ecx+0x1278] 为 RedAlert 威胁分量，+8 为威胁值。
    // EA FINAL3 Danger Level 语义：标志=1 → [分量+8]=50000（最大）；=2 → 0（归零）。
    // 拆成两个独立开关，同开时"最大"优先；恢复=双关（交还游戏自然重算）。
    // ammo: mov eax,[ecx+1278]
    private static byte[] Ammo(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Db(0x8B, 0x81, 0x78, 0x12, 0x00, 0x00);         // mov eax,[ecx+1278]
        a.MovM32AbsReg(R.Eax, (uint)(block + MasterCode.DiagWeaponEax)); // 诊断捕获
        a.Pushfd();
        a.TestRegReg(R.Eax, R.Eax);
        a.JeShort(1);                                     // 无威胁分量 → 不写
        c.Flag("threatmax");
        a.JneShort(2);
        a.MovM32RegDisp8Imm32(R.Eax, 0x08, 50000);        // [eax+08] = 50000（最大）
        a.JmpShort(1);
        a.Label(2);
        c.Flag("threatzero");
        a.JneShort(1);
        a.MovM32RegDisp8Imm32(R.Eax, 0x08, 0);            // [eax+08] = 0（归零）
        a.Label(1);
        a.Popfd();
        return c.Fin();
    }

}
