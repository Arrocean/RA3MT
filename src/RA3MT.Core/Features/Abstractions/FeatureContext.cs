using RA3MT.Core.Memory;

namespace RA3MT.Core.Features.Abstractions;

/// <summary>Immutable facts about the attached game process. Created once per
/// attach; never mutated afterwards, so features can capture it freely.</summary>
public sealed class SessionSnapshot
{
    public required IInjectionMemory Memory { get; init; }

    /// <summary>"1.12" or "1.13".</summary>
    public required string Version { get; init; }

    public required nuint ImageBase { get; init; }

    public required int Pid { get; init; }

    public required string ProcessPath { get; init; }

    public required int ResolvedSites { get; init; }

    public required int TotalSites { get; init; }

    /// <summary>Base address + RVA helper; the only place the image-base
    /// arithmetic should live.</summary>
    public nuint Va(uint rva) => ImageBase + rva;
}

/// <summary>What a feature is handed at creation time. Deliberately narrow: a
/// feature must not be able to reach the engine, the UI or other features.</summary>
public sealed class FeatureContext
{
    public required SessionSnapshot Session { get; init; }

    public required ISymbols Symbols { get; init; }

    /// <summary>The features.json model. Features need it for version-specific
    /// constants and their own private patch offsets.</summary>
    public required Model.FeaturesData Data { get; init; }

    /// <summary>Logging, change notification, memory and service lookup. Features
    /// go through this instead of holding a reference to the engine.</summary>
    public required Host.FeatureHost Host { get; init; }

    /// <summary>Written to the trainer log panel.</summary>
    public Action<string> Log => Host.Log;

    public IInjectionMemory Memory => Session.Memory;
    public string Version => Session.Version;
    public nuint ImageBase => Session.ImageBase;
}
