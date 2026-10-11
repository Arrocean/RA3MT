using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features.Host;

/// <summary>Single owner of the on/off state for every stub-flag feature.
///
/// The trainer used to track this in a dictionary on the engine that each feature
/// had to remember to update (and the "reset a dependent feature" actions mutated
/// behind the engine's back). Now the bank is the source of truth: a feature asks
/// it to flip, and the observable state follows.</summary>
public interface ISwitchBank : IFeatureService
{
    bool IsOn(string featureId);

    /// <summary>Flip a stub flag and record the observable state.</summary>
    FeatureResult Set(string featureId, bool on);

    IReadOnlyDictionary<string, bool> Snapshot { get; }

    void ResetAll();
}

public sealed class SwitchBank : ISwitchBank
{
    private readonly Dictionary<string, bool> _state = new(StringComparer.Ordinal);
    private readonly FeaturesData _data;
    private readonly Func<string, bool, FeatureResult> _writeFlag;
    private readonly Action<string> _log;

    public SwitchBank(FeaturesData data, Func<string, bool, FeatureResult> writeFlag, Action<string> log)
    {
        _data = data;
        _writeFlag = writeFlag;
        _log = log;
        foreach (var feature in data.Features)
            if (feature.Kind == "toggle") _state[feature.Id] = false;
    }

    public bool IsAvailable => true;

    public bool IsOn(string featureId) => _state.TryGetValue(featureId, out var on) && on;

    public IReadOnlyDictionary<string, bool> Snapshot => _state;

    public FeatureResult Set(string featureId, bool on)
    {
        var feature = _data.Features.FirstOrDefault(f => f.Id == featureId);
        if (feature is null) return FeatureResult.Failure("未声明的功能");
        if (feature.Kind != "toggle") return FeatureResult.Failure("功能尚未可用或非开关型功能");
        if (feature.Flag is null) return FeatureResult.Failure("功能无开关标志");

        var result = _writeFlag(feature.Flag, on);
        if (!result.Ok) return result;
        _state[featureId] = on;
        _log($"{feature.Name} = {(on ? "开" : "关")}");
        return FeatureResult.Success;
    }

    public void ResetAll()
    {
        foreach (var key in _state.Keys.ToList()) _state[key] = false;
    }
}
