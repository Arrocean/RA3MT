"""Execute the C#-exported spawn dispatcher bytes offline in Unicorn.
Run SelfCheck stubdump <dir> first, then: py tools/harness/test_spawn_dispatcher.py [dir]
Requires unicorn; no process access, remote calls, game writes or native threads.

Covers: mailbox claim gating, hash-lookup vs direct-holder template paths,
owner resolution through the playerRoot global, wrapper cdecl ABI
(five args, caller-cleans), callee-clobber/GPR/FX preservation, stack
alignment at the wrapper entry, every rejection gate, and the mouse mode:
the transform must receive the RAW INT pixels from the mouse object
(not fxsave residue), and its failure must fall back to the staged pos.
"""
from pathlib import Path
import argparse
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

ROOT = Path(__file__).resolve().parents[2]
BLOCK, GLOBAL = 0x40000000, 0x400000
STACK, DATA = 0x200000, 0x300000
SPAWN = BLOCK + 0x1580
WRAPPER, LOOKUP, TABLE_GLOBAL = 0x62E3E0, 0x80D5B0, 0xCF0108
TRANSFORM, MOUSE_GLOBAL, MOUSE_OBJ = 0x60ECF0, 0xCE43BC, DATA + 0x8000
CALLER = GLOBAL + 0x800
HOLDER, DESC, CONTROLLER, SIDE, NEWBODY, HASHROW = (
    DATA, DATA + 0x1000, DATA + 0x2000, DATA + 0x3000, DATA + 0x4000, DATA + 0x5000)
MAIL = BLOCK + 0x18C0
REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS]
XMM = [UC_X86_REG_XMM0, UC_X86_REG_XMM1, UC_X86_REG_XMM2, UC_X86_REG_XMM3,
       UC_X86_REG_XMM4, UC_X86_REG_XMM5, UC_X86_REG_XMM6, UC_X86_REG_XMM7]
POS = (117.5, -42.25, 305.0)
MOUSE_PX = (0x511, 0x437)          # integer screen pixels, as the live object stores them
TRANSFORMED = (2161.0, 190.0, 5000.0)


def put(vm, addr, value):
    vm.mem_write(addr, struct.pack('<I', value & 0xffffffff))


def get(vm, addr):
    return struct.unpack('<I', vm.mem_read(addr, 4))[0]


def fx_image(vm):
    addr = DATA + 0x10000
    vm.mem_write(GLOBAL + 0x900, b'\x0F\xAE\x05' + struct.pack('<I', addr))
    vm.emu_start(GLOBAL + 0x900, GLOBAL + 0x907, count=1)
    image = bytearray(vm.mem_read(addr, 416))
    image[8:16] = bytes(8)  # FIP/FDP are volatile in the emulator
    return bytes(image)


def base_machine(align):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr, size in [(BLOCK, 0x2000), (GLOBAL, 0x1000), (DATA, 0x20000),
                       (STACK, 0x10000), (WRAPPER & ~0xfff, 0x1000),
                       (LOOKUP & ~0xfff, 0x1000), (TABLE_GLOBAL & ~0xfff, 0x1000),
                       (TRANSFORM & ~0xfff, 0x1000), (MOUSE_GLOBAL & ~0xfff, 0x1000)]:
        vm.mem_map(addr, size)
    vm.mem_write(CALLER, b'\xE8' + struct.pack('<i', SPAWN - (CALLER + 5)) + b'\x90')
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


def shared_entries(vm):
    put(vm, HOLDER + 0x14, DESC)
    put(vm, GLOBAL, CONTROLLER)          # playerRoot global → controller
    put(vm, CONTROLLER + 0x28, SIDE)     # local side
    vm.mem_write(MAIL + 0xC, struct.pack('<fff', *POS))


def fake_lookup(vm, calls, result):
    """thiscall(ecx=table owner, [esp+4]=hash) → holder; ret 4."""
    def hook(machine, address, size, _):
        sp = machine.reg_read(UC_X86_REG_ESP)
        calls.append(('lookup', machine.reg_read(UC_X86_REG_ECX), get(machine, sp + 4)))
        machine.reg_write(UC_X86_REG_EAX, result)
        machine.reg_write(UC_X86_REG_ESP, sp + 8)
        machine.reg_write(UC_X86_REG_EIP, get(machine, sp))
    vm.hook_add(UC_HOOK_CODE, hook, begin=LOOKUP, end=LOOKUP + 1)


def fake_wrapper(vm, calls, result):
    """cdecl(0, holder, float3* pos, owner, 0) → new body."""
    def hook(machine, address, size, _):
        sp = machine.reg_read(UC_X86_REG_ESP)
        assert sp % 16 == 0, f'wrapper entry misaligned: esp%16={sp % 16}'
        args = [get(machine, sp + 4 * i) for i in range(1, 6)]
        assert args[0] == 0 and args[4] == 0
        pos_ptr = args[2]
        xyz = struct.unpack('<fff', machine.mem_read(pos_ptr, 12))
        calls.append(('wrapper', args[1], args[3], xyz, sp % 16))
        # clobber every GPR + XMM like a real game function, then return
        for i, reg in enumerate(REGS[:-2]):
            machine.reg_write(reg, 0x55550000 + i)
        for i, reg in enumerate(XMM):
            machine.reg_write(reg, (0xdeadbeefdeadbeef << 64) | 0xcafebabecafebabe)
        machine.reg_write(UC_X86_REG_EFLAGS, 0x246)
        machine.reg_write(UC_X86_REG_EAX, result)
        machine.reg_write(UC_X86_REG_EIP, get(machine, sp))
        machine.reg_write(UC_X86_REG_ESP, sp + 4)  # cdecl: caller cleans args
    vm.hook_add(UC_HOOK_CODE, hook, begin=WRAPPER, end=WRAPPER + 1)


def fake_transform(vm, calls, out_xyz, result=True):
    """cdecl(int2* pixels, float3* out, 0, 0) → al. Mirrors the game's own
    callers: raw int pixels in, float3 world out, flags 0/0, caller cleans.
    Unlike the wrapper fake, this must respect the cdecl convention and
    preserve EBX/ESI/EDI/EBP — the stub keeps its template/owner in EDI/EBP
    across the call, as it may with any real game function."""
    def hook(machine, address, size, _):
        sp = machine.reg_read(UC_X86_REG_ESP)
        args = [get(machine, sp + 4 * i) for i in range(1, 5)]
        pixels = struct.unpack('<II', machine.mem_read(args[0], 8))
        calls.append(('transform', pixels, args[1], args[2], args[3]))
        assert args[2] == 0 and args[3] == 0, 'transform flags must be 0/0'
        if result:
            machine.mem_write(args[1], struct.pack('<fff', *out_xyz))
        for reg in (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX):
            machine.reg_write(reg, 0x66660000)
        for i, reg in enumerate(XMM):
            machine.reg_write(reg, (0x0badf00d0badf00d << 64) | 0xfeedfacefeedface)
        machine.reg_write(UC_X86_REG_EFLAGS, 0x246)
        machine.reg_write(UC_X86_REG_EAX, 1 if result else 0)
        machine.reg_write(UC_X86_REG_EIP, get(machine, sp))
        machine.reg_write(UC_X86_REG_ESP, sp + 4)  # cdecl: caller cleans args
    vm.hook_add(UC_HOOK_CODE, hook, begin=TRANSFORM, end=TRANSFORM + 1)


def run(blob, align=0, state=1, mutation=None, lookup_result=HOLDER,
        wrapper_result=NEWBODY, owner=0, hash_value=0xAF4C0DA5,
        table_owner=CONTROLLER, expect_wrapper=True, expect_lookup=True,
        mouse=False, transform_result=True, expect_transform=True):
    vm = base_machine(align)
    vm.mem_write(SPAWN, blob)
    shared_entries(vm)
    if table_owner is not None:
        put(vm, TABLE_GLOBAL, table_owner)
    # hash path: table owner+0x28 → buckets; emulate the real lookup by hook.
    put(vm, MAIL + 4, hash_value)
    put(vm, MAIL + 8, HOLDER if hash_value == 0 else 0)
    put(vm, MAIL + 0x18, owner)
    put(vm, MAIL + 0x24, 1 if mouse else 0)
    if mouse:
        put(vm, MOUSE_GLOBAL, MOUSE_OBJ)
        put(vm, MOUSE_OBJ + 0x3C, MOUSE_PX[0])
        put(vm, MOUSE_OBJ + 0x40, MOUSE_PX[1])
    put(vm, MAIL, state)
    if mutation:
        mutation(vm)
    fx_before, regs_before = fx_image(vm), {r: vm.reg_read(r) for r in REGS}
    calls = []
    fake_lookup(vm, calls, lookup_result)
    fake_wrapper(vm, calls, wrapper_result)
    if mouse:
        fake_transform(vm, calls, TRANSFORMED, transform_result)
    vm.emu_start(CALLER, CALLER + 5, count=100000)
    assert all(vm.reg_read(r) == v for r, v in regs_before.items()), 'GPR/ESP/EFLAGS changed'
    assert fx_image(vm) == fx_before, 'FX image changed'
    transforms = [c for c in calls if c[0] == 'transform']
    if mouse and expect_transform:
        assert len(transforms) == 1, f'transform calls: {len(transforms)}'
        _, pixels, out_ptr, flag3, flag4 = transforms[0]
        assert pixels == MOUSE_PX, f'transform got {pixels}, want raw ints {MOUSE_PX}'
        assert out_ptr == MAIL + 0xC, f'out 0x{out_ptr:X} is not the mailbox pos'
    else:
        assert not transforms, 'unexpected transform call'
    lookups = [c for c in calls if c[0] == 'lookup']
    wrappers = [c for c in calls if c[0] == 'wrapper']
    if expect_lookup:
        assert len(lookups) == 1, f'lookup calls: {len(lookups)}'
        assert lookups[0][1] == CONTROLLER, 'lookup this != table owner'
        assert lookups[0][2] == hash_value, 'lookup hash argument wrong'
    else:
        assert not lookups, 'unexpected lookup call'
    if expect_wrapper:
        assert len(wrappers) == 1, f'wrapper calls: {len(wrappers)}'
        _, holder_arg, owner_arg, xyz, entry = wrappers[0]
        assert holder_arg == (HOLDER if hash_value == 0 else lookup_result)
        expected_xyz = TRANSFORMED if (mouse and transform_result) else POS
        assert xyz == expected_xyz, f'position mismatch: {xyz} != {expected_xyz}'
        expected_owner = SIDE if owner == 0 else owner
        assert owner_arg == expected_owner, f'owner {owner_arg:X} != {expected_owner:X}'
    else:
        assert not wrappers, 'unexpected wrapper call'
    return vm, calls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dir', nargs='?', default=str(ROOT / 'artifacts/stubs'),
                        help='stubdump output directory')
    args = parser.parse_args()
    blob = (Path(args.dir) / 'spawn_dispatcher.bin').read_bytes()
    cases = 0

    # 1) hash path happy path: lookup resolves, wrapper spawns, state 3 + result body
    vm, _ = run(blob)
    assert get(vm, MAIL) == 3
    assert get(vm, MAIL + 0x1C) == NEWBODY, 'result body not recorded'
    assert get(vm, MAIL + 0x20) == HOLDER, 'resolved holder not recorded'
    cases += 1

    # 2) hash path, every stack alignment of the caller
    for align in (0, 4, 8, 12):
        vm, _ = run(blob, align=align)
        assert get(vm, MAIL) == 3, f'align {align} failed'
        cases += 1

    # 3) direct holder path (hash == 0): no lookup call
    vm, calls = run(blob, hash_value=0, expect_lookup=False)
    assert get(vm, MAIL) == 3 and get(vm, MAIL + 0x1C) == NEWBODY
    assert not [c for c in calls if c[0] == 'lookup']
    cases += 1

    # 4) explicit owner is passed through untouched
    explicit = SIDE + 0x777
    vm, _ = run(blob, owner=explicit)
    assert get(vm, MAIL) == 3
    cases += 1

    # 5) wrapper returns 0 → reject
    vm, _ = run(blob, wrapper_result=0)
    assert get(vm, MAIL) == 4 and get(vm, MAIL + 0x1C) == 0
    cases += 1

    # 6) unknown hash (lookup returns 0) → reject, wrapper never called
    vm, _ = run(blob, lookup_result=0, expect_wrapper=False)
    assert get(vm, MAIL) == 4
    cases += 1

    # 7) hash-table global holds a null/low owner → reject before lookup
    def null_table(vm_):
        put(vm_, TABLE_GLOBAL, 0)
    vm, _ = run(blob, mutation=null_table, expect_lookup=False, expect_wrapper=False)
    assert get(vm, MAIL) == 4
    cases += 1

    # 8) direct holder path with null holder → reject
    def null_holder(vm_):
        put(vm_, MAIL + 8, 0)
    vm, _ = run(blob, hash_value=0, mutation=null_holder, expect_lookup=False, expect_wrapper=False)
    assert get(vm, MAIL) == 4
    cases += 1

    # 9) direct holder path with null descriptor → reject (wrapper would crash)
    def null_descriptor(vm_):
        put(vm_, HOLDER + 0x14, 0)
    vm, _ = run(blob, hash_value=0, mutation=null_descriptor, expect_lookup=False, expect_wrapper=False)
    assert get(vm, MAIL) == 4
    cases += 1

    # 10) owner=0 with broken playerRoot global → reject, no wrapper call
    def null_root(vm_):
        put(vm_, GLOBAL, 0)
    vm, _ = run(blob, mutation=null_root, expect_wrapper=False)
    assert get(vm, MAIL) == 4
    cases += 1

    # 11) owner=0, controller has no side at +0x28 → reject
    def null_side(vm_):
        put(vm_, CONTROLLER + 0x28, 0)
    vm, _ = run(blob, mutation=null_side, expect_wrapper=False)
    assert get(vm, MAIL) == 4
    cases += 1

    # 12) non-pending states are never claimed
    for state in (0, 2, 3, 4):
        vm, _ = run(blob, state=state, expect_lookup=False, expect_wrapper=False)
        assert get(vm, MAIL) == state, f'state {state} was consumed'
        cases += 1

    # 13) dispatcher never mutates the published payload fields
    vm, _ = run(blob)
    payload = bytes(vm.mem_read(MAIL + 4, 0x1C))
    assert struct.unpack('<I', payload[0:4])[0] == 0xAF4C0DA5
    assert struct.unpack('<fff', payload[8:20]) == POS
    cases += 1

    # 14) re-claim of a fresh pending request after a terminal state works
    vm = base_machine(0)
    vm.mem_write(SPAWN, blob)
    shared_entries(vm)
    put(vm, TABLE_GLOBAL, CONTROLLER)
    put(vm, MAIL + 4, 0xAF4C0DA5)
    put(vm, MAIL + 8, 0)
    put(vm, MAIL + 0x18, 0)
    put(vm, MAIL + 0x24, 0)
    fake_lookup(vm, [], HOLDER)
    fake_wrapper(vm, [], NEWBODY)
    put(vm, MAIL, 3)  # previous success → Submit may republish
    put(vm, MAIL, 1)
    vm.emu_start(CALLER, CALLER + 5, count=100000)
    assert get(vm, MAIL) == 3
    cases += 1

    # 15) mouse mode: transform receives the RAW INT pixels, wrapper spawns at
    # the transformed world position (regression for the fxsave-residue lea bug)
    vm, calls = run(blob, mouse=True)
    assert get(vm, MAIL) == 3
    cases += 1

    # 16) mouse mode under both stack parities
    for align in (4, 12):
        vm, _ = run(blob, align=align, mouse=True)
        assert get(vm, MAIL) == 3, f'mouse align {align} failed'
        cases += 1

    # 17) transform failure falls back to the staged mailbox position
    vm, calls = run(blob, mouse=True, transform_result=False)
    assert get(vm, MAIL) == 3, 'fallback after transform failure must still spawn'
    cases += 1

    # 18) mouse object global null → reject after lookup, before transform/wrapper
    # (must exit through the FX-restore path: the frame was already reserved)
    def null_mouse(vm_):
        put(vm_, MOUSE_GLOBAL, 0)
    vm, _ = run(blob, mouse=True, mutation=null_mouse,
                expect_wrapper=False, expect_transform=False)
    assert get(vm, MAIL) == 4
    cases += 1

    print(f'PASS {cases} spawn dispatcher Unicorn cases '
          '(claim/hash/direct/owner/ABI/clobber/FX/alignment/mouse gates)')


if __name__ == '__main__':
    main()
