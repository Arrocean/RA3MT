using RA3MT.Core.Features.Abstractions;

namespace RA3MT.Core.Features.Actions;

/// <summary>Diagnostic dump: a read-only snapshot of the hook-sited globals the
/// stubs capture. The dump itself reads several engine-owned structures (the block
/// layout, the diagnostics area, the selected-list root), so the feature takes a
/// callback rather than the engine. This keeps the feature a real feature (it
/// appears in the catalog, the UI and the health checks) without dragging the
/// engine's internals into the features layer.</summary>
public sealed class DiagnosticsFeature(string id, Func<FeatureResult> dump) : IFeature
{
    public string Id { get; } = id;
    public FeatureKind Kind => FeatureKind.Action;
    public FeatureAvailability Availability => FeatureAvailability.Ready;
    public bool IsMigrated => true;

    public IFeatureState CreateState(FeatureContext context) => new State(dump);

    private sealed class State(Func<FeatureResult> dump) : IFeatureState
    {
        public bool IsOn => false;
        public FeatureResult SetOn(bool on) => FeatureResult.Failure("非开关型功能");
        public FeatureResult Execute(string? arg) => dump();
    }
}
