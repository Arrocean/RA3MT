using System.Buffers.Binary;

namespace RA3MT.Core.Engine;

public enum R
{
    Eax = 0, Ecx, Edx, Ebx, Esp, Ebp, Esi, Edi,
}

/// <summary>A tiny x86 (32-bit) byte emitter covering exactly the encodings the
/// MasterCode stubs need. Supports short-jump label patching and rel32 patching.</summary>
public sealed class Asm
{
    private readonly List<byte> _b = new();
    private readonly List<(int patchPos, int label)> _rel8 = new();
    private readonly List<(int patchPos, uint targetVa)> _rel32 = new();
    private readonly Dictionary<int, int> _labels = new();

    public int Length => _b.Count;

    public void Db(params byte[] bytes) => _b.AddRange(bytes);
    public void Db(ReadOnlySpan<byte> bytes) { foreach (var x in bytes) _b.Add(x); }

    // ---- labels ----
    public void Label(int id) => _labels[id] = _b.Count;
    public void JeShort(int label) { Db(0x74); _rel8.Add((_b.Count, label)); _b.Add(0); }
    public void JneShort(int label) { Db(0x75); _rel8.Add((_b.Count, label)); _b.Add(0); }
    public void JaeShort(int label) { Db(0x73); _rel8.Add((_b.Count, label)); _b.Add(0); }
    public void JmpShort(int label) { Db(0xEB); _rel8.Add((_b.Count, label)); _b.Add(0); }

    /// <summary>E9 rel32 — target is an absolute VA (patched in Build).</summary>
    public void JmpTo(uint targetVa) { Db(0xE9); _rel32.Add((_b.Count, targetVa)); _b.AddRange(new byte[4]); }

    // ---- flag/register preservation ----
    public void Pushfd() => Db(0x9C);
    public void Popfd() => Db(0x9D);
    public void Pushad() => Db(0x60);
    public void Popad() => Db(0x61);
    public void Push(R r) => Db((byte)(0x50 + (int)r));
    public void Push8(byte imm) => Db(0x6A, imm);
    public void AddEsp8(byte imm) => Db(0x83, 0xC4, imm);
    public void IncReg(R r) => Db(0xFF, (byte)(0xC0 + (int)r));

    // ---- moves / compares ----
    public void CmpM8Abs(uint addr, byte imm) { Db(0x80, 0x3D); Db(BitConverter.GetBytes(addr)); Db(imm); }
    public void MovM8Abs(uint addr, byte imm) { Db(0xC6, 0x05); Db(BitConverter.GetBytes(addr)); Db(imm); }
    public void MovM32Abs(uint addr, uint imm) { Db(0xC7, 0x05); Db(BitConverter.GetBytes(addr)); Db(BitConverter.GetBytes(imm)); }

    /// <summary>C7 /0: mov dword ptr [reg+disp8], imm32</summary>
    public void MovM32RegDisp8Imm32(R reg, byte disp, uint imm)
    {
        Db(0xC7, Modrm(1, 0, reg)); Db(disp); Db(BitConverter.GetBytes(imm));
    }

    /// <summary>C7 /0: mov dword ptr [reg+disp32], imm32</summary>
    public void MovM32RegDisp32Imm32(R reg, uint disp, uint imm)
    {
        Db(0xC7, Modrm(2, 0, reg)); Db(BitConverter.GetBytes(disp)); Db(BitConverter.GetBytes(imm));
    }

    /// <summary>81 /0: add dword ptr [reg+disp8], imm32</summary>
    public void AddM32RegDisp8Imm32(R reg, byte disp, uint imm)
    {
        Db(0x81, Modrm(1, 0, reg)); Db(disp); Db(BitConverter.GetBytes(imm));
    }

    /// <summary>83 /0: add dword ptr [reg+disp8], imm8</summary>
    public void AddM32RegDisp8Imm8(R reg, byte disp, byte imm)
    {
        Db(0x83, Modrm(1, 0, reg)); Db(disp, imm);
    }

    /// <summary>A1 / 8B /r: mov reg, [abs]</summary>
    public void MovRegAbs(R reg, uint addr)
    {
        if (reg == R.Eax) { Db(0xA1); Db(BitConverter.GetBytes(addr)); return; }
        Db(0x8B, Modrm(0, reg, R.Ebp)); // mod=0 rm=101 => disp32
        Db(BitConverter.GetBytes(addr));
    }

    /// <summary>8B /r: mov reg, [reg2+disp8]</summary>
    public void MovRegRegDisp8(R dst, R src, byte disp)
    {
        if (src == R.Esp) throw new NotSupportedException("use Esp form");
        Db(0x8B, Modrm(1, dst, src)); Db(disp);
    }

    /// <summary>89 /r: mov [abs], reg</summary>
    public void MovM32AbsReg(R src, uint addr)
    {
        Db(0x89, Modrm(0, src, R.Ebp)); // mod=0 rm=101 => disp32
        Db(BitConverter.GetBytes(addr));
    }

    /// <summary>89: mov [disp32 + idx*4], src（SIB 无基址寻址，用于块内捕获数组）</summary>
    public void MovM32ScaledIdxAbs(R idx, uint baseAddr, R src)
    {
        byte sib = (byte)((2 << 6) | ((int)idx << 3) | 5); // scale=4, base=101(disp32)
        Db(0x89, Modrm(0, src, R.Esp), sib);
        Db(BitConverter.GetBytes(baseAddr));
    }

    /// <summary>81 /7: cmp dword ptr [reg+disp8], imm32</summary>
    public void CmpM32RegDisp8Imm32(R reg, byte disp, uint imm)
    {
        Db(0x81, Modrm(1, (R)7, reg)); Db(disp); Db(BitConverter.GetBytes(imm));
    }

    /// <summary>81 /7: cmp reg, imm32</summary>
    public void CmpR32Imm32(R reg, uint imm)
    {
        Db(0x81, Modrm(3, (R)7, reg)); Db(BitConverter.GetBytes(imm));
    }

    /// <summary>FF /0: inc dword ptr [abs]</summary>
    public void IncM32Abs(uint addr)
    {
        Db(0xFF, 0x05); Db(BitConverter.GetBytes(addr));
    }

    /// <summary>8B /r: mov reg, [reg2+disp32]</summary>
    public void MovRegRegDisp32(R dst, R src, uint disp)
    {
        Db(0x8B, Modrm(2, dst, src)); Db(BitConverter.GetBytes(disp));
    }

    /// <summary>8B /r: mov reg, [esp+disp32] (SIB)</summary>
    public void MovRegEspDisp32(R dst, uint disp)
    {
        Db(0x8B, Modrm(2, dst, R.Esp), 0x24); Db(BitConverter.GetBytes(disp));
    }

    /// <summary>8B /r: mov reg, [reg2]</summary>
    public void MovRegRegInd(R dst, R src)
    {
        Db(0x8B, Modrm(0, dst, src == R.Ebp ? throw new NotSupportedException() : src));
    }

    /// <summary>3B /r: cmp reg, [rm+disp32]</summary>
    public void CmpRegMRegDisp32(R reg, R rm, uint disp)
    {
        Db(0x3B, Modrm(2, reg, rm)); Db(BitConverter.GetBytes(disp));
    }

    /// <summary>3B /r: cmp reg, [esp+disp32] (SIB)</summary>
    public void CmpRegMEspDisp32(R reg, uint disp)
    {
        Db(0x3B, Modrm(2, reg, R.Esp), 0x24); Db(BitConverter.GetBytes(disp));
    }

    /// <summary>85 /r: test reg, reg</summary>
    public void TestRegReg(R a, R b) => Db(0x85, Modrm(3, a, b));

    public void Ret() => Db(0xC3);

    /// <summary>Build final bytes; baseVa is the VA of byte 0 (needed for E9 patching).</summary>
    public byte[] Build(uint baseVa)
    {
        var outp = _b.ToArray();
        foreach (var (pos, label) in _rel8)
        {
            var target = _labels[label];
            outp[pos] = (byte)(target - (pos + 1));
        }
        foreach (var (pos, targetVa) in _rel32)
        {
            var rel = (int)(targetVa - (baseVa + (uint)(pos + 4)));
            BinaryPrimitives.WriteInt32LittleEndian(outp.AsSpan(pos), rel);
        }
        return outp;
    }

    internal static byte Modrm(int mod, R reg, R rm) => (byte)((mod << 6) | ((int)reg << 3) | (int)rm);
}
