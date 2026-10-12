"""Execute C#-exported rank dispatcher bytes offline in Unicorn.
Run SelfCheck stubdump artifacts/stubs_semantic first, then this script.
Requires unicorn; no process handles, remote calls, game writes or native threads.
"""
from pathlib import Path
import argparse
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

DEFAULT = Path(__file__).resolve().parents[2] / 'artifacts/stubs_semantic/rank_dispatcher.bin'
BLOCK, STUB, API, GLOBAL = 0x40000000, 0x40001100, 0x785600, 0x400000
STACK, DATA, MAIL, CALLER = 0x200000, 0x300000, BLOCK + 0x1800, GLOBAL + 0x800
BODY, DRAWABLE, TRACKER = DATA, DATA + 0x1000, DATA + 0x2000
CONTROLLER, SIDE, WRAPPER, TEMPLATE = DATA + 0x3000, DATA + 0x4000, DATA + 0x5000, DATA + 0x6000
REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS]
XMM = [UC_X86_REG_XMM0, UC_X86_REG_XMM1, UC_X86_REG_XMM2, UC_X86_REG_XMM3,
       UC_X86_REG_XMM4, UC_X86_REG_XMM5, UC_X86_REG_XMM6, UC_X86_REG_XMM7]


def put(vm, addr, value):
    vm.mem_write(addr, struct.pack('<I', value))


def get(vm, addr):
    return struct.unpack('<I', vm.mem_read(addr, 4))[0]


def fx_image(vm):
    # Hardware instruction snapshots x87/control/MXCSR/XMM, not Python register guesses.
    addr = DATA + 0x10000
    vm.mem_write(GLOBAL + 0x900, b'\x0F\xAE\x05' + struct.pack('<I', addr))
    vm.emu_start(GLOBAL + 0x900, GLOBAL + 0x907, count=1)
    image = bytearray(vm.mem_read(addr, 416))
    # Unicorn 2.1.4 does not restore FIP with FXRSTOR (offsets 8..15).
    # Compare x87 registers, tag/control/status, MXCSR and all eight XMM values;
    # hardware FXSAVE/FXRSTOR supplies the saved instruction pointer as well.
    image[8:16] = bytes(8)
    return bytes(image)


def machine(blob, align, flags):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr, size in [(BLOCK, 0x2000), (GLOBAL, 0x1000), (DATA, 0x20000),
                       (STACK, 0x10000), (API & ~0xfff, 0x1000)]:
        vm.mem_map(addr, size)
    vm.mem_write(STUB, blob)
    vm.mem_write(CALLER, b'\xE8' + struct.pack('<i', STUB - (CALLER + 5)))
    # The fake callee executes x87/SSE mutations then RET 0x0C.
    vm.mem_write(API, bytes.fromhex('db e3 d9 e8 0f 57 c0 0f 57 ff c2 0c 00'))
    vm.mem_write(GLOBAL + 0xa00, bytes.fromhex('db e3 d9 e8 d9 eb'))
    vm.emu_start(GLOBAL + 0xa00, GLOBAL + 0xa06)
    for i, reg in enumerate(REGS[:-2]):
        vm.reg_write(reg, 0x12340000 + i)
    vm.reg_write(UC_X86_REG_ESP, STACK + 0x8000 + align)
    vm.reg_write(UC_X86_REG_EFLAGS, flags)
    vm.reg_write(UC_X86_REG_MXCSR, 0x3f80)
    for i, reg in enumerate(XMM):
        vm.reg_write(reg, (0xfedcba9876543210 << 64) | (0x123456789abcdef0 + i))
    for addr, value in [(MAIL, 1), (MAIL+4, BODY), (MAIL+8, DRAWABLE), (MAIL+12, TRACKER),
                        (MAIL+16, 0xabcdef), (MAIL+20, 0xabcdef), (BODY+0xf4, DRAWABLE),
                        (DRAWABLE+0x138, BODY), (BODY+0x3cc, TRACKER), (BODY+0x418, SIDE),
                        (GLOBAL, CONTROLLER), (CONTROLLER+0x28, SIDE), (TRACKER+4, WRAPPER),
                        (WRAPPER+0x14, TEMPLATE), (TRACKER+0x24, 7)]:
        put(vm, addr, value)
    vm.mem_write(TEMPLATE+0x245, b'\x01')
    return vm


def run(blob, state=1, mutation=None, rank_after=8, align=0, flags=0x893, recursive=False):
    vm = machine(blob, align, flags)
    put(vm, MAIL, state)
    if mutation:
        mutation(vm)
    initial_mail = bytes(vm.mem_read(MAIL, 24))
    fx_before = fx_image(vm)
    regs_before = {reg: vm.reg_read(reg) for reg in REGS}
    calls, claims = [], []
    def hook(machine, address, size, _):
        if address == API:
            assert get(vm, MAIL) == 2
            sp = vm.reg_read(UC_X86_REG_ESP)
            assert vm.reg_read(UC_X86_REG_ECX) == TRACKER
            assert [get(vm, sp+x) for x in (4, 8, 12)] == [3, 1, 0]
            assert (sp + 16) % 16 == 0
            calls.append(address)
            put(vm, TRACKER+0x24, rank_after)
            # Even all GPR callee clobbers must restore safely (saved ESP in stack).
            for i, reg in enumerate(REGS[:-2]):
                vm.reg_write(reg, 0x55550000 + i)
        elif bytes(vm.mem_read(address, size))[:3] == b'\xF0\x0F\xB1':
            claims.append(get(vm, MAIL))
    vm.hook_add(UC_HOOK_CODE, hook)
    if recursive:
        # Fake API calls the same dispatcher while state2, then returns normally.
        rel = STUB - (API + 5)
        vm.mem_write(API, b'\xE8' + struct.pack('<i', rel) + bytes.fromhex('db e3 d9 e8 0f 57 c0 c2 0c 00'))
    vm.emu_start(CALLER, CALLER+5, count=10000)
    assert vm.reg_read(UC_X86_REG_EIP) == CALLER+5
    assert all(vm.reg_read(r) == v for r, v in regs_before.items()), 'GPR/ESP/EFLAGS changed'
    assert fx_image(vm) == fx_before, 'x87/MXCSR/XMM image changed'
    assert bytes(vm.mem_read(MAIL+4, 12)) == initial_mail[4:16], 'immutable payload changed'
    if state != 1:
        assert not calls and bytes(vm.mem_read(MAIL, 24)) == initial_mail
    elif mutation:
        assert not calls and get(vm, MAIL) == 4
        assert bytes(vm.mem_read(MAIL+16, 8)) == initial_mail[16:24]
    else:
        assert len(calls) == 1
        assert get(vm, MAIL) == (3 if rank_after > 7 else 4)
        assert get(vm, MAIL+16) == 7 and get(vm, MAIL+20) == rank_after
        if recursive:
            assert claims == [1, 2], 'recursive invocation did not decline claim'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bin', type=Path, default=DEFAULT)
    blob = ap.parse_args().bin.read_bytes()
    assert blob[:2] == b'\x9C\x60' and blob[-3:] == b'\x61\x9D\xC3'
    assert b'\xF0\x0F\xB1\x15' in blob
    cases = 0
    for align in range(16):
        for flags in (0x202, 0x893, 0x647):
            for after in (8, 7, 6, 0xffffffff):
                run(blob, align=align, flags=flags, rank_after=after); cases += 1
    for state in (0, 2, 3, 4, 0xffffffff):
        run(blob, state=state, mutation=lambda vm: put(vm, MAIL+4, 0xffffffff)); cases += 1
    invalid = [lambda vm, addr=addr: put(vm, addr, 0) for addr in
               (MAIL+4, MAIL+8, MAIL+12, GLOBAL, CONTROLLER+0x28, TRACKER+4, WRAPPER+0x14)]
    invalid += [lambda vm, addr=addr: put(vm, addr, 0xffff) for addr in
                (MAIL+4, MAIL+8, MAIL+12, GLOBAL, CONTROLLER+0x28, TRACKER+4, WRAPPER+0x14)]
    invalid += [lambda vm, addr=addr: put(vm, addr, DATA+0x7000) for addr in
                (BODY+0xf4, DRAWABLE+0x138, BODY+0x3cc, BODY+0x418)]
    invalid += [lambda vm: vm.mem_write(TEMPLATE+0x245, b'\x00')]
    # NOTE: no "selected" gate exists — FINAL3 ranks freshly spawned
    # (unselected) reinforcement units, so 0x13D.6 must NOT be validated.
    for mutation in invalid:
        run(blob, mutation=mutation); cases += 1
    run(blob, recursive=True); cases += 1
    print(f'PASS: {cases} offline rank dispatcher cases; atomic claim, all validation gates, '
          'RET12 args, recursion, state/results, EFLAGS/all GPR/ESP and x87/MXCSR/all XMM preserved')


if __name__ == '__main__':
    main()
