using System.Diagnostics;
using RA3MT.Core.Platform;

namespace RA3MT.Core.Memory;

/// <summary>Read/write access to a foreign process's address space.
/// The trainer runs x86 and targets the 32-bit game, so all VAs fit in 32 bits.</summary>
public sealed class ProcessMemory : IDisposable
{
    private IntPtr _h;

    public ProcessMemory(int pid)
    {
        _h = NativeMethods.OpenProcess(NativeMethods.PROCESS_ALL_ACCESS, false, pid);
        if (_h == IntPtr.Zero)
            throw new InvalidOperationException(
                $"OpenProcess({pid}) failed (win32 {System.Runtime.InteropServices.Marshal.GetLastWin32Error()}). " +
                "请以管理员身份运行修改器。");
        Pid = pid;
    }

    public int Pid { get; }
    public bool IsClosed => _h == IntPtr.Zero;

    public byte[] Read(nuint addr, int size)
    {
        var buf = new byte[size];
        if (!NativeMethods.ReadProcessMemory(_h, addr, buf, (nuint)size, out var read))
            throw new InvalidOperationException($"ReadProcessMemory(0x{addr:X}) failed");
        if (read != (nuint)size)
            throw new InvalidOperationException($"ReadProcessMemory(0x{addr:X}) short read {read}/{size}");
        return buf;
    }

    public uint ReadU32(nuint addr) => BitConverter.ToUInt32(Read(addr, 4), 0);
    public float ReadF32(nuint addr) => BitConverter.ToSingle(Read(addr, 4), 0);

    public void Write(nuint addr, ReadOnlySpan<byte> data)
    {
        var buf = data.ToArray();
        if (!NativeMethods.WriteProcessMemory(_h, addr, buf, (nuint)buf.Length, out var written))
            throw new InvalidOperationException($"WriteProcessMemory(0x{addr:X}) failed");
        NativeMethods.FlushInstructionCache(_h, addr, (nuint)buf.Length);
    }

    public void WriteU32(nuint addr, uint value) => Write(addr, BitConverter.GetBytes(value));
    public void WriteF32(nuint addr, float value) => Write(addr, BitConverter.GetBytes(value));

    /// <summary>Allocate RWX memory in the target. Returns the base address.</summary>
    public nuint Alloc(nuint size, uint protect = NativeMethods.PAGE_EXECUTE_READWRITE)
    {
        var p = NativeMethods.VirtualAllocEx(_h, 0, size,
            NativeMethods.MEM_COMMIT | NativeMethods.MEM_RESERVE, protect);
        if (p == IntPtr.Zero)
            throw new InvalidOperationException("VirtualAllocEx failed");
        return (nuint)p;
    }

    public void Dispose()
    {
        if (_h != IntPtr.Zero)
        {
            NativeMethods.CloseHandle(_h);
            _h = IntPtr.Zero;
        }
        GC.SuppressFinalize(this);
    }

    /// <summary>Find the RA3 game process. Returns (pid, version, modulePath) or null.</summary>
    public static (int pid, string version, string modulePath)? FindGame(IEnumerable<string> moduleNames)
    {
        foreach (var p in Process.GetProcesses())
        {
            try
            {
                if (!p.ProcessName.StartsWith("ra3_1.", StringComparison.OrdinalIgnoreCase))
                    continue;
                string path;
                try { path = p.MainModule?.FileName ?? ""; } catch { continue; }
                foreach (var m in moduleNames)
                    if (Path.GetFileName(path).Equals(m, StringComparison.OrdinalIgnoreCase))
                        return (p.Id, VersionFromModule(m), path);
                // fallback: match by module enumeration
                foreach (ProcessModule? mod in p.Modules)
                {
                    if (mod == null) continue;
                    foreach (var m in moduleNames)
                        if (Path.GetFileName(mod.FileName).Equals(m, StringComparison.OrdinalIgnoreCase))
                            return (p.Id, VersionFromModule(m), mod.FileName);
                }
            }
            catch { /* access denied etc. */ }
        }
        return null;

        static string VersionFromModule(string module)
        {
            // "ra3_1.13.game" -> "1.13"
            var stem = Path.GetFileNameWithoutExtension(module); // ra3_1.13
            var idx = stem.IndexOf('_');
            return idx >= 0 ? stem[(idx + 1)..] : stem;
        }
    }
}
