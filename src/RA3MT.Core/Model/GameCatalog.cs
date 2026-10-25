namespace RA3MT.Core.Model;

public enum GameId { RedAlert3, Uprising }

public sealed record GameDefinition(GameId Id, string Name, string SteamAppId,
    string SupportedVersions, string[] ModuleNames);

/// <summary>Product identity is separate from executable build identity.</summary>
public static class GameCatalog
{
    public static readonly GameDefinition RedAlert3 = new(GameId.RedAlert3, "红色警戒 3", "17480",
        "Steam 1.12 / 1.13 · EA 原版 1.12", ["ra3_1.12.game", "ra3_1.13.game"]);
    public static readonly GameDefinition Uprising = new(GameId.Uprising, "红色警戒 3：起义时刻", "24800",
        "EA 原版 1.0 · Steam 1.0 / 1.01", ["ra3ep1_1.0.game", "ra3ep1_1.1.game"]);
    public static IReadOnlyList<GameDefinition> All { get; } = [RedAlert3, Uprising];
    public static GameDefinition Get(GameId id) => id switch
    {
        GameId.RedAlert3 => RedAlert3,
        GameId.Uprising => Uprising,
        _ => throw new ArgumentOutOfRangeException(nameof(id)),
    };
}

/// <summary>Audited object fields. Offsets describe object kinds, not a blanket
/// address delta: Uprising also changes the selection manager, AI and templates.</summary>
public sealed record GameLayout(uint Health, uint Owner, uint Tracker, uint Ai, uint Ore,
    uint Eligibility, uint SelectionHead, uint SelectionCount, uint LocomotorActive,
    uint LocomotorSet, byte WeaponCapacity, uint PowerUi, uint Vision, bool InlineOreAmount = false,
    uint BodyDrawable = 0xF4, byte UnpackStartFrame = 0x3C, uint VisionOverrideSkip = 0,
    bool GuardedResourceHooks = false)
{
    public static readonly GameLayout RedAlert3 = new(0x33C, 0x418, 0x3CC, 0x374, 0x398,
        0x245, 0x50, 0x5C, 0x21C, 0x1FC, 0x70, 0x3B0, 0x260);
    public static readonly GameLayout Uprising = new(0x34C, 0x428, 0x3DC, 0x384, 0x3A8,
        0x24D, 0x54, 0x60, 0x228, 0x208, 0x78, 0x3E0, 0x264, true, 0xF8, 0x34, 14, true);
    public static bool IsUprising(string version) => version is "uprising-1.0ea" or "uprising-1.0" or "uprising-1.01";
    public static GameLayout For(string version) => IsUprising(version) ? Uprising : RedAlert3;
}
