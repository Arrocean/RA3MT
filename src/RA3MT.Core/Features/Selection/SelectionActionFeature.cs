using RA3MT.Core.Features.Abstractions;

namespace RA3MT.Core.Features.Selection;

/// <summary>One-shot actions on the current selection (speed, freeze, health,
/// capture …). The selected-unit enumeration and every write go through
/// <see cref="SelectionActions"/>, which already validates the selection chain
/// before touching anything; this feature only maps the action id to it and keeps
/// the small amount of state a few actions need (e.g. the speed to restore).</summary>
public sealed class SelectionActionFeature(string id, string action, bool carriesState = true) : IFeature
{
    public string Id { get; } = id;
    public string Action { get; } = action;

    /// <summary>Whether this action needs the per-session restore state.</summary>
    public bool CarriesState { get; } = carriesState;

    public FeatureKind Kind => FeatureKind.Action;
    public FeatureAvailability Availability => FeatureAvailability.Ready;
    public bool IsMigrated => true;

    public IFeatureState CreateState(FeatureContext context) =>
        new State(context, this, CarriesState ? new SelectionActionState() : null);

    private sealed class State(FeatureContext context, SelectionActionFeature feature,
        SelectionActionState? actionState) : IFeatureState
    {
        public bool IsOn => false;

        public FeatureResult SetOn(bool on) => FeatureResult.Failure("非开关型功能");

        public FeatureResult Execute(string? arg)
        {
            try
            {
                var applied = SelectionActions.Apply(context.Host.Memory, context.Data, context.Version,
                    feature.Action, context.ImageBase, actionState);
                context.Host.Log($"{feature.Id}: 作用于 {applied} 个选中目标");
                if (applied == 0)
                    return FeatureResult.Failure("没有可处理的选中目标（未选中或目标不支持此功能）");
                return FeatureResult.Success;
            }
            catch (Exception ex)
            {
                context.Host.Log($"{feature.Id} 失败: {ex.Message}");
                return FeatureResult.Failure(ex.Message);
            }
        }
    }
}

/// <summary>Threat-level restore: turning both override switches off is not a
/// stub flag of its own, it is an action composed of two toggles (FINAL3 "Normal"
/// semantics — no saved value is restored).</summary>
public sealed class ThreatNormalFeature : IFeature
{
    public string Id => "threat_normal";
    public FeatureKind Kind => FeatureKind.Action;
    public FeatureAvailability Availability => FeatureAvailability.Ready;
    public bool IsMigrated => true;

    public IFeatureState CreateState(FeatureContext context) => new State(context);

    private sealed class State(FeatureContext context) : IFeatureState
    {
        public bool IsOn => false;

        public FeatureResult SetOn(bool on) => FeatureResult.Failure("非开关型功能");

        public FeatureResult Execute(string? arg)
        {
            var bank = context.Host.Services.Get<Host.ISwitchBank>();
            if (bank is null) return FeatureResult.Failure("开关服务不可用（未附加或未安装）");
            foreach (var featureId in new[] { "threat_max", "threat_zero" })
            {
                var result = bank.Set(featureId, false);
                if (!result.Ok) return result;
            }
            context.Host.Log("威胁等级恢复：覆盖已关闭，交还游戏自然重算");
            context.Host.NotifyStateChanged();
            return FeatureResult.Success;
        }
    }
}
