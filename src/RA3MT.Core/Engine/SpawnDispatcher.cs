using System.Buffers.Binary;
using RA3MT.Core.Memory;

namespace RA3MT.Core.Engine;

/// <summary>Game-thread spawn consumer: resolves a unit template either directly
/// (copy-selected path, holder already known from the selection chain) or by the
/// game's static WB-string hash table (reinforcement-code / MCV path), then calls
/// the re-packed map-start spawn wrapper — the same factory/position/activate/
/// register sequence the game itself runs at map start. The wrapper is cdecl
/// (ignored, templateHolder, float3* pos, ownerSide, ignored) → eax = new Body,
/// null-safe on failure, per the mocked-ABI verification.</summary>
public static class SpawnDispatcher
{
    public const uint MailboxOffset = 0x18C0;
    public const uint StateOffset = MailboxOffset;
    public const uint HashOffset = MailboxOffset + 4;            // 0 = direct holder
    public const uint HolderOffset = MailboxOffset + 8;          // used when hash == 0
    public const uint PosXOffset = MailboxOffset + 0xC;          // float3, read by wrapper
    public const uint PosYOffset = MailboxOffset + 0x10;
    public const uint PosZOffset = MailboxOffset + 0x14;
    public const uint OwnerOffset = MailboxOffset + 0x18;        // 0 = local side via playerRoot
    public const uint ResultBodyOffset = MailboxOffset + 0x1C;   // wrapper return value
    public const uint ResolvedHolderOffset = MailboxOffset + 0x20;
    public const uint MouseModeOffset = MailboxOffset + 0x24;     // !=0: derive pos from the live mouse on the game thread
    public const uint Idle = 0, Pending = 1, Executing = 2, Success = 3, Reject = 4;

    public const uint CodeOffset = 0x1580;

    public static byte[] Emit(nuint stubVA, nuint blockVA, nuint spawnWrapperVA,
        nuint hashLookupVA, nuint hashTableGlobalVA, nuint rootVA,
        nuint mouseObjGlobalVA, nuint transformVA)
    {
        uint start = checked((uint)stubVA), block = checked((uint)blockVA);
        uint wrapper = checked((uint)spawnWrapperVA), lookup = checked((uint)hashLookupVA);
        uint tableGlobal = checked((uint)hashTableGlobalVA), root = checked((uint)rootVA);
        uint mouseObj = checked((uint)mouseObjGlobalVA), transform = checked((uint)transformVA);
        uint Slot(uint offset) => checked(block + offset);
        var a = new Asm();
        var labels = new Dictionary<int, int>();
        var patches = new List<(int position, int label)>();
        const int Exit = 1, Rejected = 2, Direct = 3, HaveTemplate = 4,
            HaveOwner = 5, FxReject = 6, FxDone = 7, MouseSkip = 8;
        void Mark(int id) { a.Label(id); labels.Add(id, a.Length); }
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

        // ---- template resolution ----
        a.MovRegAbs(R.Esi, Slot(HashOffset));
        a.TestRegReg(R.Esi, R.Esi);
        a.JeShort(Direct);
        // Hash path: ecx = [hash table owner global]; push hash; call TemplateHashLookup.
        // The table is a startup-static registry; reading it on the game thread is the
        // same pattern the game's own map-start caller uses. Callee is thiscall ret 4.
        a.MovRegAbs(R.Ecx, tableGlobal); NonNull(R.Ecx);
        a.Push(R.Esi);
        a.Db(0xE8);                                     // CALL rel32
        int lookupDisp = a.Length; a.Db(0, 0, 0, 0);
        a.MovM32AbsReg(R.Eax, Slot(ResolvedHolderOffset));
        a.TestRegReg(R.Eax, R.Eax);
        Branch(0x84, Rejected);                        // jz rel32: target is beyond rel8 range
        a.Db(0x8B, Asm.Modrm(3, R.Edi, R.Eax));         // edi = resolved holder
        a.JmpShort(HaveTemplate);
        Mark(Direct);
        a.MovRegAbs(R.Edi, Slot(HolderOffset));
        NonNull(R.Edi);
        // The wrapper dereferences [holder+0x14] (descriptor) unconditionally;
        // gate it before the call so a stale holder rejects instead of crashing.
        a.MovRegRegDisp32(R.Eax, R.Edi, 0x14);
        NonNull(R.Eax);
        Mark(HaveTemplate);

        // ---- owner ----
        a.MovRegAbs(R.Ebp, Slot(OwnerOffset));
        a.TestRegReg(R.Ebp, R.Ebp);
        a.JneShort(HaveOwner);
        a.MovRegAbs(R.Eax, root); NonNull(R.Eax);
        a.MovRegRegDisp8(R.Eax, R.Eax, 0x28); NonNull(R.Eax);
        a.Db(0x8B, Asm.Modrm(3, R.Ebp, R.Eax));         // ebp = local side
        Mark(HaveOwner);

        // ---- wrapper call: cdecl(0, edi, &mailbox.pos, ebp, 0) ----
        a.Db(0x89, 0xE0);                               // old pushad ESP
        a.Db(0x81, 0xEC, 0x14, 0x02, 0, 0);             // reserve FX area + saved ESP
        a.Db(0x83, 0xE4, 0xF0);                         // stack alignment
        a.Db(0x89, 0x84, 0x24, 0, 0x02, 0, 0);          // [esp+200] = old ESP
        a.Db(0x0F, 0xAE, 0x04, 0x24);                   // fxsave [esp]
        a.Db(0xFC);                                     // CLD
        // ---- mouse mode: FINAL3-style live mouse → world on the game thread ----
        // MouseMode != 0: read the mouse object's integer screen pixels
        // (+0x3C/+0x40), convert to floats at [esp+0x204..0x20B] (inside the
        // reserved FX area, above the saved old-ESP), call the game's own
        // screen->world transform cdecl(screenXY*, out*, 0, 0; ret al), and
        // let it overwrite the mailbox position float3 the wrapper consumes.
        a.MovRegAbs(R.Eax, Slot(MouseModeOffset));
        a.TestRegReg(R.Eax, R.Eax);
        Branch(0x84, MouseSkip);                        // not mouse mode: keep mailbox pos
        a.MovRegAbs(R.Eax, mouseObj); NonNull(R.Eax);
        a.Db(0xDF, 0x40, 0x3C);                         // fild dword [eax+0x3C]
        a.Db(0xD9, 0x5C, 0x24, 0x04);                   // fstp dword [esp+0x204]
        a.Db(0xDF, 0x40, 0x40);                         // fild dword [eax+0x40]
        a.Db(0xD9, 0x5C, 0x24, 0x08);                   // fstp dword [esp+0x208]
        a.Push8(0);
        a.Push8(0);
        a.Db(0x68); a.Db(BitConverter.GetBytes(Slot(PosXOffset)));  // out = mailbox pos float3
        a.Db(0x8D, 0x44, 0x24, 0x14);                   // lea eax,[esp+0x14] = &screenXY
        a.Db(0x50);                                     // push &screenXY
        a.Db(0xE8);                                     // CALL rel32 transform
        int transformDisp = a.Length; a.Db(0, 0, 0, 0);
        a.Db(0x83, 0xC4, 0x10);                         // cdecl: caller cleans 4 args
        a.TestRegReg(R.Eax, R.Eax);
        Branch(0x84, FxReject);                         // transform failed -> reject
        Mark(MouseSkip);
        a.Db(0x83, 0xEC, 0x08);                         // pad: 5 args + ret = 24 → wrapper entry esp%16 == 0
        a.Push8(0);                                     // arg5: wrapper ignores it (FINAL3 passes [side+0x10])
        a.Push(R.Ebp);                                  // arg4 = owner side
        a.Db(0x68); a.Db(BitConverter.GetBytes(Slot(PosXOffset))); // arg3 = float3 in mailbox
        a.Push(R.Edi);                                  // arg2 = template holder
        a.Push8(0);                                     // arg1 (ignored)
        a.Db(0xE8);                                     // CALL rel32
        int callDisp = a.Length; a.Db(0, 0, 0, 0);
        a.Db(0x83, 0xC4, 0x08);                         // undo pad
        a.Db(0x81, 0xC4, 0x14, 0x00, 0x00, 0x00);       // cdecl caller-cleans 5 args
        a.MovM32AbsReg(R.Eax, Slot(ResultBodyOffset)); // eax = new body (or 0)
        a.TestRegReg(R.Eax, R.Eax);
        a.JeShort(FxReject);
        a.MovM32Abs(Slot(StateOffset), Success);
        a.JmpShort(FxDone);
        Mark(FxReject);
        a.MovM32Abs(Slot(StateOffset), Reject);
        Mark(FxDone);
        a.Db(0x0F, 0xAE, 0x0C, 0x24);                   // fxrstor [esp]
        a.Db(0x8B, 0xA4, 0x24, 0, 0x02, 0, 0);          // restore old pushad ESP
        Jump(Exit);
        Mark(Rejected);
        a.MovM32Abs(Slot(StateOffset), Reject);
        Mark(Exit);
        a.Popad(); a.Popfd(); a.Ret();

        var bytes = a.Build(start);
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(lookupDisp, 4),
            unchecked((int)(lookup - (start + (uint)(lookupDisp + 4)))));
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(callDisp, 4),
            unchecked((int)(wrapper - (start + (uint)(callDisp + 4)))));
        BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(transformDisp, 4),
            unchecked((int)(transform - (start + (uint)(transformDisp + 4)))));
        foreach (var (position, label) in patches)
            BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(position, 4),
                checked(labels[label] - (position + 4)));
        return bytes;
    }
}

/// <summary>Single outstanding spawn request. Publishes the payload before the
/// state byte; template may be given directly (holder path) or as a WB-string
/// hash resolved on the game thread through the game's static template table.</summary>
public sealed class SpawnRequestMailbox : RequestMailbox
{
    public const uint Offset = SpawnDispatcher.MailboxOffset;

    private uint[] _position = [];
    private bool _mouseMode;

    public SpawnRequestMailbox(IInjectionMemory memory, nuint block) : base(memory, block, Offset) { }

    public new uint State => ReadTerminalState();

    protected override void Validate(BridgeRequest request)
    {
        var hash = request.Third;
        var holder = request.Fourth;
        if (hash == 0 && holder < 0x10000)
            throw new ArgumentException("Spawn request needs a hash or a template holder");
        if (request.Body != 0 && request.Body < 0x10000)
            throw new ArgumentException("Invalid spawn owner");
    }

    protected override void WritePayload(BridgeRequest request)
    {
        WriteU32(4, request.Third);   // hash
        WriteU32(8, request.Fourth);  // holder
        WriteU32(0xC, _position.Length > 0 ? _position[0] : 0u);
        WriteU32(0x10, _position.Length > 1 ? _position[1] : 0u);
        WriteU32(0x14, _position.Length > 2 ? _position[2] : 0u);
        WriteU32(0x18, request.Body); // owner (0 = resolve local side)
        WriteU32(0x1C, 0u);
        WriteU32(0x20, 0u);
        WriteU32(0x24, _mouseMode ? 1u : 0u);
    }

    /// <summary>Submit a spawn carrying an explicit world position and owner.
    /// The position is staged on the instance so the base publish sequence stays
    /// the single place that writes the mailbox.</summary>
    public void Submit(uint hash, uint holder, float x, float y, float z, uint owner)
    {
        if (!float.IsFinite(x) || !float.IsFinite(y) || !float.IsFinite(z))
            throw new ArgumentException("Spawn position must be finite");
        _mouseMode = false;
        _position = [BitConverter.SingleToUInt32Bits(x), BitConverter.SingleToUInt32Bits(y),
                     BitConverter.SingleToUInt32Bits(z)];
        Submit(BridgeRequest.For(owner, 0, hash, holder));
    }

    /// <summary>FINAL3-style mouse mode: the stub derives the spawn position on
    /// the game thread from the live mouse (screen pixels → the game's own
    /// screen-to-world transform), so the trainer never samples a possibly
    /// frozen or mis-scaled world-coordinate cache. The fallback position is
    /// only used when the transform itself fails.</summary>
    public void SubmitAtMouse(uint hash, uint holder, float x, float y, float z, uint owner)
    {
        if (!float.IsFinite(x) || !float.IsFinite(y) || !float.IsFinite(z))
            throw new ArgumentException("Spawn fallback position must be finite");
        _mouseMode = true;
        _position = [BitConverter.SingleToUInt32Bits(x), BitConverter.SingleToUInt32Bits(y),
                     BitConverter.SingleToUInt32Bits(z)];
        Submit(BridgeRequest.For(owner, 0, hash, holder));
    }

    public (uint state, uint resultBody, uint resolvedHolder) ReadResult()
    {
        var state = ReadTerminalState();
        if (state is not (Success or Reject)) return (state, 0, 0);
        return (state, ReadU32(0x1C), ReadU32(0x20));
    }
}
