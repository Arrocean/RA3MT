"""Read-only audit of the trace_trampoline.py detour sites.

For every site it prints the raw bytes from the on-disk 1.13 image, disassembles
the first few instructions, and reports whether the tool's `displaced` byte
string actually ends on an instruction boundary. A detour that jumps back to
site+len(displaced) while displacing only 5 of a longer instruction leaves
orphan bytes that decode as fresh instructions.

Disk-only: never touches the running game.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_trampoline as t  # noqa: E402  (reuses the site tables under audit)

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_BASE = 0x400000


def sections(blob):
    pe = struct.unpack_from('<I', blob, 0x3C)[0]
    nsec = struct.unpack_from('<H', blob, pe + 6)[0]
    opt = struct.unpack_from('<H', blob, pe + 20)[0]
    out = []
    for i in range(nsec):
        off = pe + 24 + opt + i * 40
        name = blob[off:off + 8].rstrip(b'\x00').decode('ascii', 'replace')
        vsize, va, rsize, raw = struct.unpack_from('<IIII', blob, off + 8)
        out.append((name, va, vsize, raw, rsize))
    return out


def read_va(blob, secs, va, n):
    rva = va - IMAGE_BASE
    for name, sva, vsize, raw, rsize in secs:
        if sva <= rva < sva + max(vsize, rsize):
            start = raw + (rva - sva)
            return blob[start:start + n], name
    return None, None


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    print(f'image {IMAGE.name}  sections: ' +
          ', '.join(f'{n}@0x{v:X}+0x{s:X}' for n, v, s, _, _ in secs))
    print()

    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print('capstone not installed -> raw bytes only')
        Cs = None

    md = Cs(CS_ARCH_X86, CS_MODE_32) if Cs else None

    groups = [('SITES', sorted(t.SITES.items()))]
    groups.append(('PLACEHUNT', [(lbl, (va, dis)) for va, dis, lbl in t.PLACEHUNT]))

    for title, items in groups:
        print(f'===== {title} =====')
        for label, (va, displaced) in items:
            head, sec = read_va(blob, secs, va, 32)
            if head is None:
                print(f'{label}: 0x{va:X} NOT MAPPED')
                continue
            expected = head[:len(displaced)]
            ok = expected == displaced
            print(f'-- {label}  VA 0x{va:X} (sec {sec})  displaced_len={len(displaced)}')
            print(f'   tool bytes : {displaced.hex(" ")}')
            print(f'   disk bytes : {expected.hex(" ")}   {"MATCH" if ok else "*** MISMATCH ***"}')
            if md:
                consumed = 0
                for ins in md.disasm(head, va):
                    if consumed >= len(displaced):
                        break
                    flag = '  <-- displaced ends INSIDE this instruction' \
                        if consumed < len(displaced) < consumed + ins.size else ''
                    print(f'   {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}{flag}')
                    consumed += ins.size
                if consumed != len(displaced):
                    print(f'   *** displaced={len(displaced)}B but instruction boundary at '
                          f'{consumed}B -> orphan bytes remain after the E9 patch')
                    orphan = head[5:consumed]
                    if md and orphan:
                        for ins in md.disasm(orphan, va + 5):
                            print(f'       orphan {ins.address:#010x}  {ins.bytes.hex(" ")}  '
                                  f'{ins.mnemonic} {ins.op_str}')
            print()

    print('===== callers of the PLACEHUNT sites (rel32 E8 scan, .text only) =====')
    for va, displaced, label in t.PLACEHUNT:
        hits = []
        for name, sva, vsize, raw, rsize in secs:
            if name != '.text':
                continue
            data = blob[raw:raw + min(vsize, rsize)]
            for i in range(len(data) - 5):
                if data[i] != 0xE8:
                    continue
                rel = struct.unpack_from('<i', data, i + 1)[0]
                tgt = IMAGE_BASE + sva + i + 5 + rel
                if tgt == va:
                    hits.append(IMAGE_BASE + sva + i)
        calls = [h for h in hits if blob_va_ok(h)]
        print(f'{label} 0x{va:X}: {len(hits)} direct E8 callers'
              + ('  ' + ' '.join(f'0x{h:X}' for h in hits[:12]) if hits else '  (none / indirect only)'))


def blob_va_ok(_va):
    return True


if __name__ == '__main__':
    main()
