"""Read-only: is the AABB branch a safe patch point?

Dump percell 0xA2A1E0 from entry to its ret, split the FAIL path (0xA2A283) from
the PASS path (0xA2A2A6), and dump the manager vtable slot vt+0x38 that produces
the box, plus the grid query 0x5065A0 - to see whether the four comiss tests are
really "inside buildable region" and whether the PASS path still runs the
terrain/occupancy checks the report claims are preserved.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_112 = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game')
BASE = 0x400000


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n]
    return None


def dump(md, blob, secs, va, n, stop_at=None, title=''):
    print(f'\n===== {title} 0x{va:X} =====')
    code = read(blob, secs, va, n)
    for ins in md.disasm(code, va):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret') or (stop_at and ins.address >= stop_at):
            break


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    blob = IMAGE.read_bytes()
    secs = sections(blob)

    # full percell, both paths
    dump(md, blob, secs, 0xA2A1E0, 0x100, stop_at=0xA2A2A5,
         title='percell full (1.13)')

    print('\n--- what the manager vtable slot +0x38 points at (runtime, read-only) ---')
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x0410, False, 38552)
    if h:
        def u32(va):
            buf = ctypes.create_string_buffer(4)
            got = ctypes.c_size_t()
            if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, 4, ctypes.byref(got)):
                return None
            return struct.unpack('<I', buf.raw)[0]
        mgr = u32(0xCF2410)
        print(f'  [0xCF2410] manager = 0x{mgr:X}' if mgr else '  manager unreadable')
        if mgr and mgr > 0x10000:
            vt = u32(mgr)
            print(f'  vtable = 0x{vt:X}')
            if vt and vt > 0x10000:
                for slot in (0x20, 0x28, 0x38, 0x48, 0x50):
                    fn = u32(vt + slot)
                    print(f'    vt+0x{slot:X} = 0x{fn:X}')
                    if fn and BASE <= fn < 0xD0C000:
                        dump(md, blob, secs, fn, 0x40, title=f'vf+0x{slot:X} body')
    else:
        print('  game not available')

    print('\n===== 1.12 percell branch bytes =====')
    blob2 = IMAGE_112.read_bytes()
    secs2 = sections(blob2)
    raw = read(blob2, secs2, 0xA252E0, 0x60)
    for ins in md.disasm(raw, 0xA252E0):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')


if __name__ == '__main__':
    main()
