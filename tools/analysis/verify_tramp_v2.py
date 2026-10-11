"""Unicorn semantic test for the trampoline v2 stub (split hit-count /
sample-idx header). Verifies the exact contract the Python poller relies on:
  1. every execution increments [base+0] (hit count), even past cap
  2. [base+4] (written idx) stops at cap; sample area past cap stays frozen
  3. sample[i] = 8 pushad regs + 22 stack dwords, copied from entry esp
  4. all GPRs + EFLAGS restored (incl. DF), esp unchanged on return path
  5. displaced bytes replayed, then jmp back to site+len(displaced)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_trampoline as t  # noqa: E402

from unicorn import *
from unicorn.x86_const import *  # noqa: F403

TRAMP = 0x70000000
DATA = 0x70010000
SITE = 0xA2A1E0
STACK = 0x60000000
DISPLACED = bytes.fromhex('83ec34535556')
CAP = 8


def run():
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    code = t.build_trampoline(TRAMP, DATA, SITE, DISPLACED, CAP)
    mu.mem_map(TRAMP & ~0xFFF, 0x1000)
    mu.mem_write(TRAMP, code)
    mu.mem_map(DATA & ~0xFFF, 0x2000)
    mu.mem_map(STACK, 0x1000)
    # sentinel 'return address' + args on the stack the stub will snapshot
    mu.mem_write(STACK + 0x800, struct.pack('<22I', *range(0x11110, 0x11110 + 22)))

    def once(i, stop=None):
        regs = {
            UC_X86_REG_EAX: 0xAA000000 + i, UC_X86_REG_ECX: 0xCC000000 + i,
            UC_X86_REG_EDX: 0xDD000000 + i, UC_X86_REG_EBX: 0xBB000000 + i,
            UC_X86_REG_ESP: STACK + 0x800, UC_X86_REG_EBP: 0xB0B0B000 + i,
            UC_X86_REG_ESI: 0x51510000 + i, UC_X86_REG_EDI: 0xD1D10000 + i,
        }
        for r, v in regs.items():
            mu.reg_write(r, v)
        # DF set on entry: the stub's CLD must protect the rep movsd, and
        # popfd must restore DF=1 afterwards
        mu.reg_write(UC_X86_REG_EFLAGS, 0x402)  # DF | always-set
        # stop=TRAMP+0x35 lands right after popfd, BEFORE the displaced
        # replay (which legitimately shifts esp by 0x34+3 pushes)
        mu.emu_start(TRAMP, stop or SITE + len(DISPLACED))
        return regs

    # 12 hits: cap is 8 -> widx must freeze at 8, hit count keeps counting
    for i in range(12):
        regs = once(i, stop=TRAMP + 0x35)   # post-popfd, pre-displaced
        hdr = struct.unpack('<II', mu.mem_read(DATA, 8))
        assert hdr[0] == i + 1, f'hit count wrong: {hdr}'
        assert hdr[1] == min(i + 1, CAP), f'widx wrong: {hdr}'
        # registers restored?
        for r, v in regs.items():
            got = mu.reg_read(r)
            assert got == v, f'reg not restored: want {v:#x} got {got:#x}'
        # DF restored? (entry always sets DF=1 via reg_write inside once())
        after_efl = mu.reg_read(UC_X86_REG_EFLAGS)
        assert (after_efl & 0x400) == 0x400, f'DF not restored: {after_efl:#x}'
        # esp restored
        assert mu.reg_read(UC_X86_REG_ESP) == STACK + 0x800, 'esp moved'

    # full path once: after the displaced replay esp must be shifted by
    # exactly sub esp,0x34 + 3 pushes (0x40), landing on SITE+len(DISPLACED)
    once(99)
    assert mu.reg_read(UC_X86_REG_ESP) == STACK + 0x800 - 0x40, 'displaced stack effect wrong'
    hdr = struct.unpack('<II', mu.mem_read(DATA, 8))
    assert hdr[0] == 13 and hdr[1] == CAP

    # sample 0 content: pushad order (edi,esi,ebp,esp,ebx,edx,ecx,eax),
    # then the pushfd eflags snapshot (s[8]), then the raw entry stack
    # (s[9] = return address slot = 0x11110 ... s[29] = 21st stack dword).
    # This matches the poller's printing convention eflags=stack[0],
    # ret=stack[1], arg1=stack[2].
    s0 = struct.unpack('<30I', mu.mem_read(DATA + 0x10, t.SAMPLE_BYTES))
    assert s0[0] == 0xD1D10000, f'sample edi wrong: {s0[0]:#x}'      # edi
    assert s0[7] == 0xAA000000, f'sample eax wrong: {s0[7]:#x}'      # eax
    assert s0[4] == 0xBB000000, 'sample ebx wrong'                    # ebx
    assert s0[8] == 0x402, f'sample eflags snapshot wrong: {s0[8]:#x}'
    assert s0[9] == 0x11110, f'sample stack ret wrong: {s0[9]:#x}'
    assert s0[29] == 0x11110 + 20, 'sample stack tail wrong'

    # sample 8 must NOT exist (cap frozen): tail of slice stays zero
    widx = struct.unpack('<I', mu.mem_read(DATA + 4, 4))[0]
    assert widx == CAP
    beyond = mu.mem_read(DATA + 0x10 + CAP * t.SAMPLE_BYTES, 32)
    assert beyond == b'\x00' * 32, 'wrote past cap!'

    # slice bounds: header + CAP samples must fit HUNT_SLICE
    assert t.HUNT_HDR + t.HUNT_SAMPLES * t.SAMPLE_BYTES <= t.HUNT_SLICE

    print(f'ALL PASS: hit={hdr[0]} widx={widx} sample0.eax={s0[7]:#X} '
          f'cap-frozen tail zeroed, regs/DF/esp restored')


if __name__ == '__main__':
    run()
