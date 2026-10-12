using RA3MT.Core.Engine;
using RA3MT.Core.Memory;

namespace RA3MT.SelfCheck;

/// <summary>Proves the injected block layout for every combination the product
/// can actually reach.
///
/// Why this exists: before the layout was centralised, each bridge carried its
/// own hand-written overlap assertion in MasterCode.Install, the four bridges
/// were never enabled together, and three of their block regions silently
/// overlapped. This check measures the real emitted dispatcher lengths and
/// validates the whole map with all bridges enabled.
///
/// Run: SelfCheck layouttest</summary>
public static class BlockLayoutChecks
{
    private sealed class NullMemory : IInjectionMemory
    {
        public byte[] Read(nuint address, int size) => new byte[size];
        public void Write(nuint address, ReadOnlySpan<byte> data) { }
        public nuint Alloc(nuint size, uint protect = 0x40) => 0x40000000;
    }

    public static void Run()
    {
        var memory = new NullMemory();
        nuint block = 0x40000000;
        nuint root = 0xCF214C;
        var cases = 0;

        // 1) baseline layout (no bridges) must be sound
        var baseLayout = BlockLayoutCatalog.Create();
        baseLayout.Declare("StubArena", BlockLayoutCatalog.StubAreaStart, 0x4F0, "stubs");
        baseLayout.Validate();
        cases++;

        // 1b) the fixed header areas must stay strictly below the stub arena —
        //     that is the invariant the old "DiagSelIdx + 4 <= StubArea" check
        //     was approximating.
        if (BlockLayoutCatalog.DiagnosticsEnd > BlockLayoutCatalog.StubAreaStart)
            throw new Exception($"diagnostics end 0x{BlockLayoutCatalog.DiagnosticsEnd:X} reaches into the stub arena");
        if (BlockLayoutCatalog.FlagCaptureSelOffset + 4 > BlockLayoutCatalog.StubAreaStart)
            throw new Exception("capture-arm flag reaches into the stub arena");
        cases++;
        if (BlockLayoutCatalog.CaptureArrayOffset + BlockLayoutCatalog.CaptureArrayBytes >
            BlockLayoutCatalog.BlockSize)
            throw new Exception("capture array does not fit inside the block");
        cases++;

        // 2) every bridge declared, with the dispatchers actually emitted into a
        //    measurement pass — this is where the old overlaps showed up.
        var layout = BlockLayoutCatalog.Create();
        BlockLayoutCatalog.DeclareBridges(layout);

        var measured = new (string Owner, int Length)[]
        {
            ("Rank", RankDispatcher.Emit(block + 0x1100, block, (nuint)0x785600, root).Length),
            ("Capture", CaptureDispatcher.Emit(block + 0x1280, block, (nuint)0x7B5DF0, root).Length),
            ("Kill", KillDispatcher.Emit(block + 0x1400, block, (nuint)0x7C7190, root).Length),
            ("Spawn", SpawnDispatcher.Emit(block + 0x1580, block, (nuint)0x62E3E0, (nuint)0x80D5B0,
                (nuint)0xCF0108, root, 0xCE43BC, 0x60ECF0).Length),
        };
        foreach (var (owner, length) in measured)
        {
            layout.AmendSize($"{owner}Dispatcher", length);
            cases++;
        }

        layout.Declare("StubArena", BlockLayoutCatalog.StubAreaStart, 0x4F0, "stubs");
        var errors = layout.Errors();
        var sizes = string.Join(", ", measured.Select(m => $"{m.Owner}={m.Length}B"));
        if (errors.Count != 0)
            throw new Exception($"[dispatcher sizes: {sizes}] " +
                                "layout with all bridges enabled is unsound: " + string.Join("; ", errors));
        layout.Validate();
        cases++;

        // 3) every dispatcher must fit inside its declared reservation
        foreach (var (owner, length) in measured)
        {
            var region = BlockLayoutCatalog.FindBridge(owner);
            if ((uint)length > region.DispatcherSize)
                throw new Exception($"{owner} dispatcher ({length}B) exceeds its reserved " +
                                    $"{region.DispatcherSize}B slot at 0x{region.DispatcherOffset:X}");
            cases++;
        }

        // 4) drift detection: overlap and out-of-block are both reported
        var broken = BlockLayoutCatalog.Create();
        broken.Declare("A", 0x100, 0x100, "test");
        broken.Declare("B", 0x180, 0x100, "test");
        if (broken.Errors().Count == 0) throw new Exception("overlap was not detected");
        cases++;
        var beyond = new BlockLayout(0x1000);
        beyond.Declare("A", 0x800, 0x900, "test");
        if (beyond.Errors().Count == 0) throw new Exception("out-of-block region was not detected");
        cases++;

        var report = string.Join(", ", measured.Select(m => $"{m.Owner}={m.Length}B"));
        Console.WriteLine($"PASS {cases} block layout cases " +
                          $"(all-bridge layout sound, dispatchers {report}, " +
                          $"stub arena 0x{BlockLayoutCatalog.StubAreaStart:X}..0x4F0 < capture 0x{BlockLayoutCatalog.CaptureCountOffset:X})");
    }
}
