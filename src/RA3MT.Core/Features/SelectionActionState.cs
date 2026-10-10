using RA3MT.Core.Memory;

namespace RA3MT.Core.Features;

/// <summary>Original per-instance speeds scoped to one attached game session.</summary>
public sealed class SelectionActionState
{
    private readonly Dictionary<uint, (uint template, float original)> _speeds = new();

    public bool SetSpeed(IInjectionMemory memory, uint locomotor, float speed)
    {
        var template = memory.ReadU32(locomotor + 4u);
        var original = memory.ReadF32(locomotor + 8u);
        if (template < 0x10000 || !float.IsFinite(original) || original < 0) return false;
        if (!_speeds.TryGetValue(locomotor, out var saved) || saved.template != template)
            _speeds[locomotor] = (template, original);
        memory.WriteF32(locomotor + 8u, speed);
        return true;
    }

    public bool RestoreSpeed(IInjectionMemory memory, uint locomotor)
    {
        if (!_speeds.TryGetValue(locomotor, out var saved)) return false;
        if (memory.ReadU32(locomotor + 4u) != saved.template)
        {
            _speeds.Remove(locomotor);
            return false;
        }
        memory.WriteF32(locomotor + 8u, saved.original);
        _speeds.Remove(locomotor);
        return true;
    }

    public void Clear() => _speeds.Clear();
}
