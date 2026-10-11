"""Careful, deterministic search for immediate operands equal to the 1.13
placement-distance global (0x8F2CAC) in both the disk image and the live module.
Also verifies the section table the mapping relies on.
"""
import ctypes
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000
PAT = struct.pack('<I', 0x8F2CAC)
TEXT_RVA = 0x1000
TEXT_RAW = 0x1000
TEXT_SIZE = 0x7CCB0A


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def search(data, label, base_va):
    hits = []
    i = 0
    while True:
        i = data.find(PAT, i)
        if i < 0:
            break
        hits.append((base_va + i, i))
        i += 1
    print(f'{label}: {len(hits)} hits in {len(data)} bytes')
    for va, off in hits:
        lo = max(0, off - 12)
        print(f'   VA 0x{va:X} (off 0x{off:X})  ctx {data[lo:off + 16].hex(" ")}')
    return hits


def main():
    with open(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game', 'rb') as f:
        f.seek(TEXT_RAW)
        disk_text = f.read(TEXT_SIZE)
    print(f'disk .text: {len(disk_text)} bytes read from raw 0x{TEXT_RAW:X}')
    search(disk_text, 'DISK .text', BASE + TEXT_RVA)

    h = k32.OpenProcess(0x0410, False, PID)
    print(f'\nOpenProcess({PID}) = {bool(h)}')
    if h:
        live_text = rd(h, BASE + TEXT_RVA, TEXT_SIZE)
        if live_text:
            search(live_text, 'LIVE .text', BASE + TEXT_RVA)
        else:
            print('  live .text unreadable in one shot; chunking')
            agg = b''
            off = 0
            while off < TEXT_SIZE:
                n = min(0x100000, TEXT_SIZE - off)
                chunk = rd(h, BASE + TEXT_RVA + off, n)
                agg += chunk if chunk else b'\x00' * n
                off += n
            search(agg, 'LIVE .text (chunked)', BASE + TEXT_RVA)


if __name__ == '__main__':
    main()
