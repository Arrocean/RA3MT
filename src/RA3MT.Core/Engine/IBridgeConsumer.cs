namespace RA3MT.Core.Engine;

/// <summary>Stable identity of a game-thread bridge. Used as the registry key and
/// in block-region ownership, so a bridge is never addressed by a hand-written
/// switch again.</summary>
public enum BridgeId
{
    Rank,
    Capture,
    Kill,
    Spawn,
}

/// <summary>One request handed to a bridge consumer. Each consumer interprets the
/// generic slots according to its own contract (see <see cref="IBridgeConsumer"/>).</summary>
public readonly record struct BridgeRequest(uint Body, uint Drawable, uint Third, uint Fourth = 0)
{
    public static BridgeRequest For(uint body, uint drawable, uint third = 0, uint fourth = 0) =>
        new(body, drawable, third, fourth);
}

/// <summary>Terminal outcome of a bridge request.</summary>
public enum BridgeOutcome
{
    /// <summary>Still pending (or the mailbox was never claimed).</summary>
    Pending,

    /// <summary>The game thread executed the request.</summary>
    Applied,

    /// <summary>The game thread rejected it after validation.</summary>
    Rejected,
}

/// <summary>Uniform view of a bridge mailbox: state, submit, outcome. Feature code
/// waits on <see cref="BridgeOutcome"/>, never on raw state numbers.</summary>
public interface IBridgeMailbox
{
    uint RawState { get; }
    BridgeOutcome Outcome { get; }
    void Submit(BridgeRequest request);
}

/// <summary>Everything the engine needs to know about one bridge.
///
/// Contract of the generic <see cref="BridgeRequest"/> slots per consumer:
///   Rank    : Body, Drawable, Third = experience tracker
///   Capture : Body, Drawable
///   Kill    : Body, Drawable, Third = health component pointer
///   Spawn   : Third = template hash (0 = use Fourth as holder), Fourth = holder;
///             position/owner are carried by the concrete spawn mailbox.
/// </summary>
public interface IBridgeConsumer
{
    BridgeId Id { get; }

    /// <summary>Human readable name for logs.</summary>
    string DisplayName { get; }

    /// <summary>Message shown when the selection yields no target for this bridge.</summary>
    string NoTargetMessage { get; }

    /// <summary>Block footprint of this bridge (dispatcher slot + mailbox).</summary>
    BridgeBlockSlot BlockSlot { get; }

    /// <summary>Reserve this bridge's block regions on the layout being built.</summary>
    void Declare(BlockLayout layout);

    /// <summary>Emit the game-thread dispatcher at <paramref name="dispatcherVa"/>.
    /// <paramref name="blockVa"/> is the block base, used for mailbox addressing.</summary>
    byte[] EmitDispatcher(nuint dispatcherVa, nuint blockVa);

    /// <summary>Create the mailbox facade for an installed block.</summary>
    IBridgeMailbox CreateMailbox(Memory.IInjectionMemory memory, nuint blockVa);
}
