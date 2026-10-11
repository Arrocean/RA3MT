"""Offline execution coverage for the rank/money bridge export.

Run SelfCheck stubdump artifacts/stubs_semantic first, then this script.
Requires unicorn. No process access or game writes.
"""
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'artifacts/stubs_semantic/money_h2_rank.bin'
BLOCK, START, END = 0x40000000, 0x40000040, 0x452105
RANK, API, GLOBAL = 0x40001200, 0x785600, 0x400000
STACK, DATA = 0x200000, 0x300000
MAIL, BODY, DRAWABLE, TRACKER = BLOCK + 0x1800, DATA, DATA + 0x1000, DATA + 0x2000
CONTROLLER, SIDE, WRAPPER, TEMPLATE = DATA + 0x3000, DATA + 0x4000, DATA + 0x5000, DATA + 0x6000
EXTRA, VTABLE = DATA + 0x8000, DATA + 0x9000
REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
        UC_X86_REG_EFLAGS]
XMM = [UC_X86_REG_XMM0, UC_X86_REG_XMM1, UC_X86_REG_XMM2, UC_X86_REG_XMM3,
       UC_X86_REG_XMM4, UC_X86_REG_XMM5, UC_X86_REG_XMM6, UC_X86_REG_XMM7]


def put(vm, addr, value):
    vm.mem_write(addr, struct.pack('<I', value))


def get(vm, addr):
    return struct.unpack('<I', vm.mem_read(addr, 4))[0]


def fx_image(vm):
    addr = DATA + 0x10000
    vm.mem_write(GLOBAL + 0x900, b'\x0F\xAE\x05' + struct.pack('<I', addr))
    vm.emu_start(GLOBAL + 0x900, GLOBAL + 0x907, count=1)
    image = bytearray(vm.mem_read(addr, 416))
    image[8:16] = bytes(8)  # Unicorn does not restore FIP with FXRSTOR.
    return bytes(image)


def machine(blob, state, money_enabled, rejected=False):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr, size in [(BLOCK, 0x2000), (GLOBAL, 0x1000), (DATA, 0x20000),
                       (STACK, 0x10000), (API & ~0xfff, 0x1000), (END & ~0xfff, 0x1000)]:
        vm.mem_map(addr, size)
    vm.mem_write(START, blob)
    vm.mem_write(RANK, (ROOT / 'artifacts/stubs_semantic/rank_dispatcher.bin').read_bytes())
    vm.mem_write(API, bytes.fromhex('db e3 d9 e8 0f 57 c0 0f 57 ff c2 0c 00'))
    vm.mem_write(GLOBAL + 0xa00, bytes.fromhex('db e3 d9 e8 d9 eb'))
    vm.emu_start(GLOBAL + 0xa00, GLOBAL + 0xa06)
    for i, reg in enumerate(REGS[:-2]):
        vm.reg_write(reg, 0x12340000 + i)
    vm.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
    vm.reg_write(UC_X86_REG_EFLAGS, 0x893)
    vm.reg_write(UC_X86_REG_MXCSR, 0x3f80)
    for i, reg in enumerate(XMM):
        vm.reg_write(reg, (0xfedcba9876543210 << 64) | (0x123456789abcdef0 + i))
    entries = [(MAIL, state), (MAIL+4, BODY), (MAIL+8, DRAWABLE),
               (MAIL+12, TRACKER), (MAIL+16, 0xabcdef), (MAIL+20, 0xabcdef),
               (BODY+0xf4, DRAWABLE), (DRAWABLE+0x138, BODY),
               (BODY+0x3cc, TRACKER), (BODY+0x418, SIDE), (GLOBAL, CONTROLLER),
               (CONTROLLER+0x28, SIDE), (TRACKER+4, WRAPPER), (WRAPPER+0x14, TEMPLATE),
               (TRACKER+0x24, 7), (EXTRA+4, 900), (EXTRA+8, 50), (VTABLE, 0x12345678)]
    for addr, value in entries:
        put(vm, addr, value)
    vm.mem_write(DRAWABLE+0x13d, b'\x40')
    vm.mem_write(TEMPLATE+0x245, b'\x01')
    vm.mem_write(BLOCK, bytes([money_enabled]))
    if rejected:
        put(vm, BODY+0x418, SIDE + 0x100)
    vm.reg_write(UC_X86_REG_EAX, EXTRA)
    vm.reg_write(UC_X86_REG_ECX, VTABLE)
    vm.reg_write(UC_X86_REG_EDI, 10)
    return vm


def run(blob, state, money_enabled, rejected=False):
    vm = machine(blob, state, money_enabled, rejected)
    fx_before = fx_image(vm)
    before = {reg: vm.reg_read(reg) for reg in REGS}
    calls, claims = [], []

    def hook(machine, address, size, _):
        if address == API:
            assert get(vm, MAIL) == 2
            sp = vm.reg_read(UC_X86_REG_ESP)
            assert vm.reg_read(UC_X86_REG_ECX) == TRACKER
            assert [get(vm, sp+x) for x in (4, 8, 12)] == [3, 1, 0]
            calls.append(address)
            put(vm, TRACKER+0x24, 8)
            for i, reg in enumerate(REGS[:-2]):
                if reg != UC_X86_REG_ESP:
                    vm.reg_write(reg, 0x55550000 + i)
        elif bytes(vm.mem_read(address, size))[:3] == b'\xF0\x0F\xB1':
            claims.append(get(vm, MAIL))

    vm.hook_add(UC_HOOK_CODE, hook)
    baseline = machine((ROOT / 'artifacts/stubs_semantic/money_h2.bin').read_bytes(), state, money_enabled, rejected)
    baseline.emu_start(START, END, count=20000)
    vm.emu_start(START, END, count=20000)
    assert vm.reg_read(UC_X86_REG_EIP) == END
    for reg, value in before.items():
        if reg not in (UC_X86_REG_EDI, UC_X86_REG_EDX, UC_X86_REG_EFLAGS):
            assert vm.reg_read(reg) == value, ('input register changed', reg)
    assert vm.reg_read(UC_X86_REG_EFLAGS) == baseline.reg_read(UC_X86_REG_EFLAGS)
    expected_money = 100900 if money_enabled else 900
    assert vm.reg_read(UC_X86_REG_EDI) == 10 + expected_money
    assert vm.reg_read(UC_X86_REG_EDX) == 0x12345678
    assert get(vm, EXTRA+4) == expected_money
    assert get(vm, EXTRA+8) == (0x05F5E0FF if money_enabled else 50)
    assert fx_image(vm) == fx_before, 'x87/MXCSR/XMM image changed'
    valid = state == 1 and not rejected
    assert len(calls) == (1 if valid else 0)
    # The dispatcher attempts exactly one atomic claim per money settlement and
    # observes the submitted state; the claim only converts Pending(1).
    assert claims == [state], 'claim attempt count or observed state wrong'
    if valid:
        assert get(vm, MAIL) == 3 and get(vm, MAIL+16) == 7 and get(vm, MAIL+20) == 8
    elif state == 1:
        # Claimed from Pending then rejected by a validation gate.
        assert get(vm, MAIL) == 4
    else:
        # Claim declined on non-Pending state: mailbox untouched.
        assert get(vm, MAIL) == state


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bin', type=Path, default=DEFAULT)
    blob = ap.parse_args().bin.read_bytes()
    assert blob[:1] == b'\xE8', 'bridge must CALL rank dispatcher first'
    cases = 0
    for money_enabled in (0, 1):
        for state, rejected in ((0, False), (1, False), (1, True), (2, False)):
            run(blob, state, money_enabled, rejected)
            cases += 1
    print(f'PASS: {cases} offline rank/money bridge cases; rank state/owner gating, money flag, GPR and FX state')


if __name__ == '__main__':
    main()
