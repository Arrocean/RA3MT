namespace RA3MT.Core.Target;

/// <summary>
/// Strict identity resolver for the re-packed map-start spawn wrapper. This only
/// returns its address after every byte, relative CALL edge, and version-specific
/// manager global matches. The wrapper is not a supported external/thread-safe API;
/// callers must not invoke it until owner/template/lifecycle/thread contracts are
/// independently established.
/// </summary>
public static class SpawnApiResolver
{
    // Canonical 304-byte 1.13 wrapper with rel32 CALL displacements zeroed and
    // the absolute manager-global operand at +0xDA zeroed. The version-specific
    // values are reconstructed below and compared over the complete wrapper.
    private const string CanonicalHex =
        "8B4C240883EC3C5333DB33C03BCB0F841701000056578B7C24588944240C89442410" +
        "8944241489442418894424208944242483C840894C24288BCF8944241C895C242C895C" +
        "2430895C2434895C2438895C243C895C2440895C2444E8000000008944242C8D4C2428" +
        "8D44240C5189442434E8000000008BF083C4043BF30F84A40000008B56048B4214D940" +
        "6455518BCED91C24E8000000008B6C2458558BCEE8000000008B4C24546AFF5357E800" +
        "000000F30F2AC08BCFF30F118630040000E8000000008BCE8BF8E8000000003BFB7407" +
        "8BCFE8000000008B0D0000000056E8000000008B86740300003BC374388B4E048B91C0" +
        "000000C1EA04F6C20175275505FC0100005056E80000000083C40C84C07413536A0155" +
        "8BCEE800000000558BCEE8000000005D5F8BC65E5B83C43CC3";

    private static readonly int[] CallOffsets =
        [0x5B, 0x71, 0x93, 0x9F, 0xAC, 0xBF, 0xC8, 0xD3, 0xDF, 0x107, 0x119, 0x121];

    private static readonly uint[][] CallTargets =
    [
        [0x4647A0, 0x102410, 0x40C430, 0x40CFC0, 0x408AA0, 0x4647A0,
         0x350DD0, 0x466000, 0x418A00, 0x2BA1D0, 0x306460, 0x40CFC0],
        [0x4793B0, 0x11A210, 0x421450, 0x421FE0, 0x41DB00, 0x4793B0,
         0x365670, 0x47AC10, 0x42D720, 0x2CFAF0, 0x31B790, 0x421FE0],
    ];

    private static readonly (string Version, uint Entry, uint ManagerRva, int TargetSet)[] Layouts =
    [
        ("1.13", 0x22E3E0, 0x8F1DB8, 0),
        ("1.12", 0x2440F0, 0x8EDA98, 1),
    ];

    public const string Id = "spawn";

    /// <summary>Resolve the verified wrapper address; never invokes game code.</summary>
    public static nuint Resolve(string version, nuint imageBase, Func<uint, int, byte[]> readRva) =>
        Resolve(version, imageBase, new DelegateImageReader(readRva));

    public static nuint Resolve(string version, nuint imageBase, IImageReader image)
    {
        ArgumentNullException.ThrowIfNull(image);
        var layout = Layouts.FirstOrDefault(item => item.Version == version);
        if (layout.Version is null)
            throw new InvalidOperationException("Unsupported spawn wrapper version");
        if (imageBase == 0 || imageBase > uint.MaxValue)
            throw new InvalidOperationException("Spawn wrapper requires a 32-bit image base");

        var expected = Convert.FromHexString(CanonicalHex);
        if (expected.Length != 304)
            throw new InvalidOperationException("Internal spawn wrapper contract length mismatch");
        var targets = CallTargets[layout.TargetSet];
        for (var i = 0; i < CallOffsets.Length; i++)
        {
            var call = CallOffsets[i];
            var displacement = checked((int)((long)targets[i] - (layout.Entry + (uint)call + 5)));
            BitConverter.GetBytes(displacement).CopyTo(expected, call + 1);
        }

        var managerVa = checked((uint)imageBase + layout.ManagerRva);
        BitConverter.GetBytes(managerVa).CopyTo(expected, 0xDA);
        var actual = image.Read(layout.Entry, expected.Length);
        if (actual.Length != expected.Length)
            throw new InvalidOperationException("Spawn wrapper read length mismatch");
        var mismatch = actual.AsSpan().SequenceEqual(expected) ? -1 :
            Enumerable.Range(0, expected.Length).First(index => actual[index] != expected[index]);
        if (mismatch >= 0)
            throw new InvalidOperationException($"Spawn wrapper contract mismatch at +0x{mismatch:X}: " +
                $"expected {expected[mismatch]:X2}, read {actual[mismatch]:X2}");
        return imageBase + layout.Entry;
    }
}
