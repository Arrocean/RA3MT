"""Read-only: dump the FULL placement worker + its per-cell query chain
(1.13), hunting the candidate-collection predicate that decides green/red.

Layer model after the 2026-10-12 patchtest negative result:
  worker 0x520780 collects cells on PlacementGrid ([0xCE21CC], 0x28B records
  via 0xB281E0) — the candidate set is what the ghost is painted from;
  followup/percell query the SEPARATE buildability grid (0xB336E0, 0x34B
  records) — patching that layer (0xB322EA) did NOT change the ghost color,
  so color must live in the collection predicate.
Chain: worker 0x520780 -> per-cell 0x51A9E0 (3 call sites inside the worker)
-> 0x5149F0 (grid query) ; plus 0xB281E0 (cell index -> record, stride 0x28).
The FINAL3 EA patch (RVA 0xE7565: 75 0C -> EB 0C) must map onto one of the
jne-style branches in here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections, read_va  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
OUT = Path(__file__).resolve().parents[2] / 'artifacts' / 'worker_full_113.txt'

from capstone import Cs, CS_ARCH_X86, CS_MODE_32  # noqa: E402
md = Cs(CS_ARCH_X86, CS_MODE_32)

TARGETS = [
    ('worker 0x520780 FULL', 0x520780, 0x400),
    ('worker-percell 0x51A9E0 FULL', 0x51A9E0, 0x120),
    ('gridquery 0x5149F0 FULL', 0x5149F0, 0x200),
    ('cell-accessor 0xB281E0', 0xB281E0, 0x40),
]


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    lines = []
    for label, va, size in TARGETS:
        lines.append(f'\n===== {label} =====')
        code, _ = read_va(blob, secs, va, size)
        for ins in md.disasm(code, va):
            # highlight conditional branches: the FINAL3 patch was 75 0C
            tag = ''
            if ins.bytes[:1] in (b'\x75', b'\x74', b'\x0f') and ins.mnemonic.startswith('j'):
                tag = '   <<<< conditional branch' if ins.bytes[:1] in (b'\x75', b'\x74') else ''
            lines.append(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<26} {ins.mnemonic} {ins.op_str}{tag}')
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'wrote {OUT} ({len(lines)} lines)')
    # quick summary of short jne/jcc in the worker body
    print('\nshort conditional branches (75/74/7x) inside worker 0x520780..0x520B80:')
    code, _ = read_va(blob, secs, 0x520780, 0x400)
    for ins in md.disasm(code, 0x520780):
        if ins.mnemonic.startswith('j') and len(ins.bytes) == 2 and ins.mnemonic != 'jmp':
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<6} {ins.mnemonic} {ins.op_str}')


if __name__ == '__main__':
    main()
