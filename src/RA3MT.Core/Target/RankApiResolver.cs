using RA3MT.Core.Scan;

namespace RA3MT.Core.Target;

/// <summary>Verified entry contract for FINAL3-style rank increments; does not invoke game code.</summary>
public static class RankApiResolver
{
    public const string Id = "rank";

    public const string Signature = "55 8B 6C 24 08 85 ED 57 8B F9 7F 07 5F 32 C0 5D C2 0C 00 53 56 32 DB 33 F6 85 ED 7E 3D 8D 49 00 8B 0D ?? ?? ?? ?? 6A 00 57 E8 ?? ?? ?? ?? 85 C0 7E 28 8B 4C 24 1C 8B 54 24 18 51 52 6A 00 6A 00 51 F3 0F 2A C0 8B CF F3 0F 11 04 24 E8 ?? ?? ?? ?? 83 C6 01 3B F5 B3 01 7C C6 5E 8A C3 5B 5F 5D C2 0C 00";

    private readonly record struct Layout(uint Entry, uint Threshold, uint Award, uint Root);

    private static Layout For(string version) => ImageScan.Layout(version, "Rank API",
        ("1.12", new Layout(0x39A840u, 0x138F90u, 0x381EB0u, 0x8DDE7Cu)),
        ("1.13", new Layout(0x385600u, 0x1213C0u, 0x36DF90u, 0x8E219Cu)),
        // EA original 1.12: FINAL3's own call target; same 99-byte contract,
        // helper/global operands extracted from the EA image offline.
        ("1.12ea", new Layout(0x35C200u, 0xF7680u, 0x343920u, 0x8D8CDCu)));

    public static ApiAddress Resolve(string version, nuint imageBase, IImageReader image)
    {
        if (Model.GameLayout.IsUprising(version))
        {
            var address = UprisingTarget.Build(version).Verify("rank", imageBase, image);
            return new ApiAddress(address, ImageScan.Resolved("Rank API", version, imageBase,
                checked((uint)(address-imageBase)), 99));
        }
        var layout = For(version);
        var length = Pattern.Parse(Signature).Length;
        var code = ImageScan.ReadExact(image, layout.Entry, length, "Rank API");
        ImageScan.RequirePattern(code, Signature, "Rank API");
        ImageScan.RequireGlobalOperand(code, 0x22, imageBase, layout.Root, "Rank API");
        ImageScan.RequireCall(code, 0x2E, layout.Entry, layout.Threshold, "Rank API threshold");
        ImageScan.RequireCall(code, 0x51, layout.Entry, layout.Award, "Rank API award");
        return new ApiAddress(imageBase + layout.Entry,
            ImageScan.Resolved("Rank API", version, 0, layout.Entry, length));
    }

    /// <summary>Back-compat overload for callers that still pass a read delegate.</summary>
    public static nuint Resolve(string version, nuint imageBase, Func<uint, int, byte[]> readRva) =>
        Resolve(version, imageBase, new DelegateImageReader(readRva));
}
