using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features.Host;

/// <summary>Reading and writing the game's raw memory with the trainer's safety
/// conventions in one place: 32-bit pointers below 0x10000 are treated as null,
/// and reads are individually guarded so a feature never throws because a match
/// ended or an object was destroyed between two reads.</summary>
public interface IGameMemory : IFeatureService
{
    string Version { get; }
    nuint ImageBase { get; }

    /// <summary>True when the pointer is a plausible object address.</summary>
    bool IsPlausible(nuint pointer);

    uint ReadU32(nuint address);
    float ReadF32(nuint address);
    byte ReadByte(nuint address);
    byte[] ReadBytes(nuint address, int length);
    bool TryReadU32(nuint address, out uint value);
    bool TryReadF32(nuint address, out float value);

    void WriteU32(nuint address, uint value);
    void WriteF32(nuint address, float value);
    void WriteBytes(nuint address, ReadOnlySpan<byte> data);
}

/// <summary>Default implementation over the injected memory handle.</summary>
public sealed class GameMemory(IInjectionMemory memory, string version, nuint imageBase) : IGameMemory
{
    public string Version { get; } = version;
    public nuint ImageBase { get; } = imageBase;
    public bool IsAvailable => true;

    public bool IsPlausible(nuint pointer) => pointer >= 0x10000;

    public uint ReadU32(nuint address) => memory.ReadU32(address);

    public float ReadF32(nuint address) =>
        BitConverter.UInt32BitsToSingle(memory.ReadU32(address));
    public byte ReadByte(nuint address) => memory.Read(address, 1)[0];

    public byte[] ReadBytes(nuint address, int length) => memory.Read(address, length);

    public bool TryReadU32(nuint address, out uint value)
    {
        try
        {
            value = memory.ReadU32(address);
            return true;
        }
        catch
        {
            value = 0;
            return false;
        }
    }

    public bool TryReadF32(nuint address, out float value)
    {
        value = 0f;
        try
        {
            value = BitConverter.UInt32BitsToSingle(memory.ReadU32(address));
            return true;
        }
        catch
        {
            return false;
        }
    }

    public void WriteU32(nuint address, uint value) => memory.Write(address, BitConverter.GetBytes(value));
    public void WriteF32(nuint address, float value) =>
        memory.Write(address, BitConverter.GetBytes(BitConverter.SingleToUInt32Bits(value)));
    public void WriteBytes(nuint address, ReadOnlySpan<byte> data) => memory.Write(address, data);
}
