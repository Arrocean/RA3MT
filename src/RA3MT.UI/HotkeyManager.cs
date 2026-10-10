using System.Runtime.InteropServices;
using System.Windows.Interop;

namespace RA3MT.UI;

/// <summary>Global hotkey registration (RegisterHotKey) bound to the main window.</summary>
public sealed partial class HotkeyManager : IDisposable
{
    private const int WM_HOTKEY = 0x0312;
    private const uint MOD_ALT = 0x1, MOD_CONTROL = 0x2, MOD_SHIFT = 0x4, MOD_WIN = 0x8;

    private HwndSource? _src;
    private readonly Dictionary<int, (uint mod, uint vk, Action fire)> _map = new();
    private int _nextId = 1;

    /// <summary>Register a hotkey like "Ctrl+F1" / "Alt+-" / "Alt+PgUp".</summary>
    public bool Register(string hotkey, Action fire)
    {
        var (mod, vk) = Parse(hotkey);
        if (vk == 0) return false;
        var id = _nextId++;
        if (!RegisterHotKey(_src?.Handle ?? IntPtr.Zero, id, mod, vk))
            return false;
        _map[id] = (mod, vk, fire);
        return true;
    }

    public void Attach(HwndSource src)
    {
        _src = src;
        src.AddHook(WndProc);
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg != WM_HOTKEY) return IntPtr.Zero;
        if (_map.TryGetValue(wParam.ToInt32(), out var entry))
        {
            entry.fire();
            handled = true;
        }
        return IntPtr.Zero;
    }

    private static (uint mod, uint vk) Parse(string text)
    {
        uint mod = 0;
        uint vk = 0;
        foreach (var raw in text.Split('+', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
        {
            var p = raw.ToUpperInvariant();
            switch (p)
            {
                case "CTRL" or "CONTROL": mod |= MOD_CONTROL; continue;
                case "ALT": mod |= MOD_ALT; continue;
                case "SHIFT": mod |= MOD_SHIFT; continue;
                case "WIN": mod |= MOD_WIN; continue;
                case "PGUP" or "PAGEUP": vk = 0x21; continue;
                case "PGDN" or "PAGEDOWN": vk = 0x22; continue;
                case "DEL" or "DELETE": vk = 0x2E; continue;
            }
            if (p.Length == 1)
            {
                var c = p[0];
                if (c is >= 'A' and <= 'Z') { vk = (uint)c; continue; }
                if (c is >= '0' and <= '9') { vk = (uint)c; continue; }
                vk = c switch
                {
                    '-' => 0xBD, '=' => 0xBB, '[' => 0xDB, ']' => 0xDD,
                    '\\' => 0xDC, ';' => 0xBA, '\'' => 0xDE, ',' => 0xBC,
                    '.' => 0xBE, '/' => 0xBF, '`' => 0xC0,
                    _ => 0,
                };
            }
            else if (p.StartsWith('F') && int.TryParse(p[1..], out var fn) && fn is >= 1 and <= 24)
            {
                vk = (uint)(0x6F + fn); // F1 = 0x70
            }
        }
        return (mod, vk);
    }

    public void Dispose()
    {
        foreach (var id in _map.Keys)
            UnregisterHotKey(_src?.Handle ?? IntPtr.Zero, id);
        _map.Clear();
    }

    [LibraryImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool RegisterHotKey(IntPtr hWnd, int id, uint mod, uint vk);

    [LibraryImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool UnregisterHotKey(IntPtr hWnd, int id);
}
