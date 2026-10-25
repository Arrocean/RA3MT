using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Host;

namespace RA3MT.Core.Features.Actions;

/// <summary>A one-shot flag consumed and cleared by its verified game-thread hook.</summary>
public interface IFlagRequests : IFeatureService
{
    FeatureResult Submit(string flag);
}

public sealed class FlagRequests(Func<string, bool, FeatureResult> write) : IFlagRequests
{
    public bool IsAvailable => true;
    public FeatureResult Submit(string flag) => write(flag, true);
}

public sealed class FlagActionFeature(string id, string flag) : IFeature
{
    public string Id => id;
    public FeatureKind Kind => FeatureKind.Action;
    public FeatureAvailability Availability => FeatureAvailability.Ready;
    public bool IsMigrated => true;
    public IFeatureState CreateState(FeatureContext context) => new State(context, flag);
    private sealed class State(FeatureContext context, string flag) : IFeatureState
    {
        public bool IsOn => false;
        public FeatureResult SetOn(bool on) => FeatureResult.Failure("非开关型功能");
        public FeatureResult Execute(string? arg)
        {
            var requests = context.Host.Services.Get<IFlagRequests>();
            if (requests is null) return FeatureResult.Failure("未附加，无法提交请求");
            var result = requests.Submit(flag);
            return result.Ok ? FeatureResult.Succeeded("已提交，请回到战局后按 Esc 进入菜单页刷新一次生效") : result;
        }
    }
}
