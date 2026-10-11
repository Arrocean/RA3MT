using System.Buffers.Binary;
using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Game-thread destroy consumer: applies a lethal damage delta through the
/// game's own HP adjust function, so clamping and the death notification both run.
/// Modern re-derivation of FINAL3's destroy (whose EA call target was never located
/// for the repack) — adjust runs the complete death path on [hp+4] reaching zero.</summary>
public static class KillDispatcher
{
    public const uint MailboxOffset = 0x1880;
    public const uint StateOffset = MailboxOffset;
    public const uint BodyOffset = MailboxOffset + 4;
    public const uint DrawableOffset = MailboxOffset + 8;
    public const uint HpOffset = MailboxOffset + 0xC;
    // Static DamageInfo the stub passes as the adjust() context. A null context
    // skips the game's damage-processing segment (0x3781A0 modifier pass and the
    // attacker-aware path), which leaves the body dead but with no death event
    // (model stays, unit unselectable). The game only reads ctx+8/ctx+0xC here
    // (damage-type / death-type pair FINAL3 passes as 6 / 0x13); unmatched
    // pairs simply bypass armor modifiers and still run the full death flow.
    public const uint DamageInfoOffset = MailboxOffset + 0x10;  // ctx points here
    public const uint DamageTypeOffset = MailboxOffset + 0x18;  // ctx+8  = 6
    public const uint DeathTypeOffset = MailboxOffset + 0x1C;   // ctx+0xC = 0x13
    public const uint Idle = 0, Pending = 1, Executing = 2, Success = 3, Reject = 4;

    public const uint CodeOffset = 0x1400;

    private const uint LethalDelta = 0xFF7FFFFF; // float -3.4028234e38

    public static byte[] Emit(nuint stubVA, nuint blockVA, nuint adjustVA, nuint rootVA)
    {
        uint start = checked((uint)stubVA), block = checked((uint)blockVA);
        uint api = checked((uint)adjustVA), root = checked((uint)rootVA);
        uint Slot(uint offset) => checked(block + offset);
        var a = new Asm();
        var labels = new Dictionary<int, int>();
        var patches = new List<(int position, int label)>();
        const int Exit = 1, Rejected = 2;
        void Label(int id) => labels.Add(id, a.Length);
        void Branch(byte condition, int label)
        {
            a.Db(0x0F, condition); patches.Add((a.Length, label)); a.Db(0, 0, 0, 0);
        }
        void Jump(int label)
        {
            a.Db(0xE9); patches.Add((a.Length, label)); a.Db(0, 0, 0, 0);
        }
        void NonNull(R reg) { a.CmpR32Imm32(reg, 0x10000); Branch(0x82, Rejected); }

        a.Pushfd(); a.Pushad();
        a.Db(0xB8, 1, 0, 0, 0);                         // expected Pending
        a.Db(0xBA, 2, 0, 0, 0);                         // desired Executing
        a.Db(0xF0, 0x0F, 0xB1, 0x15); a.Db(BitConverter.GetBytes(Slot(StateOffset)));
        Branch(0x85, Exit);

        a.MovRegAbs(R.Esi, Slot(BodyOffset)); NonNull(R.Esi);
        a.MovRegAbs(R.Edi, Slot(DrawableOffset)); NonNull(R.Edi);
        a.CmpRegMRegDisp32(R.Edi, R.Esi, 0xF4); Branch(0x85, Rejected);
        a.CmpRegMRegDisp32(R.Esi, R.Edi, 0x138); Branch(0x85, Rejected);
        a.Db(0xF6, 0x87, 0x3D, 0x01, 0, 0, 0x40);       // selected bit 13D40
        Branch(0x84, Rejected);
        a.MovRegAbs(R.Eax, Slot(HpOffset)); NonNull(R.Eax);
        a.CmpRegMRegDisp32(R.Eax, R.Esi, 0x33C);        // hp == [body+0x33C]?
        Branch(0x85, Rejected);
        a.Db(0x8B, Asm.Modrm(3, R.Ebx, R.Eax));         // mov ebx,eax : keep hp pointer across the call

        a.Db(0x89, 0xE0);                               // old pushad ESP
        a.Db(0x81, 0xEC, 0x14, 0x02, 0, 0);             // reserve FX area + saved ESP
        a.Db(0x83, 0xE4, 0xF0);                         // stack alignment
        a.Db(0x89, 0x84, 0x24, 0, 0x02, 0, 0);          // [esp+200] = old ESP
        a.Db(0x0F, 0xAE, 0x04, 0x24);                   // fxsave [esp]
        a.Db(0xFC);                                     // CLD
        a.Db(0x83, 0xEC, 0x04);                         // pad: 2 args + ret = 12 → callee entry aligned
        a.Db(0x68); a.Db(BitConverter.GetBytes(Slot(DamageInfoOffset))); // arg2 = static DamageInfo
        a.Db(0x68); a.Db(BitConverter.GetBytes(LethalDelta));            // push delta (float bits)
        a.Db(0x8B, Asm.Modrm(3, R.Ecx, R.Ebx));         // mov ecx,ebx : this = hp object
        a.Db(0xE8);                                     // CALL rel32
        int callDisp = a.Length; a.Db(0, 0, 0, 0);
        a.Db(0x83, 0xC4, 0x04);                         // add esp,4: undo pad, esp back at FX base
        a.MovRegAbs(R.Ebx, Slot(HpOffset));              // reload after callee clobber
        a.CmpM32RegDisp8Imm32(R.Ebx, 0x04, 0);          // current hp == 0 ?
        a.JneShort(5);
        a.MovM32Abs(Slot(StateOffset), Success);
        a.JmpShort(6);
        a.Label(5);
        a.MovM32Abs(Slot(StateOffset), Reject);
        a.Label(6);
        a.Db(0x0F, 0xAE, 0x0C, 0x24);                   // fxrstor [esp]
        a.Db(0x8B, 0xA4, 0x24, 0, 0x02, 0, 0);          // restore old pushad ESP
        Jump(Exit);
        Label(Rejected);
        a.MovM32Abs(Slot(StateOffset), Reject);
        Label(Exit); a.Popad(); a.Popfd(); a.Ret();

        var bytes = a.Build(start);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(callDisp, 4),
            unchecked((int)(api - (start + (uint)(callDisp + 4)))));
        foreach (var (position, label) in patches)
            BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(position, 4),
                checked(labels[label] - (position + 4)));
        return bytes;
    }
}

/// <summary>Single outstanding destroy request.</summary>
public sealed class KillRequestMailbox
{
    public const uint Offset = KillDispatcher.MailboxOffset;
    private readonly IInjectionMemory _memory;
    private readonly nuint _address;
    private readonly object _gate = new();

    public KillRequestMailbox(IInjectionMemory memory, nuint block)
    {
        _memory = memory;
        _address = block + Offset;
    }

    public uint State => _memory.ReadU32(_address);

    public uint ReadResult()
    {
        lock (_gate)
        {
            var first = State;
            if (first is not (3 or 4)) return first;
            if (State != first) throw new InvalidOperationException("Kill result changed while reading");
            return first;
        }
    }

    public void Submit(uint body, uint drawable, uint hp)
    {
        if (body < 0x10000 || drawable < 0x10000 || hp < 0x10000)
            throw new ArgumentException("Invalid destroy request object");
        lock (_gate)
        {
            var state = State;
            if (state is not (0 or 3 or 4))
                throw new InvalidOperationException("Destroy request still pending or mailbox invalid");
            _memory.Write(_address + 4, BitConverter.GetBytes(body));
            _memory.Write(_address + 8, BitConverter.GetBytes(drawable));
            _memory.Write(_address + 0xC, BitConverter.GetBytes(hp));
            // Static DamageInfo payload: adjust() reads ctx+8/ctx+0xC only.
            // FINAL3 passes damage type 6 / death type 0x13 for its destroy.
            _memory.Write(_address + 0x18, BitConverter.GetBytes(6u));
            _memory.Write(_address + 0x1C, BitConverter.GetBytes(0x13u));
            _memory.Write(_address, BitConverter.GetBytes(1u)); // publish last
        }
    }
}
