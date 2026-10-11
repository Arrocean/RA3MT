namespace RA3MT.Core.Features.Abstractions;

/// <summary>What a feature entry can do. Mirrors the <c>kind</c> field in
/// features.json ("toggle" | "action" | "pending").</summary>
public enum FeatureKind
{
    /// <summary>A persistent on/off switch (flag, stub mode or code patch).</summary>
    Toggle,

    /// <summary>A one-shot request (bridge submission, direct write, diagnostic).</summary>
    Action,

    /// <summary>Declared but not implemented; the UI renders it disabled.</summary>
    Pending,
}

/// <summary>Whether a feature can run against the attached game build.
/// Availability is decided when the catalog builds the feature, never by the UI.</summary>
public enum FeatureAvailability
{
    /// <summary>Runnable on the attached version.</summary>
    Ready,

    /// <summary>Runnable only when an optional bridge/API passed its resolver.</summary>
    NeedsBridge,

    /// <summary>Known feature, not implemented on any version.</summary>
    NotImplemented,

    /// <summary>Not supported by the attached game version.</summary>
    UnsupportedVersion,
}

/// <summary>Outcome of a toggle/action request. <see cref="Message"/> is empty on
/// success when no detail is worth logging.</summary>
public readonly record struct FeatureResult(bool Ok, string Message)
{
    public static readonly FeatureResult Success = new(true, "");
    public static FeatureResult Succeeded(string message) => new(true, message);
    public static FeatureResult Failure(string message) => new(false, message);

    // (bool, string) tuples are the historical contract of TrainerEngine; these
    // keep the migration mechanical.
    public static implicit operator FeatureResult((bool ok, string msg) t) => new(t.ok, t.msg);

    public void Deconstruct(out bool ok, out string message)
    {
        ok = Ok;
        message = Message;
    }
}
