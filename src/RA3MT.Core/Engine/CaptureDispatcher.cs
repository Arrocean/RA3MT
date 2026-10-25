using RA3MT.Core.Model;
using System.Buffers.Binary;
using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Game-thread ownership-transition consumer (FINAL3 capture, modern path).
/// Calls the verified transition function(Body, newContext, bool=0) after the same
/// selection/ownership gates the host applies; nothing runs unless the mailbox is
/// atomically claimed from Pending.</summary>
public static class CaptureDispatcher
{
    public const uint MailboxOffset = 0x1840;
    public const uint StateOffset = MailboxOffset;
    public const uint BodyOffset = MailboxOffset + 4;
    public const uint DrawableOffset = MailboxOffset + 8;
    public const uint Idle = 0, Pending = 1, Executing = 2, Success = 3, Reject = 4;

    public const uint CodeOffset = 0x1280;

    public static byte[] Emit(nuint stubVA, nuint blockVA, nuint transitionVA, nuint rootVA, GameLayout? layout = null)
    {
        layout ??= GameLayout.RedAlert3;
        uint start = checked((uint)stubVA), block = checked((uint)blockVA);
        uint api = checked((uint)transitionVA), root = checked((uint)rootVA);
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
        a.CmpRegMRegDisp32(R.Edi, R.Esi, layout.BodyDrawable); Branch(0x85, Rejected);
        a.CmpRegMRegDisp32(R.Esi, R.Edi, 0x138); Branch(0x85, Rejected);
        a.Db(0xF6, 0x87, 0x3D, 0x01, 0, 0, 0x40);       // selected bit 13D40
        Branch(0x84, Rejected);
        a.MovRegAbs(R.Eax, root); NonNull(R.Eax);
        a.MovRegRegDisp8(R.Ebp, R.Eax, 0x28); NonNull(R.Ebp);   // EBP = local side
        a.CmpRegMRegDisp32(R.Ebp, R.Esi, layout.Owner);
        Branch(0x84, Rejected);                         // already ours → no-op
        a.MovRegRegDisp32(R.Ebx, R.Ebp, 0xAC); NonNull(R.Ebx);   // EBX = local default context (0xAC > disp8)
        a.MovRegRegDisp8(R.Ecx, R.Ebx, 4); NonNull(R.Ecx);
        a.Db(0x39, Asm.Modrm(1, R.Ebp, R.Ecx), 8);      // cmp [ecx+8], ebp : context owner == local side?
        Branch(0x85, Rejected);

        a.Db(0x89, 0xE0);                               // old pushad ESP
        a.Db(0x81, 0xEC, 0x14, 0x02, 0, 0);             // reserve FX area + saved ESP
        a.Db(0x83, 0xE4, 0xF0);                         // stack alignment
        a.Db(0x89, 0x84, 0x24, 0, 0x02, 0, 0);          // [esp+200] = old ESP
        a.Db(0x0F, 0xAE, 0x04, 0x24);                   // fxsave [esp]
        a.Db(0xFC);                                     // CLD
        a.Db(0x83, 0xEC, 0x04);                         // pad: 2 args + ret = 12 → callee entry aligned
        a.Push8(0);                                     // arg2 = 0 (normal path, not serialization)
        a.Push(R.Ebx);                                  // arg1 = new context
        a.Db(0x8B, Asm.Modrm(3, R.Ecx, R.Esi));         // mov ecx,esi : this = Body
        a.Db(0xE8);                                     // CALL rel32
        int callDisp = a.Length; a.Db(0, 0, 0, 0);
        a.Db(0x83, 0xC4, 0x04);                         // add esp,4: undo pad, esp back at FX base
        a.MovRegAbs(R.Esi, Slot(BodyOffset));            // reload after callee clobber
        a.MovRegAbs(R.Eax, root);
        a.MovRegRegDisp8(R.Ebp, R.Eax, 0x28);
        a.CmpRegMRegDisp32(R.Ebp, R.Esi, layout.Owner);          // owner now local?
        Branch(0x85, Restore);
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

/// <summary>Single outstanding capture request; payload published before state.</summary>
public sealed class CaptureRequestMailbox : RequestMailbox
{
    public const uint Offset = CaptureDispatcher.MailboxOffset;

    public CaptureRequestMailbox(IInjectionMemory memory, nuint block) : base(memory, block, Offset) { }

    public new uint State => ReadTerminalState();

    protected override void Validate(BridgeRequest request)
    {
        RequireObject(request.Body, "capture body");
        RequireObject(request.Drawable, "capture drawable");
    }

    protected override void WritePayload(BridgeRequest request)
    {
        WriteU32(4, request.Body);
        WriteU32(8, request.Drawable);
    }

    public void Submit(uint body, uint drawable) => Submit(BridgeRequest.For(body, drawable));

    /// <summary>Result after a terminal state; Reject means a gate failed or the
    /// transition did not move the target to the local side.</summary>
    public uint ReadResult() => ReadTerminalState();
}
