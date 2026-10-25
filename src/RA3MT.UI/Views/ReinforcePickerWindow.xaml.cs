using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using RA3MT.Core.Model;

namespace RA3MT.UI;

/// <summary>One picker row: an embedded table entry plus its category header
/// field (drives ListBox grouping and the template bindings).</summary>
public sealed class ReinforceRow
{
    public required string Category { get; init; }
    public required string Name { get; init; }
    public required string Zh { get; init; }
    public required string Code { get; init; }
    public required uint Hash { get; init; }
}

/// <summary>Searchable picker over the embedded reinforcement-code table.
/// Double-click / Enter / 选择 returns the picked row.</summary>
public partial class ReinforcePickerWindow : Window
{
    private readonly ObservableCollection<ReinforceRow> _rows = new();
    private readonly ICollectionView _view;

    public ReinforceRow? Selected => List.SelectedItem as ReinforceRow;

    public ReinforcePickerWindow(GameId game = GameId.RedAlert3)
    {
        InitializeComponent();
        foreach (var cat in ReinforcementCatalog.For(game).Categories)
            foreach (var row in cat.Items)
                _rows.Add(new ReinforceRow
                {
                    Category = cat.Name, Name = row.Name, Zh = row.Zh,
                    Code = row.Code, Hash = row.Hash,
                });
        _view = CollectionViewSource.GetDefaultView(_rows);
        _view.GroupDescriptions.Add(new PropertyGroupDescription(nameof(ReinforceRow.Category)));
        List.ItemsSource = _view;
    }

    private void OnSearchTextChanged(object sender, TextChangedEventArgs e)
    {
        var needle = SearchBox.Text;
        _view.Filter = string.IsNullOrWhiteSpace(needle)
            ? null
            : o => o is ReinforceRow r
                   && (r.Name.Contains(needle, StringComparison.OrdinalIgnoreCase)
                       || r.Zh.Contains(needle, StringComparison.OrdinalIgnoreCase));
    }

    private void OnItemDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (Selected is not null)
            DialogResult = true;
    }

    private void OnListKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && Selected is not null)
            DialogResult = true;
    }

    private void OnConfirm(object sender, RoutedEventArgs e)
    {
        if (Selected is null)
        {
            MessageBox.Show(this, "请先选择一个单位（可输入文字过滤）。", "选择增援单位",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        DialogResult = true;
    }
}
