using RA3MT.Core.Model;
using System.Buffers.Binary;

namespace RA3MT.Core.Engine;

/// <summary>Pure x86 CALL target for the rank mailbox; emits bytes only.</summary>
/// <remarks>
/// Requires the game's SSE/FXSAVE support. The caller publishes immutable body,
/// drawable and tracker fields before state Pending, and must not reset/reuse
/// the mailbox until a terminal state. Null and relationship checks cannot make
/// stale non-null pointers safe if the game destroys objects concurrently.
///
/// There is deliberately NO "currently selected" gate: FINAL3 promotes any
/// locally-owned unit, and the reinforcement flow ranks units it just spawned
/// (never selected). Liveness is covered by the body/drawable/tracker
/// cross-links, the local-owner check and the XP-tracker eligibility byte.
/// </remarks>
public static class RankDispatcher
{
    public const uint MailboxOffset = 0x1800;
    public const uint StateOffset = MailboxOffset;
    public const uint BodyOffset = MailboxOffset + 4;
    public const uint DrawableOffset = MailboxOffset + 8;
    public const uint TrackerOffset = MailboxOffset + 0xC;
    public const uint RankBeforeOffset = MailboxOffset + 0x10;
    public const uint RankAfterOffset = MailboxOffset + 0x14;
    public const uint Idle = 0, Pending = 1, Executing = 2, Success = 3, Reject = 4;

    public const uint CodeOffset = 0x1100;

    public static byte[] EmitMoneyBridge(nuint stubVA, nuint siteEnd, nuint blockVA, nuint rootVA,
        string stubId, params uint[] dispatcherOffsets)
        => EmitMoneyBridge(GameLayout.RedAlert3, stubVA, siteEnd, blockVA, rootVA, stubId, dispatcherOffsets);

    public static byte[] EmitMoneyBridge(GameLayout layout, nuint stubVA, nuint siteEnd, nuint blockVA, nuint rootVA,
        string stubId, params uint[] dispatcherOffsets)
    {
        var original = StubGen.Emit(stubId, stubVA + (nuint)(5 * dispatcherOffsets.Length),
            siteEnd, blockVA, rootVA, layout: layout);
        var bytes = new byte[original.Length + 5 * dispatcherOffsets.Length];
        for (var i = 0; i < dispatcherOffsets.Length; i++)
        {
            bytes[5 * i] = 0xE8;
            BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(5 * i + 1, 4),
                unchecked((int)(blockVA + dispatcherOffsets[i] - (stubVA + (nuint)(5 * i + 5)))));
        }
        original.CopyTo(bytes, 5 * dispatcherOffsets.Length);
        return bytes;
    }

    public static byte[] Emit(nuint stubVA, nuint blockVA, nuint rankFunctionVA, nuint rootVA, GameLayout? layout = null)
    {
        layout ??= GameLayout.RedAlert3;
        uint start = checked((uint)stubVA), block = checked((uint)blockVA);
        uint api = checked((uint)rankFunctionVA), root = checked((uint)rootVA);
        uint Slot(uint offset) => checked(block + offset);
        var a = new Asm();
        var labels = new Dictionary<int, int>();
        var patches = new List<(int position, int label)>();
        const int Exit = 1, Rejected = 2, Restore = 3, Terminal = 4;
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
        Branch(0x85, Exit);                             // failed claim: no payload access

        a.MovRegAbs(R.Esi, Slot(BodyOffset)); NonNull(R.Esi);
        a.MovRegAbs(R.Edi, Slot(DrawableOffset)); NonNull(R.Edi);
        a.MovRegAbs(R.Ecx, Slot(TrackerOffset)); NonNull(R.Ecx);
        a.CmpRegMRegDisp32(R.Edi, R.Esi, layout.BodyDrawable); Branch(0x85, Rejected);
        a.CmpRegMRegDisp32(R.Esi, R.Edi, 0x138); Branch(0x85, Rejected);
        a.CmpRegMRegDisp32(R.Ecx, R.Esi, layout.Tracker); Branch(0x85, Rejected);
        a.MovRegAbs(R.Eax, root); NonNull(R.Eax);
        a.MovRegRegDisp8(R.Eax, R.Eax, 0x28); NonNull(R.Eax);
        a.CmpRegMRegDisp32(R.Eax, R.Esi, layout.Owner); Branch(0x85, Rejected);
        a.MovRegRegDisp8(R.Eax, R.Ecx, 4); NonNull(R.Eax);
        a.MovRegRegDisp8(R.Eax, R.Eax, 0x14); NonNull(R.Eax);
        a.Db(0x80, 0xB8); a.Db(BitConverter.GetBytes(layout.Eligibility)); a.Db(0);          // eligibility != 0
        Branch(0x84, Rejected);
        a.MovRegRegDisp8(R.Eax, R.Ecx, 0x24);
        a.MovM32AbsReg(R.Eax, Slot(RankBeforeOffset));

        a.Db(0x89, 0xE0);                               // old pushad ESP
        a.Db(0x81, 0xEC, 0x14, 0x02, 0, 0);             // reserve FX area + saved ESP
        a.Db(0x83, 0xE4, 0xF0);                         // stack alignment
        a.Db(0x89, 0x84, 0x24, 0, 0x02, 0, 0);          // [esp+200] = old ESP
        a.Db(0x0F, 0xAE, 0x04, 0x24);                   // fxsave [esp]
        a.Db(0xFC);                                     // CLD; flags restored on return
        a.Push8(0); a.Push8(1); a.Push8(3);              // API arguments
        a.Db(0xE8);                                     // CALL rel32
        int callDisp = a.Length; a.Db(0, 0, 0, 0);
        a.MovRegAbs(R.Ecx, Slot(TrackerOffset));
        a.MovRegRegDisp8(R.Eax, R.Ecx, 0x24);
        a.MovM32AbsReg(R.Eax, Slot(RankAfterOffset));
        a.Db(0x3B, 0x05); a.Db(BitConverter.GetBytes(Slot(RankBeforeOffset)));
        Branch(0x86, Restore);                          // unsigned after <= before
        a.MovM32Abs(Slot(StateOffset), Success);
        Jump(Terminal);
        Label(Restore);
        a.MovM32Abs(Slot(StateOffset), Reject);
        Label(Terminal);
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
