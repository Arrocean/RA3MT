using System.Text;

namespace RA3MT.Core.Scan;

/// <summary>An AOB pattern with wildcards: "3B 6F 0C ?? 8B CE".</summary>
public sealed class Pattern
{
    private readonly byte[] _bytes;
    private readonly bool[] _mask; // true = must match

    public int Length => _bytes.Length;
    public int ConcreteBytes { get; private set; }
    public string Source { get; }

    private Pattern(byte[] bytes, bool[] mask, string source)
    {
        _bytes = bytes;
        _mask = mask;
        Source = source;
        ConcreteBytes = mask.Count(m => m);
    }

    public static Pattern Parse(string text)
    {
        var tokens = text.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var bytes = new byte[tokens.Length];
        var mask = new bool[tokens.Length];
        for (var i = 0; i < tokens.Length; i++)
        {
            if (tokens[i] == "?" || tokens[i] == "??")
            {
                mask[i] = false;
            }
            else
            {
                bytes[i] = Convert.ToByte(tokens[i], 16);
                mask[i] = true;
            }
        }
        return new Pattern(bytes, mask, text);
    }

    public bool Matches(ReadOnlySpan<byte> data, int offset)
    {
        if (offset + _bytes.Length > data.Length) return false;
        for (var i = 0; i < _bytes.Length; i++)
            if (_mask[i] && data[offset + i] != _bytes[i])
                return false;
        return true;
    }

    /// <summary>Scan a buffer; returns all match offsets (relative to buffer start).</summary>
    public List<int> ScanAll(ReadOnlySpan<byte> data)
    {
        var hits = new List<int>();
        if (data.Length < _bytes.Length) return hits;
        var first = FirstConcrete();
        if (first < 0)
        {
            for (var i = 0; i <= data.Length - _bytes.Length; i++)
                if (Matches(data, i)) hits.Add(i);
            return hits;
        }
        var b = _bytes[first];
        for (var i = 0; i <= data.Length - _bytes.Length; i++)
        {
            if (data[i + first] != b) continue;
            if (Matches(data, i)) hits.Add(i);
        }
        return hits;
    }

    private int FirstConcrete()
    {
        for (var i = 0; i < _mask.Length; i++)
            if (_mask[i]) return i;
        return -1;
    }

    public override string ToString() => Source;
}
