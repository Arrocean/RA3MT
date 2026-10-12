using System.Windows;

namespace RA3MT.UI;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        // Distribution hygiene: old self-extraction caches would otherwise
        // accumulate in %TEMP% forever (see SingleFileCache). Best-effort and
        // silent — never blocks startup.
        try
        {
            SingleFileCache.CleanStale();
        }
        catch
        {
            // hygiene only
        }
        base.OnStartup(e);
    }
}
