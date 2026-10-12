namespace RA3MT.Core.Target;

/// <summary>
/// Strict identity checks for the static startup hash-table and owner-record
/// helpers used by the map-start spawn path. This only resolves addresses and
/// global RVAs; it does not read live objects or invoke game code.
/// </summary>
public sealed record SpawnSupportApis(
    nuint TemplateHashLookup,
    nuint HashMapFind,
    nuint OwnerResolver,
    nuint OwnerKindPredicate,
    nuint HashTableOwnerGlobal,
    nuint OwnerKindGlobal,
    nuint MouseScreenToWorld,
    nuint MouseObjectGlobal);

public static class SpawnSupportApiResolver
{
    private sealed record Layout(
        string Version,
        uint HashLookup,
        uint HashFind,
        uint OwnerResolver,
        uint OwnerPredicate,
        uint HashTableGlobalRva,
        uint OwnerKindGlobalRva,
        uint SpawnWrapperEntry,
        uint MouseTransform,
        uint MouseObjectGlobalRva);

    private static readonly Layout[] Layouts =
    [
        new("1.13", 0x40D5B0, 0x40D2C0, 0x4647A0, 0xFF4A0, 0x8F0108, 0x8E21A4, 0x22E3E0,
            0x20ECF0, 0x8E43BC),
        new("1.12", 0x422510, 0x11F110, 0x4793B0, 0x1175D0, 0x8EBDE8, 0x8DDE84, 0x2440F0,
            0x22C500, 0x8E009C),
    ];

    // The map-start caller directly above the spawn wrapper loads the static hash
    // table and calls the lookup at the same relative offset in both versions:
    // mov ecx,[hashTableGlobal]; push edx; call TemplateHashLookup.
    private const int CallerSiteOffset = 0x1CA;

    private static readonly byte[] HashMapFindCanonical = Convert.FromHexString(
        "8B44240883EC08568B3033D2578B79088BC6F7F78B49048B049185C08D1491" +
        "740B3B30742E8B400885C075F58D04B98B08894C24088944240C8B442414" +
        "8D4C24088B118B49045F89108948045E83C408C20800");

    private static readonly byte[] HashLookupCanonical = Convert.FromHexString(
        "83EC08568D71288D442410508D4C2408518BCEE8000000008B56088B4E04" +
        "8B4424043B04915E74098B400483C408C2040033C083C408C20400");

    private static readonly byte[] OwnerCanonical = Convert.FromHexString(
        "568BF18B0D00000000E80000000084C0740F8B868C00000085C074058B40105E" +
        "C38B86AC0000005EC3");

    private static readonly byte[] OwnerPredicateCanonical = Convert.FromHexString(
        "8B814801000083F807741283F806740D83F808740883F805740332C0C3B001C3");

    // Screen->world transform (cdecl screenXY*, outWorld*, 0, 0; ret al; caller
    // cleans 0x10). Located from FINAL3's EA call target (RVA 0x1ED4A0) by its
    // unique prologue: sub esp,0xD0; cmp [esp+0xD4],0; push ebp; je far;
    // mov ebp,[esp+0xDC]; test ebp; je far. Live-verified 2026-10-12: the mouse
    // object behind the global stores INTEGER screen pixels at +0x3C/+0x40
    // (OS GetCursorPos cross-check), so the stub converts them with fild.
    private static readonly byte[] MouseTransformCanonical = Convert.FromHexString(
        "81ecd000000083bc24d400000000550f845f040000" +
        "8bac24dc00000085ed0f8450040000");

    public const string Id = "spawn-support";

    /// <summary>Validate all static helper identities and return their 32-bit addresses.</summary>
    public static SpawnSupportApis Resolve(string version, nuint imageBase,
        Func<uint, int, byte[]> readRva) =>
        Resolve(version, imageBase, new DelegateImageReader(readRva));

    public static SpawnSupportApis Resolve(string version, nuint imageBase, IImageReader image)
    {
        ArgumentNullException.ThrowIfNull(image);
        var layout = Layouts.FirstOrDefault(item => item.Version == version)
            ?? throw new InvalidOperationException("Unsupported spawn support API version");
        if (imageBase == 0 || imageBase > uint.MaxValue)
            throw new InvalidOperationException("Spawn support APIs require a 32-bit image base");

        var lookup = WithRelativeCall(HashLookupCanonical, 0x13,
            layout.HashFind - checked(layout.HashLookup + 0x18));
        Verify(image, layout.HashLookup, lookup, "template hash lookup");
        Verify(image, layout.HashFind, HashMapFindCanonical, "hash map finder");
        VerifyHashTableGlobal(image, layout, (uint)imageBase);

        var owner = WithRelativeCall(OwnerCanonical, 9,
            layout.OwnerPredicate - checked(layout.OwnerResolver + 14));
        BitConverter.GetBytes(checked((uint)imageBase + layout.OwnerKindGlobalRva)).CopyTo(owner, 5);
        Verify(image, layout.OwnerResolver, owner, "owner resolver");
        Verify(image, layout.OwnerPredicate, OwnerPredicateCanonical, "owner-kind predicate");
        Verify(image, layout.MouseTransform, MouseTransformCanonical, "mouse screen-to-world transform");

        return new SpawnSupportApis(
            imageBase + layout.HashLookup,
            imageBase + layout.HashFind,
            imageBase + layout.OwnerResolver,
            imageBase + layout.OwnerPredicate,
            imageBase + layout.HashTableGlobalRva,
            imageBase + layout.OwnerKindGlobalRva,
            imageBase + layout.MouseTransform,
            imageBase + layout.MouseObjectGlobalRva);
    }

    private static byte[] WithRelativeCall(byte[] canonical, int opcodeOffset, uint displacement)
    {
        var bytes = (byte[])canonical.Clone();
        if (opcodeOffset < 0 || opcodeOffset + 5 > bytes.Length || bytes[opcodeOffset] != 0xE8)
            throw new InvalidOperationException("Internal spawn helper call layout mismatch");
        BitConverter.GetBytes(unchecked((int)displacement)).CopyTo(bytes, opcodeOffset + 1);
        return bytes;
    }

    /// <summary>Anchor the hash-table owner global to the map-start caller's
    /// mov ecx,[global]; push edx; call TemplateHashLookup sequence.</summary>
    private static void VerifyHashTableGlobal(IImageReader image, Layout layout, uint imageBase)
    {
        var site = checked(layout.SpawnWrapperEntry + (uint)CallerSiteOffset);
        var expected = new byte[12];
        expected[0] = 0x8B;
        expected[1] = 0x0D;
        BitConverter.GetBytes(checked(imageBase + layout.HashTableGlobalRva)).CopyTo(expected, 2);
        expected[6] = 0x52;
        expected[7] = 0xE8;
        var callSite = site + 12;
        BitConverter.GetBytes(checked((int)((long)layout.HashLookup - callSite))).CopyTo(expected, 8);
        var actual = image.Read(site, expected.Length);
        if (actual.Length != expected.Length)
            throw new InvalidOperationException("hash table caller site read length mismatch");
        var mismatch = actual.AsSpan().SequenceEqual(expected) ? -1 :
            Enumerable.Range(0, expected.Length).First(index => actual[index] != expected[index]);
        if (mismatch >= 0)
            throw new InvalidOperationException($"hash table caller site mismatch at RVA 0x{site + (uint)mismatch:X}: " +
                $"expected {expected[mismatch]:X2}, read {actual[mismatch]:X2}");
    }

    private static void Verify(IImageReader image, uint rva,
        byte[] expected, string name)
    {
        var actual = image.Read(rva, expected.Length);
        if (actual.Length != expected.Length)
            throw new InvalidOperationException($"{name} read length mismatch");
        var mismatch = actual.AsSpan().SequenceEqual(expected) ? -1 :
            Enumerable.Range(0, expected.Length).First(index => actual[index] != expected[index]);
        if (mismatch >= 0)
            throw new InvalidOperationException($"{name} contract mismatch at RVA 0x{rva + (uint)mismatch:X}");
    }
}
