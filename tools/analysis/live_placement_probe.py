"""Read-only: dump live process state (module list, RSS, hook site bytes) and
disassemble the placement-verification chain 0x647300 -> 0x642450 -> 0x120780.

No writes to the game process.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections, read_va  # noqa: E402

k32 = ctypes.windll.kernel32
IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_BASE = 0x400000


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [('cb', wt.DWORD), ('PageFaultCount', wt.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


def live(pid):
    h = k32.OpenProcess(0x0410, False, pid)
    if not h:
        print(f'OpenProcess({pid}) failed')
        return None
    pmc = PROCESS_MEMORY_COUNTERS()
    pmc.cb = ctypes.sizeof(pmc)
    ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    print(f'PID {pid}: WorkingSet {pmc.WorkingSetSize/1048576:.1f} MB  '
          f'Peak {pmc.PeakWorkingSetSize/1048576:.1f} MB  '
          f'Commit {pmc.PagefileUsage/1048576:.1f} MB  PeakCommit {pmc.PeakPagefileUsage/1048576:.1f} MB')
    return h


def read_mem(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
    h = live(pid)
    blob = IMAGE.read_bytes()
    secs = sections(blob)

    print('\n--- live bytes at trace sites (VA, 16B) ---')
    sites = [0x64C970, 0x86F310, 0x818A00, 0x82B890, 0xA3AAB0, 0x5F0930,
             0x7513F0, 0x707880, 0x7A14B0, 0x642450, 0x647300]
    for va in sites:
        disk, _ = read_va(blob, secs, va, 16)
        got = read_mem(h, va, 16) if h else None
        mark = 'SAME' if got == disk else ('*** DIFFERENT (hook or stale) ***' if got else 'unreadable')
        print(f'0x{va:X}  disk {disk.hex(" ")}')
        if got is not None:
            print(f'          live {got.hex(" ")}  {mark}')

    print('\n--- placement globals ---')
    if h:
        for name, gva, off in [('placementDistance 1.13', 0x8F2CAC, 0xC),
                               ('ThePlacementGrid 1.13', 0xCE21CC, None)]:
            raw = read_mem(h, gva, 4)
            if not raw:
                print(f'{name}: unreadable')
                continue
            obj = struct.unpack('<I', raw)[0]
            print(f'{name}: [0x{gva:X}] = 0x{obj:X}')
            if off is not None and obj >= 0x10000:
                v = read_mem(h, obj + off, 4)
                if v:
                    print(f'    [+0x{off:X}] = float {struct.unpack("<f", v)[0]}  raw {v.hex(" ")}')
                    q = read_mem(h, obj, 0x40)
                    if q:
                        print(f'    obj head: {q.hex(" ")}')

    print('\n--- disasm: placement chain 0x647300 / 0x642450 (disk) ---')
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print('capstone missing')
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for va, n in [(0x647300, 0x120), (0x642450, 0x140), (0x64C970, 0x60)]:
        code, sec = read_va(blob, secs, va, n)
        print(f'\n== 0x{va:X} ({sec}) ==')
        for ins in md.disasm(code, va):
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
            if ins.mnemonic in ('ret', 'retn') or ins.mnemonic.startswith('ret'):
                break


if __name__ == '__main__':
    main()
