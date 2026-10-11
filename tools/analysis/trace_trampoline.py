"""E9-trampoline call-chain tracer — the same detour mechanism the trainer's
MasterCode uses on its 22 hook sites (battle-proven), instead of the int3
debugger that killed the game five times.

A trampoline at the target function head replays the displaced instruction,
and before that snapshots registers + raw stack into a ring buffer inside the
game process. Python polls the buffer read-only. No exceptions, no debugger,
no thread suspension.

Usage: py tools/analysis/trace_trampoline.py kill|place|placeui|anchor|top|validator|percell|placehunt [seconds] [pid]
  kill     : target 0x7513F0 (death marker), displaced 'cmp byte [esp+4],0'
  place    : target 0xA3AAB0 (placement cell query, RVA 0x63AAB0)
  placeui  : target 0x707880 (UI can-place predicate, RVA 0x307880)
  anchor   : target 0x7A14B0 (anchor search, RVA 0x3A14B0)
  top      : target 0xA47300 (placement top, RVA 0x647300)
  validator: target 0xA42450 (distance consumer, RVA 0x642450)
  percell  : target 0xA2A1E0 (per-candidate-cell AABB evaluator, RVA 0x62A1E0)
  placehunt: six sites at once (top/validator/percell/AABB-FAIL/AABB-PASS/
             vf48 control) with per-site calls/sec output. Sweep the mouse
             in placement mode — no click needed.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

k32 = ctypes.windll.kernel32

TEXT_LO, TEXT_HI = 0x401000, 0xBD0000

# 1.13: (site VA, displaced bytes, replay tail = displaced, jump back = site+len)
SITES = {
    'kill': (0x7513F0, bytes.fromhex('807C240400')),           # cmp byte [esp+4],0
    'place': (0xA3AAB0, bytes.fromhex('83EC08568BF1')),          # sub esp,8; push esi; mov esi,ecx (THE live-hit placement cell query 0x63AAB0)
    'placeui': (0x707880, bytes.fromhex('56578B7C240C8BF1')),      # push esi; push edi; mov edi,[esp+0C]; mov esi,ecx (UI can-place predicate)
    'anchor': (0x7A14B0, bytes.fromhex('8B4424088B4C240483EC0C')),  # anchor search cdecl(hash, position, restriction, out); position = mouse world float3
    'top': (0xA47300, bytes.fromhex('578BF98B4C240C')),           # placement top (RVA 0x647300; sole caller 0xAA891C)
    'validator': (0xA42450, bytes.fromhex('83EC148B44241C')),     # loads distance from [[0xCF2CAC]+0xC] (RVA 0x642450)
    'percell': (0xA2A1E0, bytes.fromhex('83EC34535556')),         # per-candidate-cell evaluator + AABB gate (RVA 0x62A1E0)
}

# Multi-target placement hunt v3 — chain re-labeled after the SDK cross-check
# (2026-10-12): the AABB box proved to be the WORLD bounding box (single
# manager record 0,0,500,560 cells), so it is a coarse clip, not the gate.
# The real per-cell permission is the cell state machine:
#   percell PASS 0xA2A2A6 -> [side+0x20] as type idx -> 0xB34740
#   -> 0xB336E0 (world->cell, 0x34B/record) -> 0xB322D0:
#        byte[rec+0x32]!=0 -> 3 (blocked)
#        word[rec+idx*2+4]==0 -> 0 (no coverage for this placement type)
#        0xFFFF -> global default [0xD233DC]; else 1 (covered)
#   consumer 0xA2A2C5: cmp eax,1 (5-byte window right after the query call —
#   samples carry the cell state directly in eax).
# SDK ground truth: buildability comes from ProjectedBuildabilityInfo radius
# circles per building (ConYard Radius=600); BuildingPlacementDistance exists
# ONLY in SkirmishAI/AITargetHeuristicLibrary.xml (200..7000) — the 90.0 at
# [0xCF2CAC]+0xC is consumed by this chain but its identity is in doubt, and
# the whole chain may be the AI site-picking path (AI builds concurrently with
# the user, which would also explain the 100000 full-map-scan freeze).
# Frequency discipline: note whether the chain lights up in a NO-AI match when
# the user merely sweeps placement mode — that single observation separates
# player path from AI path.
PLACEHUNT = [
    (0xA42450, bytes.fromhex('83ec148b44241c'),       'validator 链入口(距离消费方)'),
    (0xA2A1E0, bytes.fromhex('83ec34535556'),         'percell 候选格评估'),
    (0xA2A283, bytes.fromhex('8b7424488b4e04'),       '粗筛-FAIL(世界包围盒外)'),
    (0xA2A2A6, bytes.fromhex('8b0d4c21cf00'),         '粗筛-PASS(进入逐格查询)'),
    (0xA2A2C5, bytes.fromhex('83f801b101'),           '★格状态 cmp eax,1(eax=0/1/3)'),
    (0x5F0930, bytes.fromhex('83ec18833df030cf0000'), 'vf48 UI谓词(vt+0x48 对照)'),
]
# slice layout: +0 hit count (never reset, drives frequency output),
# +4 written-sample idx (stops at cap), +0x10 sample area.
HUNT_SLICE = 0x400                # 0x10 + 8*120 = 0x3D0 <= 0x400
HUNT_SAMPLES = 8
HUNT_HDR = 0x10

# Stack-read depth: 30 dwords = 8 pushad regs + 1 pushfd eflags snapshot +
# 21 raw stack dwords (ret addr, args, deeper frames). The poller prints
# eflags=stack[0], ret=stack[1], arg1=stack[2]. 21 stack dwords stays well
# below any realistic thread-stack top (game call chains are deep).
MAX_SAMPLES = 48
SAMPLE_DWORDS = 30          # 8 pushad + 1 eflags + 21 raw stack dwords
SAMPLE_BYTES = SAMPLE_DWORDS * 4


def read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def write_mem(h, addr, data):
    old = ctypes.c_uint32()
    if not k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), 0x40, ctypes.byref(old)):
        return False
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), None)
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old, None)
    return ok


def threads_of(pid):
    class TE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                    ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long),
                    ("tpDeltaPri", ctypes.c_long), ("dwFlags", wt.DWORD)]
    snap = k32.CreateToolhelp32Snapshot(0x4, pid)
    te = TE()
    te.dwSize = ctypes.sizeof(TE)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def suspend_all(pid):
    handles = []
    for tid in threads_of(pid):
        th = k32.OpenThread(0x0002 | 0x0004 | 0x0001, False, tid)  # SUSPEND_RESUME
        if th:
            k32.SuspendThread(th)
            handles.append(th)
    return handles


def resume_all(handles):
    for th in handles:
        k32.ResumeThread(th)
        k32.CloseHandle(th)


def find_game():
    """Find the ra3_1.1x.game PID.

    Toolhelp Process32First fails with ERROR_BAD_LENGTH on this box
    (Python 3.14 x64 / Win11 26300: thread snapshots work, process snapshots
    don't), so shell out to tasklist instead — same thing Task Manager uses.
    Returns the PID as int, or None."""
    import subprocess
    for name in ('ra3_1.13.game', 'ra3_1.12.game'):
        try:
            out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}',
                                  '/FO', 'CSV', '/NH'],
                                 capture_output=True, timeout=10).stdout
        except Exception:
            continue
        for line in out.splitlines():
            if line.lower().startswith(b'"ra3_'):
                try:
                    return int(line.split(b'","')[1])
                except (ValueError, IndexError):
                    pass
    return None


def build_trampoline(tramp_va, data_va, site, displaced, max_samples=None):
    """Hand-assembled x86. Data slice header: +0 total hit count (never reset
    — the Python side turns its deltas into calls/sec), +4 written-sample
    index (frozen at cap), +0x10.. sample area. Sample = 8 pushad dwords
    (EDI,ESI,EBP,ESP,EBX,EDX,ECX,EAX) + 22 dwords of the raw stack at entry."""
    code = bytearray()
    code += b'\x9C'                                    # pushfd
    code += b'\x60'                                    # pushad
    code += b'\xFC'                                    # cld (rep movsd direction; game threads may carry DF=1)
    # edi = data page base
    code += b'\xBF' + struct.pack('<I', data_va)       # mov edi, imm32
    # hit count always increments (frequency observable even past cap)
    code += b'\xFF\x07'                                # inc dword [edi]
    # eax = [edi+4] = written sample idx
    code += b'\x8B\x47\x04'                            # mov eax,[edi+4]
    code += b'\x3D' + struct.pack('<I', max_samples or MAX_SAMPLES)   # cmp eax, cap
    skip_fixup = len(code)
    code += b'\x0F\x8D\x00\x00\x00\x00'                # jge skip (patched)
    # edi = data + HUNT_HDR + idx*SAMPLE_BYTES
    code += b'\x69\xC0' + struct.pack('<I', SAMPLE_BYTES)  # imul eax, eax, SAMPLE_BYTES
    code += b'\x8D\x7C\x07' + struct.pack('<B', HUNT_HDR)  # lea edi,[edi+eax+HUNT_HDR]
    # copy from esp: 30 dwords
    code += b'\x8B\xF4'                                # mov esi, esp
    code += b'\xB9' + struct.pack('<I', SAMPLE_DWORDS) # mov ecx, SAMPLE_DWORDS
    code += b'\xF3\xA5'                                # rep movsd
    # written idx++
    code += b'\xBF' + struct.pack('<I', data_va)       # mov edi, imm32
    code += b'\xFF\x47\x04'                            # inc dword [edi+4]
    # skip:
    skip_pos = len(code)
    struct.pack_into('<i', code, skip_fixup + 2, skip_pos - (skip_fixup + 6))
    code += b'\x61'                                    # popad
    code += b'\x9D'                                    # popfd
    # replay the displaced instruction bytes verbatim (no relative refs in them)
    code += displaced
    # jmp site+len(displaced)
    back = site + len(displaced)
    code += b'\xE9' + struct.pack('<i', back - (tramp_va + len(code) + 5))
    return bytes(code)


def run_placehunt(pid, duration):
    """Install one trampoline per candidate site; each has its own data slice.
    Polls every 0.5s: per-site hit-count delta (calls/sec) plus new samples.
    Trigger from the game: enter placement mode and sweep the mouse across the
    map — the preview recomputes every frame, no click needed."""
    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed (admin?)')
    if HUNT_HDR + HUNT_SAMPLES * SAMPLE_BYTES > HUNT_SLICE:
        raise SystemExit('hunt slice too small')

    # pre-verify every site still has its original bytes
    for va, displaced, label in PLACEHUNT:
        cur = read_mem(h, va, len(displaced))
        if cur != displaced:
            raise SystemExit(f'{label}: site bytes mismatch: {cur.hex() if cur else None}')

    data_size = len(PLACEHUNT) * HUNT_SLICE + 0x100
    data = k32.VirtualAllocEx(h, None, data_size, 0x3000, 0x40)
    if not data:
        raise SystemExit('VirtualAllocEx data failed')
    write_mem(h, data, b'\x00' * data_size)

    installs = []   # (va, displaced, label, tramp_va)
    tramp_page_end = None
    page = k32.VirtualAllocEx(h, None, 0x1000, 0x3000, 0x40)
    if not page:
        raise SystemExit('VirtualAllocEx tramp failed')
    tramp_page_end = page + 0x1000
    cursor = page
    try:
        for idx, (va, displaced, label) in enumerate(PLACEHUNT):
            code = build_trampoline(cursor, data + idx * HUNT_SLICE, va, displaced, HUNT_SAMPLES)
            if cursor + len(code) > tramp_page_end:
                raise SystemExit('trampoline page overflow')
            if not write_mem(h, cursor, code):
                raise SystemExit(f'write trampoline failed for {label}')
            installs.append((va, displaced, label, cursor))
            cursor += (len(code) + 15) & ~15
        # freeze once, patch every site, verify, resume
        frozen = suspend_all(pid)
        time.sleep(0.08)
        ok_all = True
        for va, displaced, label, tva in installs:
            patch = b'\xE9' + struct.pack('<i', tva - (va + 5))
            ok = write_mem(h, va, patch)
            if not ok or read_mem(h, va, 5) != patch:
                ok_all = False
                print(f'!! patch failed: {label}', flush=True)
        resume_all(frozen)
        if not ok_all:
            raise SystemExit('a patch failed; aborting')
        print(f'placehunt: {len(installs)} detours installed - enter placement mode and SWEEP THE MOUSE', flush=True)

        t0 = time.time()
        last_count = [0] * len(installs)   # hit counters at previous poll
        reported = [0] * len(installs)     # samples already printed
        poll_i = 0
        while time.time() - t0 < duration:
            time.sleep(0.5)
            poll_i += 1
            # every 2s: manager allowed-zone records snapshot — if the box is
            # dynamic (shrinks around the base during placement), the record
            # array will change while the user sweeps the map. A constant
            # single (0,0,mapW,mapH) record means AABB is just map clipping
            # and the EB46 patch would be a no-op.
            if poll_i % 4 == 0:
                mgrbuf = read_mem(h, 0xCF2410, 4)
                if mgrbuf:
                    mgr = struct.unpack('<I', mgrbuf)[0]
                    if mgr:
                        arr = read_mem(h, mgr + 0x54, 8)
                        if arr and len(arr) == 8:
                            beg, end = struct.unpack('<II', arr)
                            nrec = (end - beg) // 16 if beg and end >= beg else 0
                            first = struct.unpack('<4i', read_mem(h, beg, 16)) if nrec else None
                            print(f'[mgr] allowed-zone records={nrec}'
                                  + (f' first={first}' if first else ''), flush=True)
            for idx, (va, displaced, label, tva) in enumerate(installs):
                base = data + idx * HUNT_SLICE
                hdr = read_mem(h, base, HUNT_HDR)
                if not hdr:
                    continue
                hits, widx = struct.unpack_from('<II', hdr, 0)
                delta = hits - last_count[idx]
                last_count[idx] = hits
                if hits == 0:
                    continue
                print(f'{label}: {hits} hits (+{delta}/0.5s) samples={min(widx, HUNT_SAMPLES)}', flush=True)
                raw = read_mem(h, base + HUNT_HDR, HUNT_SAMPLES * SAMPLE_BYTES)
                if not raw:
                    continue
                widx = min(widx, HUNT_SAMPLES)
                while reported[idx] < widx:
                    off = reported[idx] * SAMPLE_BYTES
                    regs = struct.unpack_from('<8I', raw, off)
                    edi, esi, ebp, esp_pad, ebx, edx, ecx, eax = regs
                    stack = struct.unpack_from(f'<{SAMPLE_DWORDS - 8}I', raw, off + 32)
                    rets = [v for v in stack[1:] if TEXT_LO <= v < TEXT_HI]
                    print(f'  #{reported[idx]} eax=0x{eax:X} ecx=0x{ecx:X} esi=0x{esi:X} '
                          f'ret=0x{stack[1]:X} arg1=0x{stack[2]:X}', flush=True)
                    print('    rets: ' + ' '.join(hex(r) for r in rets), flush=True)
                    reported[idx] += 1
        return 0
    finally:
        frozen2 = suspend_all(pid)
        time.sleep(0.08)
        for va, displaced, label, tva in installs:
            write_mem(h, va, displaced)
        resume_all(frozen2)
        time.sleep(0.1)
        k32.VirtualFreeEx(h, page, 0, 0x8000)
        k32.VirtualFreeEx(h, data, 0, 0x8000)
        print('placehunt restored', flush=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'kill'
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    pid = int(sys.argv[3], 0) if len(sys.argv) > 3 else find_game()
    if not pid:
        raise SystemExit('未找到游戏进程——红警3要开到主菜单或对局里（启动器窗口不算）。\n'
                         '如果游戏确实开着，请带 PID 运行：placehunt 90 <PID>\n'
                         '（PID 查法：任务管理器 → 详细信息 → 找 ra3_1.13.game 那行的第二列数字）')
    if mode == 'placehunt':
        return run_placehunt(pid, duration)
    site, displaced = SITES[mode]
    print(f'PID {pid} mode {mode}: site 0x{site:X} displaced {displaced.hex()}', flush=True)

    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed (admin?)')

    original = read_mem(h, site, len(displaced))
    if original != displaced:
        raise SystemExit(f'site bytes mismatch: {original.hex() if original else None}')

    # allocate: trampoline page + data pages sized for the FULL ring buffer.
    # Root cause of crashes #6/#7: the data page was 0x1000 but the ring
    # buffer needs 4 + MAX_SAMPLES*SAMPLE_BYTES = 9220 bytes; in combat the
    # marker fires dozens of times per second, so the writer crossed the page
    # into unmapped memory long before the first 0.5s poll.
    data_size = 0x4000
    if 4 + MAX_SAMPLES * SAMPLE_BYTES > data_size - 0x100:
        raise SystemExit('ring buffer exceeds data allocation')
    tramp = k32.VirtualAllocEx(h, None, 0x1000, 0x3000, 0x40)
    data = k32.VirtualAllocEx(h, None, data_size, 0x3000, 0x40)
    if not tramp or not data:
        raise SystemExit('VirtualAllocEx failed')
    print(f'trampoline 0x{tramp:X} data 0x{data:X} ({data_size:#x})', flush=True)

    code = build_trampoline(tramp, data, site, displaced)
    if not write_mem(h, tramp, code):
        raise SystemExit('write trampoline failed')
    if not write_mem(h, data, b'\x00' * data_size):
        raise SystemExit('zero data pages failed')

    # Site patch — the ONLY safe way for a 5-byte instruction at a hot site:
    # freeze every thread, give the async suspends time to park them all in
    # the kernel, write the 5 bytes in one shot, verify, then resume. Byte-by-
    # byte patching is NOT safe: the intermediate opcode/modrm/SIB states
    # decode into instructions like 'or byte [ebx], imm8' that corrupt game
    # data (two crashes, same garbage EIP 0x74467401 — deterministic, not a
    # race).
    frozen = suspend_all(pid)
    time.sleep(0.08)   # let every async suspend reach its park point
    patch = b'\xE9' + struct.pack('<i', tramp - (site + 5))
    ok = write_mem(h, site, patch)
    verify = read_mem(h, site, 5) == patch if ok else False
    resume_all(frozen)
    if not ok or not verify:
        write_mem(h, site, displaced)
        raise SystemExit('patch failed or verify mismatch')
    print('detour installed (frozen-write, verified) - play normally...', flush=True)

    try:
        t0 = time.time()
        seen = 0
        while time.time() - t0 < duration:
            time.sleep(0.5)
            hdr = read_mem(h, data, HUNT_HDR)
            raw = read_mem(h, data + HUNT_HDR, MAX_SAMPLES * SAMPLE_BYTES) if hdr else None
            if not hdr or not raw:
                continue
            hits, widx = struct.unpack_from('<II', hdr, 0)
            if hits:
                print(f'[freq] {hits} hits (+{hits - getattr(main, "_last", 0)}/0.5s)', flush=True)
                main._last = hits
            if widx > MAX_SAMPLES:
                widx = MAX_SAMPLES
            while seen < widx:
                off = seen * SAMPLE_BYTES
                regs = struct.unpack_from('<8I', raw, off)
                edi, esi, ebp, esp_pad, ebx, edx, ecx, eax = regs
                stack = struct.unpack_from(f'<{SAMPLE_DWORDS - 8}I', raw, off + 32)
                rets = [v for v in stack[1:] if TEXT_LO <= v < TEXT_HI]
                print(f'* #{seen} eax=0x{eax:X} ecx=0x{ecx:X} edx=0x{edx:X} '
                      f'si=0x{esi:X} edi=0x{edi:X} eflags=0x{stack[0]:X} '
                      f'ret=0x{stack[1]:X} arg1=0x{stack[2]:X}', flush=True)
                print('   rets: ' + ' '.join(hex(r) for r in rets), flush=True)
                seen += 1
            if seen >= MAX_SAMPLES:
                break
    finally:
        # same freeze-write discipline for the restore (single shot; displaced
        # is at most 5 bytes for the current sites)
        frozen2 = suspend_all(pid)
        time.sleep(0.08)
        write_mem(h, site, displaced)
        resume_all(frozen2)
        time.sleep(0.1)
        k32.VirtualFreeEx(h, tramp, 0, 0x8000)
        k32.VirtualFreeEx(h, data, 0, 0x8000)
        print(f'restored; {seen} samples', flush=True)


if __name__ == '__main__':
    main()
