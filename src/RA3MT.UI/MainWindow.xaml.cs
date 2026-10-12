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
    private LogWindow? _logWindow;

    public MainWindow()
    {
        InitializeComponent();
        DataContext = _vm;
        _vm.ErrorLogged += OnErrorLogged;   // 静默日志：仅在错误行出现时弹完整日志窗口
        // hotkey registration is deferred to OnSourceInitialized: RegisterHotKey
        // needs the real window handle — registering against IntPtr.Zero binds
        // the hotkeys to the thread queue where the WndProc hook never sees them
        // (that is why "21 registered" never fired).
    }

    private void RegisterHotkeys()
    {
        var ok = 0;
        foreach (var g in _vm.Groups)
        {
            foreach (var f in g.Items)
            {
                if (string.IsNullOrEmpty(f.Hotkey) || !f.IsEnabled) continue;
                FeatureVM feature = f;
                void Fire()
                {
                    if (!_vm.Attached) return;
                    if (feature.IsToggle)
                        feature.IsOn = !feature.IsOn;
                    else if (feature.IsAction)
                        feature.Execute.Execute(null);
                }
                var registered = _hotkeys.Register(f.Hotkey, () => Dispatcher.Invoke(Fire));
                if (!registered && !f.Hotkey.Contains('+'))
                {
                    // 裸功能键常被系统/其他程序占用（如 F12 的调试保留位）——自动回退 Ctrl+原键
                    var fallback = "Ctrl+" + f.Hotkey;
                    if (_hotkeys.Register(fallback, () => Dispatcher.Invoke(Fire)))
                    {
                        registered = true;
                        _vm.Log($"热键 {f.Hotkey} 被占用，{f.Name} 已改用 {fallback}");
                    }
                }
                if (registered) ok++;
                else _vm.Log($"⚠ 热键 {f.Hotkey}（{f.Name}）注册失败，可能被其他程序占用");
            }
        }
        _vm.Log($"全局热键已注册 {ok} 个。");
    }

    private void OnErrorLogged()
    {
        // 静默日志：只在出现错误行时弹一次完整日志窗口；已打开则仅激活置前。
        // 窗口 Owner=主窗口 → 随修改器关闭而关闭；缓冲在内存 → 退出即清空。
        if (_logWindow is null)
        {
            _logWindow = new LogWindow(_vm) { Owner = this };
            _logWindow.Closed += (_, _) => _logWindow = null;
            _logWindow.Show();
        }
        else
        {
            _logWindow.Activate();
        }
    }

    private void OnMinimize(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void OnClose(object sender, RoutedEventArgs e)
    {
        _vm.Engine.Detach();
        Close();
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
