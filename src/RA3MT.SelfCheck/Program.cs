using RA3MT.Core.Engine;
using RA3MT.Core.Model;
using RA3MT.Core.Scan;
using RA3MT.Core.Target;

// stub-dump mode: emit every MasterCode stub to a folder (for offline
// disassembly verification)
if (args.Length == 2 && args[0] == "stubdump")
{
    Directory.CreateDirectory(args[1]);
    var fakeBase = 0x40000000u;   // synthetic MasterCode block VA
    var fakeRoot = 0x400000u;     // synthetic player-root VA
    var fakeSite = 0x452100u;     // synthetic site VA; siteEnd = site+displacedLen
    foreach (var (id, def) in FeaturesData.LoadEmbedded().Hooks)
    {
        var stubId = def.Stub ?? id;
        if (!StubGen.Handles(stubId)) continue;
        var siteEnd = fakeSite + (uint)def.DisplacedLen;
        var code = StubGen.Emit(stubId, fakeBase + MasterCode.StubArea, siteEnd, fakeBase, fakeRoot);
        File.WriteAllBytes(Path.Combine(args[1], $"{id}.bin"), code);
        File.WriteAllText(Path.Combine(args[1], $"{id}.meta"),
            $"stubVa=0x{fakeBase + MasterCode.StubArea:X}\nsiteEnd=0x{siteEnd:X}\nlen={code.Length}\n");
        Console.WriteLine($"{id,-14} {code.Length} bytes -> {id}.bin");
    }
    return 0;
}

var data = FeaturesData.LoadEmbedded();

var dataDir = args.Length > 0 ? args[0] : TrainerGameDataDir();
if (dataDir == null)
{
    Console.Error.WriteLine("未找到游戏 Data 目录，请传入路径：SelfCheck <...\\Data>");
    return 2;
}
Console.WriteLine($"游戏目录: {dataDir}\n");

var versions = new[] { "1.12", "1.13" };
var allOk = true;
var grandTotal = 0;
var grandOk = 0;

foreach (var ver in versions)
{
    var gamePath = Path.Combine(dataDir, $"ra3_{ver}.game");
    if (!File.Exists(gamePath))
    {
        Console.WriteLine($"== {ver} == 文件不存在: {gamePath}");
        allOk = false;
        continue;
    }
    Console.WriteLine($"== {ver} == {Path.GetFileName(gamePath)} ({new FileInfo(gamePath).Length / 1024 / 1024} MB)");
    var img = new StaticImage(gamePath);

    foreach (var (id, def) in data.Hooks.OrderBy(kv => kv.Value.Rva[ver], StringComparer.OrdinalIgnoreCase))
    {
        grandTotal++;
        var rva = def.RvaFor(ver);
        var expected = def.DisplacedBytes();
        var actual = img.GetRva(rva, def.DisplacedLen);

        var ok = actual.AsSpan().SequenceEqual(expected);
        var line = ok ? "  ✓ " : "  ✗ ";
        line += $"{id,-14} rva=0x{rva:X6}  displaced={ToHex(actual)}";
        if (!ok) line += $"  期望 {ToHex(expected)}";

        // pattern cross-check
        string? patNote = null;
        if (def.Pattern != null)
        {
            var pat = Pattern.Parse(def.Pattern);
            var text = img.SectionBytes(0x1000).ToArray();
            var hits = pat.ScanAll(text)
                .Select(h => 0x1000 + (uint)h + (uint)def.PatternSiteOffset)
                .ToList();
            if (hits.Count == 1 && hits[0] == rva)
                patNote = $"特征码唯一命中 ✓";
            else
            {
                patNote = hits.Count == 0
                    ? $"特征码 0 命中!"
                    : $"特征码 {hits.Count} 命中 ({string.Join(",", hits.Take(3).Select(h => $"0x{h:X}"))}...)";
                if (ok) patNote += "（RVA 字节校验通过，特征码仅供参考）";
            }
        }
        if (ok) grandOk++;
        else allOk = false;
        Console.WriteLine(line);
        if (patNote != null) Console.WriteLine($"        · {patNote}");
    }

    // player-root global access-pattern check
    var rootRva = data.Globals.PlayerRoot.RvaFor(ver);
    var rootAbs = 0x400000 + rootRva;
    var text2 = img.SectionBytes(0x1000).ToArray();
    var found = false;
    Span<byte> needle = stackalloc byte[10];
    foreach (var prefix in new[] { new byte[] { 0x8B, 0x0D }, new byte[] { 0xA1 }, new byte[] { 0x8B, 0x1D } })
    {
        for (var i = 0; i < text2.Length - 16 && !found; i++)
        {
            var match = true;
            for (var k = 0; k < prefix.Length; k++)
                if (text2[i + k] != prefix[k]) { match = false; break; }
            if (!match) continue;
            var disp = BitConverter.ToUInt32(text2, i + prefix.Length);
            if (disp != rootAbs) continue;
            // followed within 8 bytes by 'mov reg,[reg+28]' (8B 4x/5x/6x/7x 28)
            for (var j = i + prefix.Length + 4; j < Math.Min(i + prefix.Length + 10, text2.Length - 2); j++)
                if (text2[j] == 0x8B && (text2[j + 1] & 0xC7) == 0x40 && text2[j + 2] == 0x28)
                { found = true; break; }
        }
        if (found) break;
    }
    Console.WriteLine(found
        ? $"  ✓ 玩家索引全局 [root+28]: 0x{rootRva:X} 访问模式在 .text 中确认"
        : $"  ⚠ 玩家索引全局 0x{rootRva:X} 未找到访问模式（需进游戏验证）");
    Console.WriteLine();
}

Console.WriteLine("＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝");
Console.WriteLine($"挂钩点校验: {grandOk}/{grandTotal} 通过   总体: {(allOk ? "✓ 全部通过" : "✗ 存在失配")}");
return allOk ? 0 : 1;

static string? TrainerGameDataDir()
{
    foreach (var steam in new[] {
                 Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Steam"),
                 @"D:\Steam", @"E:\Steam", @"C:\Steam" })
    {
        var vdf = Path.Combine(steam, "steamapps", "libraryfolders.vdf");
        var roots = new List<string> { steam };
        if (File.Exists(vdf))
            foreach (var line in File.ReadAllLines(vdf))
                if (line.TrimStart().StartsWith("\"path\""))
                    roots.Add(line.Split('"')[3].Replace(@"\\", "/"));
        foreach (var r in roots)
        {
            var d = Path.Combine(r, "steamapps", "common", "Command and Conquer Red Alert 3", "Data");
            if (File.Exists(Path.Combine(d, "ra3_1.13.game"))) return d;
        }
    }
    return null;
}

static string ToHex(byte[] b) => string.Join(" ", b.Select(x => x.ToString("X2")));
