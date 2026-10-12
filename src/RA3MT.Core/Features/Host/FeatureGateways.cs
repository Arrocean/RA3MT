using RA3MT.Core.Engine;
using RA3MT.Core.Features.Abstractions;

namespace RA3MT.Core.Features.Host;

/// <summary>Trainer flag switches (the dword/byte flags in the injected block that
/// the stubs branch on).</summary>
public interface IGameSwitches : IFeatureService
{
    /// <summary>Set a stub flag. Throws when the feature is not installed.</summary>
    bool TrySet(string flag, bool on);

    bool IsSet(string flag);
}

/// <summary>Selected-unit enumeration as a service, so action features share one
/// validated reader instead of each re-walking the game's selection list.</summary>
public interface ISelectionReader : IFeatureService
{
    uint[] Bodies { get; }
    int Count { get; }
}

/// <summary>Game-thread bridge submission (rank / capture / kill).</summary>
public interface IBridgeGateway : IFeatureService
{
    bool IsActive(BridgeId id);

    /// <summary>Submit the current selection to a bridge and wait for consumption.</summary>
    FeatureResult SubmitSelection(BridgeId id, string featureName);
}

/// <summary>Spawn-bridge submission (copy-selected / MCVs / reinforcement codes).</summary>
public interface ISpawnGateway : IFeatureService
{
    bool IsActive { get; }

    /// <summary>Dereference the configured template holder for one selected unit.</summary>
    IReadOnlyList<uint> CopyHolders { get; }

    /// <summary>Mouse ground position as (x, y, z), or null when unavailable.</summary>
    (float x, float y, float z)? MouseGround { get; }

    /// <summary>Position of one selected unit, or null when nothing is selected.</summary>
    (float x, float y, float z)? SelectionAnchor { get; }

    /// <summary>Submit spawn requests (hash 0 = spawn the given holder).</summary>
    FeatureResult Submit(string featureName, List<(uint hash, uint holder, float x, float y, float z)> requests);

    /// <summary>FINAL3-style reinforcement ("We need back"): spawn
    /// <paramref name="count"/> units of the hash spread around (x, y, z), then
    /// rank each new unit up through the rank bridge. Rank-up is skipped with a
    /// log line when the rank bridge is off.</summary>
    FeatureResult SubmitReinforcement(string featureName, uint hash, float x, float y, float z, int count = 8);
}

/// <summary>Fully qualified names of the stub flags, so features stop passing
/// bare strings that only features.json knows about.</summary>
public static class SwitchNames
{
    public const string Money = "money";
    public const string Power = "power";
    public const string ScPoints = "scpoints";
    public const string AllProto = "allproto";
    public const string FastBuild = "fastbuild";
    public const string InstantReady = "instantready";
    public const string FreezeEnemy = "freezeenemy";
    public const string Zoom = "zoom";
    public const string RevealMap = "revealmap";
    public const string Ammo = "ammo";
    public const string ThreatMax = "threatmax";
    public const string ThreatZero = "threatzero";
}
