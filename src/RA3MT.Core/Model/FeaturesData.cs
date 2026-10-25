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

    /// <summary>Card icon. Keeps the presentation table out of the view model.</summary>
    [JsonPropertyName("icon")] public string Icon { get; set; } = "";

    /// <summary>How the UI should collect this action's argument, if it has one.</summary>
    [JsonPropertyName("arg")] public FeatureArg? Arg { get; set; }

    /// <summary>Addresses this feature owns, e.g. a code-patch site. Keeping them
    /// here instead of in <c>globals</c> stops single-feature data from leaking
    /// into the shared game-address model.</summary>
    [JsonPropertyName("private")] public Dictionary<string, string> Private { get; set; } = new();
}

/// <summary>UI contract for an action that takes an argument. Replaces the
/// per-feature-id switches the view model used to carry.</summary>
public sealed class FeatureArg
{
    /// <summary>"code" (free text, validated by the feature) or "choice" (fixed value).</summary>
    [JsonPropertyName("kind")] public string Kind { get; set; } = "none";

    [JsonPropertyName("label")] public string Label { get; set; } = "";

    [JsonPropertyName("placeholder")] public string Placeholder { get; set; } = "";

    /// <summary>Fixed argument for <c>choice</c> kinds.</summary>
    [JsonPropertyName("value")] public string Value { get; set; } = "";

    /// <summary>Where the value comes from: "text" (inline box) or "fixed".</summary>
    [JsonPropertyName("bind")] public string Bind { get; set; } = "fixed";

    /// <summary>Named suggestion source for "code" args, e.g.
    /// "reinforcement" = the built-in unit code table. When set, the UI adds
    /// a picker button next to the text box.</summary>
    [JsonPropertyName("suggest")] public string? Suggest { get; set; }

    /// <summary>True when the user must type the argument.</summary>
    public bool NeedsText => Kind == "code" || Bind == "text";
}

public sealed class FeaturesData
{
    [JsonPropertyName("schema")] public int Schema { get; set; }
    [JsonPropertyName("game")] public GameInfo Game { get; set; } = new();
    [JsonPropertyName("hooks")] public Dictionary<string, HookDef> Hooks { get; set; } = new();
    [JsonPropertyName("globals")] public Globals Globals { get; set; } = new();
    [JsonPropertyName("features")] public List<FeatureDef> Features { get; set; } = new();

    public static FeaturesData LoadEmbedded(GameId game = GameId.RedAlert3)
    {
        var asm = typeof(FeaturesData).Assembly;
        using var s = asm.GetManifestResourceStream("RA3MT.Core.Data.features.json")
                      ?? throw new InvalidOperationException("embedded features.json not found");
        var data = System.Text.Json.JsonSerializer.Deserialize<FeaturesData>(s)
               ?? throw new InvalidOperationException("features.json failed to deserialize");
        if (game == GameId.Uprising)
        {
            var target = Target.UprisingTarget.Default;
            // Fresh definitions prevent session/UI state from leaking between games.
            data.Hooks = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string,HookDef>>(
                System.Text.Json.JsonSerializer.Serialize(target.Hooks))!;
            data.Globals = new Globals
            {
                PlayerRoot = target.Globals["playerRoot"], SelectionList = target.Globals["selectionList"],
            };
            data.Game.ModuleNames = GameCatalog.Uprising.ModuleNames.ToList();
            data.Features.Single(f => f.Id == "build_anywhere").Private["site"] =
                string.Join(';', target.BuildAnywhere.Select(kv => $"{kv.Key}={kv.Value}"));
            data.Features.AddRange(System.Text.Json.JsonSerializer.Deserialize<List<FeatureDef>>(
                System.Text.Json.JsonSerializer.Serialize(target.Features))!);
        }
        else if (game != GameId.RedAlert3) throw new ArgumentOutOfRangeException(nameof(game));
        return data;
    }

    /// <summary>Typed lookup: shared game globals only. Missing entries are null
    /// so <c>ISymbols</c> can report "unsupported on this version" instead of throwing.</summary>
    public GlobalDef? ById(GameGlobalId id) => id switch
    {
        GameGlobalId.SelectionList => Globals.SelectionList,
        GameGlobalId.PlayerRoot => Globals.PlayerRoot,
        GameGlobalId.MouseGround => Globals.MouseGround,
        _ => null,
    };
}

/// <summary>Feature-private offsets: per-feature version maps that must not live in
/// the shared <see cref="Globals"/> model.</summary>
public static class PrivateOffsets
{
    /// <summary>Read "<c>&lt;version&gt;</c>" from a feature's private map; 0 when absent.</summary>
    public static uint RvaFor(FeaturesData data, string version, string featureId, string key = "site")
    {
        var feature = data.Features.FirstOrDefault(f => f.Id == featureId);
        if (feature is null) return 0;
        if (!feature.Private.TryGetValue(key, out var map)) return 0;
        var entry = map.Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(part => part.Split('=', 2, StringSplitOptions.TrimEntries))
            .FirstOrDefault(pair => pair.Length == 2 && pair[0] == version);
        if (entry is null) return 0;
        return Convert.ToUInt32(entry[1], 16);
    }

    /// <summary>Private value declared as a plain hex string per version:
    /// <c>"1.13": "0x..."</c>.</summary>
    public static uint VersionedRva(FeaturesData data, string version, string featureId, string key)
    {
        var feature = data.Features.FirstOrDefault(f => f.Id == featureId);
        if (feature is null) return 0;
        if (!feature.Private.TryGetValue(key, out var value)) return 0;
        if (value.Contains('=')) return RvaFor(data, version, featureId, key);
        return Convert.ToUInt32(value, 16);
    }
}

/// <summary>Shared, cross-feature game globals. Feature-private addresses belong
/// to the feature's own definition, not here.</summary>
public enum GameGlobalId
{
    /// <summary>Selected-units root (linked list head + count).</summary>
    SelectionList,

    /// <summary>Local player context root; +0x28 is the side object.</summary>
    PlayerRoot,

    /// <summary>Mouse ground intersection float3 (x, z, ground y).</summary>
    MouseGround,

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
}
