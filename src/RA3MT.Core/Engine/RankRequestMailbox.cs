using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Single outstanding request for a game-thread rank dispatcher.
/// Payload published before state; do not reset a pending request on timeout —
/// the game may still consume it.</summary>
public sealed class RankRequestMailbox : RequestMailbox
{
    public const uint Offset = RankDispatcher.MailboxOffset;

    public RankRequestMailbox(IInjectionMemory memory, nuint block) : base(memory, block, Offset) { }

    public new uint State => ReadTerminalState();

    protected override void Validate(BridgeRequest request)
    {
        RequireObject(request.Body, "rank body");
        RequireObject(request.Drawable, "rank drawable");
        RequireObject(request.Third, "rank tracker");
    }

    protected override void WritePayload(BridgeRequest request) =>
        // single 20-byte payload write, then the base publishes the state
        WriteDwords(4, request.Body, request.Drawable, request.Third, 0, 0);

    public void Submit(uint body, uint drawable, uint tracker) =>
        Submit(BridgeRequest.For(body, drawable, tracker));

    public (uint state, uint before, uint after) ReadResult()
    {
        var state = ReadTerminalState();
        if (state is not (Success or Reject)) return (state, 0, 0);
        return (state, ReadU32(0x10), ReadU32(0x14));
    }
}
