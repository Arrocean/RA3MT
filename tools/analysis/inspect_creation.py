"""Bounded, disk-only PE disassembly and direct CALL xrefs for creation research.
No process APIs, executable launches or game writes. Requires pefile and capstone.
Examples:
  py tools/analysis/inspect_creation.py 1.13 0x102410 --xrefs
  py tools/analysis/inspect_creation.py 1.13 0x40CFC0 --length 0x180
RVA is always relative to the PE image; disassembly shows RVA, never mixed VA/RVA.
CALL byte matches are candidates until their instruction boundary is verified.
This utility never interacts with a running game process.
"""
import argparse
from pathlib import Path
import struct
import capstone
import pefile

DEFAULT = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data')


def call_xrefs(image, sections, target):
    hits = []
    for section in sections:
        if not section.Characteristics & 0x20000000:
            continue
        lo = section.VirtualAddress
        hi = min(len(image), lo + section.Misc_VirtualSize)
        cursor = lo
        while True:
            cursor = image.find(b'\xe8', cursor, hi - 4)
            if cursor < 0:
                break
            destination = (cursor + 5 + struct.unpack_from('<i', image, cursor + 1)[0]) & 0xffffffff
            if destination == target:
                hits.append(cursor)
            cursor += 1
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', choices=['1.12', '1.13'])
    parser.add_argument('rva', type=lambda x: int(x, 0))
    parser.add_argument('--length', type=lambda x: int(x, 0), default=0x100)
    parser.add_argument('--data', type=Path, default=DEFAULT)
    parser.add_argument('--xrefs', action='store_true')
    args = parser.parse_args()
    if not 0 < args.length <= 0x4000:
        parser.error('length must be 1..0x4000')
    pe = pefile.PE(str(args.data / f'ra3_{args.version}.game'))
    image = pe.get_memory_mapped_image()
    if not 0 <= args.rva < len(image) or args.rva + args.length > len(image):
        parser.error('RVA range outside image')
    if args.xrefs:
        hits = call_xrefs(image, pe.sections, args.rva)
        print(f'{args.version} target RVA 0x{args.rva:X}; {len(hits)} candidate CALL rel32 references')
        for rva in hits:
            print(f'  RVA 0x{rva:08X}')
        return
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    base = pe.OPTIONAL_HEADER.ImageBase
    for instruction in md.disasm(image[args.rva:args.rva + args.length], base + args.rva):
        operand = instruction.op_str
        if instruction.mnemonic.startswith('j') or instruction.mnemonic == 'call':
            if operand.startswith('0x'):
                destination = int(operand, 16)
                operand = f'RVA 0x{destination - base:X}' if base <= destination < base + len(image) else operand
        print(f'RVA {instruction.address - base:08X}: {instruction.bytes.hex(" "):<30} '
              f'{instruction.mnemonic:<8} {operand}')


if __name__ == '__main__':
    main()
