using System.Windows;
using RA3MT.UI.ViewModels;

namespace RA3MT.UI;

/// <summary>错误时自动弹出的完整日志窗口。日志只活在内存里（MainVM.LogLines），
/// 本窗口随主窗口关闭而关闭，程序退出即清空——不落盘。</summary>
public partial class LogWindow : Window
{
    private readonly MainVM _vm;

    public LogWindow(MainVM vm)
    {
        _vm = vm;
        InitializeComponent();
        Refresh();
        _vm.LogLines.CollectionChanged += (_, _) => Refresh();
    }

    private void Refresh()
    {
        Text.Text = string.Join(Environment.NewLine, _vm.LogLines);
        Text.ScrollToEnd();
    }

    private void OnCopyAll(object sender, RoutedEventArgs e)
    {
        try { Clipboard.SetText(string.Join(Environment.NewLine, _vm.LogLines)); }
        catch { /* 剪贴板被其他程序占用时静默 */ }
    }
}
