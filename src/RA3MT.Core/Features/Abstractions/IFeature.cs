using RA3MT.Core.Model;

namespace RA3MT.Core.Features.Abstractions;

/// <summary>Catalog entry for one feature. The catalog owns the mapping from
/// features.json to implementations; the engine never switches on feature ids.</summary>
public interface IFeature
{
    /// <summary>features.json id (stable; also the UI/router key).</summary>
    string Id { get; }

    FeatureKind Kind { get; }

    /// <summary>Static availability for the attached build, before a session exists.</summary>
    FeatureAvailability Availability { get; }

    /// <summary>Create the per-session state object. Called once per attach.</summary>
    IFeatureState CreateState(FeatureContext context);
}

/// <summary>Per-session behaviour of one feature. Implementations must tolerate
/// being called when the session is not attached (return a Failure instead).</summary>
public interface IFeatureState
{
    bool IsOn { get; }

    /// <summary>Toggle request. Only meaningful for <see cref="FeatureKind.Toggle"/>.</summary>
    FeatureResult SetOn(bool on);

    /// <summary>One-shot request. Only meaningful for <see cref="FeatureKind.Action"/>.</summary>
    FeatureResult Execute(string? arg);
}

/// <summary>A feature that owns one or more hook sites: it declares which sites
/// it needs and (optionally) which stub generator should run there. The data
/// still comes from features.json; this is the behavioural half.</summary>
public interface IHookPlanFeature
{
    /// <summary>Site ids (features.json "hooks" keys) this feature requires.</summary>
    IReadOnlyList<string> RequiredSites { get; }
}
