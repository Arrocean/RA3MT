using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using RA3MT.UI.ViewModels;

namespace RA3MT.UI;

public partial class MainWindow : Window
{
    private readonly MainVM _vm = new();
    private readonly HotkeyManager _hotkeys = new();
    private Dictionary<string, FeatureVM> _byId = new();

    public MainWindow()
    {
        InitializeComponent();
        DataContext = _vm;
        _vm.LogLines.CollectionChanged += (_, _) => Dispatcher.BeginInvoke(ScrollLogToEnd);
        // hotkey registration is deferred to OnSourceInitialized: RegisterHotKey
        // needs the real window handle — registering against IntPtr.Zero binds
        // the hotkeys to the thread queue where the WndProc hook never sees them
        // (that is why "21 registered" never fired).
    }

    private void RegisterHotkeys()
    {
        _byId = _vm.Groups.SelectMany(g => g.Items).ToDictionary(f => f.Id);
        var ok = 0;
        foreach (var g in _vm.Groups)
        {
            foreach (var f in g.Items)
            {
                if (string.IsNullOrEmpty(f.Hotkey) || !f.IsEnabled) continue;
                FeatureVM feature = f;
                var registered = _hotkeys.Register(f.Hotkey, () => Dispatcher.Invoke(() =>
                {
                    if (!_vm.Attached) return;
                    if (feature.IsToggle)
                        feature.IsOn = !feature.IsOn;
                    else if (feature.IsAction)
                        feature.Execute.Execute(null);
                }));
                if (registered) ok++;
                else _vm.Log($"⚠ 热键 {f.Hotkey}（{f.Name}）注册失败，可能被其他程序占用");
            }
        }
        _vm.Log($"全局热键已注册 {ok} 个。");
    }

    private void ScrollLogToEnd()
    {
        if (LogList.Items.Count > 0)
            LogList.ScrollIntoView(LogList.Items[^1]);
    }

    private void OnMinimize(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void OnClose(object sender, RoutedEventArgs e)
    {
        _vm.Engine.Detach();
        Close();
    }

    private void OnToggleLog(object sender, MouseButtonEventArgs e)
    {
        LogPanel.Visibility = LogPanel.Visibility == Visibility.Visible
            ? Visibility.Collapsed
            : Visibility.Visible;
    }

    private void OnClearLog(object sender, MouseButtonEventArgs e) => _vm.LogLines.Clear();

    private void OnCopyAllLogs(object sender, RoutedEventArgs e)
    {
        if (_vm.LogLines.Count == 0) return;
        Clipboard.SetText(string.Join(Environment.NewLine, _vm.LogLines));
        _vm.Log($"已复制 {_vm.LogLines.Count} 行日志到剪贴板");
    }

    private void OnCopyLogLine(object sender, RoutedEventArgs e)
    {
        if (sender is MenuItem { Parent: ContextMenu menu } && menu.PlacementTarget is TextBlock line)
        {
            Clipboard.SetText(line.Text);
            _vm.Log("已复制该行日志");
        }
    }

    protected override void OnPreviewKeyDown(KeyEventArgs e)
    {
        // Ctrl+C copies the selected log line (unless a text box owns the clipboard copy)
        if (e.Key == Key.C && Keyboard.Modifiers == ModifierKeys.Control &&
            Keyboard.FocusedElement is not TextBox &&
            LogList.SelectedItem is string selected)
        {
            Clipboard.SetText(selected);
            e.Handled = true;
        }
        base.OnPreviewKeyDown(e);
    }

    private void OnDiagClick(object sender, MouseButtonEventArgs e)
    {
        if (!_vm.Attached)
        {
            _vm.Log("⚠ 尚未附加游戏进程");
            return;
        }
        if (_byId.TryGetValue("diag", out var f))
            f.Execute.Execute(null);
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        _hotkeys.Attach((HwndSource)PresentationSource.FromVisual(this)!);
        RegisterHotkeys();   // now the handle exists, RegisterHotKey binds to this window
    }

    protected override void OnClosed(EventArgs e)
    {
        _hotkeys.Dispose();
        _vm.Engine.Dispose();
        base.OnClosed(e);
    }
}
