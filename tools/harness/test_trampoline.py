"""Offline Unicorn test for the E9-trampoline tracer's generated machine code
(v2 layout).

v2 data slice header: +0 hit count (never reset), +4 written-sample index
(frozen at cap), +0x10.. sample area. Each sample = 8 pushad dwords
(EDI,ESI,EBP,ESP,EBX,EDX,ECX,EAX) followed by the raw stack at entry, whose
first word is the pushfd EFLAGS snapshot.

Verifies, for both single-site modes: hit/widx bookkeeping, register capture,
stack capture, replay of the displaced instruction, and that the caller stack is
restored to exactly its pre-trampoline value.
"""
import importlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/analysis'))
import trace_trampoline as t
importlib.import_module('trace_trampoline')
importlib.reload(t)

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *

PUSHAD_REGS = [UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_EBP, UC_X86_REG_ESP,
               UC_X86_REG_EBX, UC_X86_REG_EDX, UC_X86_REG_ECX, UC_X86_REG_EAX]


def run_case(mode):
    site, displaced = t.SITES[mode]
    tramp_va, data_va = 0x2A00000, 0x2B00000
    code = t.build_trampoline(tramp_va, data_va, site, displaced)
    print(f'[{mode}] trampoline {len(code)}B: {code.hex(" ")}')

    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for base in sorted({tramp_va & ~0xFFF, data_va & ~0xFFF, site & ~0xFFF,
                        0x2100000, 0x2107000}):
        vm.mem_map(base, 0x2000)
    vm.mem_write(tramp_va, code)

    # the site is patched exactly like the live tracer does
    patch = b'\xE9' + struct.pack('<i', tramp_va - (site + 5))
    vm.mem_write(site, patch)
    # replay lands here; place-mode's prologue does 'sub esp,8; push esi', so the
    # tail must rebalance the stack before returning (the real function does it)
    tail = b'\x83\xC4\x0C\xC3' if mode == 'place' else b'\x90\xC3'
    vm.mem_write(site + len(displaced), tail)

    caller = 0x2100000
    arg1, arg2 = data_va + 0x200, data_va + 0x300
    vm.mem_write(caller, b'\x68' + struct.pack('<I', arg2)
                         + b'\x68' + struct.pack('<I', arg1)
                         + b'\xE8' + struct.pack('<i', site - (caller + 15))
                         + b'\x90')
    for i, r in enumerate(PUSHAD_REGS):
        vm.reg_write(r, 0x11110000 + i)
    esp0 = 0x2108000
    vm.reg_write(UC_X86_REG_ESP, esp0)
    vm.reg_write(UC_X86_REG_EFLAGS, 0x202)
    for off in range(0, 0x100, 4):
        vm.mem_write(esp0 + off, struct.pack('<I', data_va + 0x100))
    vm.emu_start(caller, caller + 16, count=500)

    hits = struct.unpack('<I', vm.mem_read(data_va, 4))[0]
    widx = struct.unpack('<I', vm.mem_read(data_va + 4, 4))[0]
    assert hits == 1, f'[{mode}] hit count wrong: {hits}'
    assert widx == 1, f'[{mode}] written index wrong: {widx}'

    sample = t.HUNT_HDR + 0 * t.SAMPLE_BYTES
    regs = struct.unpack('<8I', vm.mem_read(data_va + sample, 32))
    edi, esi, ebp, esp_snap, ebx, edx, ecx, eax = regs
    # PUSHAD_REGS seeds EDI..EAX = 0..7 (+0x11110000) in pushad order
    assert (edi, esi, ebp, ebx, edx, ecx, eax) == \
           (0x11110000, 0x11110001, 0x11110002, 0x11110004, 0x11110005, 0x11110006, 0x11110007), \
        f'[{mode}] regs wrong: {[hex(x) for x in regs]}'
    # ESP slot is captured after pushfd+pushad, i.e. 0x10 below the entry ESP
    assert esp_snap == esp0 - 0x10, f'[{mode}] esp snapshot wrong: {hex(esp_snap)}'

    stack = struct.unpack('<8I', vm.mem_read(data_va + sample + 32, 32))
    assert stack[0] == 0x202, f'[{mode}] eflags snapshot wrong: {hex(stack[0])}'
    assert stack[1] == caller + 15, f'[{mode}] ret addr wrong: {hex(stack[1])}'
    assert stack[2] == arg1 and stack[3] == arg2, f'[{mode}] args wrong'

    esp = vm.reg_read(UC_X86_REG_ESP)
    # the detour itself is stack-neutral; the caller pushed 2 args and never
    # rebalances them (both sites return with a plain ret), so ESP is esp0-8
    assert esp == esp0 - 8, f'[{mode}] caller stack not restored: {hex(esp)}'
    print(f'[{mode}] PASS: hit/widx bookkeeping, reg+stack capture, replay, esp restored')


def main():
    run_case('kill')
    run_case('place')
    print('PASS both trampoline modes (v2 header layout)')


if __name__ == '__main__':
    main()
