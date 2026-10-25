using RA3MT.Core.Engine;
using RA3MT.Core.Features;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;
using RA3MT.Core.Target;

namespace RA3MT.SelfCheck;

public static class UprisingChecks
{
    /// <summary>Read-only selection diagnostics, usable while a trainer is attached.
    /// Build identity comes from the original file because live hooks replace anchors.</summary>
    public static void LiveSelection(int? pid = null)
    {
        var data = FeaturesData.LoadEmbedded(GameId.Uprising);
        var found = ProcessMemory.FindGame(GameCatalog.Uprising.ModuleNames, pid)
            ?? throw new InvalidOperationException("Uprising is not running");
        var disk = new StaticImage(found.modulePath);
        var version = GameBuildClassifier.ClassifyUprising(new DelegateImageReader(disk.GetRva), found.version, data);
        using var memory = new ProcessMemory(found.pid);
        using var process = System.Diagnostics.Process.GetProcessById(found.pid);
        var imageBase = (nuint)process.MainModule!.BaseAddress;
        var global = imageBase + data.Globals.SelectionList.RvaFor(version);
        var layout = GameLayout.For(version);
        var bodies = SelectionActions.ReadSelection(a => memory.ReadU32(a), a => memory.Read(a, 1)[0], global, layout);
        var oldBodies = SelectionActions.ReadSelection(a => memory.ReadU32(a), a => memory.Read(a, 1)[0],
            global, layout with { BodyDrawable = 0xF4 });
        var rank = SelectionActions.EnumerateRankTargets(memory, data, version, imageBase);
        var kill = SelectionActions.EnumerateKillTargets(memory, data, version, imageBase);
        var copy = SpawnActions.EnumerateCopyTargets(memory, data, version, imageBase);
        Console.WriteLine($"READ-ONLY {version} PID={found.pid}: selected={bodies.Length}, legacy-F4={oldBodies.Length}, rank={rank.Count}, destroy={kill.Count}, copy={copy.Count}");
        foreach (var body in bodies)
            Console.WriteLine($"body=0x{body:X} drawable(+F8)=0x{memory.ReadU32(body+layout.BodyDrawable):X} old(+F4)=0x{memory.ReadU32(body+0xF4u):X}");
        Check(bodies.Length > 0 && rank.Count > 0 && kill.Count > 0 && copy.Count > 0,
            "Select an eligible live combat unit before running this read-only check");
        Console.WriteLine("PASS live target extraction; no hooks, requests or writes performed");
    }

    public static void LiveAttach(int? pid = null)
    {
        using var engine = new TrainerEngine();
        engine.SelectGame(GameId.Uprising);
        var found = ProcessMemory.FindGame(engine.Game.ModuleNames, pid) ?? throw new InvalidOperationException("Uprising is not running");
        using var memory = new ProcessMemory(found.pid);
        using var process = System.Diagnostics.Process.GetProcessById(found.pid);
        var imageBase = (nuint)process.MainModule!.BaseAddress;
        var version = GameBuildClassifier.ClassifyUprising(new DelegateImageReader((r, l) => memory.Read(imageBase + r, l)), found.version, engine.Data);
        var originals = engine.Data.Hooks.ToDictionary(h => h.Key, h => memory.Read(imageBase + h.Value.RvaFor(version), h.Value.LengthFor(version)));
        try
        {
            engine.Attach(found.pid);
            Check(engine.Attached && !engine.RecoveryRequired, "live attachment");
            Check(engine.RankBridgeActive && engine.CaptureBridgeActive && engine.KillBridgeActive && engine.SpawnBridgeActive, "all live bridges");
            foreach (var h in engine.Data.Hooks.Values) Check(memory.Read(imageBase + h.RvaFor(version), 1)[0] == 0xE9, "all detours installed");
            Thread.Sleep(1000);
            Check(memory.IsProcessAlive, "game remains alive");
        }
        finally { engine.Detach(); }
        Check(!engine.Attached, "clean detach");
        foreach (var (id, h) in engine.Data.Hooks) Check(memory.Read(imageBase + h.RvaFor(version), h.LengthFor(version)).SequenceEqual(originals[id]), "original bytes restored");
        Console.WriteLine($"PASS live attach/restore {version}: 28 installed detours, four bridges active, all original bytes restored");
    }

    public static void Run()
    {
        var data = FeaturesData.LoadEmbedded(GameId.Uprising);
        FeatureCatalogChecks.Run(GameId.Uprising);
        Check(data.Features.Count == FeaturesData.LoadEmbedded().Features.Count + 2, "two exclusive features");
        Check(data.Hooks.Count == 28, "28 Uprising hooks");
        var paths = new[]
        {
            ("uprising-1.0ea", Environment.GetEnvironmentVariable("RA3MT_UPRISING_EA_IMAGE") ?? @"D:\BaiduNetdiskDownload\RA3 Uprising\GAME\Data\ra3ep1_1.0.game"),
            ("uprising-1.0", Environment.GetEnvironmentVariable("RA3MT_UPRISING_10_IMAGE") ?? @"D:\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising\Data\ra3ep1_1.0.game"),
            ("uprising-1.01", Environment.GetEnvironmentVariable("RA3MT_UPRISING_101_IMAGE") ?? @"D:\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising\Data\ra3ep1_1.1.game"),
        };
        var cases = 0;
        foreach (var (version, path) in paths)
        {
            var image = new StaticImage(path);
            var reader = new DelegateImageReader(image.GetRva);
            var sites = HookResolver.ResolveAll(data, version, image.GetRva, image.SectionBytes(0x1000).ToArray(), 0x400000);
            Check(sites.Count == 28, "complete hook resolution");
            Check(sites.Values.All(x => x.Method == "exact-rva"), "exact hook identity");
            Check(GameBuildClassifier.ClassifyUprising(reader, version.EndsWith("1.01") ? "1.1" : "1.0", data) == version, "fingerprint classification");
            var build = UprisingTarget.Build(version);
            foreach (var (name, contract) in build.Contracts)
            {
                build.Verify(name, 0x400000, reader);
                // Mutating any byte in each function must reject; includes
                // helper edges, stack cleanup and SecuROM thunk operands.
                for (var i = 0; i < contract.Bytes.Length / 2; i++)
                {
                    var position = i;
                    var bad = new DelegateImageReader((r, l) =>
                    {
                        var bytes = image.GetRva(r, l);
                        if (r == contract.RvaValue) bytes[position] ^= 1;
                        return bytes;
                    });
                    Reject(() => build.Verify(name, 0x400000, bad)); cases++;
                }
            }
            RankApiResolver.Resolve(version, 0x400000, reader);
            CaptureApiResolver.Resolve(version, 0x400000, reader);
            KillApiResolver.Resolve(version, 0x400000, reader);
            SpawnApiResolver.Resolve(version, 0x400000, reader);
            var support = SpawnSupportApiResolver.Resolve(version, 0x400000, reader);
            Check(support.OwnerKindGlobal == 0x400000 + build.Rva("gameLogic") &&
                  support.OwnerKindGlobal != 0x400000 + build.Rva("playerRoot"), "game logic is distinct from player controller");
            foreach (var (id, site) in sites)
            {
                var bad = new DelegateImageReader((r, l) =>
                {
                    var bytes = image.GetRva(r, l);
                    if (r == site.Rva) bytes[0] ^= 1;
                    return bytes;
                });
                var partial = HookResolver.ResolveAll(data, version, bad.Read, [], 0x400000);
                Check(partial.Count == 27 && !partial.ContainsKey(id), "tampered hook rejected"); cases++;
            }
            var memory = new FakeMemory();
            foreach (var site in sites.Values) memory.Write(site.Va, site.Displaced);
            var master = new MasterCode(memory, 0x400000, 0x400000 + data.Globals.PlayerRoot.RvaFor(version), sites, data.Hooks, null,
                0x785600, 0x7B5DF0, 0x7C7190, 0x7513F0, 0x62E3E0, 0x80D5B0, 0xCF0108, 0xCE43BC, 0x60ECF0, GameLayout.Uprising);
            master.Install();
            var identity = memory.Read(master.Block + BlockLayoutCatalog.IdentityOffset, TrainerIdentity.RecordSize);
            Check(TrainerIdentity.TryParse(identity, out var marker) && marker.Kind == TrainerIdentityKind.GameProcess &&
                  marker.TrainerProcessId == Environment.ProcessId, "public marker independent of Uprising build");
            Check(master.Bridges.Consumers.Count == 4, "all bridge layouts fit");
            foreach (var site in sites.Values) Check(memory.Read(site.Va, 1)[0] == 0xE9, "every declared hook installed");
            master.SetFlag("challenge_money", true); master.SetFlag("challenge_time", true);
            master.Uninstall();
            Check(memory.Read(master.Block + BlockLayoutCatalog.IdentityOffset, TrainerIdentity.RecordSize).SequenceEqual(identity), "public game marker retained after detach");
            foreach (var site in sites.Values) Check(memory.Read(site.Va, site.Displaced.Length).SequenceEqual(site.Displaced), "exact restoration");
            Console.WriteLine($"PASS {version}: 28 hooks, {build.Contracts.Count} API/global/layout contracts, four-bridge install/restore");
        }
        // Reject unknown modules and missing/ambiguous fingerprints, never guess.
        Reject(() => GameBuildClassifier.ClassifyUprising(new DelegateImageReader((_, l) => new byte[l]), "1.0", data));
        Reject(() => GameBuildClassifier.ClassifyUprising(new DelegateImageReader((_, l) => new byte[l]), "1.2", data));
        SelectionLayout();
        Check(ReinforcementCatalog.Uprising.Entries.Count == 137, "Uprising unit table");
        Check(ReinforcementCatalog.Uprising.TryResolve("AlliedMCV", out var hash, out _) && hash == 0x28DA574E, "MCV hash");
        Check(ReinforcementCatalog.Uprising.Entries.Any(e => e.Name.Contains("Desolator")), "Uprising units included");
        using var engine = new TrainerEngine();
        engine.SelectGame(GameId.Uprising);
        Check(engine.Data.Features.Count == data.Features.Count, "switch product metadata");
        Check(!engine.ExecuteAction("challenge_money", "").ok, "unattached action denied");
        engine.SelectGame(GameId.RedAlert3);
        Check(!engine.Data.Features.Any(f => f.Id.StartsWith("challenge_")), "exclusive features cleared");
        Check(engine.Data.Hooks.Count == 26, "original profile restored");
        Console.WriteLine($"PASS {cases} Uprising byte-tamper cases; classification, layout, catalog and game switching");
    }

    private static void SelectionLayout()
    {
        var m = new FakeMemory();
        void Put(nuint address, uint value) => m.Write(address, BitConverter.GetBytes(value));
        const uint global = 0x10000, manager = 0x20000, node = 0x30000, draw = 0x40000, body = 0x50000, ai = 0x60000, loc = 0x70000;
        Put(global, manager); Put(manager + 0x54, node); Put(manager + 0x60, 1);
        Put(node, manager + 0x54); Put(node + 8, draw); Put(draw + 0x138, body); Put(body + 0xF8, draw); m.Write(draw + 0x13D, new byte[] { 0x40 });
        Check(SelectionActions.ReadSelection(a => m.ReadU32(a), a => m.Read(a, 1)[0], global, GameLayout.Uprising).SequenceEqual(new[] { body }), "Uprising selection manager");
        Check(SelectionActions.ReadSelection(a => m.ReadU32(a), a => m.Read(a, 1)[0], global,
            GameLayout.Uprising with { BodyDrawable = 0xF4 }).Length == 0, "legacy F4 rejects real Uprising object layout");
        Check(SelectionActions.IsSelectedBody(a => m.ReadU32(a), a => m.Read(a, 1)[0], body, GameLayout.Uprising), "F8 round-trip accepted");
        Put(body+0xF4,draw); Put(body+0xF8,0);
        Check(!SelectionActions.IsSelectedBody(a => m.ReadU32(a), a => m.Read(a, 1)[0], body, GameLayout.Uprising), "stale F8 must reject even when legacy field looks valid");
        Put(body+0xF4,0); Put(body+0xF8,draw);
        Put(body + 0x384, ai); Put(ai + 0x228, loc);
        Check(SelectionActions.ReadLocomotors(a => m.ReadU32(a), body, false, GameLayout.Uprising).SequenceEqual(new[] { loc }), "Uprising active locomotor");
        var data = FeaturesData.LoadEmbedded(GameId.Uprising);
        const string version = "uprising-1.01";
        Put(0x400000 + data.Globals.SelectionList.RvaFor(version), manager);
        Put(body + 0x3A8, 0x80000); Put(0x80028, 10000); Put(0x80014, 500);
        Check(SelectionActions.RestoreOreMines(m, data, version, 0x400000) == 1, "inline ore restored");
        Check(m.ReadU32(0x80028) == 100000 && m.ReadU32(0x80014) == 0, "Uprising inline ore counters");
        Put(body + 0x34C, 0x90000); Put(body + 0x33C, 0xDEADBEEF); Put(0x90010, BitConverter.SingleToUInt32Bits(150f));
        Check(SelectionActions.Apply(m, data, version, "hpmax", 0x400000) == 1, "health action uses new component");
        Check(m.ReadU32(0x90004) == BitConverter.SingleToUInt32Bits(999999f), "new health written");
        Check(m.ReadU32(body + 0x33C) == 0xDEADBEEF, "old health field untouched");
        Check(SelectionActions.Apply(m, data, version, "hpnormal", 0x400000) == 1 && m.ReadU32(0x90004) == BitConverter.SingleToUInt32Bits(150f), "health maximum restored");
        var actionState = new SelectionActionState();
        Put(loc + 4, 0xE0000); Put(loc + 8, BitConverter.SingleToUInt32Bits(25f));
        Check(SelectionActions.Apply(m, data, version, "speed1", 0x400000, actionState) == 1, "speed uses current locomotor");
        Check(m.ReadU32(loc + 8) == BitConverter.SingleToUInt32Bits(500f), "speed value");
        Put(body + 0x3DC, 0xA0000); Put(0xA0004, 0xB0000); Put(0xB0014, 0xC0000); m.Write(0xC024D, new byte[] { 1 });
        Check(SelectionActions.EnumerateRankTargets(m, data, version, 0x400000).Single().tracker == 0xA0000, "new tracker and eligibility");
        Check(SpawnActions.EnumerateCopyTargets(m, data, version, 0x400000).Single().holder == 0xB0000, "copy uses new tracker");
        Check(SelectionActions.EnumerateKillTargets(m, data, version, 0x400000).Single().hp == 0x90000, "destroy uses new health");
    }

    private static void Reject(Action action)
    {
        try { action(); } catch (InvalidOperationException) { return; }
        throw new Exception("Expected contract rejection");
    }
    private static void Check(bool value, string label) { if (!value) throw new Exception(label); }
    private sealed class FakeMemory : IInjectionMemory
    {
        private readonly Dictionary<nuint, byte> _bytes = new();
        public byte[] Read(nuint address, int size) => Enumerable.Range(0, size).Select(i => _bytes.GetValueOrDefault(address + (nuint)i)).ToArray();
        public void Write(nuint address, ReadOnlySpan<byte> bytes) { for (var i = 0; i < bytes.Length; i++) _bytes[address + (nuint)i] = bytes[i]; }
        public nuint Alloc(nuint size, uint protect = 0x40) => 0x40000000;
    }
}
