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

        // rank mailbox: rejection classification. The dispatcher writes the rank
        // value before/after the award call; equal non-zero slots = award did not
        // move it (already at max rank — the benign case), zeroed slots = the
        // validation path rejected before the award ran (a real error).
        foreach (var (before, after, benign) in new (uint, uint, bool)[]
                 {
                     (0x300u, 0x300u, true),    // unchanged non-zero: already maxed
                     (0u, 0u, false),           // untouched slots: validation rejection
                     (0x300u, 0x500u, false),   // value moved but rejected state: real rejection
                     (0x500u, 0x300u, false),   // value moved backwards: real rejection
                 })
        {
            var memory = new Memory();
            memory.State(block + RankDispatcher.StateOffset, 4); // Reject
            memory.State(block + RankDispatcher.RankBeforeOffset, before);
            memory.State(block + RankDispatcher.RankAfterOffset, after);
            if (new RankRequestMailbox(memory, block).RejectedBecauseAlreadyRanked() != benign)
                throw new Exception($"Rank rejection misclassified for {before:X}/{after:X}");
            cases++;
        }
        foreach (var state in new uint[] { 0, 1, 2, 3 })
        {
            var memory = new Memory();
            memory.State(block + RankDispatcher.StateOffset, state);
            memory.State(block + RankDispatcher.RankBeforeOffset, 0x300);
            memory.State(block + RankDispatcher.RankAfterOffset, 0x300);
            if (new RankRequestMailbox(memory, block).RejectedBecauseAlreadyRanked())
                throw new Exception("Non-reject state reported already-ranked");
            cases++;
        }

        // spawn mailbox @0x18C0: state transitions and publish-last ordering
        foreach (var state in new uint[] { 0, 1, 2, 3, 4, 55 })
        {
            var memory = new Memory();
            memory.State(block + SpawnDispatcher.StateOffset, state);
            memory.Writes.Clear();
            var refused = false;
            try { new SpawnRequestMailbox(memory, block).Submit(0xAF4C0DA5, 0, 100f, -50f, 25f, 0); }
            catch (InvalidOperationException) { refused = true; }
            var allowed = state is 0 or 3 or 4;
            if (refused == allowed) throw new Exception("Invalid spawn mailbox transition");
            if (allowed)
            {
                var expectedOrder = new List<nuint>();
                for (var slot = 4; slot <= 0x24; slot += 4)
                    expectedOrder.Add(block + SpawnDispatcher.MailboxOffset + (nuint)slot);
                expectedOrder.Add(block + SpawnDispatcher.StateOffset);
                if (!memory.Writes.SequenceEqual(expectedOrder))
                    throw new Exception("Spawn request not published last");
                if (new SpawnRequestMailbox(memory, block).State != 1) throw new Exception("Bad spawn publish");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Outstanding spawn request overwritten");
            cases++;
        }
        // spawn validation: no template at all, low owner, non-finite position
        foreach (var bad in new (uint hash, uint holder, float x, float y, float z, uint owner)[]
                 {
                     (0, 0, 1, 1, 1, 0),                       // neither hash nor holder
                     (0, 0x20000, 1, 1, 1, 0x100),             // low owner
                     (0, 0x20000, float.NaN, 1, 1, 0),         // NaN x
                     (0, 0x20000, 1, float.NegativeInfinity, 1, 0),
                     (0, 0x20000, 1, 1, float.PositiveInfinity, 0),
                 })
        {
            var memory = new Memory();
            var refused = false;
            try { new SpawnRequestMailbox(memory, block).Submit(bad.hash, bad.holder, bad.x, bad.y, bad.z, bad.owner); }
            catch (ArgumentException) { refused = true; }
            if (!refused || memory.Writes.Count != 0) throw new Exception("Invalid spawn request published");
            cases++;
        }
        // spawn result read: only terminal states return payloads, must be stable
        {
            var memory = new Memory();
            memory.State(block + SpawnDispatcher.StateOffset, 3);
            var mailbox = new SpawnRequestMailbox(memory, block);
            memory.Write(block + SpawnDispatcher.ResultBodyOffset, BitConverter.GetBytes(0x60FF00u));
            memory.Write(block + SpawnDispatcher.ResolvedHolderOffset, BitConverter.GetBytes(0x70000u));
            var (state, body, resolved) = mailbox.ReadResult();
            if (state != 3 || body != 0x60FF00 || resolved != 0x70000)
                throw new Exception("Spawn terminal result not read back");
            cases++;
        }
        {
            var memory = new Memory();
            memory.State(block + SpawnDispatcher.StateOffset, 1);
            var (state, _, _) = new SpawnRequestMailbox(memory, block).ReadResult();
            if (state != 1) throw new Exception("Spawn non-terminal state leaked a payload");
            cases++;
        }
        Console.WriteLine($"PASS {cases} capture/kill/spawn mailbox lifecycle and publish-order cases");
    }
}
