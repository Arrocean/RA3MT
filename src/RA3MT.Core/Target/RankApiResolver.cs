using RA3MT.Core.Scan;

namespace RA3MT.Core.Target;

/// <summary>Verified entry contract for FINAL3-style rank increments; does not invoke game code.</summary>
public static class RankApiResolver
{
    public const string Signature = "55 8B 6C 24 08 85 ED 57 8B F9 7F 07 5F 32 C0 5D C2 0C 00 53 56 32 DB 33 F6 85 ED 7E 3D 8D 49 00 8B 0D ?? ?? ?? ?? 6A 00 57 E8 ?? ?? ?? ?? 85 C0 7E 28 8B 4C 24 1C 8B 54 24 18 51 52 6A 00 6A 00 51 F3 0F 2A C0 8B CF F3 0F 11 04 24 E8 ?? ?? ?? ?? 83 C6 01 3B F5 B3 01 7C C6 5E 8A C3 5B 5F 5D C2 0C 00";

    public static nuint Resolve(string version, nuint imageBase, Func<uint, int, byte[]> readRva)
    {
        var layout = version switch
        {
            "1.12" => (entry: 0x39A840u, threshold: 0x138F90u, award: 0x381EB0u, root: 0x8DDE7Cu),
            "1.13" => (entry: 0x385600u, threshold: 0x1213C0u, award: 0x36DF90u, root: 0x8E219Cu),
            _ => throw new InvalidOperationException("Unsupported rank API version"),
        };
        var pattern = Pattern.Parse(Signature);
        var code = readRva(layout.entry, pattern.Length);
        if (code.Length != pattern.Length || !pattern.Matches(code, 0))
            throw new InvalidOperationException("Rank API instruction contract mismatch");
        if (BitConverter.ToUInt32(code, 0x22) != checked((uint)(imageBase + layout.root)))
            throw new InvalidOperationException("Rank API context global mismatch");
        void CheckCall(int displacementOffset, uint returnOffset, uint targetRva)
        {
            var target = (long)layout.entry + returnOffset + BitConverter.ToInt32(code, displacementOffset);
            if (target != targetRva)
                throw new InvalidOperationException("Rank API helper target mismatch");
        }
        CheckCall(0x2A, 0x2E, layout.threshold);
        CheckCall(0x4D, 0x51, layout.award);
        return imageBase + layout.entry;
    }
}
