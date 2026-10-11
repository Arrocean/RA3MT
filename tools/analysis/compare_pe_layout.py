"""Read-only: compare the PE headers of the on-disk ra3_1.13.game with the
headers actually mapped in the running process.

If SizeOfImage / section RVAs differ, the running module is NOT the file we keep
disassembling, and every disk-derived RVA (assets/features.json, NOTES anchors)
is off by whatever the delta is.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
from pathlib import Path

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def parse_pe(blob, label):
    pe = struct.unpack_from('<I', blob, 0x3C)[0]
    assert blob[pe:pe + 4] == b'PE\0\0', f'{label}: not PE (sig {blob[pe:pe+4]!r})'
    machine, nsec = struct.unpack_from('<HH', blob, pe + 4)
    opt = struct.unpack_from('<H', blob, pe + 20)[0]
    magic = struct.unpack_from('<H', blob, pe + 24)[0]
    image_base, = struct.unpack_from('<I', blob, pe + 24 + 28)
    size_img, = struct.unpack_from('<I', blob, pe + 24 + 56)
    checksum, = struct.unpack_from('<I', blob, pe + 24 + 64)
    subsys, = struct.unpack_from('<H', blob, pe + 24 + 68)
    ts, = struct.unpack_from('<I', blob, pe + 8)
    print(f'--- {label} ---')
    print(f'  machine 0x{machine:X} sections {nsec} optmagic 0x{magic:X} '
          f'imageBase 0x{image_base:X} sizeOfImage 0x{size_img:X} checksum 0x{checksum:X} '
          f'subsystem {subsys} timestamp 0x{ts:X} ({ts})')
    secs = []
    for i in range(nsec):
        off = pe + 24 + opt + i * 40
        name = blob[off:off + 8].rstrip(b'\x00').decode('ascii', 'replace')
        vsize, va, rsize, raw = struct.unpack_from('<IIII', blob, off + 8)
        chars, = struct.unpack_from('<I', blob, off + 36)
        secs.append((name, va, vsize, raw, rsize, chars))
        print(f'    {name:<10} RVA 0x{va:<8X} vsize 0x{vsize:<8X} raw 0x{raw:<8X} '
              f'rsize 0x{rsize:<8X} chars 0x{chars:X}')
    return secs, size_img, pe, opt


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    disk = IMAGE.read_bytes()
    print(f'disk file size 0x{len(disk):X}')
    dsecs, dsize, dpe, dopt = parse_pe(disk, 'DISK ra3_1.13.game')
    print(f'  {len(disk) - dsecs[-1][3] - dsecs[-1][4]} bytes of overlay after last section')

    head = rd(h, 0x400000, 0x1000)
    if not head:
        raise SystemExit('cannot read live headers at 0x400000')
    lsecs, lsize, lpe, lopt = parse_pe(head, f'LIVE PID {PID} @0x400000')

    print('\n--- section delta (live RVA - disk RVA) ---')
    for (dn, dva, dvs, _, drs, _), (ln, lva, lvs, _, lrs, _) in zip(dsecs, lsecs):
        same = 'SAME' if (dn == ln and dva == lva and dvs == lvs) else '*** DIFFERENT ***'
        print(f'  {dn:<10} disk RVA 0x{dva:<8X} vsz 0x{dvs:<8X} | live RVA 0x{lva:<8X} '
              f'vsz 0x{lvs:<8X}  {same}')
    print(f'\n  SizeOfImage disk 0x{dsize:X}  live 0x{lsize:X}  delta 0x{lsize - dsize:X}')

    print('\n--- does the live image match the disk bytes at the hook sites? ---')
    dsites = {0x7513F0: 'kill', 0x707880: 'placeui', 0x64C970: 'gridA', 0x5F0930: 'region'}
    for va, lbl in dsites.items():
        off = None
        for n, sva, vs, raw, rs, _ in dsecs:
            if sva <= va - 0x400000 < sva + max(vs, rs):
                off = raw + (va - 0x400000 - sva)
        disk_bytes = disk[off:off + 16] if off else None
        live_bytes = rd(h, va, 16)
        print(f'  {lbl} @0x{va:X}\n    disk {disk_bytes.hex(" ") if disk_bytes else None}'
              f'\n    live {live_bytes.hex(" ") if live_bytes else None}')

    print('\n--- search the LIVE image for the disk byte pattern of 0x7513F0 ---')
    pat = disk[off:off + 16] if off else None
    if pat:
        found = []
        addr = 0x401000
        step = 0x100000
        while addr < 0x1200000 and len(found) < 8:
            buf = rd(h, addr, step)
            if buf:
                i = 0
                while True:
                    i = buf.find(pat, i)
                    if i < 0:
                        break
                    found.append(addr + i)
                    i += 1
            addr += step
        print('  ' + (' '.join(f'0x{a:X}' for a in found) if found else 'not found'))


if __name__ == '__main__':
    main()
