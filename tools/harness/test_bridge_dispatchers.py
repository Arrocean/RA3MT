"""Execute C#-exported capture/kill dispatcher bytes offline in Unicorn.
Run SelfCheck stubdump artifacts/stubs_semantic first, then this script.
Requires unicorn; no process access, remote calls, game writes or native threads.
"""
from pathlib import Path
import argparse
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

ROOT = Path(__file__).resolve().parents[2]
BLOCK, GLOBAL = 0x40000000, 0x400000
STACK, DATA = 0x200000, 0x300000
CAPTURE, KILL, CAPTURE_API, KILL_API = BLOCK + 0x1300, BLOCK + 0x1400, 0x7B5DF0, 0x78CB30
CALLER = GLOBAL + 0x800
BODY, DRAWABLE, CONTROLLER, SIDE, CTX, HP = (DATA, DATA + 0x1000, DATA + 0x2000,
                                             DATA + 0x3000, DATA + 0x4000, DATA + 0x5000)
MAILC, MAILK = BLOCK + 0x1840, BLOCK + 0x1880
REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS]
XMM = [UC_X86_REG_XMM0, UC_X86_REG_XMM1, UC_X86_REG_XMM2, UC_X86_REG_XMM3,
       UC_X86_REG_XMM4, UC_X86_REG_XMM5, UC_X86_REG_XMM6, UC_X86_REG_XMM7]


def put(vm, addr, value):
    vm.mem_write(addr, struct.pack('<I', value & 0xffffffff))


def get(vm, addr):
    return struct.unpack('<I', vm.mem_read(addr, 4))[0]


def fx_image(vm):
    addr = DATA + 0x10000
    vm.mem_write(GLOBAL + 0x900, b'\x0F\xAE\x05' + struct.pack('<I', addr))
    vm.emu_start(GLOBAL + 0x900, GLOBAL + 0x907, count=1)
    image = bytearray(vm.mem_read(addr, 416))
    image[8:16] = bytes(8)
    return bytes(image)


def base_machine(align):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr, size in [(BLOCK, 0x2000), (GLOBAL, 0x1000), (DATA, 0x20000),
                       (STACK, 0x10000), (CAPTURE_API & ~0xfff, 0x1000), (KILL_API & ~0xfff, 0x1000)]:
        vm.mem_map(addr, size)
    vm.mem_write(CALLER, b'\xE8' + struct.pack('<i', 0) + b'\x90')  # patched per dispatcher
    vm.mem_write(GLOBAL + 0xa00, bytes.fromhex('db e3 d9 e8 d9 eb'))
    vm.emu_start(GLOBAL + 0xa00, GLOBAL + 0xa06)
    for i, reg in enumerate(REGS[:-2]):
        vm.reg_write(reg, 0x12340000 + i)
    vm.reg_write(UC_X86_REG_ESP, STACK + 0x8000 + align)
    vm.reg_write(UC_X86_REG_EFLAGS, 0x893)
    vm.reg_write(UC_X86_REG_MXCSR, 0x3f80)
    for i, reg in enumerate(XMM):
        vm.reg_write(reg, (0xfedcba9876543210 << 64) | (0x123456789abcdef0 + i))
    return vm


def shared_entries(vm, own=False):
    put(vm, MAILC + 4, BODY)
    put(vm, MAILC + 8, DRAWABLE)
    put(vm, MAILK + 4, BODY)
    put(vm, MAILK + 8, DRAWABLE)
    put(vm, MAILK + 12, HP)
    put(vm, BODY + 0xF4, DRAWABLE)
    put(vm, DRAWABLE + 0x138, BODY)
    put(vm, BODY + 0x33C, HP)
    vm.mem_write(DRAWABLE + 0x13D, b'\x40')
    put(vm, GLOBAL, CONTROLLER)
    put(vm, CONTROLLER + 0x28, SIDE)
    put(vm, BODY + 0x418, SIDE if own else SIDE + 0x100)
    put(vm, SIDE + 0xAC, CTX)
    put(vm, CTX + 4, DATA + 0x6000)
    put(vm, DATA + 0x6008, SIDE)


def run_capture(blob, align=0, state=1, mutation=None, api_side_effect=True):
    vm = base_machine(align)
    vm.mem_write(CAPTURE, blob)
    vm.mem_write(CALLER, b'\xE8' + struct.pack('<i', CAPTURE - (CALLER + 5)))
    vm.mem_write(CAPTURE_API, bytes.fromhex('C2 08 00'))
    shared_entries(vm)
    put(vm, MAILC, state)
    if mutation:
        mutation(vm)
    payload = bytes(vm.mem_read(MAILC + 4, 8))
    fx_before, regs_before = fx_image(vm), {r: vm.reg_read(r) for r in REGS}
    calls = []
    def fake_api(machine, address, size, _):
        sp = machine.reg_read(UC_X86_REG_ESP)
        assert machine.reg_read(UC_X86_REG_ECX) == BODY
        assert get(machine, sp + 4) == CTX and get(machine, sp + 8) == 0
        assert (sp + 16) % 16 == 0
        calls.append(address)
        if api_side_effect:
            put(machine, BODY + 0x418, SIDE)
        for i, reg in enumerate(REGS[:-2]):
            machine.reg_write(reg, 0x55550000 + i)
    vm.hook_add(UC_HOOK_CODE, fake_api, begin=CAPTURE_API, end=CAPTURE_API + 1)
    vm.emu_start(CALLER, CALLER + 5, count=10000)
    assert all(vm.reg_read(r) == v for r, v in regs_before.items()), 'GPR/ESP/EFLAGS changed'
    assert fx_image(vm) == fx_before, 'FX image changed'
    assert bytes(vm.mem_read(MAILC + 4, 8)) == payload, 'payload mutated'
    valid = state == 1 and not mutation and api_side_effect
    assert len(calls) == (1 if state == 1 and not mutation else 0)
    if valid:
        assert get(vm, MAILC) == 3
    elif state != 1:
        assert get(vm, MAILC) == state
    else:
        assert get(vm, MAILC) == 4


def run_kill(blob, align=0, state=1, mutation=None, api_zeroes=True):
    vm = base_machine(align)
    vm.mem_write(KILL, blob)
    vm.mem_write(CALLER, b'\xE8' + struct.pack('<i', KILL - (CALLER + 5)))
    vm.mem_write(KILL_API, bytes.fromhex('C2 08 00'))
    shared_entries(vm)
    put(vm, MAILK, state)
    put(vm, HP + 4, struct.unpack('<I', struct.pack('<f', 45.0))[0])
    if mutation:
        mutation(vm)
    payload = bytes(vm.mem_read(MAILK + 4, 12))
    fx_before, regs_before = fx_image(vm), {r: vm.reg_read(r) for r in REGS}
    calls = []
    def fake_api(machine, address, size, _):
        sp = machine.reg_read(UC_X86_REG_ESP)
        assert machine.reg_read(UC_X86_REG_ECX) == HP
        assert get(machine, sp + 4) == 0xFF7FFFFF and get(machine, sp + 8) == 0
        assert (sp + 16) % 16 == 0
        calls.append(address)
        if api_zeroes:
            machine.mem_write(HP + 4, b'\x00\x00\x00\x00')
        for i, reg in enumerate(REGS[:-2]):
            machine.reg_write(reg, 0x55550000 + i)
    vm.hook_add(UC_HOOK_CODE, fake_api, begin=KILL_API, end=KILL_API + 1)
    vm.emu_start(CALLER, CALLER + 5, count=10000)
    assert all(vm.reg_read(r) == v for r, v in regs_before.items()), 'GPR/ESP/EFLAGS changed'
    assert fx_image(vm) == fx_before, 'FX image changed'
    assert bytes(vm.mem_read(MAILK + 4, 12)) == payload, 'payload mutated'
    assert len(calls) == (1 if state == 1 and not mutation else 0)
    if state == 1 and not mutation:
        assert get(vm, MAILK) == (3 if api_zeroes else 4)
    elif state != 1:
        assert get(vm, MAILK) == state
    else:
        assert get(vm, MAILK) == 4


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture-bin', type=Path, default=ROOT / 'artifacts/stubs_semantic/capture_dispatcher.bin')
    ap.add_argument('--kill-bin', type=Path, default=ROOT / 'artifacts/stubs_semantic/kill_dispatcher.bin')
    cblob, kblob = ap.parse_args().capture_bin.read_bytes(), ap.parse_args().kill_bin.read_bytes()
    assert cblob[:2] == b'\x9C\x60' and cblob[-3:] == b'\x61\x9D\xC3'
    assert kblob[:2] == b'\x9C\x60' and kblob[-3:] == b'\x61\x9D\xC3'
    cases = 0
    for align in range(16):
        run_capture(cblob, align=align); run_kill(kblob, align=align); cases += 2
    for state in (0, 2, 3, 4, 0xffffffff):
        run_capture(cblob, state=state); run_kill(kblob, state=state); cases += 2
    for mut in [lambda vm: put(vm, MAILC + 4, 0), lambda vm: put(vm, MAILC + 8, 0xffff),
                lambda vm: put(vm, BODY + 0xF4, DATA + 0x9000),
                lambda vm: put(vm, DRAWABLE + 0x138, DATA + 0x9000),
                lambda vm: vm.mem_write(DRAWABLE + 0x13D, b'\x00'),
                lambda vm: put(vm, GLOBAL, 0),
                lambda vm: put(vm, CONTROLLER + 0x28, 0),
                lambda vm: put(vm, SIDE + 0xAC, 0),
                lambda vm: put(vm, CTX + 4, 0),
                lambda vm: put(vm, DATA + 0x6008, SIDE + 8)]:
        run_capture(cblob, mutation=mut); cases += 1
    run_capture(cblob, mutation=None, api_side_effect=False); cases += 1  # transition no-op → Reject
    run_capture(cblob, mutation=lambda vm: put(vm, BODY + 0x418, SIDE)); cases += 1  # already ours → Reject
    for mut in [lambda vm: put(vm, MAILK + 12, DATA + 0x7000),
                lambda vm: put(vm, BODY + 0x33C, DATA + 0x7000),
                lambda vm: put(vm, BODY + 0xF4, DATA + 0x9000),
                lambda vm: vm.mem_write(DRAWABLE + 0x13D, b'\x10'),
                lambda vm: put(vm, MAILK + 4, 0)]:
        run_kill(kblob, mutation=mut); cases += 1
    run_kill(kblob, api_zeroes=False); cases += 1  # hp stays alive → Reject
    print(f'PASS: {cases} capture/kill dispatcher cases; claim gating, validation gates, '
          'thiscall args, stack alignment, callee-clobber and FX preservation')


if __name__ == '__main__':
    main()
