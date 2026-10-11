using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Single outstanding request for a future game-thread rank dispatcher.</summary>
public sealed class RankRequestMailbox
{
    public const uint Offset = 0x1800;
    private readonly IInjectionMemory _memory;
    private readonly nuint _address;
    private readonly object _gate = new();

    public RankRequestMailbox(IInjectionMemory memory, nuint block)
    {
        _memory = memory;
        _address = block + Offset;
    }

    public uint State => _memory.ReadU32(_address);

    // Do not reset a pending/executing request on timeout: the game may still consume it.
    public void Submit(uint body, uint drawable, uint tracker)
    {
        if (body < 0x10000 || drawable < 0x10000 || tracker < 0x10000)
            throw new ArgumentException("Invalid rank request object");
        lock (_gate)
        {
            var state = State;
            if (state != 0 && state != 3 && state != 4)
                throw new InvalidOperationException("Rank request still pending or mailbox state invalid");
            var payload = new byte[20];
            BitConverter.GetBytes(body).CopyTo(payload, 0);
            BitConverter.GetBytes(drawable).CopyTo(payload, 4);
            BitConverter.GetBytes(tracker).CopyTo(payload, 8);
            _memory.Write(_address + 4, payload);
            // Publish last, after all pointers/results are complete.
            _memory.Write(_address, BitConverter.GetBytes(1u));
        }
    }

    public (uint state, uint before, uint after) ReadResult()
    {
        lock (_gate)
        {
            var first = State;
            if (first != 3 && first != 4) return (first, 0, 0);
            var before = _memory.ReadU32(_address + 0x10);
            var after = _memory.ReadU32(_address + 0x14);
            if (State != first) throw new InvalidOperationException("Rank result changed while reading");
            return (first, before, after);
        }
    }
}
