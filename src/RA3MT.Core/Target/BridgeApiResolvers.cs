using RA3MT.Core.Scan;

namespace RA3MT.Core.Target;

/// <summary>Strict byte contracts for the game-thread bridge APIs (capture transition
/// and HP adjust). All anchors must match exactly or the bridge is not installed.</summary>
public static class CaptureApiResolver
{
    // 51 55 8B 6C 24 0C 56 8B F1 8B 8E 14 04 00 00 3B CD 0F 84
    private const string Prologue =
        "51 55 8B 6C 24 0C 56 8B F1 8B 8E 14 04 00 00 3B CD 0F 84";

    public static nuint Resolve(string version, nuint imageBase, Func<uint, int, byte[]> readRva)
    {
        var layout = version switch
        {
            "1.12" => (entry: 0x3CBF50u, helper: 0x166340u, root: 0x8EDE2Cu, retOffset: 0x285u),
            "1.13" => (entry: 0x3B5DF0u, helper: 0x2FDBC0u, root: 0x8F214Cu, retOffset: 0x285u),
            _ => throw new InvalidOperationException("Unsupported capture API version"),
        };
        var code = readRva(layout.entry, 0x50);
        var prologue = Pattern.Parse(Prologue);
        if (code.Length != 0x50 || !prologue.Matches(code, 0))
            throw new InvalidOperationException("Capture transition prologue mismatch");
        void CheckCall(int displacementOffset, uint returnOffset)
        {
            if (code[displacementOffset] != 0xE8)
                throw new InvalidOperationException("Capture helper call opcode mismatch");
            var target = (long)layout.entry + returnOffset +
                         BitConverter.ToInt32(code, displacementOffset + 1);
            if (target != layout.helper)
                throw new InvalidOperationException("Capture helper target mismatch");
        }
        CheckCall(0x21, 0x26);
        CheckCall(0x2A, 0x2F);
        if (BitConverter.ToUInt32(code, 0x48) != checked((uint)(imageBase + layout.root)))
            throw new InvalidOperationException("Capture context global mismatch");
        var tail = readRva(layout.entry + layout.retOffset, 3);
        if (tail.Length != 3 || tail[0] != 0xC2 || tail[1] != 0x08 || tail[2] != 0x00)
            throw new InvalidOperationException("Capture transition RET8 mismatch");
        return imageBase + layout.entry;
    }
}

public static class KillApiResolver
{
    // Both repack versions share these entry bytes at the HP adjust function:
    // 8B 44 24 08 85 C0 F3 0F 10 4C 24 04 56 8B F1 F3 0F 10 46 04
    // F3 0F 11 46 08 F3 0F 58 C1 57 F3 0F 11 46 04 74
    private const string Entry =
        "8B 44 24 08 85 C0 F3 0F 10 4C 24 04 56 8B F1 F3 0F 10 46 04 " +
        "F3 0F 11 46 08 F3 0F 58 C1 57 F3 0F 11 46 04 74";

    public static nuint Resolve(string version, nuint imageBase, Func<uint, int, byte[]> readRva)
    {
        var entry = version switch
        {
            "1.12" => 0x3A3650u,
            "1.13" => 0x38CB30u,
            _ => throw new InvalidOperationException("Unsupported kill API version"),
        };
        var code = readRva(entry, 0x28);
        if (code.Length != 0x28 || !Pattern.Parse(Entry).Matches(code, 0))
            throw new InvalidOperationException("HP adjust entry contract mismatch");
        var tail = readRva(entry + 0xC6, 3);
        if (tail.Length != 3 || tail[0] != 0xC2 || tail[1] != 0x08 || tail[2] != 0x00)
            throw new InvalidOperationException("HP adjust RET8 mismatch");
        return imageBase + entry;
    }
}
