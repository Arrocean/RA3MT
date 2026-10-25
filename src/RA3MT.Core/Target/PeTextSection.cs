using System.Text;

namespace RA3MT.Core.Target;

/// <summary>Read the actual mapped .text extent, including Uprising 1.01's
/// larger code section. Reject unexpected origins instead of shifting AOB RVAs.</summary>
public static class PeTextSection
{
    public static byte[] Read(IImageReader image)
    {
        var header = ImageScan.ReadExact(image, 0, 0x1000, "PE header");
        if (header[0] != 'M' || header[1] != 'Z') throw new InvalidDataException("Missing MZ header");
        var pe = BitConverter.ToInt32(header, 0x3C);
        if (pe < 0x40 || pe > 0xC00 || BitConverter.ToUInt32(header, pe) != 0x4550)
            throw new InvalidDataException("Invalid PE header");
        var count = BitConverter.ToUInt16(header, pe + 6);
        var offset = pe + 24 + BitConverter.ToUInt16(header, pe + 20);
        if (count > 32 || offset + count * 40 > header.Length) throw new InvalidDataException("Invalid PE sections");
        for (var i = 0; i < count; i++)
        {
            var section = offset + i * 40;
            if (Encoding.ASCII.GetString(header, section, 8).TrimEnd('\0') != ".text") continue;
            var rva = BitConverter.ToUInt32(header, section + 12);
            var size = BitConverter.ToInt32(header, section + 8);
            if (rva != 0x1000 || size <= 0 || size > 0x1000000) throw new InvalidDataException("Unexpected .text layout");
            return ImageScan.ReadExact(image, rva, size, ".text");
        }
        throw new InvalidDataException("Missing .text section");
    }
}
