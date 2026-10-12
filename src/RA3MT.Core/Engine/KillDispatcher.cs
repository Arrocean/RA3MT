using System.Buffers.Binary;
using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Game-thread destroy consumer: routes the kill through the game's
/// FULL damage entry (thiscall Body, args damage-type 6 / death-type 0x13 / 0,
/// ret 0xC) — the same call FINAL3's destroy uses (EA 1.12 RVA 0x39EA50,
/// live-verified with death animations). The entry constructs a DamageInfo and
/// drives [Body+0x33C]'s complete pipeline, so the death decision, animation
/// dispatch and model recycling all run inside the game's own path. The
/// previous implementation called the bottom-level HP adjust and mirrored the
/// Die executor by hand, which left the body dead with no death animation.</summary>
public static class KillDispatcher
{
    public const uint MailboxOffset = 0x1880;
    public const uint StateOffset = MailboxOffset;
    public const uint BodyOffset = MailboxOffset + 4;
    public const uint DrawableOffset = MailboxOffset + 8;
    public const uint HpOffset = MailboxOffset + 0xC;
    public const uint Idle = 0, Pending = 1, Executing = 2, Success = 3, Reject = 4;

    public const uint CodeOffset = 0x1400;

    // FINAL3's destroy argument triple: damage type 6, death type 0x13, 0.
    private const uint DamageType = 6;
    private const uint DeathType = 0x13;

    public static byte[] Emit(nuint stubVA, nuint blockVA, nuint damageEntryVA, nuint rootVA)
    {
        uint start = checked((uint)stubVA), block = checked((uint)blockVA);
        uint api = checked((uint)damageEntryVA), root = checked((uint)rootVA);
        _ = root; // reserved: consumer layout passes the player root uniformly
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

        // Full damage entry call. Callee is thiscall(ecx = Body) with three
        // stack args and ret 0xC (verified contract), so we only align and
        // push: FXSAVE area first (SSE safe), then args in push order
        // (0, death-type, damage-type).
        a.Db(0x89, 0xE0);                               // old pushad ESP
        a.Db(0x81, 0xEC, 0x14, 0x02, 0, 0);             // reserve FX area + saved ESP
        a.Db(0x83, 0xE4, 0xF0);                         // stack alignment
        a.Db(0x89, 0x84, 0x24, 0, 0x02, 0, 0);          // [esp+200] = old ESP
        a.Db(0x0F, 0xAE, 0x04, 0x24);                   // fxsave [esp]
        a.Db(0xFC);                                     // CLD
        a.Db(0x6A, 0x00);                               // push 0        (arg3)
        a.Db(0x68); a.Db(BitConverter.GetBytes(DeathType));  // push 0x13    (arg2)
        a.Db(0x68); a.Db(BitConverter.GetBytes(DamageType)); // push 6       (arg1)
        a.Db(0x8B, Asm.Modrm(3, R.Ecx, R.Esi));         // mov ecx,esi : this = Body
        a.Db(0xE8);                                     // CALL rel32 (ret 0xC: callee cleans)
        int callDisp = a.Length; a.Db(0, 0, 0, 0);
        // esp is back at the FX base: the callee removed its 3 args itself.

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
public sealed class KillRequestMailbox : RequestMailbox
{
    public const uint Offset = KillDispatcher.MailboxOffset;

    public KillRequestMailbox(IInjectionMemory memory, nuint block) : base(memory, block, Offset) { }

    public new uint State => ReadTerminalState();

    protected override void Validate(BridgeRequest request)
    {
        RequireObject(request.Body, "destroy body");
        RequireObject(request.Drawable, "destroy drawable");
        RequireObject(request.Third, "destroy health component");
    }

    protected override void WritePayload(BridgeRequest request)
    {
        WriteU32(4, request.Body);
        WriteU32(8, request.Drawable);
        WriteU32(0xC, request.Third);
        // Damage-type / death-type are stub constants (6 / 0x13, FINAL3's
        // triple) — the full damage entry takes them as immediate stack args,
        // so no static DamageInfo lives in the mailbox anymore.
    }

    public void Submit(uint body, uint drawable, uint hp) =>
        Submit(BridgeRequest.For(body, drawable, hp));

    public uint ReadResult() => ReadTerminalState();
}
