using System.IO;
using System.Reflection;

namespace RA3MT.UI;

/// <summary>Single-file extraction cache hygiene.
///
/// Every published build has a unique AssemblyName (the version is part of
/// the distribution name), and .NET's single-file host extracts the native
/// WPF dependencies into a fresh %TEMP%\.net\&lt;AssemblyName&gt;\&lt;bundle&gt; folder
/// for each distinct build — the folders are never deleted on exit, so
/// releases accumulate forever (measured: 34 MB after one day of testing).
///
/// On startup we delete the cache folders of every OTHER build of this
/// product family. The current build's folder is never touched, not even
/// its stale bundle subfolders: at startup some natives (D3DCompiler…)
/// are not LoadLibrary-locked yet, and deleting them crashes WPF when it
/// first renders — learned the hard way. Same-version rebuild leakage only
/// happens when the developer republishes an identical version number, so
/// users never hit it.</summary>
internal static class SingleFileCache
{
    private const string FamilyPrefix = "Red Alert 3 Modern Trainer";
    private const string DevName = "RA3MT.UI";

    /// <summary>Bytes freed by the last <see cref="CleanStale"/> call (logged
    /// by the view model once it is up).</summary>
    public static long FreedBytes { get; private set; }

    public static void CleanStale()
    {
        FreedBytes = 0;
        var root = Path.Combine(Path.GetTempPath(), ".net");
        if (!Directory.Exists(root))
            return;
        var current = Assembly.GetExecutingAssembly().GetName().Name;
        foreach (var appDir in Directory.EnumerateDirectories(root))
        {
            var name = Path.GetFileName(appDir);
            if (!IsFamily(name) || name == current)
                continue;
            TryDelete(appDir);
        }
    }

    private static bool IsFamily(string dirName) =>
        dirName.StartsWith(FamilyPrefix, StringComparison.OrdinalIgnoreCase)
        || dirName.Equals(DevName, StringComparison.OrdinalIgnoreCase);

    private static void TryDelete(string path)
    {
        try
        {
            FreedBytes += Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories)
                .Sum(f => new FileInfo(f).Length);
            Directory.Delete(path, recursive: true);
        }
        catch
        {
            // in-use bundle (this process) or racing cleanup — leave it be
        }
    }
}
