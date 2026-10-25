using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.Core.Target;

/// <summary>Classifies which build a running ra3_1.12.game process belongs
/// to. The Steam repack and the EA original share the module name, so the
/// discriminator probes two independent EA anchor slots (money chain +
/// zoom/selection iterator): both matching the EA displaced bytes proves the
/// EA build; anything else keeps the repack answer so an unknown build fails
/// loudly in the hook verifier instead of being guessed here. Read-only.</summary>
public static class GameBuildClassifier
{
    public const string Ea112 = "1.12ea";

    private static readonly string[] ProbeIds = ["money_h1", "zoom_unit_xp"];

    public static string ClassifyUprising(IImageReader image, string moduleVersion, FeaturesData data)
    {
        string[] candidates = moduleVersion switch
        {
            "1.0" => ["uprising-1.0ea", "uprising-1.0"],
            "1.1" => ["uprising-1.01"],
            _ => throw new InvalidOperationException($"不支持的起义时刻模块版本：{moduleVersion}"),
        };
        var matches = candidates.Where(version => ProbeIds.All(id =>
        {
            var def = data.Hooks[id];
            var want = def.DisplacedBytes(version);
            try { return image.Read(def.RvaFor(version),want.Length).AsSpan().SequenceEqual(want); }
            catch { return false; }
        })).ToArray();
        return matches.Length == 1 ? matches[0] : throw new InvalidOperationException("无法唯一识别起义时刻构建，拒绝附加");
    }

    public static string Classify(ProcessMemory mem, nuint baseAddr, FeaturesData data)
    {
        foreach (var id in ProbeIds)
        {
            if (!data.Hooks.TryGetValue(id, out var def) || !def.Rva.TryGetValue(Ea112, out var rvaStr))
                return "1.12";
            var want = def.DisplacedBytes();
            try
            {
                var probe = mem.Read(baseAddr + Convert.ToUInt32(rvaStr, 16), want.Length);
                if (!probe.AsSpan().SequenceEqual(want))
                    return "1.12";
            }
            catch
            {
                // unreadable probe — let the repack path surface the real error
                return "1.12";
            }
        }
        return Ea112;
    }
}
