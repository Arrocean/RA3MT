"""Read-only: the manager box predicate vt+0x38 = 0x5F07D0 (verified live:
[0xCF2410] obj vtable 0xC13A10, +0x38 -> 0x5F07D0, +0x48 -> 0x5F0930 = vf48 —
same manager class, two methods).

Semantics (full continuous disassembly below):
    out = {0, 0, yMin, 0, 0, yMax}
    for each 16-byte record in manager->[0x54, 0x58):   ; count = (end-beg)/16
        rec[0]*10 < out.minX -> out.minX = rec[0]*10    ; *10 = cell->world
        rec[4]*10 < out.minZ -> out.minZ = rec[4]*10
        rec[8]*10 > out.maxX -> out.maxX = rec[8]*10
        rec[0xC]*10 > out.maxZ -> out.maxZ = rec[0xC]*10
    out.yMin = mgr->[0x1438]; out.yMax = mgr->[0x143C]
So the box is the bounding rectangle of ALL allowed-build rectangles the
manager tracks (one 16B record per allowed zone), scaled to world units.
percell 0xA2A1E0 then requires each candidate cell's world X/Z to fall inside
this union box (4x comiss; the Y fields are written but never compared).

The live section prints the actual records so we can see what the allowed
zones look like mid-match (expect: rectangles around own buildings).
"""
import ctypes
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections, read_va  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
BASE = 0x400000
MANAGER_GLOBAL = 0xCF2410


def disasm_predicate(blob, secs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    code, _ = read_va(blob, secs, 0x5F07D0, 0x100)
    print('===== manager box predicate vt+0x38 = 0x5F07D0 (continuous) =====')
    for ins in md.disasm(code, 0x5F07D0):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            break


def live_records(pid):
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x10 | 0x20, False, pid)
    if not h:
        print(f'live: OpenProcess({pid}) failed')
        return

    def rd(addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    mgr = struct.unpack('<I', rd(MANAGER_GLOBAL, 4))[0]
    if not mgr:
        print('live: manager global empty (no match?)')
        k32.CloseHandle(h)
        return
    beg, end = struct.unpack('<II', rd(mgr + 0x54, 8))
    ymin, ymax = struct.unpack('<ff', rd(mgr + 0x1438, 8))
    n = (end - beg) // 16 if beg and end >= beg else 0
    print(f'\n===== live manager 0x{mgr:X}: {n} allowed-zone records =====')
    print(f'  height window [0x1438]: y={ymin}..{ymax}')
    box = None
    for i in range(min(n, 12)):
        rec = struct.unpack('<4i', rd(beg + i * 16, 16))
        w = (rec[0] * 10, rec[1] * 10, rec[2] * 10, rec[3] * 10)
        print(f'  #{i}: cells {rec} -> world x[{w[0]}..{w[2]}] z[{w[1]}..{w[3]}]'
              f'  ({(w[2]-w[0])/10}x{(w[3]-w[1])/10} cells)')
        b = (min(b0 for b0 in (w[0], box[0]) if b0 is not None) if box else w[0])
        if box:
            box = (min(box[0], w[0]), min(box[1], w[1]), max(box[2], w[2]), max(box[3], w[3]))
        else:
            box = w
    if box:
        print(f'  union box: x[{box[0]}..{box[2]}] z[{box[1]}..{box[3]}] '
              f'({(box[2]-box[0])//10}x{(box[3]-box[1])//10} cells)')
    k32.CloseHandle(h)


if __name__ == '__main__':
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    disasm_predicate(blob, secs)
    pid = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0
    if pid:
        live_records(pid)
    else:
        print('\n(pass a PID to print live allowed-zone records)')
