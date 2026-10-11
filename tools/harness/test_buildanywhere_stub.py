"""Offline Unicorn tests for the build-anywhere detour stub.
Run SelfCheck stubdump <dir> first, then: py tools/harness/test_buildanywhere_stub.py [dir]

The stub replaces the head of the game's region-line check (thiscall ret 8).
Flag on  → mov al,1; ret 8            (any two points count as the same region)
Flag off → replay the displaced bytes verbatim and jump back (exact original
           semantics: the following jne consumes the replayed test's flags).
"""
from pathlib import Path
import argparse
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *

ROOT = Path(__file__).resolve().parents[2]
BLOCK = 0x40000000                        # synthetic MasterCode block VA (stubdump layout)
FLAG = BLOCK + 0x0B                       # buildanywhere flag byte in the block
STACK, DATA = 0x200000, 0x300000
CALLER = 0x400000                         # small trampoline area (calls the site)
# stubdump synthesizes stubs for a site at 0x452100 (see Program.cs fakeSite);
# the emitted jmp-back target is baked in, so the test must use the same VA.
SITE = 0x452100
SITE_END = SITE + 12                      # after the displaced 12 bytes
ARG1, ARG2 = DATA + 0x100, DATA + 0x200
DISPLACED = bytes.fromhex('83EC608B411485C0894C2438')


def setup():
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr, size in [(BLOCK, 0x2000), (STACK, 0x10000), (DATA, 0x1000), (CALLER, 0x1000),
                       (SITE & ~0xFFF, 0x2000), (0x451000, 0x1000), (0x501000, 0x1000)]:
        vm.mem_map(addr, size)
    # displaced + the original jne; both paths balance the replayed sub esp,0x60
    # and return to the caller exactly like the real function does.
    vm.mem_write(SITE, DISPLACED +
                 b'\x75\x08'                                   # jne true-path
                 b'\x32\xC0\x83\xC4\x60\xC2\x08\x00'           # false: xor al,al; add esp,0x60; ret 8
                 b'\xB0\x01\x83\xC4\x60\xC2\x08\x00')          # true:  mov al,1;  add esp,0x60; ret 8
    # caller: push arg2; push arg1; call site; land marker
    vm.mem_write(CALLER, b'\x68' + struct.pack('<I', ARG2) +
                 b'\x68' + struct.pack('<I', ARG1) +
                 b'\xE8' + struct.pack('<i', SITE - (CALLER + 15)) +
                 b'\x90')
    return vm


def run(flag_on):
    vm = setup()
    stub = (Path(ARTS) / 'buildanywhere.bin').read_bytes()
    stub_va = BLOCK + 0x40
    vm.mem_write(stub_va, stub)
    # patch the site with E9 -> stub + NOP padding (12 bytes)
    patch = b'\xE9' + struct.pack('<i', stub_va - (SITE + 5)) + b'\x90' * 7
    vm.mem_write(SITE, patch)
    vm.mem_write(FLAG, b'\x01' if flag_on else b'\x00')
    # pre-call state
    vm.reg_write(UC_X86_REG_ECX, 0x501234)
    vm.reg_write(UC_X86_REG_EAX, 0xDEAD)
    esp0 = STACK + 0x8000
    vm.reg_write(UC_X86_REG_ESP, esp0)
    vm.reg_write(UC_X86_REG_EFLAGS, 0x202)
    # this-call: the site expects [esp+4]=arg1, [esp+8]=arg2 after the return address.
    # Our trampoline pushes them, then CALL pushes the return address.
    stop = CALLER + 16  # after the trailing 0x90
    vm.emu_start(CALLER, stop, count=1000)
    return vm, esp0


ARTS = str(ROOT / 'artifacts/stubs_v2')


def main():
    global ARTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dir', nargs='?', default=ARTS)
    args = parser.parse_args()
    ARTS = args.dir
    stub = (Path(ARTS) / 'buildanywhere.bin').read_bytes()
    assert stub[0:1] == b'\x9c', 'stub must start with pushfd'
    cases = 0

    # flag on: immediate success return, no memory writes, args cleaned by ret 8
    vm, esp0 = run(True)
    assert vm.reg_read(UC_X86_REG_EIP) == CALLER + 16, 'did not return to caller'
    assert vm.reg_read(UC_X86_REG_EAX) & 0xFF == 1, 'flag-on must return al=1'
    assert vm.reg_read(UC_X86_REG_ESP) == esp0, 'ret 8 must pop both args'
    assert vm.mem_read(DATA + 0x40, 4) == b'\x00' * 4, 'flag-on must not touch data'
    cases += 1

    # flag off: replay the original prologue verbatim then jump to the jne.
    vm, esp0 = run(False)
    assert vm.reg_read(UC_X86_REG_EIP) == CALLER + 16, 'flag-off must return through the site tail'
    assert vm.reg_read(UC_X86_REG_ESP) == esp0, 'site tail must balance the replayed sub esp,0x60'
    # replayed mov [esp+0x38],ecx wrote the caller-save slot below the args
    saved = struct.unpack('<I', vm.mem_read(esp0 - 12 - 0x60 + 0x38, 4))[0]
    assert saved == 0x501234, 'replayed mov [esp+38],ecx not executed'
    # eax==0 (null field) -> ZF=1 -> the site's jne takes the false path (al=0)
    assert vm.reg_read(UC_X86_REG_EAX) & 0xFF == 0, 'replay must produce the false path'
    cases += 1

    # flag off with a non-null [ecx+0x14]: ZF clear, matching the original test.
    vm2 = setup()
    stub_va = BLOCK + 0x40
    vm2.mem_write(stub_va, stub)
    patch = b'\xE9' + struct.pack('<i', stub_va - (SITE + 5)) + b'\x90' * 7
    vm2.mem_write(SITE, patch)
    vm2.mem_write(FLAG, b'\x00')
    vm2.mem_write(0x501234 + 0x14, struct.pack('<I', 0x777))
    vm2.reg_write(UC_X86_REG_ECX, 0x501234)
    vm2.reg_write(UC_X86_REG_ESP, STACK + 0x8000)
    vm2.reg_write(UC_X86_REG_EFLAGS, 0x202)
    vm2.emu_start(CALLER, CALLER + 16, count=1000)
    # non-null field -> ZF=0 -> the jne takes the true path (al=1)
    assert vm2.reg_read(UC_X86_REG_EAX) & 0xFF == 1, 'non-null must produce the true path'
    cases += 1

    print(f'PASS {cases} build-anywhere stub cases '
          '(flag-on success return; flag-off verbatim replay + ZF semantics)')


if __name__ == '__main__':
    main()
