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

    /// <summary>Argument input shown for features that declare one. Everything the
    /// card needs comes from the feature definition, so the view model has no
    /// per-feature knowledge.</summary>
    public bool NeedsCode => Def.Arg?.NeedsText == true;
    public string ArgLabel => Def.Arg?.Label ?? "";
    public string ArgPlaceholder => Def.Arg?.Placeholder ?? "";

    /// <summary>True when the argument has a named suggestion source (the
    /// picker button shows next to the text box).</summary>
    public bool HasPicker => NeedsCode && !string.IsNullOrEmpty(Def.Arg?.Suggest);
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
        Icon = string.IsNullOrEmpty(def.Icon) ? "🔧" : def.Icon;
        Execute = new RelayCommand(_ =>
        {
            var (ok, msg) = _main.Engine.ExecuteAction(Def.Id, ResolveArgument());
            _main.Log(ok
                ? $"✓ {Def.Name} 已执行"
                : $"⚠ {Def.Name}: {(msg.Length > 0 ? msg : "执行失败")}");
        }, _ => _main.Attached && IsEnabled);
    }

    /// <summary>The action argument: typed text for a "code" argument, the declared
    /// fixed value for a "choice", empty otherwise.</summary>
    private string ResolveArgument() => Def.Arg switch
    {
        null => "",
        { NeedsText: true } => CodeText,
        var arg => arg.Value,
    };

    public void SyncFromEngine() => Set(ref _isOn, _main.Engine.IsOn(Def.Id), nameof(IsOn));

}

public sealed class FeatureGroupVM
{
    public string Name { get; init; } = "";
    public ObservableCollection<FeatureVM> Items { get; } = new();
}

public sealed class MainVM : ObservableObject
{
    /// <summary>Single source of truth for the displayed version. Scheme
    /// (from v261013): date + per-day sequence — vYYMMDD-N, N counts the
    /// releases of that calendar day.</summary>
    public const string AppVersion = "v261013-9";
    public string BannerText => $"{AppVersion} · 现代重制版";

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

    /// <summary>True while we asked Steam to launch the game and are polling
    /// for the process to auto-attach (WeMod-style single button).</summary>
    public bool WaitingForGame
    {
        get => _waitingForGame;
        private set
        {
            if (Set(ref _waitingForGame, value))
            {
                Raise(nameof(AttachChipText));
                Raise(nameof(StartButtonText));
            }
        }
    }
    private bool _waitingForGame;
    private CancellationTokenSource? _waitCts;

    public string Version { get => _version; private set => Set(ref _version, value); }
    public string VersionText => Version == "1.12ea" ? "1.12 EA原版" : Version;
    public int Pid { get => _pid; private set => Set(ref _pid, value); }
    public int Resolved { get => _resolved; private set => Set(ref _resolved, value); }
    public int TotalFeatures { get; private set; }
    public int TotalSites { get; private set; }
    public int HotkeyCount { get; private set; }

    public int EnabledCount => Engine.ToggleState.Count(kv => kv.Value);
    public string PidText => Attached ? Pid.ToString() : "—";
    public string AttachChipText => Engine.RecoveryRequired ? "挂钩恢复未完成"
        : Attached ? "✓ 已附加游戏进程"
        : WaitingForGame ? "已请求启动 · 等待游戏进程中"
        : "未检测到进程 · 点击「开始游戏」";
    public string StartButtonText => Attached ? "脱离进程"
        : WaitingForGame ? "取消等待"
        : "开始游戏";
    public string AttachButtonText => StartButtonText;
    public string ProcessStateText => Engine.RecoveryRequired ? "恢复失败" : Attached ? "已附加"
        : WaitingForGame ? "等待中" : "未附加";
    public string SiteCheckText => Engine.RecoveryRequired ? "功能已禁用，请重试脱离" : Attached
        ? $"挂钩点 {Resolved}/{TotalSites} 校验通过"
        : $"支持 1.12 / 1.13 · {TotalSites} 个挂钩点";

    /// <summary>WeMod 式单键：游戏在跑就直接附加；没在跑就请求 Steam 启动并
    /// 后台轮询进程，出现后自动附加；已附加时点击则脱离。</summary>
    public ICommand StartCmd { get; }
    public ICommand AttachCmd => StartCmd;   // kept for compatibility with old bindings
    public ICommand DetachCmd { get; }

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

        StartCmd = new RelayCommand(_ =>
        {
            if (Attached)
            {
                Engine.Detach();
                Log("已脱离。");
                return;
            }
            if (WaitingForGame)
            {
                CancelWait("已取消等待游戏启动。");
                return;
            }
            TryStartOrAttach();
        }, _ => !Engine.RecoveryRequired || Attached);
        DetachCmd = new RelayCommand(_ =>
        {
            Engine.Detach();
            Log("已脱离。");
        }, _ => Attached);

        Log($"RA3 Trainer 现代重制版 {AppVersion} 就绪 — 支持 1.12 / 1.13（{TotalFeatures} 项功能，{Engine.Data.Hooks.Count} 个挂钩点）");
        if (SingleFileCache.FreedBytes > 0)
            Log($"已清理旧版本运行缓存 {SingleFileCache.FreedBytes / 1048576.0:F1} MB（%TEMP%\\.net，避免版本更替累积占用）");
        Log("提示：点击「开始游戏」会自动启动游戏并附加；游戏已在运行时点击则直接附加。");
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

    /// <summary>Attach when the game is already running; otherwise ask Steam
    /// to launch it and poll quietly until the process shows up.</summary>
    private void TryStartOrAttach()
    {
        if (Engine.ProbeGameRunning())
        {
            TryAttach();
            return;
        }
        try
        {
            Process.Start(new ProcessStartInfo("steam://rungameid/17480") { UseShellExecute = true });
            Log("已请求 Steam 启动红警3（appid 17480）— 检测到游戏后将自动附加…");
        }
        catch
        {
            Log("✗ 无法通过 Steam 启动（appid 17480），请手动启动游戏后再点「开始游戏」。");
            return;
        }
        WaitingForGame = true;
        _waitCts = new CancellationTokenSource();
        var token = _waitCts.Token;
        _ = Task.Run(() => WaitAndAttachAsync(token));
    }

    private async Task WaitAndAttachAsync(CancellationToken token)
    {
        try
        {
            for (var i = 0; i < 150 && !token.IsCancellationRequested; i++)   // 2s x 150 = 5 min
            {
                await Task.Delay(2000, token);
                if (!Engine.ProbeGameRunning()) continue;
                WaitingForGame = false;
                System.Windows.Application.Current?.Dispatcher.BeginInvoke(TryAttach);
                return;
            }
            if (!token.IsCancellationRequested)
            {
                WaitingForGame = false;
                Log("✗ 等待超时：5 分钟内未检测到游戏进程，请手动点「开始游戏」重试。");
            }
        }
        catch (OperationCanceledException)
        {
            // user cancelled — state already reset by CancelWait
        }
    }

    private void CancelWait(string message)
    {
        _waitCts?.Cancel();
        _waitCts = null;
        WaitingForGame = false;
        Log(message);
    }

    private void OnStateChanged()
    {
        Attached = Engine.Attached;
        Version = Engine.Attached ? Engine.Version : "—";
        Pid = Engine.Pid;
        Resolved = Engine.ResolvedSites;
        Raise(nameof(AttachChipText));
        Raise(nameof(AttachButtonText));
        Raise(nameof(StartButtonText));
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
            while (LogLines.Count > 2000) LogLines.RemoveAt(0);
            if (IsErrorLine(line))
                ErrorLogged?.Invoke();
        });
    }

    /// <summary>静默日志只在出错时弹窗：这些行意味着功能与预期不符
    /// （地址校验未通过/桥拒绝/找不到进程等），其余全部留在后台缓冲。</summary>
    public static bool IsErrorLine(string line) =>
        line.Contains("  ⚠") || line.Contains("  ✗")
        || line.Contains("失败") || line.Contains("未通过") || line.Contains("异常")
        || line.Contains("找不到") || line.Contains("未找到") || line.Contains("不可用")
        || line.Contains("被校验拒绝") || line.Contains("无法附加") || line.Contains("未消费");

    /// <summary>每条错误日志进入缓冲时触发（UI 线程）；弹窗窗口自行去重。</summary>
    public event Action? ErrorLogged;
}
