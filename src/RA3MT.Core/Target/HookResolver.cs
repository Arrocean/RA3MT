using RA3MT.Core.Model;
using RA3MT.Core.Scan;

namespace RA3MT.Core.Target;

/// <summary>Resolves every hook site for a game version and verifies the bytes
/// under each site match the displaced instructions we intend to replace.</summary>
public sealed class HookResolution
{
    public required string HookId { get; init; }
    public required uint Rva { get; init; }
    /// <summary>Virtual address once the game base is known.</summary>
    public nuint Va => GameBase + Rva;
    public nuint GameBase { get; init; }
    public required byte[] Displaced { get; init; }
    public required string Method { get; init; }   // exact-rva | pattern | displaced-scan
    public string? Note { get; init; }
}

public static class HookResolver
{
    /// <param name="readRva">bytes at an RVA in the live target (or static image)</param>
    /// <param name="text">the full .text section bytes (RVA 0x1000 based)</param>
    public static Dictionary<string, HookResolution> ResolveAll(
        FeaturesData data, string version,
        Func<uint, int, byte[]> readRva, byte[] text, nuint gameBase,
        Action<string>? log = null)
    {
        var result = new Dictionary<string, HookResolution>();

        foreach (var (id, def) in data.Hooks)
        {
            if (!def.Rva.TryGetValue(version, out var rvaStr))
            {
                log?.Invoke($"[resolver] {id}: 无 {version} RVA，跳过");
                continue;
            }
            var rva = Convert.ToUInt32(rvaStr, 16);

            // Primary: exact RVA + displaced-byte verification.
            var expected = def.DisplacedBytes(version);
            var actual = readRva(rva, expected.Length);
            if (actual.AsSpan().SequenceEqual(expected))
            {
                result[id] = new HookResolution
                {
                    HookId = id, Rva = rva, GameBase = gameBase,
                    Displaced = expected, Method = "exact-rva",
                };
                log?.Invoke($"[resolver] {id}: RVA 0x{rva:X} 字节校验通过");
                continue;
            }

            // Fallback 1: cross-version AOB pattern from .text.
            if (def.Pattern != null)
            {
                var pat = Pattern.Parse(def.Pattern);
                var hits = pat.ScanAll(text)
                    .Select(h => 0x1000u + (uint)h + (uint)def.PatternSiteOffset)
                    .ToList();
                if (hits.Count == 1 && readRva(hits[0], expected.Length).AsSpan().SequenceEqual(expected))
                {
                    result[id] = new HookResolution
                    {
                        HookId = id, Rva = hits[0], GameBase = gameBase,
                        Displaced = expected, Method = "pattern",
                        Note = $"静态 RVA 0x{rva:X} 失配，特征码重定位 0x{hits[0]:X}",
                    };
                    log?.Invoke($"[resolver] {id}: 静态 RVA 失配，特征码重定位 0x{hits[0]:X}");
                    continue;
                }
            }

            // A few displaced bytes or sibling proximity cannot prove the
            // object's semantics. Refuse relocation without unique context.
            log?.Invoke($"[resolver] {id}: !! 无法定位（静态 0x{rva:X} 字节失配且无后备命中）");
        }
        return result;
    }
}
