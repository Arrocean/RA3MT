using RA3MT.Core.Features;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.SelfCheck;

public static class ActionChecks
{
    private sealed class Memory : IInjectionMemory
    {
        public readonly Dictionary<nuint, byte> Bytes = new();
        public readonly List<nuint> Writes = new();
        public byte[] Read(nuint address, int size) => Enumerable.Range(0, size)
            .Select(i => Bytes.GetValueOrDefault(address + (nuint)i)).ToArray();
        public void Write(nuint address, ReadOnlySpan<byte> data)
        {
            Writes.Add(address);
            for (var i = 0; i < data.Length; i++) Bytes[address + (nuint)i] = data[i];
        }
        public nuint Alloc(nuint size, uint protect = 0x40) => throw new NotSupportedException();
        public void U32(nuint address, uint value) => Write(address, BitConverter.GetBytes(value));
    }

    public static void Run()
    {
        var data = FeaturesData.LoadEmbedded();
        var global = (nuint)(0x400000 + data.Globals.SelectionList.RvaFor("1.13"));
        Memory Fixture(float maximum)
        {
            var memory = new Memory();
            memory.U32(global, 0x20000);
            memory.U32(0x20050, 0x30000);
            memory.U32(0x2005C, 1);
            memory.U32(0x30000, 0x20050);
            memory.U32(0x30008, 0x40000);
            memory.U32(0x40138, 0x50000);
            memory.U32(0x500F4, 0x40000);
            memory.Write(0x4013D, new byte[] { 0x40 });
            memory.U32(0x5033C, 0x60000);
            memory.WriteF32(0x60004, 50);
            memory.WriteF32(0x6000C, maximum);
            memory.WriteF32(0x60010, 100);
            memory.Writes.Clear();
            return memory;
        }
        var count = 0;
        foreach (var maximum in new[] { 200f, 0f, -1f, float.NaN, float.PositiveInfinity })
        {
            var memory = Fixture(maximum);
            var applied = SelectionActions.Apply(memory, data, "1.13", "heal", 0x400000);
            var valid = float.IsFinite(maximum) && maximum > 0;
            if (applied != (valid ? 1 : 0)) throw new Exception("Invalid full-heal outcome");
            if (valid)
            {
                if (memory.ReadF32(0x60004) != maximum || !memory.Writes.SequenceEqual(new nuint[] { 0x60004 }))
                    throw new Exception("Full heal must change only current HP");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Invalid maximum caused write");
            if (memory.ReadF32(0x60010) != 100) throw new Exception("Base maximum changed");
            count++;
        }
        foreach (var baseMaximum in new[] { 100f, 0f, -1f, float.NaN, float.PositiveInfinity })
        {
            var memory = Fixture(999999);
            memory.WriteF32(0x60010, baseMaximum);
            memory.Writes.Clear();
            var applied = SelectionActions.Apply(memory, data, "1.13", "hpnormal", 0x400000);
            var valid = float.IsFinite(baseMaximum) && baseMaximum > 0;
            if (applied != (valid ? 1 : 0)) throw new Exception("Invalid normal-restore outcome");
            if (valid)
            {
                if (memory.ReadF32(0x60004) != baseMaximum || memory.ReadF32(0x6000C) != baseMaximum ||
                    !memory.Writes.SequenceEqual(new nuint[] { 0x60004, 0x6000C }))
                    throw new Exception("Normal restore must reset effective max and current HP");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Invalid base maximum caused write");
            count++;
        }
        foreach (var action in new[] { "capture", "destroy" })
        {
            var memory = Fixture(200);
            var refused = false;
            try { SelectionActions.Apply(memory, data, "1.13", action, 0x400000); }
            catch (NotSupportedException) { refused = true; }
            if (!refused || memory.Writes.Count != 0) throw new Exception("Unsafe action was not refused");
            count++;
        }
        var deselected = Fixture(200);
        deselected.Write(0x4013D, new byte[] { 0 });
        deselected.Writes.Clear();
        if (SelectionActions.Apply(deselected, data, "1.13", "hpnormal", 0x400000) != 0 || deselected.Writes.Count != 0)
            throw new Exception("Deselected target changed");
        Console.WriteLine($"PASS {count + 1} action-write cases: FINAL3 normal restore, effective-max heal, invalid floats and unsafe action refusal");
    }
}
