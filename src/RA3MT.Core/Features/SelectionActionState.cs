using RA3MT.Core.Memory;
using RA3MT.Core.Features.Host;

namespace RA3MT.Core.Features;

/// <summary>Original per-instance speeds scoped to one attached game session.</summary>
public sealed class SelectionActionState : IFeatureService
{
    public bool IsAvailable => true;
    private readonly Dictionary<uint, (uint template, float original, float written)> _speeds = new();

    public bool SetSpeed(IInjectionMemory memory, uint locomotor, float speed)
    {
        if (locomotor < 0x10000 || !float.IsFinite(speed) || speed < 0) return false;
        var template = memory.ReadU32(locomotor + 4u);
        var original = memory.ReadF32(locomotor + 8u);
        if (template < 0x10000 || !float.IsFinite(original) || original < 0) return false;
        if (_speeds.TryGetValue(locomotor, out var saved) && saved.template == template && original == saved.written)
            original = saved.original;
        memory.WriteF32(locomotor + 8u, speed);
        _speeds[locomotor] = (template, original, speed);
        return true;
    }

    public bool RestoreSpeed(IInjectionMemory memory, uint locomotor)
    {
        if (!_speeds.TryGetValue(locomotor, out var saved)) return false;
        if (memory.ReadU32(locomotor + 4u) != saved.template || memory.ReadF32(locomotor + 8u) != saved.written)
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
