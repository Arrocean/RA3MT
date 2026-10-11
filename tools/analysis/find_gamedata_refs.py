"""Read-only: find every code reference to the local GameData object
([0x8F2CAC]) and to its +0x0C field (BuildingPlacementDistance).

Scans for:
  A1 AC 2C 8F 00          mov eax, [0x8F2CAC]
  A3 AC 2C 8F 00          mov [0x8F2CAC], eax
  8B xx AC 2C 8F 00       mov reg, [0x8F2CAC]
  8B xx 0C                mov reg, [reg+0x0C]   (context: right after a load of
                                                  the GameData pointer)
then disassembles a window around each hit.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_BASE = 0x400000
GAMEDATA_VA = 0x8F2CAC          # 1.13 placementDistance global (pointer holder)
GAMEDATA_VA_112 = 0x8EE98C      # 1.12


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    text = [(n, sva, raw, min(vs, rs)) for n, sva, vs, raw, rs in secs if n == '.text']
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    for target, label in ((GAMEDATA_VA, '1.13'), (GAMEDATA_VA_112, '1.12')):
        pat = struct.pack('<I', target)
        hits = []
        for name, sva, raw, size in text:
            data = blob[raw:raw + size]
            start = 0
            while True:
                i = data.find(pat, start)
                if i < 0:
                    break
                start = i + 1
                hits.append((IMAGE_BASE + sva + i, data[i - 2:i + 10]))
        print(f'\n########## GameData global 0x{target:X} ({label}): {len(hits)} operand hits ##########')
        for va, ctx in hits:
            # operand address is va; instruction may start up to 3 bytes earlier
            for back in (2, 1, 3):
                ins_va = va - back
                code = blob[text[0][2] + (ins_va - text[0][1] - IMAGE_BASE):
                            text[0][2] + (ins_va - text[0][1] - IMAGE_BASE) + 16]
                ins = next(iter(md.disasm(code, ins_va)), None)
                if ins and pat in ins.bytes:
                    print(f'  0x{ins_va:X}  {ins.bytes.hex(" "):<20} {ins.mnemonic} {ins.op_str}')
                    break
            else:
                print(f'  ~0x{va:X} (no instruction match) ctx {ctx.hex(" ")}')

    # who reads [gamedata+0x0C]: find "8B ?? 0C" right after a load of the pointer
    print('\n########## [gamedata+0x0C] readers (load gameData ptr, then +0x0C) ##########')
    for name, sva, raw, size in text:
        data = blob[raw:raw + size]
        pat = struct.pack('<I', GAMEDATA_VA)
        i = 0
        while True:
            i = data.find(pat, i)
            if i < 0:
                break
            i += 1
            va = IMAGE_BASE + sva + i - 1
            tail = data[i + 3:i + 3 + 24]
            # look for a mov reg,[reg+0x0C] / movss xmm,[reg+0x0C] within 24 bytes
            if b'\x0c' in tail:
                print(f'  around 0x{va:X}: {data[max(0,i-8):i+32].hex(" ")}')


if __name__ == '__main__':
    main()
