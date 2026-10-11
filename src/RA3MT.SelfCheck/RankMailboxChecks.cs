using RA3MT.Core.Engine;
using RA3MT.Core.Memory;

namespace RA3MT.SelfCheck;

public static class RankMailboxChecks
{
    private sealed class Memory : IInjectionMemory
    {
        public readonly Dictionary<nuint, byte> Bytes = new();
        public readonly List<nuint> Writes = new();
        public bool FailPayload;
        public byte[] Read(nuint address, int size) => Enumerable.Range(0, size)
            .Select(i => Bytes.GetValueOrDefault(address + (nuint)i)).ToArray();
        public void Write(nuint address, ReadOnlySpan<byte> data)
        {
            if (FailPayload && data.Length == 20) throw new InvalidOperationException("Injected payload failure");
            Writes.Add(address);
            for (var i = 0; i < data.Length; i++) Bytes[address + (nuint)i] = data[i];
        }
        public nuint Alloc(nuint size, uint protect = 0x40) => throw new NotSupportedException();
        public void State(uint value) => Write(0x40001800, BitConverter.GetBytes(value));
    }

    public static void Run()
    {
        var cases = 0;
        foreach (var state in new uint[] { 0, 1, 2, 3, 4, 5, uint.MaxValue })
        {
            var memory = new Memory();
            memory.State(state);
            memory.Writes.Clear();
            var mailbox = new RankRequestMailbox(memory, 0x40000000);
            var refused = false;
            try { mailbox.Submit(0x20000, 0x30000, 0x40000); }
            catch (InvalidOperationException) { refused = true; }
            var allowed = state is 0 or 3 or 4;
            if (refused == allowed) throw new Exception("Invalid mailbox state transition");
            if (allowed)
            {
                if (!memory.Writes.SequenceEqual(new nuint[] { 0x40001804, 0x40001800 }))
                    throw new Exception("Request not published last");
                if (mailbox.State != 1 || memory.ReadU32(0x40001804) != 0x20000 ||
                    memory.ReadU32(0x40001808) != 0x30000 || memory.ReadU32(0x4000180C) != 0x40000)
                    throw new Exception("Bad rank payload");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Outstanding request overwritten");
            cases++;
        }
        foreach (var target in new[] { (0u, 0x30000u, 0x40000u), (0x20000u, 0u, 0x40000u), (0x20000u, 0x30000u, 0u) })
        {
            var memory = new Memory();
            var refused = false;
            try { new RankRequestMailbox(memory, 0x40000000).Submit(target.Item1, target.Item2, target.Item3); }
            catch (ArgumentException) { refused = true; }
            if (!refused || memory.Writes.Count != 0) throw new Exception("Invalid rank object published");
            cases++;
        }
        var failing = new Memory { FailPayload = true };
        var failingMailbox = new RankRequestMailbox(failing, 0x40000000);
        try { failingMailbox.Submit(0x20000, 0x30000, 0x40000); throw new Exception("Payload failure ignored"); }
        catch (InvalidOperationException) { }
        if (failingMailbox.State != 0 || failing.Writes.Count != 0) throw new Exception("Failed payload published");
        cases++;
        var complete = new Memory();
        complete.State(3);
        complete.Write(0x40001810, BitConverter.GetBytes(1u));
        complete.Write(0x40001814, BitConverter.GetBytes(3u));
        if (new RankRequestMailbox(complete, 0x40000000).ReadResult() != (3u, 1u, 3u))
            throw new Exception("Bad completed result");
        cases++;
        Console.WriteLine($"PASS {cases} rank mailbox lifecycle and publish-order cases");
    }
}
