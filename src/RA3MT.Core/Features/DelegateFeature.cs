using RA3MT.Core.Features.Abstractions;

namespace RA3MT.Core.Features;

/// <summary>A state object built from two delegates. Used while features are being
/// migrated: the engine keeps the historical implementation and the catalog wires
/// it in as a feature, so the router/UI contract exists before the code moves.</summary>
public sealed class DelegateFeatureState : IFeatureState
{
    private readonly Func<bool> _isOn;
    private readonly Func<bool, FeatureResult> _setOn;
    private readonly Func<string?, FeatureResult> _execute;

    public DelegateFeatureState(Func<bool> isOn, Func<bool, FeatureResult> setOn, Func<string?, FeatureResult> execute)
    {
        _isOn = isOn;
        _setOn = setOn;
        _execute = execute;
    }

    public bool IsOn => _isOn();

    public FeatureResult SetOn(bool on) => _setOn(on);

    public FeatureResult Execute(string? arg) => _execute(arg);
}

/// <summary>Catalog entry backed by delegates.</summary>
public sealed class DelegateFeature : IFeature
{
    private readonly Func<FeatureContext, IFeatureState> _factory;
    private readonly IReadOnlyList<string> _sites;

    public DelegateFeature(string id, FeatureKind kind, FeatureAvailability availability,
        Func<FeatureContext, IFeatureState> factory, IReadOnlyList<string>? sites = null)
    {
        Id = id;
        Kind = kind;
        Availability = availability;
        _factory = factory;
        _sites = sites ?? [];
    }

    public string Id { get; }
    public FeatureKind Kind { get; }
    public FeatureAvailability Availability { get; }

    public IFeatureState CreateState(FeatureContext context) => _factory(context);
}
