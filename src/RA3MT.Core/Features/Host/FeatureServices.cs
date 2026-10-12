using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Model;
using RA3MT.Core.Memory;

namespace RA3MT.Core.Features.Host;

/// <summary>A capability a feature may depend on. Services are identified by type
/// and looked up at run time, so a feature declares what it needs
/// (<see cref="IFeatureServices.Get{T}"/>) instead of holding a reference to the
/// whole engine. Adding a capability therefore adds one service class rather than
/// widening an interface that every feature already implements against.</summary>
public interface IFeatureService
{
    /// <summary>Whether this service can be used right now (e.g. a bridge is
    /// installed, the game has a match loaded).</summary>
    bool IsAvailable { get; }
}

/// <summary>Per-session service lookup handed to every feature state.</summary>
public interface IFeatureServices
{
    /// <summary>Get a service, or null when it is not available for this session.</summary>
    T? Get<T>() where T : class, IFeatureService;

    /// <summary>Get a service that the feature cannot work without.</summary>
    T Require<T>() where T : class, IFeatureService =>
        Get<T>() ?? throw new InvalidOperationException($"功能依赖的服务 {typeof(T).Name} 不可用");
}

public sealed class FeatureServiceRegistry : IFeatureServices
{
    private readonly Dictionary<Type, IFeatureService> _byType = [];

    public FeatureServiceRegistry Register<T>(T service) where T : class, IFeatureService
    {
        _byType[typeof(T)] = service;
        return this;
    }

    public T? Get<T>() where T : class, IFeatureService =>
        _byType.TryGetValue(typeof(T), out var service) ? service as T : null;

    public IReadOnlyCollection<IFeatureService> All => _byType.Values;
}

/// <summary>Engine-side surface a feature state talks to: logging, change
/// notification and the raw memory accessor. Deliberately minimal — anything more
/// specific belongs in a service.</summary>
public sealed class FeatureHost
{
    public required Action<string> Log { get; init; }
    public required Action NotifyStateChanged { get; init; }
    public required IInjectionMemory Memory { get; init; }
    public required IFeatureServices Services { get; init; }
    public required ISymbols Symbols { get; init; }
}
