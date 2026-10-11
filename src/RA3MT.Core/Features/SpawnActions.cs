using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features;

/// <summary>Spawn-bridge request building: template holders and anchor positions
/// derived from the live selection. Host-side extraction only — the game-thread
/// dispatcher re-validates the holder and resolves hashes itself.</summary>
public static class SpawnActions
{
    // body+0x38/0x3C/0x40 = x/y/z integer mirrors, written by the game's own
    // position-set function (verified in both repack images alongside the
    // spawn wrapper; the wrapper reads its float3 argument the same way).
    public const uint PosXOff = 0x38, PosYOff = 0x3C, PosZOff = 0x40;

    /// <summary>WB-string hashes for the three faction MCVs, verified against the
    /// game's own WBStringHashes.big string-hash asset (data/stringhashes.xml).</summary>
    public static readonly Dictionary<string, uint> McvHashes = new()
    {
        ["allied"] = 0x28DA574E, // AlliedMCV
        ["soviet"] = 0xAF4C0DA5, // SovietMCV
        ["japan"] = 0x1C2EF767,  // JapanMCV
    };

    public static bool TryReadPosition(IInjectionMemory mem, uint body, out float x, out float y, out float z)
    {
        x = y = z = 0;
        if (body < 0x10000) return false;
        x = mem.ReadF32(body + PosXOff);
        y = mem.ReadF32(body + PosYOff);
        z = mem.ReadF32(body + PosZOff);
        return float.IsFinite(x) && float.IsFinite(y) && float.IsFinite(z) &&
               MathF.Abs(x) < 1e6f && MathF.Abs(y) < 1e6f && MathF.Abs(z) < 1e6f;
    }

    /// <summary>Copy-selected targets: (holder, x, y, z) per selected unit. The
    /// holder is the shared per-type template holder from the selection chain
    /// (body+0x3CC → tracker, tracker+4 → holder); the spawn wrapper reads the
    /// descriptor through holder+0x14 exactly like this chain, so it is the
    /// same object kind the game itself spawns from.</summary>
    public static List<(uint holder, float x, float y, float z)> EnumerateCopyTargets(
        IInjectionMemory mem, FeaturesData data, string version, nuint imageBase)
    {
        var bodies = SelectionActions.ReadSelection(
            address => mem.ReadU32(address), address => mem.Read(address, 1)[0],
            imageBase + data.Globals.SelectionList.RvaFor(version));
        var targets = new List<(uint, float, float, float)>();
        var spread = 0;
        foreach (var body in bodies)
        {
            if (!SelectionActions.IsSelectedBody(
                    address => mem.ReadU32(address), address => mem.Read(address, 1)[0], body)) continue;
            var tracker = mem.ReadU32(body + 0x3CCu);
            if (tracker < 0x10000) continue;
            var holder = mem.ReadU32(tracker + 4u);
            if (holder < 0x10000 || mem.ReadU32(holder + 0x14u) < 0x10000) continue;
            if (!TryReadPosition(mem, body, out var x, out var y, out var z)) continue;
            // Nudge each copy off its original so overlapping spawns disperse.
            var offset = 18f * (1 + spread % 5);
            targets.Add((holder, x + offset, y, z + offset));
            spread++;
        }
        return targets;
    }

    /// <summary>Anchor position for hash-based spawns (MCV / reinforcement code):
    /// the first selected unit's own coordinates, so the player controls where
    /// the new unit appears by selecting one of their units first.</summary>
    public static (float x, float y, float z)? GetSelectionAnchor(
        IInjectionMemory mem, FeaturesData data, string version, nuint imageBase)
    {
        var bodies = SelectionActions.ReadSelection(
            address => mem.ReadU32(address), address => mem.Read(address, 1)[0],
            imageBase + data.Globals.SelectionList.RvaFor(version));
        foreach (var body in bodies)
        {
            if (!SelectionActions.IsSelectedBody(
                    address => mem.ReadU32(address), address => mem.Read(address, 1)[0], body)) continue;
            if (TryReadPosition(mem, body, out var x, out var y, out var z))
                return (x, y, z);
        }
        return null;
    }

    /// <summary>Parse a reinforcement code like "6586A5A0" / "0x6586A5A0".</summary>
    public static bool TryParseHash(string text, out uint hash)
    {
        hash = 0;
        if (string.IsNullOrWhiteSpace(text)) return false;
        var s = text.Trim();
        if (s.StartsWith("0x", StringComparison.OrdinalIgnoreCase)) s = s[2..];
        return s.Length is > 0 and <= 8 && uint.TryParse(s,
            System.Globalization.NumberStyles.HexNumber, null, out hash);
    }
}
