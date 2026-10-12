"""Read-only: linear-sweep the live 1.13 .text, collect REAL callers of the
screen->world transform 0x60ECF0, and print the 14 instructions leading into
each call — to see how the game fills the 16-byte input buffer (x, y, +8, z).

Usage: py tools/analysis/find_transform_callers.py [pid]
"""
import ctypes
import struct
import subprocess
import sys

import capstone

TARGET_VA = 0x60ECF0
BASE = 0x400000


def find_game():
    for name in ('ra3_1.13.game', 'ra3_1.12.game'):
        try:
            out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}',
                                  '/FO', 'CSV', '/NH'], capture_output=True, timeout=10).stdout
        except Exception:
            continue
        for line in out.splitlines():
            if line.lower().startswith(b'"ra3_'):
                try:
                    return int(line.split(b'","')[1])
                except (ValueError, IndexError):
                    pass
    return None


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else find_game()
    if not pid:
        print('game not running')
        return
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x30, False, pid)
    if not h:
        print('OpenProcess failed')
        return

    def read(addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    pe = read(BASE, 0x600)
    lfanew = struct.unpack_from('<I', pe, 0x3C)[0]
    nsec = struct.unpack_from('<H', pe, lfanew + 6)[0]
    opt = struct.unpack_from('<H', pe, lfanew + 0x14)[0]
    text = None
    for i in range(nsec):
        off = lfanew + 0x18 + opt + i * 40
        name = pe[off:off + 8].rstrip(b'\0').decode(errors='replace')
        vsize, vaddr = struct.unpack_from('<II', pe, off + 8)
        if name == '.text':
            text = (vaddr, vsize)
    code = read(BASE + text[0], text[1])
    print(f'.text RVA 0x{text[0]:X} size 0x{text[1]:X}')

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    ctx = []
    hits = 0
    for ins in md.disasm(code, BASE + text[0]):
        ctx.append(ins)
        if len(ctx) > 15:
            ctx.pop(0)
        if ins.mnemonic == 'call' and ins.op_str == f'0x{TARGET_VA:x}':
            hits += 1
            print(f'\n== real caller #{hits} at 0x{ins.address:X} ==')
            for c in ctx:
                print(f'  0x{c.address:X}: {c.mnemonic} {c.op_str}')
            # also show a few instructions AFTER the call
    print(f'\ntotal real callers: {hits}')
    k32.CloseHandle(h)


if __name__ == '__main__':
    main()
