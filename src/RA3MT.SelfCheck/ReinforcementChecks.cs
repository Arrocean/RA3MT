using RA3MT.Core.Model;

namespace RA3MT.SelfCheck;

/// <summary>Checks the embedded reinforcement-code table: it loads, the hash
/// values match the ones verified live against the running game, and all
/// three resolution paths (hex code / internal name / localized name) work.
/// Run: SelfCheck reinforcetest</summary>
public static class ReinforcementChecks
{
    public static void Run()
    {
        var catalog = ReinforcementCatalog.Default;
        var cases = 0;

        if (catalog.Entries.Count < 100)
            throw new Exception($"table suspiciously small: {catalog.Entries.Count} entries");
        foreach (var expectCategory in new[] { "盟军", "苏军", "升阳帝国" })
            if (catalog.Categories.All(c => c.Name != expectCategory))
                throw new Exception($"category '{expectCategory}' missing");
        cases++;

        // hashes verified live against the running game (memory: v18e/v32)
        var known = new (string name, uint hash)[]
        {
            ("AlliedMCV", 0x28DA574E),
            ("SovietMCV", 0xAF4C0DA5),
            ("JapanMCV", 0x1C2EF767),
            ("JapanCommandoTech1", 0x6586A5A0),
        };
        foreach (var (name, hash) in known)
        {
            if (!catalog.TryResolve(name, out var got, out var entry) || got != hash)
                throw new Exception($"{name} resolved 0x{got:X8}, expected 0x{hash:X8}");
            if (entry == null) throw new Exception($"{name} resolved without a table entry");
        }
        cases += known.Length;

        // every entry's code round-trips back to itself
        foreach (var e in catalog.Entries)
        {
            if (!catalog.TryResolve(e.Code, out var hash, out _) || hash != e.Hash)
                throw new Exception($"{e.Name} code {e.Code} does not round-trip");
            if (string.IsNullOrWhiteSpace(e.Zh)) throw new Exception($"{e.Name} has no localized name");
        }
        cases++;

        // localized-name resolution (the picker may paste it) and search.
        // Internal names are semantic ("SovietAntiVehicleVehicleTech3"), so
        // English community nicknames ("Apocalypse") are not search keys —
        // the localized names are.
        if (!catalog.TryResolve("維和步兵", out var zhHash, out _) || zhHash != 0x139CBC97)
            throw new Exception("localized name '維和步兵' did not resolve to the peacekeeper hash");
        if (!catalog.TryResolve("天啟坦克", out var apocHash, out _) || apocHash != 0x9E45383C)
            throw new Exception("localized name '天啟坦克' did not resolve to the apocalypse hash");
        if (catalog.Search("坦克").Count() == 0)
            throw new Exception("search '坦克' returned nothing");
        if (catalog.Search("so vietmcv".Replace(" ", "").ToUpperInvariant()).Count() == 0)
            throw new Exception("case-insensitive internal-name search failed");
        cases++;

        // community-guide raw hex still resolves (no table entry required)
        if (!catalog.TryResolve("0x6586A5A0", out var raw, out _))
            throw new Exception("raw hex code with 0x prefix rejected");
        cases++;

        Console.WriteLine($"PASS {cases} reinforcement catalog checks " +
                          $"({catalog.Entries.Count} entries, " +
                          $"{string.Join("/", catalog.Categories.Select(c => $"{c.Name} {c.Items.Count}"))})");
    }
}
