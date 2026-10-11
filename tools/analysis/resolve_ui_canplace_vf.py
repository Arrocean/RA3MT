"""Read-only: resolve the placement manager's vt+0x48 (the UI can-place vf) in the
live process and disassemble it. If it is a small rule function, it is the exact
UI-side counterpart of RA1's Passes_Proximity_Check / Debug_Map early-out.
"""
import ctypes
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000
IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n]
    return None


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    blob = IMAGE.read_bytes()
    secs = sections(blob)

    h = k32.OpenProcess(0x0410, False, PID)
    if not h:
        raise SystemExit('OpenProcess failed')
    mgr = struct.unpack('<I', rd(h, 0xCF2410, 4))[0]
    vt = struct.unpack('<I', rd(h, mgr, 4))[0]
    print(f'manager 0x{mgr:X}  vtable 0x{vt:X}')
    print('\n  vtable slots (live):')
    for slot in range(0, 0x60, 4):
        fn = struct.unpack('<I', rd(h, vt + slot, 4))[0]
        mark = ''
        if slot == 0x48:
            mark = '   <== the UI can-place predicate calls this'
        if slot == 0x38:
            mark = '   <== percell calls this (box)'
        print(f'    +0x{slot:02X} = 0x{fn:X}{mark}')

    for slot in (0x48, 0x38):
        fn = struct.unpack('<I', rd(h, vt + slot, 4))[0]
        if not (BASE <= fn < 0xD0C000):
            print(f'\n  vt+0x{slot:X} = 0x{fn:X} not in module image; skip')
            continue
        print(f'\n===== vt+0x{slot:X} body 0x{fn:X} =====')
        code = read(blob, secs, fn, 0x100)
        if not code:
            print('  unreadable')
            continue
        for ins in md.disasm(code, fn):
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
            if ins.mnemonic.startswith('ret'):
                break


if __name__ == '__main__':
    main()
