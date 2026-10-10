namespace RA3MT.Core.Memory;

/// <summary>Memory operations used by the hook installer and fault-injection tests.</summary>
public interface IInjectionMemory
{
    byte[] Read(nuint address, int size);
    void Write(nuint address, ReadOnlySpan<byte> data);
    nuint Alloc(nuint size, uint protect = 0x40);
}
