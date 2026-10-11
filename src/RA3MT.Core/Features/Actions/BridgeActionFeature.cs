using RA3MT.Core.Engine;
using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Host;

namespace RA3MT.Core.Features.Actions;

/// <summary>Bridge actions that submit the current selection to a game-thread
/// bridge (rank / capture / destroy). One class for all three: the bridge id and
/// the wording are the only differences, and the engine no longer has to know that
/// "lv", "capture" and "destroy" exist.</summary>
public sealed class BridgeActionFeature(string id, BridgeId bridge, string unavailableReason) : IFeature
{
    public string Id { get; } = id;
    public BridgeId Bridge { get; } = bridge;
    public string UnavailableReason { get; } = unavailableReason;

    public FeatureKind Kind => FeatureKind.Action;
    public FeatureAvailability Availability => FeatureAvailability.NeedsBridge;
    public bool IsMigrated => true;

    public IFeatureState CreateState(FeatureContext context) => new State(context, this);

    private sealed class State(FeatureContext context, BridgeActionFeature feature) : IFeatureState
    {
        public bool IsOn => false;

        public FeatureResult SetOn(bool on) => FeatureResult.Failure("非开关型功能");

        public FeatureResult Execute(string? arg)
        {
            var gateway = context.Host.Services.Get<IBridgeGateway>();
            if (gateway is null || !gateway.IsActive(feature.Bridge))
                return FeatureResult.Failure(feature.UnavailableReason);
            return gateway.SubmitSelection(feature.Bridge, feature.Id);
        }
    }
}
