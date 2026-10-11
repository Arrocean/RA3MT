using System.Text.Json.Serialization;

namespace RA3MT.Core.Model;

/// <summary>A code hook site: the exact RVA per game version, the original
/// (displaced) instruction bytes our detour overwrites and replays, plus an
/// optional cross-version AOB pattern used to verify the build matches.</summary>
public sealed class HookDef
{
    [JsonPropertyName("rva")] public Dictionary<string, string> Rva { get; set; } = new();
    [JsonPropertyName("displaced")] public string Displaced { get; set; } = "";
    /// <summary>Per-version displaced bytes when the two game versions differ
    /// at this site (checked before the shared "displaced" value).</summary>
    [JsonPropertyName("displacedByVersion")] public Dictionary<string, string>? DisplacedByVersion { get; set; }
    [JsonPropertyName("displacedLen")] public int DisplacedLen { get; set; }
    [JsonPropertyName("asm")] public string? Asm { get; set; }
    [JsonPropertyName("pattern")] public string? Pattern { get; set; }
    [JsonPropertyName("patternSiteOffset")] public int PatternSiteOffset { get; set; }
    [JsonPropertyName("sibling")] public string? Sibling { get; set; }
    /// <summary>Stub id in StubGen when different from the site id (shared stubs).</summary>
    [JsonPropertyName("stub")] public string? Stub { get; set; }

    public byte[] DisplacedBytes(string? version = null)
    {
        if (version != null && DisplacedByVersion != null && DisplacedByVersion.TryGetValue(version, out var perVersion))
            return Convert.FromHexString(perVersion.Replace(" ", ""));
        return Convert.FromHexString(Displaced.Replace(" ", ""));
    }

    public int LengthFor(string version) => DisplacedByVersion != null && DisplacedByVersion.ContainsKey(version)
        ? DisplacedBytes(version).Length
        : DisplacedLen;
    public uint RvaFor(string version) => Convert.ToUInt32(Rva[version], 16);
}

public sealed class GlobalDef
{
    [JsonPropertyName("rva")] public Dictionary<string, string> Rva { get; set; } = new();
    [JsonPropertyName("note")] public string? Note { get; set; }

    public uint RvaFor(string version) => Convert.ToUInt32(Rva[version], 16);
}

public sealed class FeatureDef
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("no")] public string No { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("group")] public string Group { get; set; } = "";
    /// <summary>"toggle" | "action" | "pending"</summary>
    [JsonPropertyName("kind")] public string Kind { get; set; } = "toggle";
    [JsonPropertyName("hotkey")] public string Hotkey { get; set; } = "";
    [JsonPropertyName("hooks")] public List<string> Hooks { get; set; } = new();
    [JsonPropertyName("flag")] public string? Flag { get; set; }
    [JsonPropertyName("action")] public string? Action { get; set; }
    [JsonPropertyName("desc")] public string Desc { get; set; } = "";
    [JsonPropertyName("src")] public string? Src { get; set; }
}

public sealed class FeaturesData
{
    [JsonPropertyName("schema")] public int Schema { get; set; }
    [JsonPropertyName("game")] public GameInfo Game { get; set; } = new();
    [JsonPropertyName("hooks")] public Dictionary<string, HookDef> Hooks { get; set; } = new();
    [JsonPropertyName("globals")] public Globals Globals { get; set; } = new();
    [JsonPropertyName("features")] public List<FeatureDef> Features { get; set; } = new();

    public static FeaturesData LoadEmbedded()
    {
        var asm = typeof(FeaturesData).Assembly;
        using var s = asm.GetManifestResourceStream("RA3MT.Core.Data.features.json")
                      ?? throw new InvalidOperationException("embedded features.json not found");
        return System.Text.Json.JsonSerializer.Deserialize<FeaturesData>(s)
               ?? throw new InvalidOperationException("features.json failed to deserialize");
    }
}

public sealed class GameInfo
{
    [JsonPropertyName("moduleNames")] public List<string> ModuleNames { get; set; } = new();
    [JsonPropertyName("imageBase")] public string ImageBase { get; set; } = "0x400000";
    [JsonPropertyName("bits")] public int Bits { get; set; } = 32;
}

public sealed class Globals
{
    [JsonPropertyName("selectionList")] public GlobalDef SelectionList { get; set; } = new();
    [JsonPropertyName("playerRoot")] public GlobalDef PlayerRoot { get; set; } = new();
    [JsonPropertyName("mouseGround")] public GlobalDef? MouseGround { get; set; }
    [JsonPropertyName("buildAnywherePatch")] public GlobalDef? BuildAnywherePatch { get; set; }
}
