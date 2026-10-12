using RA3MT.Core.Scan;

namespace RA3MT.Core.Target;

/// <summary>Verification primitives shared by every API resolver. Each one throws
/// with a stable, human-readable reason so a failed resolve explains which anchor
/// of the contract disagreed — before this existed, the same four checks were
/// re-implemented (and mis-worded) in five separate classes.</summary>
public static class ImageScan
{
    /// <summary>Read exactly <paramref name="length"/> bytes at <paramref name="rva"/>.</summary>
    public static byte[] ReadExact(IImageReader image, uint rva, int length, string what)
    {
        var code = image.Read(rva, length);
        if (code.Length != length)
            throw new InvalidOperationException($"{what}: short read ({code.Length}/{length} bytes at RVA 0x{rva:X})");
        return code;
    }

    /// <summary>Require the byte pattern to match at <paramref name="code"/>[0..].</summary>
    public static void RequirePattern(byte[] code, string signature, string what)
    {
        var pattern = Pattern.Parse(signature);
        if (pattern.Length > code.Length || !pattern.Matches(code, 0))
            throw new InvalidOperationException($"{what}: instruction contract mismatch");
    }

    /// <summary>Require the byte pattern at an explicit offset inside the read block.</summary>
    public static void RequirePatternAt(byte[] code, string signature, int offset, string what)
    {
        var pattern = Pattern.Parse(signature);
        if (offset < 0 || offset + pattern.Length > code.Length || !pattern.Matches(code, offset))
            throw new InvalidOperationException($"{what}: instruction contract mismatch at +0x{offset:X}");
    }

    /// <summary>Require the relative call whose NEXT instruction starts at
    /// <paramref name="nextInstructionOffset"/> to target <paramref name="targetRva"/>.
    /// Callers pass the offset recorded in the original hand-written contracts
    /// (Rank 0x2E/0x51, Capture 0x26/0x2F); the E8 opcode therefore sits at
    /// <c>offset - 5</c> and its displacement at <c>offset - 4</c>.
    ///
    /// The arithmetic is deliberately 32-bit wrapping: both ends are module RVAs, so
    /// the displacement is frequently a large negative number.</summary>
    public static void RequireCall(byte[] code, int nextInstructionOffset, uint functionRva, uint targetRva,
        string what)
    {
        var opcodeOffset = nextInstructionOffset - 5;
        var displacementOffset = nextInstructionOffset - 4;
        if (opcodeOffset < 0 || nextInstructionOffset > code.Length)
            throw new InvalidOperationException($"{what}: call site out of range");
        var target = unchecked(functionRva + (uint)nextInstructionOffset +
                               (uint)BitConverter.ToInt32(code, displacementOffset));
        if (target != targetRva)
            throw new InvalidOperationException(
                $"{what}: helper target mismatch (read 0x{target:X}, expected 0x{targetRva:X})");
    }

    /// <summary>Require an absolute operand at <paramref name="operandOffset"/> to
    /// equal <paramref name="imageBase"/> + <paramref name="globalRva"/>.</summary>
    public static void RequireGlobalOperand(byte[] code, int operandOffset, nuint imageBase, uint globalRva,
        string what)
    {
        if (operandOffset < 0 || operandOffset + 4 > code.Length)
            throw new InvalidOperationException($"{what}: global operand out of range");
        var value = BitConverter.ToUInt32(code, operandOffset);
        if (value != checked((uint)(imageBase + globalRva)))
            throw new InvalidOperationException($"{what}: context global mismatch");
    }

    /// <summary>Require the function tail to be <c>ret imm16</c> with the given
    /// stack cleanup, which proves the calling convention we rely on.</summary>
    public static void RequireRet(IImageReader image, uint functionRva, uint retOffset, ushort cleanup,
        string what)
    {
        var tail = image.Read(functionRva + retOffset, 3);
        if (tail.Length != 3)
            throw new InvalidOperationException($"{what}: ret bytes unreadable");
        var expected = new byte[] { 0xC2, (byte)(cleanup & 0xFF), (byte)(cleanup >> 8) };
        if (!tail.AsSpan().SequenceEqual(expected))
            throw new InvalidOperationException($"{what}: ret {cleanup:X} mismatch");
    }

    /// <summary>Select the per-version layout, or fail with a clear reason.</summary>
    public static TLayout Layout<TLayout>(string version, string apiName, string version112, TLayout layout112,
        string version113, TLayout layout113)
    {
        if (version == version112) return layout112;
        if (version == version113) return layout113;
        throw new InvalidOperationException($"{apiName}: unsupported version '{version}'");
    }

    /// <summary>Three-or-more-version layout table ("1.12" / "1.13" /
    /// "1.12ea" …). Pairs are checked in order; unknown versions fail with the
    /// API name for context.</summary>
    public static TLayout Layout<TLayout>(string version, string apiName,
        params (string Version, TLayout Layout)[] table)
    {
        foreach (var (key, layout) in table)
            if (version == key)
                return layout;
        throw new InvalidOperationException($"{apiName}: unsupported version '{version}'");
    }

    /// <summary>Build the resolution record that goes into logs and tests.</summary>
    public static ApiResolution Resolved(string name, string version, nuint imageBase, uint rva, int verifiedBytes) =>
        new(name, version, imageBase + rva, verifiedBytes);
}
