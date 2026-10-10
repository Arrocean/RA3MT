using System.Text;

namespace RA3MT.Core.Target;

/// <summary>A PE32 image mapped from disk (section table + raw content),
/// addressable by RVA — used by the offline self-check.</summary>
public sealed class StaticImage
{
    private readonly (string Name, uint Va, uint RawPtr, uint RawSize, uint VSize)[] _sections;
    private readonly byte[] _file;

    public StaticImage(string path)
    {
        _file = File.ReadAllBytes(path);
        // DOS header
        if (_file.Length < 0x40 || _file[0] != 'M' || _file[1] != 'Z')
            throw new InvalidDataException($"{path}: not a PE (MZ missing)");
        var peOff = BitConverter.ToInt32(_file, 0x3C);
        if (BitConverter.ToUInt32(_file, peOff) != 0x00004550)
            throw new InvalidDataException($"{path}: PE signature missing");
        ushort numSections = BitConverter.ToUInt16(_file, peOff + 6);
        ushort optSize = BitConverter.ToUInt16(_file, peOff + 20);
        var secOff = peOff + 24 + optSize;

        var list = new List<(string, uint, uint, uint, uint)>();
        for (var i = 0; i < numSections; i++)
        {
            var o = secOff + 40 * i;
            var name = Encoding.ASCII.GetString(_file, o, 8).TrimEnd('\0');
            uint vsize = BitConverter.ToUInt32(_file, o + 8);
            uint va = BitConverter.ToUInt32(_file, o + 12);
            uint rawsize = BitConverter.ToUInt32(_file, o + 16);
            uint rawptr = BitConverter.ToUInt32(_file, o + 20);
            list.Add((name, va, rawptr, rawsize, vsize));
        }
        _sections = list.ToArray();
    }

    /// <summary>Read <paramref name="len"/> bytes at an RVA (raw file content; good
    /// enough for .text which is file-backed verbatim).</summary>
    public byte[] GetRva(uint rva, int len)
    {
        foreach (var (name, va, rawPtr, rawSize, vsize) in _sections)
        {
            if (rva < va || rva >= va + Math.Max(vsize, rawSize)) continue;
            var inRaw = rva - va < rawSize ? (int)(rva - va) : -1;
            var buf = new byte[len];
            if (inRaw >= 0)
            {
                var avail = Math.Min(len, (int)Math.Min(rawSize - (uint)inRaw, int.MaxValue));
                Array.Copy(_file, rawPtr + inRaw, buf, 0, Math.Max(0, avail));
            } // else: zero-fill (BSS-like)
            return buf;
        }
        throw new InvalidOperationException($"RVA 0x{rva:X} not in any section");
    }

    /// <summary>Bytes of the whole section containing the RVA (for scanning).</summary>
    public ReadOnlySpan<byte> SectionBytes(uint rva)
    {
        foreach (var (name, va, rawPtr, rawSize, vsize) in _sections)
        {
            if (rva < va || rva >= va + Math.Max(vsize, rawSize)) continue;
            return _file.AsSpan((int)rawPtr, (int)Math.Min(rawSize, _file.Length - rawPtr));
        }
        throw new InvalidOperationException($"RVA 0x{rva:X} not in any section");
    }

    public uint SectionVa(uint rva)
    {
        foreach (var (name, va, rawPtr, rawSize, vsize) in _sections)
            if (rva >= va && rva < va + Math.Max(vsize, rawSize))
                return va;
        throw new InvalidOperationException($"RVA 0x{rva:X} not in any section");
    }
}
