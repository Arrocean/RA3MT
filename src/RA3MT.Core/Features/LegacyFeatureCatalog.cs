using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features;

/// <summary>Builds the feature registry from features.json.
///
/// Right now every entry is wrapped as a <see cref="DelegateFeature"/> that calls
/// back into <see cref="TrainerEngine"/>'s historical switch-based code. That
/// keeps behaviour identical while the router/UI contract (id in, state out)
/// exists. As features migrate to their own IFeature implementations (M5), the
/// delegate entries are replaced one by one and the engine branches are deleted.
/// </summary>
public static class LegacyFeatureCatalog
{
    public static FeatureRegistry Build(FeaturesData data, TrainerEngine? engine = null)
    {
        var features = new List<IFeature>(data.Features.Count);
        foreach (var def in data.Features)
        {
            var kind = def.Kind switch
            {
                "toggle" => FeatureKind.Toggle,
                "action" => FeatureKind.Action,
                _ => FeatureKind.Pending,
            };
            var availability = kind == FeatureKind.Pending
                ? FeatureAvailability.NotImplemented
                : FeatureAvailability.Ready;

            var captured = def;
            features.Add(new DelegateFeature(
                def.Id,
                kind,
                availability,
                context => engine is null
                    ? new UnboundFeatureState(captured)
                    : new DelegateFeatureState(
                        () => engine.ToggleState.TryGetValue(captured.Id, out var on) && on,
                        on => engine.SetFeatureToggle(captured.Id, on),
                        arg => engine.RunFeatureAction(captured.Id, arg)),
                def.Hooks));
        }

        return new FeatureRegistry(features);
    }

    /// <summary>State used when the catalog is built without an engine (offline
    /// checks): every request fails with a stable message.</summary>
    private sealed class UnboundFeatureState : IFeatureState
    {
        public UnboundFeatureState(FeatureDef def) => Def = def;

        public FeatureDef Def { get; }
        public bool IsOn => false;
        public FeatureResult SetOn(bool on) => FeatureResult.Failure("no engine bound");
        public FeatureResult Execute(string? arg) => FeatureResult.Failure("no engine bound");
    }
}
