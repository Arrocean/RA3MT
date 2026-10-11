namespace RA3MT.Core.Engine;

/// <summary>Single source of truth for what lives where inside the injected
/// block. Before this existed, every offset was a <c>const</c> on
/// <see cref="MasterCode"/> and each bridge contributed its own pairwise overlap
/// assertion to <c>Install()</c>. Now the whole map is declared here and proven
/// once by <see cref="BlockLayout.Validate"/>.</summary>
public static class BlockLayoutCatalog
{
    /// <summary>Reserved size of the injected block (VirtualAllocEx).</summary>
    public const uint BlockSize = 0x2000;

    /// <summary>First byte available to stub code (below it: flags/diagnostics).</summary>
    public const uint StubAreaStart = 0x40;

    /// <summary>Capture buffer for selected entries; also the stub arena's ceiling.</summary>
    public const uint CaptureCountOffset = 0xFFC;
    public const uint CaptureArrayOffset = 0x1000;
    public const uint CaptureArrayBytes = 64 * 4;

    /// <summary>Diagnostics slots written by diagnostic stubs. They live *below*
    /// <see cref="StubAreaStart"/>, so they can never collide with stub code; the
    /// layout self-check asserts that relationship.</summary>
    public const uint DiagnosticsOffset = 0x10;
    public const uint DiagnosticsSize = 0x20;

    /// <summary>Highest byte any diagnostic slot may occupy.</summary>
    public const uint DiagnosticsEnd = DiagnosticsOffset + DiagnosticsSize;

    /// <summary>Capture-arm flag, also below the stub arena.</summary>
    public const uint FlagCaptureSelOffset = 0x0C;

    /// <summary>Offset of the local-player side object inside the player context.</summary>
    public const uint SideFieldOffset = 0x1188;

    /// <summary>Mailbox field sizes (state + payload + result).</summary>
    public const int MailboxSize = 0x40;

    /// <summary>Alignment every stub/dispatcher/consumer slot is padded to.</summary>
    public const uint SlotAlign = 16;

    /// <summary>Declare the regions that always exist. Bridge regions are added
    /// by <see cref="DeclareBridges"/> because they only matter when the bridge is
    /// actually enabled — that keeps a disabled-bridge install free of
    /// never-written reservations.</summary>
    public static BlockLayout Create()
    {
        var layout = new BlockLayout(BlockSize);
        layout.Declare("Diagnostics", DiagnosticsOffset, DiagnosticsSize, "diagnostics");
        layout.Declare("CaptureCount", CaptureCountOffset, 4, "selection-capture");
        layout.Declare("CaptureArray", CaptureArrayOffset, CaptureArrayBytes, "selection-capture");
        return layout;
    }

    /// <summary>Declare the block footprint of the bridges that are enabled.
    /// Call once per enabled bridge, then let the caller measure the emitted
    /// dispatcher and declare it before <see cref="BlockLayout.Validate"/>.</summary>
    public static BlockRegion DeclareBridge(BlockLayout layout, string owner)
    {
        var slot = FindBridge(owner);
        layout.Declare($"{slot.Owner}Dispatcher", slot.DispatcherOffset, slot.DispatcherSize, slot.Owner);
        layout.Declare($"{slot.Owner}Mailbox", slot.MailboxOffset, MailboxSize, slot.Owner);
        return layout.TryGet($"{slot.Owner}Dispatcher", out var region)
            ? region
            : throw new BlockLayoutException($"bridge '{owner}' declaration failed");
    }

    /// <summary>Look up a bridge's block footprint by owner name.</summary>
    public static BridgeBlockSlot FindBridge(string owner)
    {
        foreach (var bridge in Bridges)
            if (bridge.Owner == owner) return bridge;
        throw new BlockLayoutException($"unknown bridge '{owner}'");
    }

    /// <summary>Declare every bridge (used by the layout self-check so the whole
    /// map is proven even though the shipping default enables none).</summary>
    public static void DeclareBridges(BlockLayout layout)
    {
        foreach (var bridge in Bridges) DeclareBridge(layout, bridge.Owner);
    }

    /// <summary>Every game-thread bridge's block footprint.
    ///
    /// The consumer stub is NOT a separate region: <c>RankDispatcher.EmitMoneyBridge</c>
    /// prepends one 5-byte <c>call</c> per enabled dispatcher to the settlement-site
    /// stub, so consumers live inside the unmanaged tail of the stub arena.
    /// <see cref="DispatcherSize"/> is the budget the layout check compares the
    /// measured dispatcher against.</summary>
    public static readonly BridgeBlockSlot[] Bridges =
    [
        new("Rank", DispatcherOffset: 0x1100, DispatcherSize: 0x180, MailboxOffset: 0x1800),
        new("Capture", DispatcherOffset: 0x1280, DispatcherSize: 0x180, MailboxOffset: 0x1840),
        new("Kill", DispatcherOffset: 0x1400, DispatcherSize: 0x180, MailboxOffset: 0x1880),
        new("Spawn", DispatcherOffset: 0x1580, DispatcherSize: 0x280, MailboxOffset: 0x18C0),
    ];
}

/// <summary>Block footprint of one game-thread bridge.</summary>
public readonly record struct BridgeBlockSlot(
    string Owner,
    uint DispatcherOffset,
    uint DispatcherSize,
    uint MailboxOffset);
