using System.Buffers.Binary;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Xml.Linq;
using Microsoft.Win32.SafeHandles;
using RA3MT.Core.Engine;
using RA3MT.Core.Model;
using RA3MT.Core.Platform;

namespace RA3MT.SelfCheck;

public static class IdentityChecks
{
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern SafeProcessHandle OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ReadProcessMemory(SafeProcessHandle process, nuint address,
        [Out] byte[] bytes, nuint size, out nuint read);

    public static void Child()
    {
        using var identity = new TrainerProcessIdentity();
        Console.WriteLine($"{Environment.ProcessId} {identity.Address:X}");
        Console.Out.Flush();
        Console.ReadLine(); // test parent releases its own helper; no game involved
    }

    public static void Run()
    {
        var cases = 0;
        void Check(bool ok, string name) { if (!ok) throw new Exception(name); cases++; }
        Check(TrainerIdentity.ProjectId == "2A616556-4683-43AF-8863-359BF95B0FEE", "permanent project ID");
        Check(TrainerIdentity.MutexName(1234) == @"Local\RA3MT.Identity.2A616556-4683-43AF-8863-359BF95B0FEE.1234", "permanent discovery name");
        Check(TrainerIdentity.Checksum([]) == 2166136261u, "FNV-1a empty vector");
        Check(TrainerIdentity.Checksum("hello"u8) == 0x4F9F2CABu, "FNV-1a reference vector");
        Check(TrainerIdentity.Signature.Length == 32, "fixed signature length");
        Check(Convert.ToHexString(TrainerIdentity.Signature) ==
            "5241334D542D4944454E5449545900002A616556468343AF8863359BF95B0FEE", "permanent public signature");
        foreach (var kind in new[] { TrainerIdentityKind.TrainerProcess, TrainerIdentityKind.GameProcess })
        {
            var bytes = TrainerIdentity.CreateRecord(kind, 4321, 1234);
            Check(TrainerIdentity.TryParse(bytes, out var record) && record == new TrainerIdentityRecord(kind, 4321, 1234), "record roundtrip");
            for (var i = 0; i < bytes.Length; i++)
            {
                var altered = bytes.ToArray(); altered[i] ^= 1;
                Check(!TrainerIdentity.TryParse(altered, out _), "single-byte corruption rejected");
            }
            Check(!TrainerIdentity.TryParse(bytes.AsSpan(0, 63), out _), "partial read rejected");
            foreach (var (offset, value) in new[] { (0x20, 2u), (0x24, 63u), (0x28, 3u), (0x34, 1u), (0x38, 1u) })
            {
                var altered = bytes.ToArray();
                BinaryPrimitives.WriteUInt32LittleEndian(altered.AsSpan(offset), value);
                BinaryPrimitives.WriteUInt32LittleEndian(altered.AsSpan(0x3C), TrainerIdentity.Checksum(altered.AsSpan(0, 0x3C)));
                Check(!TrainerIdentity.TryParse(altered, out _), "unsupported protocol/role/reserved fields rejected with valid checksum");
            }
        }
        var layout = BlockLayoutCatalog.Create(); BlockLayoutCatalog.DeclareBridges(layout); layout.Validate();
        Check(layout.Regions.Single(r => r.Name == "TrainerIdentity").End == BlockLayoutCatalog.BlockSize, "identity has a reserved tail region");
        var manifest = XDocument.Load("src/RA3MT.UI/app.manifest");
        XNamespace ns = "urn:schemas-microsoft-com:asm.v1";
        Check((string?)manifest.Root?.Element(ns + "assemblyIdentity")?.Attribute("name") == TrainerIdentity.ManifestName, "PE manifest agrees with public identity");

        // A separate process owns the marker and mutex. The detector uses only
        // PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, never remote writes.
        var start = new ProcessStartInfo("dotnet")
        {
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
        };
        start.ArgumentList.Add(Assembly.GetExecutingAssembly().Location);
        start.ArgumentList.Add("identity-child");
        using var child = Process.Start(start) ?? throw new Exception("identity helper did not start");
        try
        {
            var ready = child.StandardOutput.ReadLineAsync();
            Check(ready.Wait(TimeSpan.FromSeconds(5)), "identity helper ready");
            var fields = (ready.Result ?? throw new Exception("identity helper exited: " + child.StandardError.ReadToEnd())).Split(' ');
            Check(int.Parse(fields[0]) == child.Id, "helper reports its PID");
            var address = (nuint)Convert.ToUInt64(fields[1], 16);
            var marker = new byte[TrainerIdentity.RecordSize];
            using var process = OpenProcess(0x410, false, child.Id);
            Check(!process.IsInvalid && ReadProcessMemory(process, address, marker, (nuint)marker.Length, out var count) && count == (nuint)marker.Length, "read marker from another process");
            Check(TrainerIdentity.TryParse(marker, out var record) && record.Kind == TrainerIdentityKind.TrainerProcess &&
                  record.OwnerProcessId == child.Id && record.TrainerProcessId == child.Id, "cross-process identity and PID validation");
            Check(Mutex.TryOpenExisting(TrainerIdentity.MutexName(child.Id), out var signal), "cross-process discovery mutex");
            signal?.Dispose();
            child.StandardInput.WriteLine();
            Check(child.WaitForExit(5000) && child.ExitCode == 0, "helper clean exit");
            var stillExists = Mutex.TryOpenExisting(TrainerIdentity.MutexName(child.Id), out var stale);
            stale?.Dispose();
            Check(!stillExists, "mutex disappears after last handle closes");
        }
        finally
        {
            if (!child.HasExited) { child.StandardInput.WriteLine(); if (!child.WaitForExit(5000)) child.Kill(); }
        }
        Console.WriteLine($"PASS {cases} identity cases: permanent signature, corruption/ABI, reserved region, PE manifest, cross-process read/mutex/exit");
    }
}
