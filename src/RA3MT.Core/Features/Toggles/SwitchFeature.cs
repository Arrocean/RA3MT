using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Host;

namespace RA3MT.Core.Features.Toggles;

/// <summary>One stub-flag toggle. The trainer has a dozen of these (money, power,
/// protocol points, fast build, freeze, threat levels …): they differ only in the
/// flag name and the wording, so they are one class with a definition instead of a
/// branch per feature id.</summary>
public sealed class SwitchFeature(string id, string switchName) : IFeature
{
    public string Id { get; } = id;
    public FeatureKind Kind => FeatureKind.Toggle;
    public FeatureAvailability Availability => FeatureAvailability.Ready;
    public bool IsMigrated => true;

    /// <summary>Flag name as the stub generator knows it.</summary>
    public string SwitchName { get; } = switchName;

    public IFeatureState CreateState(FeatureContext context) => new State(context, this);

    private sealed class State(FeatureContext context, SwitchFeature feature) : IFeatureState
    {
        public bool IsOn => context.Host.Services.Get<ISwitchBank>()?.IsOn(feature.Id) ?? false;

        public FeatureResult SetOn(bool on)
        {
            // Fail closed, never throw: a feature may be asked to toggle while the
            // session is gone (that is what the unbound-state check enforces).
            var bank = context.Host.Services.Get<ISwitchBank>();
            if (bank is null) return FeatureResult.Failure("开关服务不可用（未附加或未安装）");
            var result = bank.Set(feature.Id, on);
            if (result.Ok) context.Host.NotifyStateChanged();
            return result;
        }

        public FeatureResult Execute(string? arg) => FeatureResult.Failure("非动作型功能");
    }
}
