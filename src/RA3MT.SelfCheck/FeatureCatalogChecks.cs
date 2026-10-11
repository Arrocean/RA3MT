using RA3MT.Core.Features;
using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Model;

namespace RA3MT.SelfCheck;

/// <summary>Enforces the catalog invariant the refactor depends on: every feature
/// declared in features.json has exactly one implementation, ids are unique, and
/// every runnable feature produces a state object without an engine attached.
/// Run: SelfCheck featuretest</summary>
public static class FeatureCatalogChecks
{
    public static void Run()
    {
        var data = FeaturesData.LoadEmbedded();
        var cases = 0;

        // 1) one registry entry per declaration, no strays
        var registry = LegacyFeatureCatalog.Build(data);
        var missing = registry.MissingFrom(data);
        var unknown = registry.UnknownIn(data);
        if (missing.Count != 0)
            throw new Exception($"features.json declares {missing.Count} feature(s) with no implementation: " +
                                string.Join(", ", missing));
        if (unknown.Count != 0)
            throw new Exception($"registry has {unknown.Count} entry(ies) absent from features.json: " +
                                string.Join(", ", unknown));
        if (registry.Features.Count != data.Features.Count)
            throw new Exception($"registry size {registry.Features.Count} != declared {data.Features.Count}");
        cases++;

        // 2) ids unique and non-empty
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var f in data.Features)
        {
            if (string.IsNullOrWhiteSpace(f.Id)) throw new Exception("empty feature id");
            if (!seen.Add(f.Id)) throw new Exception($"duplicate feature id '{f.Id}'");
        }
        cases++;

        // 3) kind maps to a known FeatureKind and pending entries stay non-runnable
        foreach (var f in data.Features)
        {
            registry.TryGet(f.Id, out var feature);
            var expected = f.Kind switch
            {
                "toggle" => FeatureKind.Toggle,
                "action" => FeatureKind.Action,
                "pending" => FeatureKind.Pending,
                _ => throw new Exception($"feature '{f.Id}' has unknown kind '{f.Kind}'"),
            };
            if (feature.Kind != expected)
                throw new Exception($"feature '{f.Id}' kind mismatch: {feature.Kind} != {expected}");
            if (expected == FeatureKind.Toggle && string.IsNullOrEmpty(f.Flag) && f.Id != "build_anywhere")
                throw new Exception($"toggle '{f.Id}' has neither a flag nor a private patch");
            if (expected == FeatureKind.Action && string.IsNullOrEmpty(f.Action))
                throw new Exception($"action '{f.Id}' has no action id");
            cases++;
        }

        // 4) unbound state must fail closed, never throw
        var unbound = LegacyFeatureCatalog.Build(data);
        foreach (var f in unbound.Features.Where(x => x.Kind != FeatureKind.Pending))
        {
            var state = f.CreateState(new FeatureContext
            {
                Session = new SessionSnapshot
                {
                    Memory = null!, Version = "1.13", ImageBase = 0x400000, Pid = 0,
                    ProcessPath = "", ResolvedSites = 0, TotalSites = 0,
                },
                Symbols = null!,
                Data = data,
                Host = UnboundHost(),
            });
            var (toggleOk, _) = state.SetOn(true);
            if (toggleOk) throw new Exception($"unbound '{f.Id}' reported a successful toggle");
            var (actionOk, _) = state.Execute(null);
            if (actionOk) throw new Exception($"unbound '{f.Id}' reported a successful action");
            cases++;
        }

        // 5) hook references resolve to declared sites
        foreach (var f in data.Features)
        {
            foreach (var hook in f.Hooks)
            {
                if (!data.Hooks.ContainsKey(hook))
                    throw new Exception($"feature '{f.Id}' references undeclared hook '{hook}'");
                cases++;
            }
        }

        // 6) migration gate: every runnable feature must carry its own
        //    implementation. This is the check that keeps M5 from regressing —
        //    a feature that falls back to the engine's historical switch fails here.
        var stillDelegating = registry.Features
            .Where(f => f.Kind != FeatureKind.Pending && !f.IsMigrated)
            .Select(f => f.Id)
            .ToList();
        if (stillDelegating.Count != 0)
            throw new Exception($"{stillDelegating.Count} feature(s) still delegate to the engine: " +
                                string.Join(", ", stillDelegating));
        cases++;

        Console.WriteLine($"PASS {cases} feature catalog cases " +
                          $"({data.Features.Count} features, {data.Hooks.Count} hooks, ids unique, unbound states fail closed)");
    }

    /// <summary>Host with no services: what a feature sees when the catalog is built
    /// without an engine (offline checks).</summary>
    private static RA3MT.Core.Features.Host.FeatureHost UnboundHost() => new()
    {
        Log = _ => { },
        NotifyStateChanged = () => { },
        Memory = null!,
        Services = new RA3MT.Core.Features.Host.FeatureServiceRegistry(),
        Symbols = null!,
    };
}
