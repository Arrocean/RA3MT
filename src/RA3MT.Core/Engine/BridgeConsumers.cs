using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Rank bridge: promotes the selected units through the game's own rank
/// function, called on the game thread from the money settlement stub.</summary>
public sealed class RankBridgeConsumer(nuint rankFunctionVa, nuint rootVa) : IBridgeConsumer
{
    public BridgeId Id => BridgeId.Rank;
    public string DisplayName => "晋级桥";
    public string NoTargetMessage => "没有可晋级目标（未选中或不支持经验）";
    public BridgeBlockSlot BlockSlot => BlockLayoutCatalog.FindBridge("Rank");

    public void Declare(BlockLayout layout) => BlockLayoutCatalog.DeclareBridge(layout, "Rank");

    public byte[] EmitDispatcher(nuint dispatcherVa, nuint blockVa) =>
        RankDispatcher.Emit(dispatcherVa, blockVa, rankFunctionVa, rootVa);

    public IBridgeMailbox CreateMailbox(IInjectionMemory memory, nuint blockVa) =>
        new RankRequestMailbox(memory, blockVa);
}

/// <summary>Capture bridge: runs the complete ownership transition on the game
/// thread (never a raw owner-pointer write).</summary>
public sealed class CaptureBridgeConsumer(nuint captureFunctionVa, nuint rootVa) : IBridgeConsumer
{
    public BridgeId Id => BridgeId.Capture;
    public string DisplayName => "俘虏桥";
    public string NoTargetMessage => "没有可俘虏目标（未选中或目标已属己方）";
    public BridgeBlockSlot BlockSlot => BlockLayoutCatalog.FindBridge("Capture");

    public void Declare(BlockLayout layout) => BlockLayoutCatalog.DeclareBridge(layout, "Capture");

    public byte[] EmitDispatcher(nuint dispatcherVa, nuint blockVa) =>
        CaptureDispatcher.Emit(dispatcherVa, blockVa, captureFunctionVa, rootVa);

    public IBridgeMailbox CreateMailbox(IInjectionMemory memory, nuint blockVa) =>
        new CaptureRequestMailbox(memory, blockVa);
}

/// <summary>Kill bridge: routes destruction through the game's FULL damage entry
/// so the death decision, animation dispatch and model recycling all run inside
/// the game's own path (FINAL3-identical call).</summary>
public sealed class KillBridgeConsumer(nuint damageEntryVa, nuint rootVa) : IBridgeConsumer
{
    public BridgeId Id => BridgeId.Kill;
    public string DisplayName => "摧毁桥";
    public string NoTargetMessage => "没有可摧毁目标（未选中或无生命组件）";
    public BridgeBlockSlot BlockSlot => BlockLayoutCatalog.FindBridge("Kill");

    public void Declare(BlockLayout layout) => BlockLayoutCatalog.DeclareBridge(layout, "Kill");

    public byte[] EmitDispatcher(nuint dispatcherVa, nuint blockVa) =>
        KillDispatcher.Emit(dispatcherVa, blockVa, damageEntryVa, rootVa);

    public IBridgeMailbox CreateMailbox(IInjectionMemory memory, nuint blockVa) =>
        new KillRequestMailbox(memory, blockVa);
}

/// <summary>Spawn bridge: creates units through the game's map-start spawn
/// wrapper, resolving WB-string hashes on the game thread.</summary>
public sealed class SpawnBridgeConsumer(nuint wrapperVa, nuint hashLookupVa, nuint hashTableGlobalVa,
    nuint rootVa) : IBridgeConsumer
{
    public BridgeId Id => BridgeId.Spawn;
    public string DisplayName => "生成桥";
    public string NoTargetMessage => "没有可生成的目标（未选中或目标缺少模板链）";
    public BridgeBlockSlot BlockSlot => BlockLayoutCatalog.FindBridge("Spawn");

    public void Declare(BlockLayout layout) => BlockLayoutCatalog.DeclareBridge(layout, "Spawn");

    public byte[] EmitDispatcher(nuint dispatcherVa, nuint blockVa) =>
        SpawnDispatcher.Emit(dispatcherVa, blockVa, wrapperVa, hashLookupVa, hashTableGlobalVa, rootVa);

    public IBridgeMailbox CreateMailbox(IInjectionMemory memory, nuint blockVa) =>
        new SpawnRequestMailbox(memory, blockVa);
}

/// <summary>Lookup helper: map a bridge id to the consumer the engine built.</summary>
public sealed class BridgeConsumerSet
{
    private readonly Dictionary<BridgeId, IBridgeConsumer> _byId;

    public BridgeConsumerSet(IEnumerable<IBridgeConsumer> consumers)
    {
        _byId = consumers.ToDictionary(c => c.Id);
    }

    public IReadOnlyCollection<IBridgeConsumer> Consumers => _byId.Values;

    public bool TryGet(BridgeId id, out IBridgeConsumer consumer) => _byId.TryGetValue(id, out consumer!);

    public IBridgeConsumer this[BridgeId id] =>
        _byId.TryGetValue(id, out var consumer)
            ? consumer
            : throw new InvalidOperationException($"bridge '{id}' is not enabled");
}
