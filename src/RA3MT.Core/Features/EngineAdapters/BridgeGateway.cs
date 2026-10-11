using RA3MT.Core.Engine;
using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Host;

namespace RA3MT.Core.Features.EngineAdapters;

/// <summary>Engine-side implementation of <see cref="IBridgeGateway"/>. Keeps the
/// bridge plumbing (mailboxes, waiting, logging) in the engine while features only
/// see "is this bridge usable" and "submit my selection".</summary>
public sealed class BridgeGateway(
    Func<BridgeId, bool> isActive,
    Func<BridgeId, string, (bool ok, string msg)> submitSelection) : IBridgeGateway
{
    public bool IsAvailable => true;

    public bool IsActive(BridgeId id) => isActive(id);

    public FeatureResult SubmitSelection(BridgeId id, string featureName)
    {
        var (ok, msg) = submitSelection(id, featureName);
        return ok ? FeatureResult.Succeeded(msg) : FeatureResult.Failure(msg);
    }
}
