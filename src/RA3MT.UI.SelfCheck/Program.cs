using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using RA3MT.Core.Model;
using RA3MT.UI.ViewModels;

namespace RA3MT.UI.SelfCheck;

/// <summary>Exercise the real WPF bindings without opening games or installing hooks.</summary>
public static class Program
{
    [STAThread]
    public static int Main(string[] args)
    {
        var app = new App();
        app.InitializeComponent();
        var window = new MainWindow();
        var vm = (MainVM)window.DataContext;
        var root = (FrameworkElement)window.Content;
        root.Measure(new Size(1240, 840)); root.Arrange(new Rect(0, 0, 1240, 840)); root.UpdateLayout();
        var selector = Descendants(root).OfType<ListBox>().Single();
        var changes = 0;
        vm.GameChanged += () => changes++;
        for (var i = 0; i < 10; i++)
        {
            selector.SelectedIndex = 1;
            Check(vm.SelectedGame.Id == GameId.Uprising, "selector updates game");
            Check(vm.TotalFeatures == 36 && vm.TotalSites == 28, "Uprising counters");
            Check(vm.Groups.Single(g => g.Name == "挑战模式").Items.Count == 2, "exclusive cards");
            Check(vm.GameTitle.Contains("起义时刻") && vm.SupportedVersions.Contains("1.01"), "product labels");
            selector.SelectedIndex = 0;
            Check(vm.SelectedGame.Id == GameId.RedAlert3, "switch back");
            Check(vm.TotalFeatures == 34 && vm.TotalSites == 26, "RA3 counters");
            Check(!vm.Groups.Any(g => g.Name == "挑战模式"), "exclusive cards removed");
        }
        Check(changes == 20, "hotkey refresh notification per switch");
        selector.SelectedIndex = 1;
        root.Measure(new Size(1240, 840)); root.Arrange(new Rect(0, 0, 1240, 840)); root.UpdateLayout();
        var output = Path.GetFullPath(args.Length > 0 ? args[0] : "artifacts/uprising/ui-preview.png");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        var bitmap = new RenderTargetBitmap(1240, 840, 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(root);
        var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
        using (var file = File.Create(output)) png.Save(file);
        // Attaching disables product selection. WPF's stock ListBox template
        // paints its disabled background with the light Windows theme brush.
        selector.SetCurrentValue(UIElement.IsEnabledProperty, false);
        root.UpdateLayout();
        var disabled = new RenderTargetBitmap((int)Math.Ceiling(selector.ActualWidth),
            (int)Math.Ceiling(selector.ActualHeight), 96, 96, PixelFormats.Pbgra32);
        disabled.Render(selector);
        var pixels = new byte[disabled.PixelWidth * disabled.PixelHeight * 4];
        disabled.CopyPixels(pixels, disabled.PixelWidth * 4, 0);
        var whitePixels = Enumerable.Range(0, pixels.Length / 4).Count(i =>
            pixels[i * 4] > 245 && pixels[i * 4 + 1] > 245 && pixels[i * 4 + 2] > 245 && pixels[i * 4 + 3] > 245);
        Check(whitePixels == 0, $"disabled game selector must retain dark/transparent background; white pixels={whitePixels}");
        Check(vm.SelectedGame.Id == GameId.Uprising, "disabled selector retains selected game");
        var disabledPng = new PngBitmapEncoder(); disabledPng.Frames.Add(BitmapFrame.Create(disabled));
        using (var file = File.Create(Path.ChangeExtension(output, ".disabled.png"))) disabledPng.Save(file);
        selector.SetCurrentValue(UIElement.IsEnabledProperty, true);
        root.UpdateLayout();
        Check(selector.IsEnabled, "selection becomes available after detach");
        vm.Engine.Dispose();
        Console.WriteLine($"PASS WPF: 20 game switches; disabled selection retains dark background and current game; re-enable works. Preview: {output}");
        return 0;
    }

    private static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            yield return child;
            foreach (var descendant in Descendants(child)) yield return descendant;
        }
    }
    private static void Check(bool value, string name) { if (!value) throw new Exception(name); }
}
