using System.Windows;
using RA3MT.Core.Platform;

namespace RA3MT.UI;

public partial class App : Application
{
    private TrainerProcessIdentity? _identity;

    protected override void OnStartup(StartupEventArgs e)
    {
        try { _identity = new TrainerProcessIdentity(); }
        catch (Exception ex)
        {
            MessageBox.Show("无法创建公开识别标记，修改器未启动：" + ex.Message,
                "RA3 Trainer", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(1);
            return;
        }
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

    protected override void OnExit(ExitEventArgs e)
    {
        try { base.OnExit(e); }
        finally { _identity?.Dispose(); }
    }
}
