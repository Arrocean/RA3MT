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
        ["buildanywhere"] = 0x0B,
        ["threatmax"] = 0x0D,
        ["threatzero"] = 0x0E,
            };

    public const uint BlockSize = 0x2000;
    public const uint StubArea = 0x40;

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

    public nuint Block { get; private set; }
    public bool Installed { get; private set; }

    private readonly IInjectionMemory _mem;
    private readonly nuint _rankApi;
    private readonly nuint _captureApi;
    private readonly nuint _killApi;
    private readonly nuint _spawnWrapperApi;
    private readonly nuint _hashLookupApi;
    private readonly nuint _hashTableGlobalVa;
    public bool RankBridgeEnabled => _rankApi != 0;
    public bool CaptureBridgeEnabled => _captureApi != 0;
    public bool KillBridgeEnabled => _killApi != 0;
    public bool SpawnBridgeEnabled => _spawnWrapperApi != 0 && _hashLookupApi != 0 && _hashTableGlobalVa != 0;
    public RankRequestMailbox? RankMailbox { get; private set; }
    public CaptureRequestMailbox? CaptureMailbox { get; private set; }
    public KillRequestMailbox? KillMailbox { get; private set; }
    public SpawnRequestMailbox? SpawnMailbox { get; private set; }
    private readonly nuint _rootVa;             // player-context root global
    private readonly Dictionary<string, HookResolution> _sites;
    private readonly Dictionary<string, string> _stubBySite;   // site id -> stub id
    private readonly List<(string hookId, byte[] original, nuint va)> _patched = new();
    private readonly Action<string>? _log;

    public MasterCode(IInjectionMemory mem, nuint imageBase, nuint playerRootVa,
        Dictionary<string, HookResolution> sites, IReadOnlyDictionary<string, HookDef> defs, Action<string>? log,
        nuint rankApi = 0, nuint captureApi = 0, nuint killApi = 0,
        nuint spawnWrapperApi = 0, nuint hashLookupApi = 0, nuint hashTableGlobalVa = 0)
    {
        _mem = mem;
        _rankApi = rankApi;
        _captureApi = captureApi;
        _killApi = killApi;
        _spawnWrapperApi = spawnWrapperApi;
        _hashLookupApi = hashLookupApi;
        _hashTableGlobalVa = hashTableGlobalVa;
        _rootVa = playerRootVa;
        _sites = sites;
        _stubBySite = defs.ToDictionary(kv => kv.Key, kv => kv.Value.Stub ?? kv.Key);
        _log = log;
    }

    public void Install()
    {
        if (Installed) return;
        if (_patched.Count != 0) throw new InvalidOperationException("残留挂钩尚未恢复，拒绝重新安装");
        if (StubArea < DiagSelIdx + 4)
            throw new InvalidOperationException("块内布局冲突：诊断区与桩代码区重叠");
        Block = _mem.Alloc(BlockSize);
        _mem.Write(Block, new byte[BlockSize]); // zero

        var layouts = new List<(string id, byte[] code)>();
        uint off = StubArea;
        foreach (var (id, site) in _sites.OrderBy(kv => kv.Key))
        {
            if (!_stubBySite.TryGetValue(id, out var stubId) || !StubGen.Handles(stubId)) continue;
            var siteEnd = site.Va + (nuint)site.Displaced.Length;
            var bridgeOffsets = new List<uint>();
            if (RankBridgeEnabled) bridgeOffsets.Add(RankDispatcher.CodeOffset);
            if (CaptureBridgeEnabled) bridgeOffsets.Add(CaptureDispatcher.CodeOffset);
            if (KillBridgeEnabled) bridgeOffsets.Add(KillDispatcher.CodeOffset);
            if (SpawnBridgeEnabled) bridgeOffsets.Add(SpawnDispatcher.CodeOffset);
            // Bridge consumers ride both settlement sites: money_h2 (cash settle)
            // and money_h1 (power settle). With infinite cash enabled the cash
            // settlement can go quiet for long stretches, but the power settle
            // keeps ticking, so mailbox requests get consumed either way.
            var code = bridgeOffsets.Count != 0 && (stubId == "money_h2" || stubId == "money_h1")
                ? RankDispatcher.EmitMoneyBridge(Block + off, siteEnd, Block, _rootVa, stubId, bridgeOffsets.ToArray())
                : StubGen.Emit(stubId, Block + off, siteEnd, Block, _rootVa, site.Displaced);
            var next = checked(off + (uint)((code.Length + 15) & ~15));
            if (next > CaptureCount)
                throw new InvalidOperationException($"Stub area overlaps capture data at hook '{id}'");
            layouts.Add((id, code));
            off = next;
        }

        if (RankBridgeEnabled)
        {
            if (!_sites.ContainsKey("money_h2")) throw new InvalidOperationException("Rank bridge requires money_h2");
            var dispatcher = RankDispatcher.Emit(Block + RankDispatcher.CodeOffset, Block, _rankApi, _rootVa);
            if (RankDispatcher.CodeOffset + (uint)dispatcher.Length > CaptureDispatcher.CodeOffset)
                throw new InvalidOperationException("Rank dispatcher overlaps capture dispatcher");
            _mem.Write(Block + RankDispatcher.CodeOffset, dispatcher);
            RankMailbox = new RankRequestMailbox(_mem, Block);
        }
        if (CaptureBridgeEnabled)
        {
            if (!_sites.ContainsKey("money_h2")) throw new InvalidOperationException("Capture bridge requires money_h2");
            var dispatcher = CaptureDispatcher.Emit(Block + CaptureDispatcher.CodeOffset, Block, _captureApi, _rootVa);
            if (CaptureDispatcher.CodeOffset + (uint)dispatcher.Length > KillDispatcher.CodeOffset)
                throw new InvalidOperationException("Capture dispatcher overlaps kill dispatcher");
            _mem.Write(Block + CaptureDispatcher.CodeOffset, dispatcher);
            CaptureMailbox = new CaptureRequestMailbox(_mem, Block);
        }
        if (KillBridgeEnabled)
        {
            if (!_sites.ContainsKey("money_h2")) throw new InvalidOperationException("Kill bridge requires money_h2");
            var dispatcher = KillDispatcher.Emit(Block + KillDispatcher.CodeOffset, Block, _killApi, _rootVa);
            if (KillDispatcher.CodeOffset + (uint)dispatcher.Length > RankRequestMailbox.Offset)
                throw new InvalidOperationException("Kill dispatcher overlaps mailboxes");
            _mem.Write(Block + KillDispatcher.CodeOffset, dispatcher);
            KillMailbox = new KillRequestMailbox(_mem, Block);
        }
        if (SpawnBridgeEnabled)
        {
            if (!_sites.ContainsKey("money_h2")) throw new InvalidOperationException("Spawn bridge requires money_h2");
            var dispatcher = SpawnDispatcher.Emit(Block + SpawnDispatcher.CodeOffset, Block,
                _spawnWrapperApi, _hashLookupApi, _hashTableGlobalVa, _rootVa);
            if (SpawnDispatcher.CodeOffset + (uint)dispatcher.Length > RankRequestMailbox.Offset)
                throw new InvalidOperationException("Spawn dispatcher overlaps mailboxes");
            _mem.Write(Block + SpawnDispatcher.CodeOffset, dispatcher);
            SpawnMailbox = new SpawnRequestMailbox(_mem, Block);
        }

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

    /// <summary>读取诊断捕获区（Block+0x10..0x30，8 个 dword）。</summary>
    public (nuint esi, nuint prodEax, nuint prodEsi, uint owner, nuint selEntry, nuint selArr, uint selIdx, nuint weaponEax)? ReadDiagnostics()
    {
        if (!Installed) return null;
        var b = _mem.Read(Block + 0x10, 0x20);
        return (
            BitConverter.ToUInt32(b, 0x00),
            BitConverter.ToUInt32(b, 0x04),
            BitConverter.ToUInt32(b, 0x08),
            BitConverter.ToUInt32(b, 0x0C),
            BitConverter.ToUInt32(b, 0x10),
            BitConverter.ToUInt32(b, 0x14),
            BitConverter.ToUInt32(b, 0x18),
            BitConverter.ToUInt32(b, 0x1C));
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
        "buildanywhere" => true,
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
        "buildanywhere" => BuildAnywhere(stubVa, siteEnd, block, replay),
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
    private static byte[] SidebarPts(nuint stubVa, nuint siteEnd, nuint block)
    {
        var c = new C(stubVa, siteEnd, block);
        c.A.Db(0x8B, 0x48, 0x50, 0x3B, 0x4E, 0x20);
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

    // 随地建造 — buildanywhere: 区域连线检查函数头（thiscall ret 8）
    // 目标函数唯一被 UI 放置谓词的 vf+0x48 调用（双版本各仅 1 个 xref），
    // 语义 = "A/B 两点（Bresenham 采样连线）是否同属一个可建造区域"。
    // 开 → 直接 al=1 返回（任意两点视为同区域，FINAL3 同语义）；
    // 关 → 逐字节重放 displaced 原指令后跳回（两版指令均无位置相关性）。
    // 地形/占用/碰撞由谓词第二层 ThePlacementGrid 验证保留，不会把建筑放进山里。
    private static byte[] BuildAnywhere(nuint stubVa, nuint siteEnd, nuint block, byte[]? replay)
    {
        if (replay is null || replay.Length < 5)
            throw new InvalidOperationException("buildanywhere requires the displaced replay bytes");
        var c = new C(stubVa, siteEnd, block);
        var a = c.A;
        a.Pushfd();
        c.Flag("buildanywhere");
        a.JneShort(1);
        a.Popfd();
        a.Db(0xB0, 0x01);                               // mov al,1
        a.Db(0xC2, 0x08, 0x00);                         // ret 8 (thiscall, two args)
        a.Label(1);
        a.Popfd();
        a.Db(replay);                                   // original position-independent prologue
        return c.Fin();                                 // jmp siteEnd
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
