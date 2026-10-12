using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features;

/// <summary>Feature id -> implementation map. Built once per process from
/// features.json; states are created per attach session.
///
/// Invariant for the migration: every feature declared in features.json must be
/// present here, so the UI never has to special-case an id. <see cref="Verify"/>
/// enforces that during SelfCheck.</summary>
public sealed class FeatureRegistry
{
    private readonly Dictionary<string, IFeature> _byId;

    public FeatureRegistry(IEnumerable<IFeature> features)
    {
        _byId = features.ToDictionary(f => f.Id, StringComparer.Ordinal);
    }

    public IReadOnlyCollection<IFeature> Features => _byId.Values;

    public bool TryGet(string id, out IFeature feature) => _byId.TryGetValue(id, out feature!);

    /// <summary>Ids declared in features.json but missing from the registry.</summary>
    public IReadOnlyList<string> MissingFrom(FeaturesData data) =>
        data.Features.Where(f => !_byId.ContainsKey(f.Id)).Select(f => f.Id).ToList();

    /// <summary>Registry entries with no declaration in features.json.</summary>
    public IReadOnlyList<string> UnknownIn(FeaturesData data) =>
        _byId.Keys.Where(id => data.Features.All(f => f.Id != id)).ToList();
}
