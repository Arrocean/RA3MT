using RA3MT.Core.Engine;
using RA3MT.Core.Memory;

namespace RA3MT.SelfCheck;

public static class BridgeMailboxChecks
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
        public void State(nuint address, uint value) => Write(address, BitConverter.GetBytes(value));
    }

    public static void Run()
    {
        var cases = 0;
        const nuint block = 0x40000000;

        // capture mailbox @0x1840
        foreach (var state in new uint[] { 0, 1, 2, 3, 4, 77 })
        {
            var memory = new Memory();
            memory.State(block + CaptureDispatcher.StateOffset, state);
            memory.Writes.Clear();
            var refused = false;
            try { new CaptureRequestMailbox(memory, block).Submit(0x20000, 0x30000); }
            catch (InvalidOperationException) { refused = true; }
            var allowed = state is 0 or 3 or 4;
            if (refused == allowed) throw new Exception("Invalid capture mailbox transition");
            if (allowed)
            {
                if (!memory.Writes.SequenceEqual(new nuint[]
                        { block + CaptureDispatcher.BodyOffset, block + CaptureDispatcher.DrawableOffset, block + CaptureDispatcher.StateOffset }))
                    throw new Exception("Capture request not published last");
                if (new CaptureRequestMailbox(memory, block).State != 1) throw new Exception("Bad capture publish");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Outstanding capture request overwritten");
            cases++;
        }
        foreach (var target in new[] { (0u, 0x30000u), (0x20000u, 0u) })
        {
            var memory = new Memory();
            var refused = false;
            try { new CaptureRequestMailbox(memory, block).Submit(target.Item1, target.Item2); }
            catch (ArgumentException) { refused = true; }
            if (!refused || memory.Writes.Count != 0) throw new Exception("Invalid capture object published");
            cases++;
        }

        // kill mailbox @0x1880
        foreach (var state in new uint[] { 0, 1, 2, 3, 4, 99 })
        {
            var memory = new Memory();
            memory.State(block + KillDispatcher.StateOffset, state);
            memory.Writes.Clear();
            var refused = false;
            try { new KillRequestMailbox(memory, block).Submit(0x20000, 0x30000, 0x40000); }
            catch (InvalidOperationException) { refused = true; }
            var allowed = state is 0 or 3 or 4;
            if (refused == allowed) throw new Exception("Invalid kill mailbox transition");
            if (allowed)
            {
                if (!memory.Writes.SequenceEqual(new nuint[]
                        { block + KillDispatcher.BodyOffset, block + KillDispatcher.DrawableOffset,
                          block + KillDispatcher.HpOffset, block + KillDispatcher.StateOffset }))
                    throw new Exception("Kill request not published last");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Outstanding kill request overwritten");
            cases++;
        }
        foreach (var target in new[] { (0u, 0x30000u, 0x40000u), (0x20000u, 0u, 0x40000u), (0x20000u, 0x30000u, 0u) })
        {
            var memory = new Memory();
            var refused = false;
            try { new KillRequestMailbox(memory, block).Submit(target.Item1, target.Item2, target.Item3); }
            catch (ArgumentException) { refused = true; }
            if (!refused || memory.Writes.Count != 0) throw new Exception("Invalid kill object published");
            cases++;
        }
        Console.WriteLine($"PASS {cases} capture/kill mailbox lifecycle and publish-order cases");
    }
}
