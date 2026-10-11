namespace RA3MT.Core.Engine;

/// <summary>One reserved area inside the injected code block. <see cref="Owner"/>
/// names the feature/bridge that claims it, so a collision reports which two
/// subsystems disagree instead of just "overlap".</summary>
public readonly record struct BlockRegion(string Name, uint Offset, uint Size, string Owner)
{
    public uint End => Offset + Size;
    public bool Contains(uint address) => address >= Offset && address < End;
}

/// <summary>A layout conflict or a declaration mistake. Derives from
/// <see cref="InvalidOperationException"/> so installers treat it as a normal
/// refusal (callers already catch that type) rather than an unexpected crash.</summary>
public sealed class BlockLayoutException(string message) : InvalidOperationException(message);

/// <summary>Owns the layout of the injected code block.
///
/// Every area — stub code, per-bridge dispatchers, mailboxes, consumer stubs,
/// diagnostics and capture buffers — is declared once through <see cref="Declare"/>,
/// and <see cref="Validate"/> proves the whole thing fits and does not overlap.
/// Adding a bridge is therefore a declaration, not a hand-picked offset plus a
/// new pairwise assertion.</summary>
public sealed class BlockLayout
{
    private readonly List<BlockRegion> _regions = [];
    private readonly Dictionary<string, BlockRegion> _byName = new(StringComparer.Ordinal);

    public BlockLayout(uint blockSize)
    {
        BlockSize = blockSize;
    }

    public uint BlockSize { get; }

    public IReadOnlyList<BlockRegion> Regions => _regions;

    /// <summary>Declare a region. Duplicate names are a programming error.</summary>
    public BlockRegion Declare(string name, uint offset, uint size, string owner)
    {
        if (size == 0) throw new BlockLayoutException($"region '{name}' has zero size");
        if (!_byName.TryAdd(name, new BlockRegion(name, offset, size, owner)))
            throw new BlockLayoutException($"region '{name}' declared twice");
        var region = _byName[name];
        _regions.Add(region);
        return region;
    }

    /// <summary>Shrink (or grow) a declared region once the emitted code length is
    /// known. Growing past the reservation is allowed but will fail
    /// <see cref="Validate"/> if it reaches a neighbour, which is exactly the
    /// "dispatcher outgrew its slot" failure we want to catch loudly.</summary>
    public BlockRegion AmendSize(string name, int actualSize)
    {
        if (!_byName.TryGetValue(name, out var region))
            throw new BlockLayoutException($"region '{name}' was never declared");
        if (actualSize <= 0)
            throw new BlockLayoutException($"region '{name}' amended to non-positive size {actualSize}");
        var updated = region with { Size = (uint)actualSize };
        _byName[name] = updated;
        for (var i = 0; i < _regions.Count; i++)
            if (_regions[i].Name == name) _regions[i] = updated;
        return updated;
    }

    public uint OffsetOf(string name) =>
        _byName.TryGetValue(name, out var r)
            ? r.Offset
            : throw new BlockLayoutException($"region '{name}' was never declared");

    public uint SizeOf(string name) =>
        _byName.TryGetValue(name, out var r)
            ? r.Size
            : throw new BlockLayoutException($"region '{name}' was never declared");

    public bool TryGet(string name, out BlockRegion region) => _byName.TryGetValue(name, out region);

    /// <summary>True when [start, start+length) fits entirely inside the region.</summary>
    public bool FitsWithin(string name, uint start, uint length) =>
        _byName.TryGetValue(name, out var r) && start >= r.Offset && start + length <= r.End;

    /// <summary>All overlapping pairs, plus out-of-block regions. Empty means the
    /// layout is sound.</summary>
    public IReadOnlyList<string> Errors()
    {
        var errors = new List<string>();
        foreach (var r in _regions)
        {
            if (r.End > BlockSize)
                errors.Add($"region '{r.Name}' ({r.Owner}) ends at 0x{r.End:X} beyond block 0x{BlockSize:X}");
        }

        for (var i = 0; i < _regions.Count; i++)
        {
            for (var j = i + 1; j < _regions.Count; j++)
            {
                var a = _regions[i];
                var b = _regions[j];
                if (a.Offset < b.End && b.Offset < a.End)
                    errors.Add($"region '{a.Name}' ({a.Owner}) overlaps '{b.Name}' ({b.Owner})");
            }
        }

        return errors;
    }

    /// <summary>Throw unless the layout is sound. Call once, after every region
    /// that depends on runtime decisions has been declared.</summary>
    public void Validate()
    {
        var errors = Errors();
        if (errors.Count != 0)
            throw new BlockLayoutException("块内布局冲突：" + string.Join("；", errors));
    }

    /// <summary>Smallest free offset at or above <paramref name="from"/>, aligned
    /// up to <paramref name="align"/>. For growth areas such as the stub arena.</summary>
    public uint NextFree(uint from, uint align, uint size)
    {
        var candidate = Align(from, align);
        foreach (var r in _regions.OrderBy(r => r.Offset))
        {
            if (candidate + size <= r.Offset) break;
            if (candidate < r.End) candidate = Align(r.End, align);
        }
        return candidate;
    }

    public static uint Align(uint value, uint align) =>
        align <= 1 ? value : (value + align - 1) / align * align;
}
