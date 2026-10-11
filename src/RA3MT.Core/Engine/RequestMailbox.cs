using RA3MT.Core.Engine;
using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Shared lifecycle for every bridge mailbox: validate the payload,
/// publish the payload, then publish the state last, and read results back with a
/// change check. Derived classes only describe their payload and their terminal
/// result fields — the state machine itself is written once.
///
/// The concrete mailboxes keep their historical public methods
/// (<c>Submit(body, drawable, tracker)</c> …) for compatibility; they delegate
/// here. State constants: 0 idle, 1 pending, 2 executing, 3 success, 4 reject.</summary>
public abstract class RequestMailbox : IBridgeMailbox
{
    protected const uint Idle = 0, Pending = 1, Executing = 2, Success = 3, Reject = 4;

    private readonly IInjectionMemory _memory;
    private readonly nuint _address;
    private readonly object _gate = new();

    protected RequestMailbox(IInjectionMemory memory, nuint block, uint offset)
    {
        _memory = memory;
        _address = block + offset;
    }

    public nuint Address => _address;

    public uint State => _memory.ReadU32(_address);

    public uint RawState => State;

    public BridgeOutcome Outcome => State switch
    {
        Success => BridgeOutcome.Applied,
        Reject => BridgeOutcome.Rejected,
        _ => BridgeOutcome.Pending,
    };

    /// <summary>Write the request payload (everything except the state dword at
    /// +0). Called under the mailbox lock, before the state is published.</summary>
    protected abstract void WritePayload(BridgeRequest request);

    /// <summary>Reject malformed requests before anything is written.</summary>
    protected virtual void Validate(BridgeRequest request) { }

    /// <summary>Called after the request reached a terminal state, to refresh any
    /// cached result fields. Must not write.</summary>
    protected virtual void OnTerminal(uint state) { }

    public virtual void Submit(BridgeRequest request)
    {
        Validate(request);
        lock (_gate)
        {
            var state = State;
            if (state is not (Idle or Success or Reject))
                throw new InvalidOperationException($"{GetType().Name} request still pending or mailbox invalid");
            WritePayload(request);
            _memory.Write(_address, BitConverter.GetBytes(Pending)); // publish last
        }
    }

    /// <summary>Terminal state, or <c>Pending</c>'s raw value while unfinished.
    /// Re-reads the state after touching result fields and throws if the game
    /// thread moved on in the meantime — results are never returned torn.</summary>
    protected uint ReadTerminalState()
    {
        lock (_gate)
        {
            var first = State;
            if (first is not (Success or Reject)) return first;
            OnTerminal(first);
            if (State != first) throw new InvalidOperationException($"{GetType().Name} result changed while reading");
            return first;
        }
    }

    protected uint ReadU32(int byteOffset) => _memory.ReadU32(_address + (nuint)byteOffset);

    protected void WriteU32(int byteOffset, uint value) =>
        _memory.Write(_address + (nuint)byteOffset, BitConverter.GetBytes(value));

    /// <summary>Write several consecutive dwords as ONE memory write. The shape of
    /// the write sequence is part of the mailbox contract the offline checks pin
    /// down ("payload first, state last"), so consumers keep their original shape.</summary>
    protected void WriteDwords(int byteOffset, params uint[] values)
    {
        var buffer = new byte[values.Length * 4];
        for (var i = 0; i < values.Length; i++) BitConverter.GetBytes(values[i]).CopyTo(buffer, i * 4);
        _memory.Write(_address + (nuint)byteOffset, buffer);
    }

    protected void WriteBytes(int byteOffset, ReadOnlySpan<byte> value) =>
        _memory.Write(_address + (nuint)byteOffset, value);

    // ---- payload helpers -------------------------------------------------

    protected static void RequireObject(uint value, string what)
    {
        if (value < 0x10000) throw new ArgumentException($"Invalid {what} pointer");
    }
}
