using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Toggles;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features;

/// <summary>Builds the <see cref="FeatureRegistry"/> from features.json —
/// the single registration point: every declared feature is wired to its
/// IFeature implementation here (M5 is complete; entries that match no
/// pattern fall through to a fail-closed DelegateFeature that reports the
/// id as unimplemented, so a stale UI copy can never reach old engine
/// switches — there are none left).
/// </summary>
public static class FeatureCatalog
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

            // Toggles that are a plain stub flag are already fully migrated: they
            // need nothing from the engine beyond the switch bank service.
            if (def.Id == Patches.BuildAnywhereFeature.FeatureId)
            {
                features.Add(new Patches.BuildAnywhereFeature());
                continue;
            }

            if (kind == FeatureKind.Toggle && !string.IsNullOrEmpty(def.Flag))
            {
                features.Add(new SwitchFeature(def.Id, def.Flag));
                continue;
            }

            // Selection actions and threat-normal are migrated too: they only need
            // the memory accessor, the model and the validated selection helper.
            if (kind == FeatureKind.Action)
            {
                var bridge = def.Action switch
                {
                    "lv" => (Engine.BridgeId?)Engine.BridgeId.Rank,
                    "capture" => Engine.BridgeId.Capture,
                    "destroy" => Engine.BridgeId.Kill,
                    _ => null,
                };
                if (bridge is not null)
                {
                    features.Add(new Actions.BridgeActionFeature(def.Id, bridge.Value, def.Action switch
                    {
                    "lv" => "晋级桥未启用（晋级函数校验未通过，或被环境变量 RA3MT_RANK_BRIDGE=0 关闭）",
                    "capture" => "俘虏桥未启用（校验未通过，或被环境变量 RA3MT_BRIDGES=0 关闭）",
                    _ => "摧毁桥未启用（校验未通过，或被环境变量 RA3MT_BRIDGES=0 关闭）",
                    }));
                    continue;
                }
            }

            // Spawn-bridge actions: copy-selected / the three MCVs / reinforcement
            // codes. They differ only in how the request is shaped.
            if (kind == FeatureKind.Action)
            {
                var spawnKind = def.Action switch
                {
                    "selcopy" => (Actions.SpawnActionKind?)Actions.SpawnActionKind.CopySelection,
                    // "spawnhash" backs two different features: the MCV buttons carry
                    // their side in the UI argument, the reinforcement box carries a
                    // hex code. The feature id is what distinguishes them.
                    "spawnhash" => def.Id.StartsWith("mcv_", StringComparison.Ordinal)
                        ? Actions.SpawnActionKind.Mcv
                        : Actions.SpawnActionKind.HashCode,
                    _ => null,
                };
                if (spawnKind is not null)
                {
                    features.Add(new Actions.SpawnActionFeature(def.Id, spawnKind.Value));
                    continue;
                }
            }

            if (kind == FeatureKind.Action && def.Action is not null
                && def.Action is not ("selcopy" or "spawnhash"))
            {
                features.Add(def.Action == "threatnormal"
                    ? new Selection.ThreatNormalFeature()
                    : new Selection.SelectionActionFeature(def.Id, def.Action));
                continue;
            }

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
