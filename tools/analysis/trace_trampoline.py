"""E9-trampoline call-chain tracer — the same detour mechanism the trainer's
MasterCode uses on its 22 hook sites (battle-proven), instead of the int3
debugger that killed the game five times.

A trampoline at the target function head replays the displaced instruction,
and before that snapshots registers + raw stack into a ring buffer inside the
game process. Python polls the buffer read-only. No exceptions, no debugger,
no thread suspension.

Usage: py tools/analysis/trace_trampoline.py kill|place [seconds] [pid]
  kill : target 0x7513F0 (death marker), displaced 'cmp byte [esp+4],0'
  place: target 0x511E00 (placement-grid check), displaced 'sub esp,0x38...'
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
    'place': (0x511E00, bytes.fromhex('83EC0C8B442410F30F1010')),  # sub esp,0C; mov eax,[esp+10]; movss xmm2,[eax]
}

# Stack-read depth: 12 dwords above the entry esp (48 bytes). Deeper reads
# could cross the top of a shallow thread stack into unmapped memory; 48
# bytes still covers eflags + return address + args + several frames.
MAX_SAMPLES = 48
SAMPLE_DWORDS = 20          # 8 pushad regs + 12 raw stack dwords
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
    class PE(ctypes.Structure):
        _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong),
                    ('th32ProcessID', ctypes.c_ulong), ('th32ModuleID', ctypes.c_ulong),
                    ('cntThreads', ctypes.c_ulong), ('th32ParentProcessID', ctypes.c_ulong),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong),
                    ('szExeFile', ctypes.c_char * 260)]
    procs = []
    lppe = PE()
    lppe.dwSize = ctypes.sizeof(PE)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if k32.Process32First(snap, ctypes.byref(lppe)):
        while k32.Process32Next(snap, ctypes.byref(lppe)):
            if lppe.szExeFile.decode().startswith('ra3_1.1'):
                procs.append(lppe.th32ProcessID)
    k32.CloseHandle(snap)
    return procs[0] if procs else None


def build_trampoline(tramp_va, data_va, site, displaced):
    """Hand-assembled x86. Sample = 8 pushad dwords (EDI,ESI,EBP,ESP,EBX,EDX,ECX,EAX)
    + 16 dwords of the raw stack at entry (return address, args, deeper frames)."""
    code = bytearray()
    code += b'\x9C'                                    # pushfd
    code += b'\x60'                                    # pushad
    code += b'\xFC'                                    # cld (rep movsd direction; game threads may carry DF=1)
    # edi = data page base
    code += b'\xBF' + struct.pack('<I', data_va)       # mov edi, imm32
    # eax = [edi] = sample count
    code += b'\x8B\x07'                                # mov eax,[edi]
    code += b'\x3D' + struct.pack('<I', MAX_SAMPLES)   # cmp eax, MAX
    skip_fixup = len(code)
    code += b'\x0F\x8D\x00\x00\x00\x00'                # jge skip (patched)
    # edi = data + 4 + count*SAMPLE_BYTES
    code += b'\x69\xC0' + struct.pack('<I', SAMPLE_BYTES)  # imul eax, eax, SAMPLE_BYTES
    code += b'\x8D\x7C\x07\x04'                        # lea edi,[edi+eax+4]
    # copy from esp: 24 dwords
    code += b'\x8B\xF4'                                # mov esi, esp
    code += b'\xB9' + struct.pack('<I', SAMPLE_DWORDS) # mov ecx, 24
    code += b'\xF3\xA5'                                # rep movsd
    # count++
    code += b'\xBF' + struct.pack('<I', data_va)       # mov edi, imm32
    code += b'\xFF\x07'                                # inc dword [edi]
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


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'kill'
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    pid = int(sys.argv[3], 0) if len(sys.argv) > 3 else find_game()
    if not pid:
        raise SystemExit('game not running')
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
            raw = read_mem(h, data, 4 + MAX_SAMPLES * SAMPLE_BYTES)
            if not raw:
                continue
            count = struct.unpack_from('<I', raw, 0)[0]
            if count > MAX_SAMPLES:
                count = MAX_SAMPLES
            while seen < count:
                off = 4 + seen * SAMPLE_BYTES
                regs = struct.unpack_from('<8I', raw, off)
                edi, esi, ebp, esp_pad, ebx, edx, ecx, eax = regs
                stack = struct.unpack_from('<16I', raw, off + 32)
                rets = [v for v in stack[1:] if TEXT_LO <= v < TEXT_HI]
                print(f'* #{seen} eax=0x{eax:X} ecx=0x{ecx:X} edx=0x{edx:X} '
                      f'esi=0x{esi:X} edi=0x{edi:X} eflags=0x{stack[0]:X} '
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
