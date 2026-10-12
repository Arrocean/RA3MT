using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.Core.Engine;

/// <summary>ISymbols implementation over the features.json globals for one
/// attached session. All version-specific address arithmetic funnels through
/// here so features never touch <c>Globals</c> directly.</summary>
public sealed class SessionSymbols : ISymbols
{
    private readonly FeaturesData _data;
    private readonly IInjectionMemory _mem;
    private readonly nuint _imageBase;

    public SessionSymbols(FeaturesData data, IInjectionMemory mem, string version, nuint imageBase)
    {
        _data = data;
        _mem = mem;
        Version = version;
        _imageBase = imageBase;
    }

    public string Version { get; }

    public bool TryRva(GameGlobalId id, out uint rva)
    {
        rva = 0;
        var def = _data.ById(id);
        if (def is null || !def.Rva.TryGetValue(Version, out var hex))
            return false;
        rva = Convert.ToUInt32(hex, 16);
        return true;
    }

    public bool TryAddress(GameGlobalId id, out nuint address)
    {
        address = 0;
        if (!TryRva(id, out var rva)) return false;
        address = _imageBase + rva;
        return true;
    }

    public bool TryPointer(GameGlobalId id, out nuint pointer)
    {
        pointer = 0;
        return TryRva(id, out var rva) && TryPointerAtRva(rva, out pointer);
    }

    public bool TryPointerAtRva(uint rva, out nuint pointer)
    {
        pointer = 0;
        if (rva == 0) return false;
        try
        {
            pointer = _mem.ReadU32(_imageBase + rva);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
