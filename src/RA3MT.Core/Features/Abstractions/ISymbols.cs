namespace RA3MT.Core.Features.Abstractions;

using RA3MT.Core.Model;

/// <summary>Game addresses a feature may depend on, resolved by id instead of by
/// poking at the raw globals model. Resolution is version aware and returns
/// <c>0</c> (or false) rather than throwing, so a feature can degrade.</summary>
public interface ISymbols
{
    string Version { get; }

    /// <summary>Raw RVA of a registered global for the current version.</summary>
    bool TryRva(GameGlobalId id, out uint rva);

    /// <summary>Absolute address of a registered global (the global slot itself).</summary>
    bool TryAddress(GameGlobalId id, out nuint address);

    /// <summary>Dereference a registered global (one pointer hop).</summary>
    bool TryPointer(GameGlobalId id, out nuint pointer);

    /// <summary>Pointer hop for a feature-private RVA that is not a shared global.</summary>
    bool TryPointerAtRva(uint rva, out nuint pointer);
}
