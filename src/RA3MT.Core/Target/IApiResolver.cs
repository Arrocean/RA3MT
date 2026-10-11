namespace RA3MT.Core.Target;

/// <summary>Byte-level access to the on-disk game image we are validating against.
/// Replaces the <c>Func&lt;uint,int,byte[]&gt;</c> delegate that every resolver used
/// to take, so resolvers can be described, composed and tested without closures.</summary>
public interface IImageReader
{
    /// <summary>Read <paramref name="length"/> bytes at the given RVA. Callers must
    /// treat a short read as a mismatch.</summary>
    byte[] Read(uint rva, int length);
}

/// <summary>Adapter for code that already has a read delegate (tests, SelfCheck,
/// the attach path).</summary>
public sealed class DelegateImageReader(Func<uint, int, byte[]> read) : IImageReader
{
    public byte[] Read(uint rva, int length) => read(rva, length);
}

/// <summary>What one resolver verified, for logging and diagnostics.</summary>
public readonly record struct ApiResolution(string Name, string Version, nuint Entry, int VerifiedBytes)
{
    public string Describe() => $"{Name} {Version} 0x{Entry:X} ({VerifiedBytes} bytes verified)";
}

/// <summary>Strict API resolver: verifies a byte/instruction contract in the game
/// image and returns the address to call. A resolver never invokes game code, and
/// must throw (not return a partial result) when any anchor mismatches, so the
/// caller can refuse to install the dependent bridge.</summary>
public interface IApiResolver<out TApi> where TApi : struct
{
    /// <summary>Stable id (also used as the registry key and in log lines).</summary>
    string Id { get; }

    TApi Resolve(string version, nuint imageBase, IImageReader image);
}

/// <summary>Resolver for APIs that resolve to a single callable address.</summary>
public readonly record struct ApiAddress(nuint Value, ApiResolution Detail)
{
    public static implicit operator nuint(ApiAddress address) => address.Value;
    public bool IsResolved => Value != 0;

    public override string ToString() => Detail.Describe();
}
