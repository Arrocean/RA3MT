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

    private static Layout For(string version) => ImageScan.Layout(version, "Capture transition",
        ("1.12", new Layout(0x3CBF50u, 0x166340u, 0x8EDE2Cu, 0x285u)),
        ("1.13", new Layout(0x3B5DF0u, 0x2FDBC0u, 0x8F214Cu, 0x285u)),
        // EA original 1.12: prologue contract hits uniquely; helper called at
        // the same three offsets (+0x21/+0x2A/+0x55); root global mirrors the
        // repack layout (also confirmed by the zoom function's side-getter).
        ("1.12ea", new Layout(0x38DBB0u, 0x124C60u, 0x8E8C9Cu, 0x285u)));

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

    // Full damage entry (thiscall Body; push 0 / death-type / damage-type;
    // ret 0xC): constructs a DamageInfo and drives [Body+0x33C]'s complete
    // damage pipeline, so the death decision, animation dispatch and model
    // recycling all run. This is the exact call FINAL3's destroy uses
    // (EA 1.12 RVA 0x39EA50, live-verified with death animations on the
    // pirated copy), located in both repacks by signature — the two segments
    // below skip the version-specific .rdata tag (+0x11) and helper call
    // (+0x15). Tail ret 0xC at +0xB7 proves the callee cleans the 3 args.
    private const string DamageEntryHead =
        "81 EC 9C 00 00 00 56 8B F1 8D 4C 24 08 C7 44 24 04";
    private const string DamageEntryBody =
        "8B 8C 24 A8 00 00 00 0F 57 C0 8B 84 24 A4 00 00 00 " +
        "8B 94 24 AC 00 00 00 89 4C 24 38 8B 8E 3C 03 00 00";

    private readonly record struct Layout(uint Entry, uint Marker, uint DamageEntry);

    private static Layout For(string version) => ImageScan.Layout(version, "HP adjust",
        ("1.12", new Layout(0x3A3650u, 0x365C90u, 0x3DCDF0u)),
        ("1.13", new Layout(0x38CB30u, 0x3513F0u, 0x3C7190u)),
        // EA original 1.12: all three contracts hit uniquely; the damage entry
        // is the exact address FINAL3's destroy calls (live-verified there).
        ("1.12ea", new Layout(0x365190u, 0x327890u, 0x39EA50u)));

    /// <summary>Resolve the HP adjust function, the death marker and the full
    /// damage entry; never invokes game code.</summary>
    public static (nuint adjust, nuint deathMarker, nuint damageEntry) Resolve(
        string version, nuint imageBase, IImageReader image)
    {
        var layout = For(version);
        var code = ImageScan.ReadExact(image, layout.Entry, 0x28, "HP adjust");
        ImageScan.RequirePattern(code, Entry, "HP adjust");
        ImageScan.RequireRet(image, layout.Entry, 0xC6, 8, "HP adjust");

        var markerLength = DeathMarkerEntry.Replace(" ", "").Length / 2;
        var markerCode = ImageScan.ReadExact(image, layout.Marker, markerLength, "Death marker");
        ImageScan.RequirePattern(markerCode, DeathMarkerEntry, "Death marker");

        var damage = ImageScan.ReadExact(image, layout.DamageEntry, 0x3C, "Damage entry");
        ImageScan.RequirePatternAt(damage, DamageEntryHead, 0, "Damage entry");
        ImageScan.RequirePatternAt(damage, DamageEntryBody, 0x1A, "Damage entry");
        ImageScan.RequireRet(image, layout.DamageEntry, 0xB7, 0xC, "Damage entry");
        return (imageBase + layout.Entry, imageBase + layout.Marker, imageBase + layout.DamageEntry);
    }

    public static (nuint adjust, nuint deathMarker, nuint damageEntry) Resolve(string version, nuint imageBase,
        Func<uint, int, byte[]> readRva) =>
        Resolve(version, imageBase, new DelegateImageReader(readRva));
}
