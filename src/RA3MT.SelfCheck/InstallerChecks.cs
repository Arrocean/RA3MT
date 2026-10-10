using RA3MT.Core.Engine;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;
using RA3MT.Core.Target;

namespace RA3MT.SelfCheck;

public static class InstallerChecks
{
    private sealed class FakeMemory : IInjectionMemory
    {
        public readonly Dictionary<nuint, byte> Bytes = new();
        public readonly List<nuint> Writes = new();
        public readonly Dictionary<int, int> Failures = new();
        public int WriteCount;

        public byte[] Read(nuint address, int size) => Enumerable.Range(0, size)
            .Select(i => Bytes.GetValueOrDefault(address + (nuint)i)).ToArray();

        public void Write(nuint address, ReadOnlySpan<byte> data)
        {
            Writes.Add(address);
            WriteCount++;
            var failed = Failures.TryGetValue(WriteCount, out var mode);
            var length = failed ? mode switch { 0 => 0, 1 => Math.Min(2, data.Length), _ => data.Length } : data.Length;
            for (var i = 0; i < length; i++) Bytes[address + (nuint)i] = data[i];
            if (failed) throw new InvalidOperationException("Injected memory failure");
        }

        public nuint Alloc(nuint size, uint protect = 0x40) => 0x40000000;
    }

    public static void Run()
    {
        var data = FeaturesData.LoadEmbedded();
        var sites = data.Hooks.ToDictionary(pair => pair.Key, pair => new HookResolution
        {
            HookId = pair.Key, Rva = pair.Value.RvaFor("1.13"), GameBase = 0x400000,
            Displaced = pair.Value.DisplacedBytes(), Method = "fixture",
        });
        var cases = 0;
        FakeMemory Memory()
        {
            var memory = new FakeMemory();
            foreach (var site in sites.Values)
                for (var i = 0; i < site.Displaced.Length; i++)
                    memory.Bytes[site.Va + (nuint)i] = site.Displaced[i];
            return memory;
        }
        MasterCode Installer(FakeMemory memory) => new(memory, 0x400000, 0xCF214C, sites, data.Hooks, null);
        void Original(FakeMemory memory)
        {
            foreach (var site in sites.Values)
                if (!memory.Read(site.Va, site.Displaced.Length).SequenceEqual(site.Displaced))
                    throw new Exception("Original bytes not restored: " + site.HookId);
        }
        var totalWrites = 1 + 2 * sites.Count;
        for (var failure = 1; failure <= totalWrites; failure++)
        {
            foreach (var mode in new[] { 0, 1, 2 })
            {
                var memory = Memory();
                memory.Failures[failure] = mode;
                var installer = Installer(memory);
                var rejected = false;
                try { installer.Install(); } catch (InvalidOperationException) { rejected = true; }
                if (!rejected) throw new Exception("Installation failure not surfaced");
                installer.Uninstall();
                Original(memory);
                if (installer.Installed) throw new Exception("Installation still marked active after recovery");
                cases++;
            }
        }
        foreach (var failRestore in new[] { 1, sites.Count / 2, sites.Count })
        {
            var memory = Memory();
            var installer = Installer(memory);
            installer.Install();
            var patchedOrder = memory.Writes.Skip(1 + sites.Count).ToArray();
            memory.Failures[memory.WriteCount + failRestore] = 0;
            var start = memory.Writes.Count;
            var failed = false;
            try { installer.Uninstall(); } catch (AggregateException) { failed = true; }
            if (!failed || !installer.Installed) throw new Exception("Recovery failure state lost");
            if (!memory.Writes.Skip(start).SequenceEqual(patchedOrder.Reverse()))
                throw new Exception("Uninstall did not attempt every hook in reverse order");
            var retryStart = memory.Writes.Count;
            installer.Uninstall();
            if (memory.Writes.Count != retryStart + 1) throw new Exception("Retry wrote already restored hooks");
            Original(memory);
            if (installer.Installed) throw new Exception("Retry did not clear active state");
            cases++;
        }
        Console.WriteLine($"PASS {cases} installer failure/recovery cases (before, partial, post-write and retry)");
    }
}
