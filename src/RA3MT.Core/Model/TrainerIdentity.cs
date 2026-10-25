using System.Buffers.Binary;

namespace RA3MT.Core.Model;

public enum TrainerIdentityKind : uint { TrainerProcess = 1, GameProcess = 2 }

public readonly record struct TrainerIdentityRecord(TrainerIdentityKind Kind,
    uint OwnerProcessId, uint TrainerProcessId);

/// <summary>Public, permanent project identity for cooperating platform detectors.
/// Never regenerate the ID per release/build. The checksum detects corruption;
/// this voluntary marker is not a signature or proof against modified forks.</summary>
public static class TrainerIdentity
{
    public const string ProjectId = "2A616556-4683-43AF-8863-359BF95B0FEE";
    public const string ManifestName = "RA3MT.Trainer." + ProjectId;
    public const string MutexPrefix = @"Local\RA3MT.Identity." + ProjectId + ".";
    public const uint ProtocolVersion = 1;
    public const int RecordSize = 64;

    // ASCII "RA3MT-IDENTITY\0\0", then canonical GUID hex bytes (not .NET's
    // mixed-endian Guid.ToByteArray representation). These first 32 bytes are
    // the invariant search signature; PID/role/checksum follow it.
    private static readonly byte[] Prefix = Convert.FromHexString(
        "5241334D542D4944454E544954590000" + "2A616556468343AF8863359BF95B0FEE");
    public static ReadOnlySpan<byte> Signature => Prefix;

    public static string MutexName(int processId) => processId > 0
        ? MutexPrefix + processId.ToString(System.Globalization.CultureInfo.InvariantCulture)
        : throw new ArgumentOutOfRangeException(nameof(processId));

    public static byte[] CreateRecord(TrainerIdentityKind kind, uint ownerProcessId, uint trainerProcessId)
    {
        if (kind is not (TrainerIdentityKind.TrainerProcess or TrainerIdentityKind.GameProcess))
            throw new ArgumentOutOfRangeException(nameof(kind));
        var bytes = new byte[RecordSize];
        Prefix.CopyTo(bytes, 0);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(0x20), ProtocolVersion);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(0x24), RecordSize);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(0x28), (uint)kind);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(0x2C), ownerProcessId);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(0x30), trainerProcessId);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(0x3C), Checksum(bytes.AsSpan(0, 0x3C)));
        return bytes;
    }

    public static bool TryParse(ReadOnlySpan<byte> bytes, out TrainerIdentityRecord record)
    {
        record = default;
        if (bytes.Length < RecordSize || !bytes[..32].SequenceEqual(Prefix)) return false;
        if (BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x20..]) != ProtocolVersion ||
            BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x24..]) != RecordSize ||
            BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x34..]) != 0 ||
            BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x38..]) != 0 ||
            BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x3C..]) != Checksum(bytes[..0x3C])) return false;
        var kind = (TrainerIdentityKind)BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x28..]);
        if (kind is not (TrainerIdentityKind.TrainerProcess or TrainerIdentityKind.GameProcess)) return false;
        record = new TrainerIdentityRecord(kind,
            BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x2C..]),
            BinaryPrimitives.ReadUInt32LittleEndian(bytes[0x30..]));
        return true;
    }

    public static uint Checksum(ReadOnlySpan<byte> bytes)
    {
        var hash = 2166136261u;
        foreach (var value in bytes) hash = unchecked((hash ^ value) * 16777619u);
        return hash;
    }
}
