using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Windows.Input;
using RA3MT.Core.Features;
using RA3MT.Core.Model;

namespace RA3MT.UI.ViewModels;

/// <summary>One feature card in the UI.</summary>
public sealed class FeatureVM : ObservableObject
{
    private readonly MainVM _main;
    private bool _isOn;

    public FeatureDef Def { get; }
    public string Id => Def.Id;
    public string Name => Def.Name;
    public string Group => Def.Group;
    public string Desc => Def.Desc;
    public string Hotkey => Def.Hotkey;
    public string Icon { get; }
    public bool IsToggle => Def.Kind == "toggle";
    public bool IsAction => Def.Kind == "action";
    public bool IsPending => Def.Kind == "pending";
    public bool IsEnabled => Def.Kind != "pending";
    public bool HasHotkey => !string.IsNullOrEmpty(Def.Hotkey);

    public bool IsOn
    {
        get => _isOn;
        set
        {
            if (value == _isOn) return;
            var (ok, msg) = _main.Engine.SetToggle(Def.Id, value);
            if (ok)
                _isOn = value;
            else
                _main.Log($"⚠ {Def.Name} 切换失败: {msg}");
            Raise();
            _main.RaiseEnabled();
        }
    }

    /// <summary>战场增援代码输入（仅 reinforce_code 卡片显示输入框）。</summary>
    public bool NeedsCode => Def.Id == "reinforce_code";
    private string _codeText = "";
    public string CodeText
    {
        get => _codeText;
        set => Set(ref _codeText, value);
    }

    public ICommand Execute { get; }

    public FeatureVM(FeatureDef def, MainVM main)
    {
        Def = def;
        _main = main;
        Icon = IconFor(def);
        Execute = new RelayCommand(_ =>
        {
            var arg = Def.Id switch
            {
                "reinforce_code" => CodeText,
                "mcv_allied" => "allied",
                "mcv_soviet" => "soviet",
                "mcv_japan" => "japan",
                _ => "",
            };
            var (ok, msg) = _main.Engine.ExecuteAction(Def.Id, arg);
            _main.Log(ok
                ? $"✓ {Def.Name} 已执行"
                : $"⚠ {Def.Name}: {(msg.Length > 0 ? msg : "执行失败")}");
        }, _ => _main.Attached && IsEnabled);
    }

    public void SyncFromEngine() => Set(ref _isOn, _main.Engine.IsOn(Def.Id), nameof(IsOn));

    private static string IconFor(FeatureDef d) => d.Id switch
    {
        "money" => "💰",
        "power" => "⚡",
        "scpoints" => "🎖",
        "allproto" => "🔓",
        "fastbuild" => "🏗",
        "instantready" => "❄",
        "freezeenemy" => "🚫",
        "cooldown" => "⏱",
        "revealmap" => "🗺",
        "zoomlimit" => "🔍",
        "xp999" => "⭐",
        "ammo" => "💣",
        "instadone" => "⏩",
        "sel_lv" => "🌟",
        "sel_speed" => "🏃",
        "sel_speed2" => "🏃‍♀️",
        "sel_freeze" => "🧊",
        "sel_freeze2" => "🧊",
        "sel_hpmax" => "❤️",
        "sel_hpmin" => "💀",
        "sel_hpnormal" => "🩹",
        "sel_capture" => "🏹",
        "sel_destroy" => "☠️",
        "threat_max" => "🔺",
        "threat_zero" => "🔻",
        "threat_normal" => "↩️",
        "oremine" => "⛏",
        "sel_copy" => "📋",
        "mcv_allied" => "🛻",
        "mcv_soviet" => "🚚",
        "mcv_japan" => "🚛",
        "reinforce_code" => "📡",
        _ => "🔧",
    };
}

public sealed class FeatureGroupVM
{
    public string Name { get; init; } = "";
    public ObservableCollection<FeatureVM> Items { get; } = new();
}

public sealed class MainVM : ObservableObject
{
    public TrainerEngine Engine { get; } = new();
    public ObservableCollection<FeatureGroupVM> Groups { get; } = new();
    public ObservableCollection<string> LogLines { get; } = new();

    private bool _attached;
    private string _version = "—";
    private int _pid;
    private int _resolved;

    public bool Attached
    {
        get => _attached;
        private set { Set(ref _attached, value); Raise(nameof(NotAttached)); }
    }

    public bool NotAttached => !Attached;
    public string Version { get => _version; private set => Set(ref _version, value); }
    public int Pid { get => _pid; private set => Set(ref _pid, value); }
    public int Resolved { get => _resolved; private set => Set(ref _resolved, value); }
    public int TotalFeatures { get; private set; }
    public int TotalSites { get; private set; }
    public int HotkeyCount { get; private set; }

    public int EnabledCount => Engine.ToggleState.Count(kv => kv.Value);
    public string PidText => Attached ? Pid.ToString() : "—";
    public string AttachChipText => Engine.RecoveryRequired ? "挂钩恢复未完成" : Attached ? "✓ 已附加游戏进程" : "未检测到进程 · 请先启动游戏";
    public string AttachButtonText => Attached ? "脱离进程" : "附加进程";
    public string ProcessStateText => Engine.RecoveryRequired ? "恢复失败" : Attached ? "已附加" : "未附加";
    public string SiteCheckText => Engine.RecoveryRequired ? "功能已禁用，请重试脱离" : Attached
        ? $"挂钩点 {Resolved}/{TotalSites} 校验通过"
        : $"支持 1.12 / 1.13 · {TotalSites} 个挂钩点";

    public ICommand AttachCmd { get; }
    public ICommand DetachCmd { get; }
    public ICommand LaunchCmd { get; }

    public MainVM()
    {
        Engine.Log += Log;
        Engine.StateChanged += OnStateChanged;

        foreach (var g in Engine.Data.Features.GroupBy(f => f.Group))
        {
            var gv = new FeatureGroupVM { Name = g.Key };
            foreach (var f in g) gv.Items.Add(new FeatureVM(f, this));
            Groups.Add(gv);
        }
        TotalFeatures = Engine.Data.Features.Count;
        TotalSites = Engine.Data.Hooks.Count;
        HotkeyCount = Engine.Data.Features.Count(f =>
            !string.IsNullOrEmpty(f.Hotkey) && f.Kind != "pending");

        AttachCmd = new RelayCommand(_ =>
        {
            if (Attached) Engine.Detach();
            else TryAttach();
        });
        DetachCmd = new RelayCommand(_ =>
        {
            Engine.Detach();
            Log("已脱离。");
        }, _ => Attached);
        LaunchCmd = new RelayCommand(_ => TryLaunchGame(), _ => NotAttached);

        Log($"RA3 Trainer 现代重制版 v2.0 就绪 — 支持 1.12 / 1.13（{TotalFeatures} 项功能，{Engine.Data.Hooks.Count} 个挂钩点）");
        Log("提示：先启动红警3并进入主菜单，再点击「附加进程」。");
    }

    private void TryAttach()
    {
        try
        {
            Engine.Attach();
        }
        catch (Exception ex)
        {
            Log($"✗ 附加失败：{ex.Message}");
        }
    }

    private void TryLaunchGame()
    {
        try
        {
            Process.Start(new ProcessStartInfo("steam://rungameid/17480") { UseShellExecute = true });
            Log("已请求 Steam 启动红警3（appid 17480）…");
        }
        catch
        {
            Log("✗ 无法通过 Steam 启动（appid 17480），请手动启动游戏。");
        }
    }

    private void OnStateChanged()
    {
        Attached = Engine.Attached;
        Version = Engine.Attached ? Engine.Version : "—";
        Pid = Engine.Pid;
        Resolved = Engine.ResolvedSites;
        Raise(nameof(AttachChipText));
        Raise(nameof(AttachButtonText));
        Raise(nameof(ProcessStateText));
        Raise(nameof(SiteCheckText));
        Raise(nameof(PidText));
        foreach (var g in Groups)
            foreach (var f in g.Items)
                f.SyncFromEngine();
        Raise(nameof(EnabledCount));
    }

    public void RaiseEnabled() => Raise(nameof(EnabledCount));

    public void Log(string s)
    {
        var line = $"{DateTime.Now:HH:mm:ss}  {s}";
        System.Windows.Application.Current?.Dispatcher.BeginInvoke(() =>
        {
            LogLines.Add(line);
            while (LogLines.Count > 400) LogLines.RemoveAt(0);
        });
    }
}
