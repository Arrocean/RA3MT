using RA3MT.Core.Scan;

namespace RA3MT.Core.Target;

/// <summary>Strict byte contracts for the game-thread bridge APIs (capture transition
/// and HP adjust). All anchors must match exactly or the bridge is not installed.</summary>
public static class CaptureApiResolver
{
    public const string Id = "capture";

    // 51 55 8B 6C 24 0C 56 8B F1 8B 8E 14 04 00 00 3B CD 0F 84
    private const string Prologue =
        "51 55 8B 6C 24 0C 56 8B F1 8B 8E 14 04 00 00 3B CD 0F 84";

    private readonly record struct Layout(uint Entry, uint Helper, uint Root, uint RetOffset);

    private static Layout For(string version) => ImageScan.Layout(version, "Capture transition", "1.12",
        new Layout(0x3CBF50u, 0x166340u, 0x8EDE2Cu, 0x285u),
        "1.13",
        new Layout(0x3B5DF0u, 0x2FDBC0u, 0x8F214Cu, 0x285u));

    public static ApiAddress Resolve(string version, nuint imageBase, IImageReader image)
    {
        var layout = For(version);
        var code = ImageScan.ReadExact(image, layout.Entry, 0x50, "Capture transition");
        ImageScan.RequirePattern(code, Prologue, "Capture transition");
        ImageScan.RequireCall(code, 0x26, layout.Entry, layout.Helper, "Capture transition helper 1");
        ImageScan.RequireCall(code, 0x2F, layout.Entry, layout.Helper, "Capture transition helper 2");
        ImageScan.RequireGlobalOperand(code, 0x48, imageBase, layout.Root, "Capture transition");
        ImageScan.RequireRet(image, layout.Entry, layout.RetOffset, 8, "Capture transition");
        return new ApiAddress(imageBase + layout.Entry,
            ImageScan.Resolved("Capture transition", version, 0, layout.Entry, code.Length));
    }

    public static nuint Resolve(string version, nuint imageBase, Func<uint, int, byte[]> readRva) =>
        Resolve(version, imageBase, new DelegateImageReader(readRva));
}

public static class KillApiResolver
{
    public const string Id = "kill";

    // Both repack versions share these entry bytes at the HP adjust function:
    // 8B 44 24 08 85 C0 F3 0F 10 4C 24 04 56 8B F1 F3 0F 10 46 04
    // F3 0F 11 46 08 F3 0F 58 C1 57 F3 0F 11 46 04 74
    private const string Entry =
        "8B 44 24 08 85 C0 F3 0F 10 4C 24 04 56 8B F1 F3 0F 10 46 04 " +
        "F3 0F 11 46 08 F3 0F 58 C1 57 F3 0F 11 46 04 74";

    // Death marker (thiscall Body, push al; ret 4) — identical prologue in both
    // versions; captured live as the terminal call of the natural-death path.
    private const string DeathMarkerEntry = "80 7C 24 04 00 56 8B F1 8A 86 71 04 00 00";

    private readonly record struct Layout(uint Entry, uint Marker);

    private static Layout For(string version) => ImageScan.Layout(version, "HP adjust", "1.12",
        new Layout(0x3A3650u, 0x365C90u),
        "1.13",
        new Layout(0x38CB30u, 0x3513F0u));

    /// <summary>Resolve the HP adjust function and the death marker; never invokes game code.</summary>
    public static (nuint adjust, nuint deathMarker) Resolve(string version, nuint imageBase, IImageReader image)
    {
        var layout = For(version);
        var code = ImageScan.ReadExact(image, layout.Entry, 0x28, "HP adjust");
        ImageScan.RequirePattern(code, Entry, "HP adjust");
        ImageScan.RequireRet(image, layout.Entry, 0xC6, 8, "HP adjust");

        var markerLength = DeathMarkerEntry.Replace(" ", "").Length / 2;
        var markerCode = ImageScan.ReadExact(image, layout.Marker, markerLength, "Death marker");
        ImageScan.RequirePattern(markerCode, DeathMarkerEntry, "Death marker");
        return (imageBase + layout.Entry, imageBase + layout.Marker);
    }

    public static (nuint adjust, nuint deathMarker) Resolve(string version, nuint imageBase,
        Func<uint, int, byte[]> readRva) =>
        Resolve(version, imageBase, new DelegateImageReader(readRva));
}
