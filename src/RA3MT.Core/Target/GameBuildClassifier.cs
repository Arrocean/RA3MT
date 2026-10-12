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
