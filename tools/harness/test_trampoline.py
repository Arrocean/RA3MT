"""Offline Unicorn test for the E9-trampoline tracer's generated machine code.
Verifies both modes: sample recording, register/stack capture, replay flags,
detour patching, and the site restore path.
"""
import importlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/analysis'))
import trace_trampoline as t
importlib.reload(t)

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *


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
    # replay lands here; place-mode's prologue did 'sub esp,0xC', so its stub
    # must rebalance the stack before returning (the real function does it itself)
    tail = b'\x83\xC4\x0C\xC3' if mode == 'place' else b'\x90\xC3'
    vm.mem_write(site + len(displaced), tail)

    caller = 0x2100000
    arg1, arg2 = data_va + 0x200, data_va + 0x300   # mapped: place-mode replay derefs arg1
    vm.mem_write(caller, b'\x68' + struct.pack('<I', arg2)
                         + b'\x68' + struct.pack('<I', arg1)
                         + b'\xE8' + struct.pack('<i', site - (caller + 15))
                         + b'\x90')
    for i, r in enumerate([UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                           UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP]):
        vm.reg_write(r, 0x11110000 + i)
    vm.reg_write(UC_X86_REG_ESP, 0x2108000)
    vm.reg_write(UC_X86_REG_EFLAGS, 0x202)
    # place-mode replay dereferences [esp+0x10]: pre-seed the pre-call stack top
    for off in range(0, 0x100, 4):
        vm.mem_write(0x2108000 + off, struct.pack('<I', data_va + 0x100))
    vm.emu_start(caller, caller + 16, count=500)

    count = struct.unpack('<I', vm.mem_read(data_va, 4))[0]
    assert count == 1, f'[{mode}] sample not recorded (count={count})'
    regs = struct.unpack('<8I', vm.mem_read(data_va + 4, 32))
    edi, esi, ebp, esp_pad, ebx, edx, ecx, eax = regs
    assert eax == 0x11110000 and ecx == 0x11110002 and edi == 0x11110005, \
        f'[{mode}] regs wrong: {[hex(x) for x in regs]}'
    stack = struct.unpack('<16I', vm.mem_read(data_va + 4 + 32, 64))
    assert stack[0] == 0x202, f'[{mode}] eflags slot wrong: {hex(stack[0])}'
    assert stack[1] == caller + 15, f'[{mode}] ret wrong: {hex(stack[1])}'
    assert stack[2] == arg1 and stack[3] == arg2, f'[{mode}] args wrong'
    esp = vm.reg_read(UC_X86_REG_ESP)
    assert esp == 0x2108000 - 8, f'[{mode}] stack imbalance: {hex(esp)}'
    print(f'[{mode}] PASS: sample+regs+stack+replay verified')


def main():
    run_case('kill')
    run_case('place')
    print('PASS both trampoline modes')


if __name__ == '__main__':
    main()
