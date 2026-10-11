using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Host;

namespace RA3MT.Core.Features.EngineAdapters;

/// <summary>Engine-side <see cref="ISpawnGateway"/>: the engine owns the spawn
/// mailbox lifecycle and the unit/template walk, features own the request shape.</summary>
public sealed class SpawnGateway(
    bool active,
    Func<IReadOnlyList<uint>> copyHolders,
    Func<(float x, float y, float z)?> mouseGround,
    Func<(float x, float y, float z)?> selectionAnchor,
    Func<string, List<(uint hash, uint holder, float x, float y, float z)>, (bool ok, string msg)> submit)
    : ISpawnGateway
{
    public bool IsAvailable => active;
    public bool IsActive => active;
    public IReadOnlyList<uint> CopyHolders => copyHolders();
    public (float x, float y, float z)? MouseGround => mouseGround();
    public (float x, float y, float z)? SelectionAnchor => selectionAnchor();

    public FeatureResult Submit(string featureName,
        List<(uint hash, uint holder, float x, float y, float z)> requests)
    {
        var (ok, msg) = submit(featureName, requests);
        return ok ? FeatureResult.Succeeded(msg) : FeatureResult.Failure(msg);
    }
}
