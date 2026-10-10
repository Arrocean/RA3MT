namespace RA3MT.Core.Memory;

public static class MemoryValues
{
    public static uint ReadU32(this IInjectionMemory memory, nuint address) =>
        BitConverter.ToUInt32(memory.Read(address, 4));

    public static float ReadF32(this IInjectionMemory memory, nuint address) =>
        BitConverter.ToSingle(memory.Read(address, 4));

    public static void WriteF32(this IInjectionMemory memory, nuint address, float value) =>
        memory.Write(address, BitConverter.GetBytes(value));
}
