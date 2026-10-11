"""Read-only: dump the .rdata float-constant neighbourhoods that contain 90.0
and find which .text operands reference them (the real consumers).
"""
import struct
from pathlib import Path

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
BASE = 0x400000
TEXT_VA, TEXT_RAW, TEXT_VS, TEXT_RS = 0x1000, 0x1000, 0x7CCB0A, 0x7CD000
RD_VA, RD_RAW, RD_VS, RD_RS = 0x7CE000, 0x7CE000, 0xE4C1A, 0xE5000


def main():
    disk = IMAGE.read_bytes()
    rdata = disk[RD_RAW:RD_RAW + RD_VS]
    text = disk[TEXT_RAW:TEXT_RAW + TEXT_VS]

    for centre in (0xBED828, 0xC67470):
        va = centre
        off = va - BASE - RD_VA
        print(f'\n===== .rdata around 0x{va:X} =====')
        for k in range(-5, 9):
            p = off + k * 4
            u = struct.unpack_from('<I', rdata, p)[0]
            f = struct.unpack_from('<f', rdata, p)[0]
            print(f'  0x{BASE + RD_VA + p:08X}  {u:08X}  float {f:>16.7g}')

        print(f'  --- .text operands pointing into [0x{va - 0x200:X}, 0x{va + 0x200:X}) ---')
        lo, hi = va - 0x200, va + 0x200
        n = 0
        for i in range(0, len(text) - 4):
            v = struct.unpack_from('<I', text, i)[0]
            if lo <= v < hi:
                print(f'    VA 0x{BASE + TEXT_VA + i:X} -> 0x{v:X}  '
                      f'ctx {text[max(0, i - 10):i + 10].hex(" ")}')
                n += 1
                if n > 25:
                    break
        if n == 0:
            print('    (no direct operand - float constants are usually reached as [reg+disp])')

    print('\n===== is 90.0f reachable as an absolute operand anywhere? =====')
    p90 = struct.pack('<f', 90.0)
    for i in range(0, len(text) - 4):
        if text[i:i + 4] == p90:
            print(f'  VA 0x{BASE + TEXT_VA + i:X}')


if __name__ == '__main__':
    main()
