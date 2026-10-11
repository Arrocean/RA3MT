namespace RA3MT.Core.Target;

/// <summary>Central registry of the API resolvers the trainer knows about.
///
/// The value is not the list itself — it is that <see cref="ResolveCapabilities"/>
/// turns "walk the resolvers, log what verified, remember what did not" into one
/// place. Before this, <c>TrainerEngine.Attach</c> repeated a try/catch/log block
/// per bridge, and a failure message would silently drift out of sync with the
/// resolver it described.</summary>
public static class ApiResolverCatalog
{
    public const string Rank = "rank";
    public const string Capture = "capture";
    public const string Kill = "kill";
    public const string Spawn = "spawn";
    public const string SpawnSupport = "spawn-support";

    /// <summary>Resolve one optional capability: on success report what verified,
    /// on failure report why it was skipped without aborting the attach.</summary>
    public static bool TryResolve<T>(string capability, Func<T> resolve, Action<T> accept,
        Action<string> log)
    {
        try
        {
            var value = resolve();
            accept(value);
            return true;
        }
        catch (Exception ex)
        {
            log($"{capability}：校验失败，已跳过（{ex.Message}）");
            return false;
        }
    }

    /// <summary>Resolve a mandatory capability: failure propagates.</summary>
    public static T Resolve<T>(Func<T> resolve, Action<string> log, string capability)
    {
        var value = resolve();
        log($"{capability}：校验通过");
        return value;
    }
}
