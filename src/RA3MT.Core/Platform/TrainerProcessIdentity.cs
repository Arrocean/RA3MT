using System.Runtime.InteropServices;
using RA3MT.Core.Model;

namespace RA3MT.Core.Platform;

/// <summary>Unmanaged, readable process marker plus a public discovery mutex.
/// No ownership/waiting protocol: keep the mutex handle open until app exit.</summary>
public sealed class TrainerProcessIdentity : IDisposable
{
    private IntPtr _address;
    private Mutex? _mutex;
    public nuint Address => (nuint)_address;

    public TrainerProcessIdentity()
    {
        try
        {
            var pid = checked((uint)Environment.ProcessId);
            var record = TrainerIdentity.CreateRecord(TrainerIdentityKind.TrainerProcess, pid, pid);
            _address = Marshal.AllocHGlobal(record.Length);
            Marshal.Copy(record, 0, _address, record.Length);
            _mutex = new Mutex(false, TrainerIdentity.MutexName(Environment.ProcessId));
        }
        catch { Dispose(); throw; }
    }

    public void Dispose()
    {
        _mutex?.Dispose(); _mutex = null;
        if (_address == IntPtr.Zero) return;
        Marshal.FreeHGlobal(_address); _address = IntPtr.Zero;
    }
}
