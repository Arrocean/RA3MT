using RA3MT.Core.Engine;
using RA3MT.Core.Model;
using RA3MT.Core.Scan;
using RA3MT.Core.Target;

if (args.Length == 1 && args[0] == "identitytest")
{
    RA3MT.SelfCheck.IdentityChecks.Run();
    return 0;
}
if (args.Length == 1 && args[0] == "identity-child")
{
    RA3MT.SelfCheck.IdentityChecks.Child();
    return 0;
}

// stub-dump mode: emit every MasterCode stub to a folder (for offline
// disassembly verification)
if (args.Length == 1 && args[0] == "uprisingtest")
{
    RA3MT.SelfCheck.UprisingChecks.Run();
    return 0;
}

if (args.Length is 1 or 2 && args[0] == "uprisingattachtest")
{
    RA3MT.SelfCheck.UprisingChecks.LiveAttach(args.Length==2 ? int.Parse(args[1]) : null);
    return 0;
}

if (args.Length is 1 or 2 && args[0] == "uprising-selectiontest")
{
    RA3MT.SelfCheck.UprisingChecks.LiveSelection(args.Length == 2 ? int.Parse(args[1]) : null);
    return 0;
}

if (args.Length is 2 or 3 && args[0] is "stubdump" or "uprising-stubdump")
{
    var uprisingDump = args[0] == "uprising-stubdump";
    var dumpData = FeaturesData.LoadEmbedded(uprisingDump ? GameId.Uprising : GameId.RedAlert3);
    var dumpVersion = args.Length == 3 ? args[2] : uprisingDump ? "uprising-1.01" : "1.13";
    if (uprisingDump != GameLayout.IsUprising(dumpVersion))
        throw new ArgumentException("Dump version does not belong to the selected game");
    if (dumpData.Hooks.Values.Any(h => !h.Rva.ContainsKey(dumpVersion)))
        throw new ArgumentException("Unknown dump build");
    var dumpLayout = GameLayout.For(dumpVersion);
    Directory.CreateDirectory(args[1]);
    var fakeBase = 0x40000000u;   // synthetic MasterCode block VA
    var fakeRoot = 0x400000u;     // synthetic player-root VA
    var fakeSite = 0x452100u;     // synthetic site VA; siteEnd = site+displacedLen
    foreach (var (id, def) in dumpData.Hooks)
    {
        var stubId = def.Stub ?? id;
        if (!StubGen.Handles(stubId)) continue;
        var displaced = def.DisplacedBytes(dumpVersion);
        var siteEnd = fakeSite + (uint)displaced.Length;
        var code = StubGen.Emit(stubId, fakeBase + MasterCode.StubArea, siteEnd, fakeBase, fakeRoot, displaced, dumpLayout);
        File.WriteAllBytes(Path.Combine(args[1], $"{id}.bin"), code);
        File.WriteAllText(Path.Combine(args[1], $"{id}.meta"),
            $"stubVa=0x{fakeBase + MasterCode.StubArea:X}\nsiteEnd=0x{siteEnd:X}\nlen={code.Length}\n");
        Console.WriteLine($"{id,-14} {code.Length} bytes -> {id}.bin");
    }
    File.WriteAllBytes(Path.Combine(args[1], "money_h2_rank.bin"),
        RankDispatcher.EmitMoneyBridge(dumpLayout, 0x40000040, 0x452105, 0x40000000, 0x400000, "money_h2", RankDispatcher.CodeOffset));
    File.WriteAllBytes(Path.Combine(args[1], "money_h2_full_bridge.bin"),
        RankDispatcher.EmitMoneyBridge(dumpLayout, 0x40000040, 0x452105, 0x40000000, 0x400000, "money_h2",
            RankDispatcher.CodeOffset, CaptureDispatcher.CodeOffset, KillDispatcher.CodeOffset));
    File.WriteAllBytes(Path.Combine(args[1], "money_h1_full_bridge.bin"),
        RankDispatcher.EmitMoneyBridge(dumpLayout, fakeBase+MasterCode.StubArea,
            fakeSite+(uint)dumpData.Hooks["money_h1"].DisplacedBytes(dumpVersion).Length, fakeBase, fakeRoot, "money_h1",
            RankDispatcher.CodeOffset,CaptureDispatcher.CodeOffset,KillDispatcher.CodeOffset,SpawnDispatcher.CodeOffset));
    File.WriteAllBytes(Path.Combine(args[1], "rank_dispatcher.bin"),
        RankDispatcher.Emit(0x40001100, 0x40000000, 0x785600, 0x400000, dumpLayout));
    File.WriteAllBytes(Path.Combine(args[1], "capture_dispatcher.bin"),
        CaptureDispatcher.Emit(0x40001280, 0x40000000, 0x7B5DF0, 0x400000, dumpLayout));
    File.WriteAllBytes(Path.Combine(args[1], "kill_dispatcher.bin"),
        KillDispatcher.Emit(0x40001400, 0x40000000, 0x7C7190, 0x400000, dumpLayout));
    File.WriteAllBytes(Path.Combine(args[1], "spawn_dispatcher.bin"),
        SpawnDispatcher.Emit(0x40001580, 0x40000000, 0x62E3E0, 0x80D5B0, 0xCF0108, 0x400000,
            0xCE43BC, 0x60ECF0));
    File.WriteAllBytes(Path.Combine(args[1], "money_h2_spawn_bridge.bin"),
        RankDispatcher.EmitMoneyBridge(dumpLayout, 0x40000040, 0x452105, 0x40000000, 0x400000, "money_h2",
            RankDispatcher.CodeOffset, CaptureDispatcher.CodeOffset, KillDispatcher.CodeOffset,
            SpawnDispatcher.CodeOffset));
    return 0;
}

if (args.Length is >=1 and <=3 && args[0] == "livetest")
{
    // Read-only live verification: find the running game, classify the build,
    // resolve every hook site and bridge API against live memory. Nothing is
    // written and no hooks are installed — safe to run against any build.
    var liveGame = args.Length>=2 && args[1]=="uprising" ? GameId.Uprising : GameId.RedAlert3;
    var liveData = FeaturesData.LoadEmbedded(liveGame);
    var liveFound = RA3MT.Core.Memory.ProcessMemory.FindGame(liveData.Game.ModuleNames,args.Length==3?int.Parse(args[2]):null)
                    ?? throw new InvalidOperationException("未找到运行中的红警3进程（请先启动游戏）");
    var liveMem = new RA3MT.Core.Memory.ProcessMemory(liveFound.pid);
    var liveMain = System.Diagnostics.Process.GetProcessById(liveFound.pid).MainModule
                   ?? throw new InvalidOperationException("无法读取主模块");
    var liveBase = (nuint)liveMain.BaseAddress;
    var liveVersion = liveGame == GameId.Uprising
        ? GameBuildClassifier.ClassifyUprising(new DelegateImageReader((r,l) => liveMem.Read(liveBase+r,l)),liveFound.version,liveData)
        : liveFound.version == "1.12"
        ? RA3MT.Core.Target.GameBuildClassifier.Classify(liveMem, liveBase, liveData)
        : liveFound.version;

    Console.WriteLine($"live pid={liveFound.pid}");
    Console.WriteLine($"live module={liveFound.modulePath}");
    Console.WriteLine($"live module-version={liveFound.version} -> classified={liveVersion}");

    var liveImage = new RA3MT.Core.Target.DelegateImageReader((rva, len) => liveMem.Read(liveBase + rva, len));
    var liveText = PeTextSection.Read(liveImage);
    var liveSites = HookResolver.ResolveAll(liveData, liveVersion, liveImage.Read, liveText, liveBase);
    Console.WriteLine($"live hook sites: {liveSites.Count}/{liveData.Hooks.Count} 字节校验通过");
    var liveMethods = liveSites.Values.GroupBy(s => s.Method)
        .Select(g => $"{g.Key}={g.Count()}");
    Console.WriteLine($"live methods: {string.Join(" ", liveMethods)}");

    var rank = RA3MT.Core.Target.RankApiResolver.Resolve(liveVersion, liveBase, liveImage);
    var capture = RA3MT.Core.Target.CaptureApiResolver.Resolve(liveVersion, liveBase, liveImage);
    var (killAdj, killMark, killDmg) = RA3MT.Core.Target.KillApiResolver.Resolve(liveVersion, liveBase, liveImage);
    var spawn = SpawnApiResolver.Resolve(liveVersion, liveBase, liveImage.Read);
    var support = SpawnSupportApiResolver.Resolve(liveVersion, liveBase, liveImage.Read);
    Console.WriteLine($"live bridges: rank=0x{rank.Value:X} capture=0x{capture.Value:X} kill=0x{killAdj:X}/0x{killMark:X}/0x{killDmg:X}");
    Console.WriteLine($"live spawn: wrapper=0x{spawn:X} lookup=0x{support.TemplateHashLookup:X} " +
                      $"owner=0x{support.OwnerResolver:X} transform=0x{support.MouseScreenToWorld:X}");

    var ok = liveSites.Count == liveData.Hooks.Count;
    Console.WriteLine(ok
        ? $"PASS live {liveVersion}: full hook + bridge resolution against the running process"
        : $"FAIL live {liveVersion}: only {liveSites.Count}/{liveData.Hooks.Count} sites resolved");
    return ok ? 0 : 1;
}

if (args.Length == 1 && args[0] == "bridgetest")
{
    var rankDataDir = TrainerGameDataDir() ?? throw new InvalidOperationException("Game Data directory not found");
    foreach (var (version, gameFile) in VersionImages(rankDataDir))
    {
        var image = new StaticImage(gameFile);
        var rank = RA3MT.Core.Target.RankApiResolver.Resolve(version, 0x400000, (rva, len) => image.GetRva(rva, len));
        var capture = RA3MT.Core.Target.CaptureApiResolver.Resolve(version, 0x400000, (rva, len) => image.GetRva(rva, len));
        var (kill, killMarker, killDamage) = RA3MT.Core.Target.KillApiResolver.Resolve(version, 0x400000, (rva, len) => image.GetRva(rva, len));
        Console.WriteLine($"PASS {version} rank 0x{rank:X} capture 0x{capture:X} kill-damage 0x{killDamage:X} marker 0x{killMarker:X}");
        foreach (var (name, resolve, altered) in new (string, Func<object>, int)[]
                 {
                     ("rank", () => RA3MT.Core.Target.RankApiResolver.Resolve(version, 0x400000, (r, l) => Alter(image, r, l, 0)), 0),
                     ("capture", () => RA3MT.Core.Target.CaptureApiResolver.Resolve(version, 0x400000, (r, l) => Alter(image, r, l, 1)), 1),
                     ("kill-damage", () => RA3MT.Core.Target.KillApiResolver.Resolve(version, 0x400000, (r, l) => Alter(image, r, l, 0xA)), 0xA),
                     ("kill-adjust", () => RA3MT.Core.Target.KillApiResolver.Resolve(version, 0x400000, (r, l) => Alter(image, r, l, 0x2)), 0x2),
                 })
        {
            var refused = false;
            try { resolve(); }
            catch (InvalidOperationException) { refused = true; }
            if (!refused) throw new Exception($"Altered {name} contract accepted");
        }
        Console.WriteLine($"PASS {version} four altered bridge contracts rejected");
    }
    RA3MT.SelfCheck.BridgeMailboxChecks.Run();
    return 0;

    byte[] Alter(StaticImage img, uint rva, int len, int index)
    {
        var code = img.GetRva(rva, len);
        if (index < code.Length) code[index] ^= 1;
        return code;
    }
}

if (args.Length == 1 && args[0] == "spawntest")
{
    var spawnDataDir = TrainerGameDataDir() ?? throw new InvalidOperationException("Game Data directory not found");
    var cases = 0;
    foreach (var (version, gameFile) in VersionImages(spawnDataDir))
    {
        var image = new StaticImage(gameFile);
        var address = SpawnApiResolver.Resolve(version, 0x400000, (rva, len) => image.GetRva(rva, len));
        Console.WriteLine($"PASS {version} strict spawn wrapper identity 0x{address:X} (304 bytes)");
        var support = SpawnSupportApiResolver.Resolve(version, 0x400000,
            (rva, len) => image.GetRva(rva, len));
        Console.WriteLine($"PASS {version} startup hash/owner helper identities " +
                          $"lookup=0x{support.TemplateHashLookup:X}, owner=0x{support.OwnerResolver:X}");
        foreach (var changedRva in new[]
                 {
                     version switch { "1.12" => 0x422510u, "1.12ea" => 0x3E4230u, _ => 0x40D5B0u },
                     version switch { "1.12" => 0x4793B0u, "1.12ea" => 0x43B300u, _ => 0x4647A0u },
                     version switch { "1.12" => 0x1175D0u, "1.12ea" => 0xD5400u, _ => 0xFF4A0u },
                     version switch { "1.12" => 0x2442BAu, "1.12ea" => 0x20540Au, _ => 0x22E5AAu }, // caller-site anchor
                 })
        {
            var refused = false;
            try
            {
                SpawnSupportApiResolver.Resolve(version, 0x400000, (rva, len) =>
                {
                    var bytes = image.GetRva(rva, len);
                    if (rva == changedRva) bytes[^1] ^= 1;
                    return bytes;
                });
            }
            catch (InvalidOperationException) { refused = true; }
            if (!refused) throw new Exception($"Altered {version} spawn support API accepted at 0x{changedRva:X}");
            cases++;
        }
        var entry = version switch { "1.12" => 0x2440F0u, "1.12ea" => 0x205240u, _ => 0x22E3E0u };
        var changed = new HashSet<int> { 0, 0x19, 0x98, 0xA7, 0xDA, 0x12F };
        foreach (var offset in new[] { 0x5B, 0x71, 0x93, 0x9F, 0xAC, 0xBF, 0xC8, 0xD3, 0xDF, 0x107, 0x119, 0x121 })
            changed.Add(offset + 1); // each rel32 edge
        foreach (var offset in changed)
        {
            var refused = false;
            try
            {
                SpawnApiResolver.Resolve(version, 0x400000, (rva, len) =>
                {
                    var bytes = image.GetRva(rva, len);
                    if (rva == entry && offset < bytes.Length) bytes[offset] ^= 1;
                    return bytes;
                });
            }
            catch (InvalidOperationException) { refused = true; }
            if (!refused) throw new Exception($"Altered {version} spawn wrapper accepted at +0x{offset:X}");
            cases++;
        }
        var shortReadRefused = false;
        try { SpawnApiResolver.Resolve(version, 0x400000, (rva, len) => image.GetRva(rva, len - 1)); }
        catch (InvalidOperationException) { shortReadRefused = true; }
        if (!shortReadRefused) throw new Exception($"Short {version} spawn wrapper read accepted");
        cases++;
    }
    Console.WriteLine($"PASS {cases} spawn wrapper byte/relative-call/manager/length mutation refusals");
    Console.WriteLine("Identity only: no game invocation, allocation/lifecycle/thread-safety claim, or production dispatcher.");
    return 0;
}

if (args.Length == 1 && args[0] == "rankmailboxtest")
{
    RA3MT.SelfCheck.RankMailboxChecks.Run();
    return 0;
}

if (args.Length == 1 && args[0] == "ranktest")
{
    var rankDataDir = TrainerGameDataDir() ?? throw new InvalidOperationException("Game Data directory not found");
    foreach (var (version, gameFile) in VersionImages(rankDataDir))
    {
        var image = new StaticImage(gameFile);
        var address = RA3MT.Core.Target.RankApiResolver.Resolve(version, 0x400000,
            (rva, len) => image.GetRva(rva, len));
        Console.WriteLine($"PASS {version} rank API 0x{address:X}");
        foreach (var changedOffset in new[] { 0, 0x22, 0x2A, 0x4D })
        {
            var refused = false;
            try
            {
                RA3MT.Core.Target.RankApiResolver.Resolve(version, 0x400000, (rva, len) =>
                {
                    var code = image.GetRva(rva, len);
                    code[changedOffset] ^= 1;
                    return code;
                });
            }
            catch (InvalidOperationException) { refused = true; }
            if (!refused) throw new Exception($"Altered rank contract accepted at {changedOffset:X}");
        }
        Console.WriteLine($"PASS {version} four altered rank contracts rejected");
    }
    return 0;
}

if (args.Length == 1 && args[0] == "actiontest")
{
    RA3MT.SelfCheck.ActionChecks.Run();
    return 0;
}

if (args.Length == 1 && args[0] == "installertest")
{
    RA3MT.SelfCheck.InstallerChecks.Run();
    return 0;
}

if (args.Length == 1 && args[0] == "layouttest")
{
    RA3MT.SelfCheck.BlockLayoutChecks.Run();
    return 0;
}

if (args.Length == 1 && args[0] == "featuretest")
{
    RA3MT.SelfCheck.FeatureCatalogChecks.Run();
    return 0;
}

if (args.Length == 1 && args[0] == "processtest")
{
    // IsProcessAlive drives the dead-process fast path in Detach: handle-based
    // wait, immune to PID reuse. Three cases: own process (alive), a disposed
    // accessor (closed handle), and a process we watched exit (signalled
    // handle — the exact state after the game quits under the trainer).
    var self = new RA3MT.Core.Memory.ProcessMemory(Environment.ProcessId);
    if (!self.IsProcessAlive) throw new Exception("Own process reported dead");
    self.Dispose();
    if (self.IsProcessAlive) throw new Exception("Disposed accessor reported alive");
    using var victim = System.Diagnostics.Process.Start(
        new System.Diagnostics.ProcessStartInfo("cmd.exe", "/c exit") { UseShellExecute = false })!;
    victim.WaitForExit();
    using var dead = new RA3MT.Core.Memory.ProcessMemory(victim.Id);
    if (dead.IsProcessAlive) throw new Exception("Exited process reported alive");
    Console.WriteLine("PASS 3 process-liveness cases (own alive / handle closed / exited signalled)");
    return 0;
}

if (args.Length == 1 && args[0] == "reinforcetest")
{
    RA3MT.SelfCheck.ReinforcementChecks.Run();
    return 0;
}

if (args.Length == 1 && args[0] == "resolvertest")
{
    var fixture = new FeaturesData();
    fixture.Hooks["test"] = new HookDef
    {
        Rva = new() { ["1.13"] = "0x1000" }, Displaced = "83C8FF01461C", DisplacedLen = 6,
    };
    var text = new byte[64];
    var expected = fixture.Hooks["test"].DisplacedBytes();
    expected.CopyTo(text, 16);
    Dictionary<string, HookResolution> Resolve() => HookResolver.ResolveAll(fixture, "1.13",
        (rva, length) => text.AsSpan((int)rva - 0x1000, length).ToArray(), text, 0x400000);
    if (Resolve().Count != 0) throw new Exception("Raw-byte relocation was accepted");
    fixture.Hooks["test"].Pattern = "83 C8 FF 01 46 1C";
    if (Resolve()["test"].Rva != 0x1010) throw new Exception("Unique pattern failed");
    expected.CopyTo(text, 32);
    if (Resolve().Count != 0) throw new Exception("Ambiguous pattern accepted");
    expected.CopyTo(text, 0);
    if (Resolve()["test"].Method != "exact-rva") throw new Exception("Exact RVA failed");
    Console.WriteLine("PASS 4 resolver refusal and unique-context cases");
    return 0;
}

if (args.Length == 1 && args[0] == "asmtest")
{
    foreach (var distance in new[] { 127, 128 })
    {
        var asm = new Asm();
        asm.JmpShort(1);
        asm.Db(new byte[distance]);
        asm.Label(1);
        var rejected = false;
        try
        {
            var code = asm.Build(0x10000);
            if (distance == 127 && code[1] != 127) throw new Exception("Bad rel8 encoding");
        }
        catch (InvalidOperationException) { rejected = true; }
        if (rejected != (distance == 128)) throw new Exception("Forward rel8 range check failed");
    }
    foreach (var padding in new[] { 126, 127 })
    {
        var asm = new Asm();
        asm.Label(1);
        asm.Db(new byte[padding]);
        asm.JmpShort(1);
        var rejected = false;
        try
        {
            var code = asm.Build(0x10000);
            if (padding == 126 && code[^1] != 128) throw new Exception("Bad backward encoding");
        }
        catch (InvalidOperationException) { rejected = true; }
        if (rejected != (padding == 127)) throw new Exception("Backward rel8 range check failed");
    }
    var missing = new Asm();
    missing.JeShort(99);
    try { missing.Build(0); throw new Exception("Missing label accepted"); }
    catch (InvalidOperationException) { }
    uint offset = MasterCode.StubArea;
    foreach (var (id, def) in FeaturesData.LoadEmbedded().Hooks.OrderBy(pair => pair.Key))
    {
        var stubId = def.Stub ?? id;
        if (!StubGen.Handles(stubId)) continue;
        var displaced = def.DisplacedByVersion != null && def.DisplacedByVersion.Count != 0
            ? def.DisplacedBytes("1.13")
            : def.DisplacedBytes();
        var code = StubGen.Emit(stubId, 0x40000000u + offset,
            0x452100u + (uint)displaced.Length, 0x40000000u, 0x400000u, displaced);
        offset += (uint)((code.Length + 15) & ~15);
    }
    if (offset > MasterCode.CaptureCount) throw new Exception("Stub layout overlaps capture data");
    Console.WriteLine($"PASS 5 assembler branch boundary cases; aligned stub end 0x{offset:X} < capture 0x{MasterCode.CaptureCount:X}");
    return 0;
}

if (args.Length == 1 && args[0] == "selectiontest")
{
    var words = new Dictionary<nuint, uint>
    {
        [0x10000] = 0x20000, [0x20050] = 0x30000, [0x2005C] = 2,
        [0x30000] = 0x30020, [0x30008] = 0x40000,
        [0x30020] = 0x20050, [0x30028] = 0x41000,
        [0x40138] = 0x50000, [0x41138] = 0x51000,
        [0x500F4] = 0x40000, [0x510F4] = 0x41000,
    };
    uint[] Read() => RA3MT.Core.Features.SelectionActions.ReadSelection(
        address => words.GetValueOrDefault(address), _ => 0x40, 0x10000);
    void Check(bool ok, string name)
    {
        if (!ok) throw new InvalidOperationException(name);
        Console.WriteLine("PASS " + name);
    }
    Check(Read().Order().SequenceEqual(new uint[] { 0x50000, 0x51000 }), "multi-selection chain");
    words[0x2005C] = 0;
    Check(Read().Length == 0, "empty selection");
    words[0x2005C] = 2;
    words[0x510F4] = 0;
    Check(Read().SequenceEqual(new uint[] { 0x50000 }), "stale drawable rejected");
    words[0x2005C] = 3;
    var rejected = false;
    try { Read(); } catch (InvalidOperationException) { rejected = true; }
    Check(rejected, "early sentinel with excessive count rejected");
    words[0x2005C] = 2;
    var countReads = 0;
    rejected = false;
    try
    {
        RA3MT.Core.Features.SelectionActions.ReadSelection(address =>
            address == 0x2005C && ++countReads == 2 ? 1u : words.GetValueOrDefault(address),
            _ => 0x40, 0x10000);
    }
    catch (InvalidOperationException) { rejected = true; }
    Check(rejected, "selection count mutation rejected");
    words[0x30020] = 0x30000;
    rejected = false;
    try { Read(); } catch (InvalidOperationException) { rejected = true; }
    Check(rejected, "cyclic corrupt list rejected");
    words[0x2005C] = 4097;
    rejected = false;
    try { Read(); } catch (InvalidOperationException) { rejected = true; }
    Check(rejected, "oversized count rejected");
    words.Clear();
    words[0x50374] = 0x60000;
    words[0x6021C] = 0x70020;
    words[0x60200] = 0x80000;
    words[0x60204] = 0x80008;
    words[0x80000] = 0x70000;
    words[0x80004] = 0x70020;
    var current = RA3MT.Core.Features.SelectionActions.ReadLocomotors(
        address => words.GetValueOrDefault(address), 0x50000, false);
    Check(current.SequenceEqual(new uint[] { 0x70020 }), "active locomotor is not first array entry");
    var modes = RA3MT.Core.Features.SelectionActions.ReadLocomotors(
        address => words.GetValueOrDefault(address), 0x50000, true);
    Check(modes.Order().SequenceEqual(new uint[] { 0x70000, 0x70020 }), "current locomotor set deduplicated");
    words[0x60200] = words[0x60204] = 0;
    Check(RA3MT.Core.Features.SelectionActions.ReadLocomotors(
        address => words.GetValueOrDefault(address), 0x50000, true).SequenceEqual(current),
        "empty array retains valid active locomotor");
    words[0x60200] = 0x80000;
    words[0x60204] = 0x80003;
    rejected = false;
    try
    {
        RA3MT.Core.Features.SelectionActions.ReadLocomotors(
            address => words.GetValueOrDefault(address), 0x50000, true);
    }
    catch (InvalidOperationException) { rejected = true; }
    Check(rejected, "misaligned locomotor array rejected");
    words.Clear();
    words[0x90004] = 0xA0000;
    words[0xA0014] = 0xB0000;
    bool Eligible(uint tracker, byte flag) => RA3MT.Core.Features.SelectionActions.CanGainExperience(
        address => words.GetValueOrDefault(address), _ => flag, tracker);
    Check(Eligible(0x90000, 1), "eligible experience template accepted");
    Check(!Eligible(0x90000, 0), "non-veterancy target rejected");
    Check(!Eligible(0, 1), "missing tracker rejected");
    words[0xA0014] = 0;
    Check(!Eligible(0x90000, 1), "missing experience template rejected");
    words.Clear();
    words[0x500F4] = 0x40000;
    words[0x40138] = 0x50000;
    bool StillSelected(byte flags) => RA3MT.Core.Features.SelectionActions.IsSelectedBody(
        address => words.GetValueOrDefault(address), _ => flags, 0x50000);
    Check(StillSelected(0x40), "selected target revalidation accepted");
    Check(!StillSelected(0), "deselected target rejected before write");
    words[0x40138] = 0x51000;
    Check(!StillSelected(0x40), "changed drawable reference rejected before write");
    return 0;
}

var data = FeaturesData.LoadEmbedded();

var dataDir = args.Length > 0 ? args[0] : TrainerGameDataDir();
if (dataDir == null)
{
    Console.Error.WriteLine("未找到游戏 Data 目录，请传入路径：SelfCheck <...\\Data>");
    return 2;
}
Console.WriteLine($"游戏目录: {dataDir}\n");

var allOk = true;
var grandTotal = 0;
var grandOk = 0;

foreach (var (ver, gamePath) in VersionImages(dataDir))
{
    if (!File.Exists(gamePath))
    {
        Console.WriteLine($"== {ver} == 文件不存在: {gamePath}");
        allOk = false;
        continue;
    }
    Console.WriteLine($"== {ver} == {Path.GetFileName(gamePath)} ({new FileInfo(gamePath).Length / 1024 / 1024} MB)");
    var img = new StaticImage(gamePath);

    foreach (var (id, def) in data.Hooks.OrderBy(kv => kv.Value.Rva[ver], StringComparer.OrdinalIgnoreCase))
    {
        grandTotal++;
        var rva = def.RvaFor(ver);
        var expected = def.DisplacedBytes();
        var actual = img.GetRva(rva, def.DisplacedLen);

        var ok = actual.AsSpan().SequenceEqual(expected);
        var line = ok ? "  ✓ " : "  ✗ ";
        line += $"{id,-14} rva=0x{rva:X6}  displaced={ToHex(actual)}";
        if (!ok) line += $"  期望 {ToHex(expected)}";

        // pattern cross-check
        string? patNote = null;
        if (def.Pattern != null)
        {
            var pat = Pattern.Parse(def.Pattern);
            var text = img.SectionBytes(0x1000).ToArray();
            var hits = pat.ScanAll(text)
                .Select(h => 0x1000 + (uint)h + (uint)def.PatternSiteOffset)
                .ToList();
            if (hits.Count == 1 && hits[0] == rva)
                patNote = $"特征码唯一命中 ✓";
            else
            {
                patNote = hits.Count == 0
                    ? $"特征码 0 命中!"
                    : $"特征码 {hits.Count} 命中 ({string.Join(",", hits.Take(3).Select(h => $"0x{h:X}"))}...)";
                if (ok) patNote += "（RVA 字节校验通过，特征码仅供参考）";
            }
        }
        if (ok) grandOk++;
        else allOk = false;
        Console.WriteLine(line);
        if (patNote != null) Console.WriteLine($"        · {patNote}");
    }

    // player-root global access-pattern check
    var rootRva = data.Globals.PlayerRoot.RvaFor(ver);
    var rootAbs = 0x400000 + rootRva;
    var text2 = img.SectionBytes(0x1000).ToArray();
    var found = false;
    foreach (var prefix in new[] { new byte[] { 0x8B, 0x0D }, new byte[] { 0xA1 }, new byte[] { 0x8B, 0x1D } })
    {
        for (var i = 0; i < text2.Length - 16 && !found; i++)
        {
            var match = true;
            for (var k = 0; k < prefix.Length; k++)
                if (text2[i + k] != prefix[k]) { match = false; break; }
            if (!match) continue;
            var disp = BitConverter.ToUInt32(text2, i + prefix.Length);
            if (disp != rootAbs) continue;
            // followed within 8 bytes by 'mov reg,[reg+28]' (8B 4x/5x/6x/7x 28)
            for (var j = i + prefix.Length + 4; j < Math.Min(i + prefix.Length + 10, text2.Length - 2); j++)
                if (text2[j] == 0x8B && (text2[j + 1] & 0xC7) == 0x40 && text2[j + 2] == 0x28)
                { found = true; break; }
        }
        if (found) break;
    }
    Console.WriteLine(found
        ? $"  ✓ 本地阵营全局 [root+28]: 0x{rootRva:X} 访问模式在 .text 中确认"
        : $"  ⚠ 玩家索引全局 0x{rootRva:X} 未找到访问模式（需进游戏验证）");
    Console.WriteLine();
}

Console.WriteLine("＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝");
Console.WriteLine($"挂钩点校验: {grandOk}/{grandTotal} 通过   总体: {(allOk ? "✓ 全部通过" : "✗ 存在失配")}");
return allOk ? 0 : 1;

static string? TrainerGameDataDir()
{
    foreach (var steam in new[] {
                 Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Steam"),
                 @"D:\Steam", @"E:\Steam", @"C:\Steam" })
    {
        var vdf = Path.Combine(steam, "steamapps", "libraryfolders.vdf");
        var roots = new List<string> { steam };
        if (File.Exists(vdf))
            foreach (var line in File.ReadAllLines(vdf))
                if (line.TrimStart().StartsWith("\"path\""))
                    roots.Add(line.Split('"')[3].Replace(@"\\", "/"));
        foreach (var r in roots)
        {
            var d = Path.Combine(r, "steamapps", "common", "Command and Conquer Red Alert 3", "Data");
            if (File.Exists(Path.Combine(d, "ra3_1.13.game"))) return d;
        }
    }
    return null;
}

static string? TrainerEaDataDir()
{
    var candidates = new List<string>();
    var env = Environment.GetEnvironmentVariable("RA3MT_EA_DIR");
    if (!string.IsNullOrEmpty(env)) candidates.Add(env);
    candidates.Add(@"D:\BaiduNetdiskDownload\Red Alert 3\Data");
    foreach (var c in candidates)
        if (File.Exists(Path.Combine(c, "ra3_1.12.game"))) return c;
    return null;
}

/// <summary>Every game image the checks verify: repack 1.12/1.13 plus the EA
/// original 1.12 when its Data directory is present (same module filename,
/// different build).</summary>
static List<(string ver, string path)> VersionImages(string repackDir)
{
    var list = new List<(string, string)>
    {
        ("1.12", Path.Combine(repackDir, "ra3_1.12.game")),
        ("1.13", Path.Combine(repackDir, "ra3_1.13.game")),
    };
    var ea = TrainerEaDataDir();
    if (ea != null)
    {
        list.Add(("1.12ea", Path.Combine(ea, "ra3_1.12.game")));
        Console.WriteLine($"EA 原版目录: {ea}");
    }
    else
    {
        Console.WriteLine("EA 原版目录未找到（设置 RA3MT_EA_DIR 可指定）——跳过 1.12ea 站点校验");
    }
    return list;
}

static string ToHex(byte[] b) => string.Join(" ", b.Select(x => x.ToString("X2")));
