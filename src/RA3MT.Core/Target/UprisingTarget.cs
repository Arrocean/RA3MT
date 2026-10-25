using System.Text.Json;
using System.Text.Json.Serialization;
using RA3MT.Core.Model;

namespace RA3MT.Core.Target;

/// <summary>EA FINAL-derived anchors, independently paired with both Steam
/// images. All contracts are exact bytes, including calls and global operands.</summary>
public sealed class UprisingTarget
{
    [JsonPropertyName("hooks")] public Dictionary<string, HookDef> Hooks { get; set; } = new();
    [JsonPropertyName("features")] public List<FeatureDef> Features { get; set; } = new();
    [JsonPropertyName("globals")] public Dictionary<string, GlobalDef> Globals { get; set; } = new();
    [JsonPropertyName("buildAnywhere")] public Dictionary<string, string> BuildAnywhere { get; set; } = new();
    [JsonPropertyName("apis")] public Dictionary<string, UprisingBuild> Apis { get; set; } = new();
    public static UprisingTarget Default { get; } = Load();
    private static UprisingTarget Load()
    {
        using var stream = typeof(UprisingTarget).Assembly.GetManifestResourceStream("RA3MT.Core.Data.uprising.json")
            ?? throw new InvalidOperationException("Missing Uprising contracts");
        return JsonSerializer.Deserialize<UprisingTarget>(stream) ?? throw new InvalidOperationException("Invalid Uprising contracts");
    }

    public static UprisingBuild Build(string version) => Default.Apis.TryGetValue(version, out var build)
        ? build : throw new InvalidOperationException($"Unsupported Uprising build: {version}");
}

public sealed class UprisingBuild
{
    [JsonPropertyName("addresses")] public Dictionary<string, string> Addresses { get; set; } = new();
    [JsonPropertyName("contracts")] public Dictionary<string, InstructionContract> Contracts { get; set; } = new();
    public uint Rva(string name) => Convert.ToUInt32(Addresses[name], 16);
    public nuint Verify(string name, nuint imageBase, IImageReader image)
    {
        if (imageBase != 0x400000) throw new InvalidOperationException("Uprising requires its audited image base 0x400000");
        var contract = Contracts[name];
        var expected = Convert.FromHexString(contract.Bytes);
        var actual = ImageScan.ReadExact(image, contract.RvaValue, expected.Length, name);
        if (!actual.AsSpan().SequenceEqual(expected))
            throw new InvalidOperationException($"Uprising {name}: instruction contract mismatch at RVA 0x{contract.RvaValue:X}");
        return imageBase + contract.RvaValue;
    }
}

public sealed class InstructionContract
{
    [JsonPropertyName("rva")] public string Rva { get; set; } = "";
    [JsonPropertyName("bytes")] public string Bytes { get; set; } = "";
    public uint RvaValue => Convert.ToUInt32(Rva, 16);
}
