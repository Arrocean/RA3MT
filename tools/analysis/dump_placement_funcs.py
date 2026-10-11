"""Read-only: dump the FULL placement verification chain (1.13, VAs).

Chain established by the v18m live deep-stack capture, now with correct
addressing (v18m notes record RVAs; +0x400000 for VAs):

  top      VA 0xA47300..   (RVA 0x647300)  placement top; calls validator
  validator VA 0xA42450    (RVA 0x642450)  loads distance from [0xCF2CAC]+0xC
  worker   VA 0x520780     (RVA 0x120780)  grid worker, radius = distance
  followup VA 0xA41510     (RVA 0x641510)
  cellq    VA 0xA3AAB0     (RVA 0x63AAB0)  cell query (deepest live frame)
  vf48     VA 0x5F0930     (RVA 0x1F0930)  UI predicate (proved NOT the gate)
  sixiter  VA 0x64C970     (RVA 0x24C970)  6-iteration predicate (PLACEHUNT)

Writes everything to artifacts/placement_chain_113.txt.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections, read_va  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_BASE = 0x400000
OUT = Path(__file__).resolve().parents[2] / 'artifacts' / 'placement_chain_113.txt'

from capstone import Cs, CS_ARCH_X86, CS_MODE_32  # noqa: E402
md = Cs(CS_ARCH_X86, CS_MODE_32)

MARKS = {
    0xA42457: 'GameData global load',
    0xA42484: 'fld [edx+0xC]  <- BuildingPlacementDistance',
    0xA42496: 'or ecx,0xC4020 (collision mask)',
    0xA424AD: 'mov ecx,[ThePlacementGrid]',
    0xA424B3: 'call worker 0x520780',
    0xA424C1: 'call followup 0xA41510',
    0xA47326: 'call validator 0xA42450',
    0x5F098E: 'call regionline 0x90FD60 (v18g RVA 0x50FD60)',
}

TARGETS = [
    ('top 0xA47300 (head; 0xA472FF is int3 pad)', 0xA47300),
    ('validator 0xA42450', 0xA42450),
    ('worker 0x520780', 0x520780),
    ('worker-percell-a 0x51A9E0', 0x51A9E0),
    ('worker-percell-b 0xB281E0', 0xB281E0),
    ('followup 0xA41510', 0xA41510),
    ('followup-percell-a 0xA2A1E0', 0xA2A1E0),
    ('followup-percell-b 0xA2A5D0', 0xA2A5D0),
    ('gridquery 0x5065A0', 0x5065A0),
    ('cellq 0xA3AAB0', 0xA3AAB0),
    ('vf48 0x5F0930', 0x5F0930),
    ('regionline 0x90FD60 (v18g RVA 0x50FD60)', 0x90FD60),
    ('sixiter 0x64C970', 0x64C970),
]


def func_start(blob, secs, va, window=0xA00):
    for cand in range(va - 1, va - window, -1):
        prev = read_va(blob, secs, cand - 1, 5)[0]
        if prev is None:
            continue
        if prev[0] in (0xC3, 0xC2, 0xCC) or prev[:4] == b'\xCC\xCC\xCC\xCC':
            return cand
    return None


def disasm_func(blob, secs, head, max_bytes=0x800):
    code, sec = read_va(blob, secs, head, max_bytes)
    out = []
    for ins in md.disasm(code, head):
        tag = ''
        if ins.address in MARKS:
            tag = '   <== ' + MARKS[ins.address]
        out.append(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<26} {ins.mnemonic} {ins.op_str}{tag}')
        if ins.mnemonic.startswith('ret') or ins.mnemonic == 'int3':
            break
    return out


def callers(blob, secs, target):
    for name, sva, vsize, raw, rsize in secs:
        if name == '.text':
            base = IMAGE_BASE + sva
            data = blob[raw:raw + min(vsize, rsize)]
            out = []
            for i in range(len(data) - 5):
                if data[i] == 0xE8:
                    rel = struct.unpack_from('<i', data, i + 1)[0]
                    if base + i + 5 + rel == target:
                        out.append(base + i)
            return out
    return []


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    lines = []
    for label, anchor in TARGETS:
        if 'find head' in label:
            head = func_start(blob, secs, anchor)
            lines.append(f'\n===== {label}: anchor 0x{anchor:X} -> head 0x{head:X} (RVA 0x{head-IMAGE_BASE:X}) =====')
        else:
            head = anchor
            lines.append(f'\n===== {label} (RVA 0x{anchor-IMAGE_BASE:X}) =====')
        lines.extend(disasm_func(blob, secs, head))
        cs = callers(blob, secs, head)
        lines.append(f'  -- direct E8 callers ({len(cs)}): ' + ' '.join(hex(c) for c in cs[:24]))
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'wrote {OUT} ({len(lines)} lines)')
    # print head addresses for quick reference
    for label, anchor in TARGETS:
        head = func_start(blob, secs, anchor) if 'find head' in label else anchor
        print(f'{label:<36} head VA 0x{head:X}  RVA 0x{head-IMAGE_BASE:X}')


if __name__ == '__main__':
    main()
