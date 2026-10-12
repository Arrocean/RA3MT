"""Execute exported C# x86 stubs in Unicorn, without accessing a game process.
Run stubdump artifacts/stubs_semantic first, then py tools/harness/test_execution_stubs.py.
Requires unicorn. These tests validate synthetic contracts, not gameplay effects.
"""
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *

OUT = Path(__file__).resolve().parents[2] / 'artifacts/stubs_semantic'
BLOCK, START, END = 0x40000000, 0x40000040, 0x452100
GLOBAL, STACK, DATA = 0x400000, 0x200000, 0x300000
REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP]


def put(vm, address, value):
    vm.mem_write(address, struct.pack('<I', value))


def get(vm, address):
    return struct.unpack('<I', vm.mem_read(address, 4))[0]


def machine(name):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for address, size in [(BLOCK, 0x2000), (GLOBAL, 0x1000),
                          (STACK, 0x2000), (DATA, 0x10000), (END & ~0xfff, 0x1000)]:
        vm.mem_map(address, size)
    code = (OUT / (name + '.bin')).read_bytes()
    meta = dict(line.split('=') for line in (OUT / (name + '.meta')).read_text().splitlines())
    end = int(meta['siteEnd'], 16)
    vm.mem_write(START, code)
    for i, reg in enumerate(REGS):
        vm.reg_write(reg, 0x1230 + i)
    vm.reg_write(UC_X86_REG_ESP, STACK + 0x1000)
    vm.reg_write(UC_X86_REG_EFLAGS, 0x893)
    return vm, end


def execute(vm, end):
    vm.emu_start(START, end, count=100000)
    assert vm.reg_read(UC_X86_REG_EIP) == end, 'stub failed to reach continuation'


def preserved(vm, before, changed):
    for reg, value in before.items():
        if reg not in changed:
            assert vm.reg_read(reg) == value, ('register changed', reg)


def snapshot(vm):
    return {reg: vm.reg_read(reg) for reg in REGS + [UC_X86_REG_EFLAGS]}


cases = 0
for enabled in [0, 1]:
    for original in [0, 4, 99]:
        vm, end = machine('money_h3')
        vm.reg_write(UC_X86_REG_EAX, DATA)
        vm.reg_write(UC_X86_REG_ESI, DATA + 0x1000)
        put(vm, DATA + 0x34, original)
        put(vm, DATA + 0x103c, 0x123456)
        vm.mem_write(BLOCK + 2, bytes([enabled]))
        before = snapshot(vm)
        execute(vm, end)
        expected = 15 if enabled else original
        assert get(vm, DATA + 0x34) == expected
        assert vm.reg_read(UC_X86_REG_EDI) == expected
        assert vm.reg_read(UC_X86_REG_ECX) == 0x123456
        preserved(vm, before, [UC_X86_REG_EDI, UC_X86_REG_ECX])
        cases += 1

for ready in [0, 1]:
    for freeze in [0, 1]:
        for local in [False, True]:
            for context in ['valid', 'null_root', 'null_side']:
                vm, end = machine('build_power')
                body, cooldown, controller = DATA, DATA + 0x1000, DATA + 0x2000
                side = DATA + 0x3000
                owner = side if local else side + 0x100
                put(vm, GLOBAL, controller if context != 'null_root' else 0)
                put(vm, controller + 0x28, side if context != 'null_side' else 0)
                put(vm, body + 0x418, owner)
                put(vm, cooldown + 0x20, 800)
                vm.mem_write(BLOCK + 5, bytes([ready, freeze]))
                vm.reg_write(UC_X86_REG_EAX, body)
                vm.reg_write(UC_X86_REG_ESI, cooldown)
                vm.reg_write(UC_X86_REG_EDI, 800)
                before = snapshot(vm)
                execute(vm, end)
                value = 800
                if context == 'valid':
                    if local and ready:
                        value = 0
                    elif not local and freeze:
                        value = 801
                assert get(vm, cooldown + 0x20) == value
                assert vm.reg_read(UC_X86_REG_EDI) == value
                assert vm.reg_read(UC_X86_REG_EBX) == owner
                preserved(vm, before, [UC_X86_REG_EDI, UC_X86_REG_EBX])
                cases += 1

for ready in [0, 1]:
    for freeze in [0, 1]:
        for local in [False, True]:
            for shape in ['matched_second', 'missing', 'empty', 'cycle', 'null_root', 'null_side']:
                vm, end = machine('build_hp_a')
                clock, sentinel = DATA, DATA + 0x1000
                node1, node2, controller = DATA + 0x2000, DATA + 0x3000, DATA + 0x4000
                side = DATA + 0x5000
                put(vm, GLOBAL, controller if shape != 'null_root' else 0)
                put(vm, controller + 0x28, side if shape != 'null_side' else 0)
                put(vm, clock + 0x50, 700)
                put(vm, sentinel, sentinel if shape == 'empty' else node1)
                put(vm, sentinel + 0xc, 0xabcdef)
                put(vm, node1, node2)
                put(vm, node1 + 8, 11)
                put(vm, node1 + 0xc, 801)
                put(vm, node2, node1 if shape == 'cycle' else sentinel)
                put(vm, node2 + 8, 22 if shape not in ['missing', 'cycle'] else 33)
                put(vm, node2 + 0xc, 900)
                put(vm, STACK + 0x1004, side if local else side + 0x100)
                vm.mem_write(BLOCK + 5, bytes([ready, freeze]))
                vm.reg_write(UC_X86_REG_EAX, clock)
                vm.reg_write(UC_X86_REG_ECX, sentinel)
                vm.reg_write(UC_X86_REG_EDX, 22)
                before = snapshot(vm)
                execute(vm, end)
                value = 900
                if shape == 'matched_second':
                    if local and ready:
                        value = 700
                    elif not local and freeze:
                        value = 901
                assert get(vm, node2 + 0xc) == value, (ready, freeze, local, shape)
                assert get(vm, node1 + 0xc) == 801
                assert get(vm, sentinel + 0xc) == 0xabcdef
                assert vm.reg_read(UC_X86_REG_EAX) == (sentinel if shape == 'empty' else node1)
                assert vm.reg_read(UC_X86_REG_ESI) == 700
                preserved(vm, before, [UC_X86_REG_EAX, UC_X86_REG_ESI])
                cases += 1

for enabled in [0, 1]:
    for flags in [0x202, 0x243, 0x893]:
        vm, end = machine('power_cool')
        vm.mem_write(BLOCK + 7, bytes([enabled]))
        vm.reg_write(UC_X86_REG_ESI, DATA)
        vm.reg_write(UC_X86_REG_EFLAGS, flags)
        vm.reg_write(UC_X86_REG_XMM0, 0x3f800000)
        before = snapshot(vm)
        execute(vm, end)
        assert get(vm, DATA + 0x44) == 0x3f800000
        assert vm.reg_read(UC_X86_REG_EFLAGS) == (flags | (0x40 if enabled else 0))
        preserved(vm, before, [UC_X86_REG_EFLAGS])
        cases += 1

for capture in [0, 1]:
    for entry in [0, DATA + 0x1000]:
        vm, end = machine('zoom_unit_xp')
        put(vm, DATA, entry)
        vm.reg_write(UC_X86_REG_EDX, DATA)
        vm.reg_write(UC_X86_REG_EDI, 0)
        vm.mem_write(BLOCK + 0xc, bytes([capture]))
        before = snapshot(vm)
        execute(vm, end)
        assert vm.reg_read(UC_X86_REG_ECX) == entry
        flags = vm.reg_read(UC_X86_REG_EFLAGS)
        assert bool(flags & 0x40) == (entry == 0)
        assert (flags & 0x801) == 0
        assert get(vm, BLOCK + 0xffc) == capture
        if capture:
            assert get(vm, BLOCK + 0x1000) == entry
        preserved(vm, before, [UC_X86_REG_ECX, UC_X86_REG_EFLAGS])
        cases += 1

for name in ['ammo'] + ['ammo_' + str(i) for i in range(2, 7)]:
    for component in [0, DATA + 0x2000]:
        for maxon, zeroon in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            vm, end = machine(name)
            vm.reg_write(UC_X86_REG_ECX, DATA)
            put(vm, DATA + 0x1278, component)
            put(vm, DATA + 0x2008, 25)
            vm.mem_write(BLOCK + 0xD, bytes([maxon]))
            vm.mem_write(BLOCK + 0xE, bytes([zeroon]))
            before = snapshot(vm)
            execute(vm, end)
            assert vm.reg_read(UC_X86_REG_EAX) == component
            assert get(vm, BLOCK + 0x2c) == component
            expected = 25
            if component != 0:
                if maxon: expected = 50000
                elif zeroon: expected = 0
            assert get(vm, DATA + 0x2008) == expected, (name, component, maxon, zeroon)
            preserved(vm, before, [UC_X86_REG_EAX])
            cases += 1

for name in ['build_hp_b', 'sidebar_pts']:
    for left, right in [(700, 700), (700, 800), (800, 700)]:
        vm, end = machine(name)
        vm.reg_write(UC_X86_REG_EAX, DATA)
        vm.reg_write(UC_X86_REG_ECX, DATA + 0x1000)
        vm.reg_write(UC_X86_REG_ESI, DATA + 0x2000)
        put(vm, DATA + 0xc, right)
        put(vm, DATA + 0x1050, left)
        put(vm, DATA + 0x50, left)
        put(vm, DATA + 0x2020, right)
        vm.mem_write(BLOCK + 6, b'\x01')
        before = snapshot(vm)
        execute(vm, end)
        target = UC_X86_REG_EDX if name == 'build_hp_b' else UC_X86_REG_ECX
        assert vm.reg_read(target) == left
        assert bool(vm.reg_read(UC_X86_REG_EFLAGS) & 0x40) == (left == right)
        assert get(vm, DATA + 0xc) == right
        assert get(vm, DATA + 0x2020) == right
        preserved(vm, before, [target, UC_X86_REG_EFLAGS])
        cases += 1

for enabled in [0, 1]:
    for selected in [False, True]:
        for local in [False, True]:
            for capacity in [0, 1, 8, 999999, 1000001, 0xffffffff]:
                vm, end = machine('weapon_clip')
                weapon, slot, body = DATA, DATA + 0x1000, DATA + 0x2000
                drawable, controller = DATA + 0x3000, DATA + 0x4000
                wrapper, template, side = DATA + 0x5000, DATA + 0x6000, DATA + 0x7000
                put(vm, weapon + 8, slot)
                put(vm, slot + 0x10, body)
                put(vm, body + 0xf4, drawable)
                vm.mem_write(drawable + 0x13d, bytes([0x40 if selected else 0]))
                put(vm, GLOBAL, controller)
                put(vm, controller + 0x28, side)
                put(vm, body + 0x418, side if local else side + 0x100)
                put(vm, weapon + 4, wrapper)
                put(vm, wrapper + 4, template)
                put(vm, template + 0x70, capacity)
                put(vm, weapon + 0x1c, 3)
                put(vm, weapon + 0x24, 7)
                put(vm, weapon + 0x2c, 9)
                vm.mem_write(BLOCK + 0xa, bytes([enabled]))
                vm.reg_write(UC_X86_REG_ESI, weapon)
                before = snapshot(vm)
                execute(vm, end)
                expected = capacity if enabled and selected and local and 0 < capacity <= 1000000 else 2
                assert get(vm, weapon + 0x1c) == expected
                assert vm.reg_read(UC_X86_REG_EAX) == 0xffffffff
                assert get(vm, weapon + 0x24) == 7 and get(vm, weapon + 0x2c) == 9
                assert (vm.reg_read(UC_X86_REG_EFLAGS) & 0x8d5) == 0x11
                preserved(vm, before, [UC_X86_REG_EAX, UC_X86_REG_EFLAGS])
                cases += 1

for missing in ['slot', 'body', 'drawable', 'controller', 'side', 'wrapper', 'template']:
    vm, end = machine('weapon_clip')
    weapon, slot, body = DATA, DATA + 0x1000, DATA + 0x2000
    drawable, controller = DATA + 0x3000, DATA + 0x4000
    wrapper, template, side = DATA + 0x5000, DATA + 0x6000, DATA + 0x7000
    put(vm, weapon + 8, slot if missing != 'slot' else 0)
    put(vm, slot + 0x10, body if missing != 'body' else 0)
    put(vm, body + 0xf4, drawable if missing != 'drawable' else 0)
    vm.mem_write(drawable + 0x13d, b'\x40')
    put(vm, GLOBAL, controller if missing != 'controller' else 0)
    put(vm, controller + 0x28, side if missing != 'side' else 0)
    put(vm, body + 0x418, side)
    put(vm, weapon + 4, wrapper if missing != 'wrapper' else 0)
    put(vm, wrapper + 4, template if missing != 'template' else 0)
    put(vm, template + 0x70, 8)
    put(vm, weapon + 0x1c, 3)
    vm.mem_write(BLOCK + 0xa, b'\x01')
    vm.reg_write(UC_X86_REG_ESI, weapon)
    before = snapshot(vm)
    execute(vm, end)
    assert get(vm, weapon + 0x1c) == 2, missing
    assert vm.reg_read(UC_X86_REG_EAX) == 0xffffffff
    preserved(vm, before, [UC_X86_REG_EAX, UC_X86_REG_EFLAGS])
    cases += 1


# aiblock [F10] 禁止电脑建造: enemy production increment pinned to 1 per tick.
# entry+0xC is a player SLOT INDEX (game resolves via [root+idx*4+0x30]);
# the local slot index is [[root]+0x28]+0x20 — the game's own local check
# chain (0x11F4BE). The replayed `cmp edx,edi` must set CF exactly like the
# original code so the game's following jb branches correctly.
for enabled in [0, 1]:
    for local in [False, True]:
        for context in ['valid', 'null_root', 'null_side']:
            for local_slot in [0, 2]:       # slot 0 is legal and must not test-skip
                vm, end = machine('aiblock')
                entry, controller, side = DATA, DATA + 0x2000, DATA + 0x3000
                slot = local_slot if local else local_slot + 1
                put(vm, GLOBAL, controller if context != 'null_root' else 0)
                put(vm, controller + 0x28, side if context != 'null_side' else 0)
                put(vm, side + 0x20, local_slot)
                put(vm, entry + 0xC, slot)
                put(vm, entry + 0x14, 4321)      # escrow accumulated
                put(vm, entry + 0x4, 77)         # per-tick increment
                vm.mem_write(BLOCK + 0xB, bytes([enabled]))
                vm.reg_write(UC_X86_REG_EAX, entry)
                vm.reg_write(UC_X86_REG_EDX, 4321)
                vm.reg_write(UC_X86_REG_EDI, 5000)  # remaining budget
                before = snapshot(vm)
                execute(vm, end)
                pinned = enabled == 1 and context == 'valid' and not local
                increment = 1 if pinned else 77
                assert get(vm, entry + 0x4) == increment, (enabled, local, context, local_slot)
                new_edx = 4321 + increment
                assert vm.reg_read(UC_X86_REG_EDX) == new_edx
                # replayed cmp must restore the branch decision for the game's jb
                cf = vm.reg_read(UC_X86_REG_EFLAGS) & 1
                assert cf == (1 if new_edx < 5000 else 0), 'cmp flags not live'
                preserved(vm, before, [UC_X86_REG_EDX, UC_X86_REG_EFLAGS])
                cases += 1


# godmode [F11] 玩家无敌: health fields re-pinned at the health-bar reader.
# ebx=drawable ([ebx+0x138]=body, body+0x418=owner), esi=health module
# ([esi]=vtable, +4 current, +0xC max), eax=[esi] at the site.
import struct as _s
CUR, MAXHP = _s.unpack('<I', _s.pack('<f', 137.0))[0], _s.unpack('<I', _s.pack('<f', 300.0))[0]
PIN = 0x497423F0  # 1000000.0f
for enabled in [0, 1]:
    for local in [False, True]:
        for context in ['valid', 'null_body', 'null_health', 'null_root', 'null_side']:
            vm, end = machine('godmode')
            drawable, body, health, vtable = DATA, DATA + 0x1000, DATA + 0x2000, DATA + 0x4000
            controller, side = DATA + 0x3000, DATA + 0x5000
            owner = side if local else side + 0x100
            put(vm, drawable + 0x138, body if context != 'null_body' else 0)
            put(vm, body + 0x418, owner)
            put(vm, controller + 0x28, side if context != 'null_side' else 0)
            put(vm, GLOBAL, controller if context != 'null_root' else 0)
            put(vm, health, vtable)
            put(vm, health + 0x4, CUR)
            put(vm, health + 0xC, MAXHP)
            put(vm, vtable + 0x3C, 0x5151)
            vm.mem_write(BLOCK + 0xF, bytes([enabled]))
            vm.reg_write(UC_X86_REG_EBX, drawable)
            vm.reg_write(UC_X86_REG_ESI, health if context != 'null_health' else 0)
            vm.reg_write(UC_X86_REG_EAX, vtable)
            before = snapshot(vm)
            execute(vm, end)
            pinned = enabled == 1 and context == 'valid' and local
            assert get(vm, health + 0x4) == (PIN if pinned else CUR), (enabled, local, context)
            assert get(vm, health + 0xC) == (PIN if pinned else MAXHP), (enabled, local, context)
            # replay: mov edx,[eax+3C]; mov ecx,esi
            assert vm.reg_read(UC_X86_REG_EDX) == 0x5151, 'replay mov edx,[eax+3C] lost'
            assert vm.reg_read(UC_X86_REG_ECX) == (health if context != 'null_health' else 0), 'replay mov ecx,esi lost'
            preserved(vm, before, [UC_X86_REG_EDX, UC_X86_REG_ECX])
            cases += 1


# onekill [F12] 一击必杀 family: two data hooks capture the processed body and
# its health module; the main hook (HP adjust write) zeroes current+max HP for
# a non-local victim that passes the combat gate.
vm, end = machine('onekill_a')
body, health = DATA, DATA + 0x4000
put(vm, body + 0x33C, health)
vm.reg_write(UC_X86_REG_ESI, body)
before = snapshot(vm)
execute(vm, end)
assert get(vm, BLOCK + 0x30) == body and get(vm, BLOCK + 0x34) == health
assert vm.reg_read(UC_X86_REG_ECX) == health, 'replay mov ecx,[esi+33C] lost'
preserved(vm, before, [UC_X86_REG_ECX])
cases += 1

vm, end = machine('onekill_b')
put(vm, body + 0x33C, health)
vm.reg_write(UC_X86_REG_ECX, body)
before = snapshot(vm)
execute(vm, end)
assert get(vm, BLOCK + 0x30) == body and get(vm, BLOCK + 0x34) == health
assert vm.reg_read(UC_X86_REG_ECX) == health, 'replay mov ecx,[ecx+33C] lost'
preserved(vm, before, [UC_X86_REG_ECX])  # displaced itself rewrites ecx
cases += 1

import struct as _s2
CUR = _s2.unpack('<I', _s2.pack('<f', 137.0))[0]
for enabled in [0, 1]:
    for victim in ['match_enemy', 'match_local', 'other_health']:
        for context in ['valid', 'gate_zero', 'null_owner', 'null_root', 'null_side']:
            vm, end = machine('onekill')
            drawable = body
            controller, side, owner_obj = DATA + 0x1000, DATA + 0x2000, DATA + 0x5000
            put(vm, controller + 0x28, side if context != 'null_side' else 0)
            put(vm, GLOBAL, controller if context != 'null_root' else 0)
            put(vm, side + 0x20, 2)                       # local slot
            local_owner = victim == 'match_local'
            put(vm, owner_obj + 0x20, 2 if local_owner else 3)
            put(vm, body + 0x418, owner_obj if context != 'null_owner' else 0)
            put(vm, body + 0x390, 5 if context != 'gate_zero' else 0)  # combat gate
            health_now = health if victim.startswith('match') else health + 0x10
            put(vm, BLOCK + 0x30, body)
            put(vm, BLOCK + 0x34, health)
            put(vm, health_now + 0x4, CUR)
            put(vm, health_now + 0xC, CUR)
            vm.mem_write(BLOCK + 0x38, bytes([enabled]))
            vm.reg_write(UC_X86_REG_ESI, health_now)
            vm.reg_write(UC_X86_REG_XMM0, 0x40490000)     # 3.0f as pending new HP
            before = snapshot(vm)
            execute(vm, end)
            kill = enabled == 1 and victim == 'match_enemy' and context == 'valid'
            expected_hp = 0 if kill else 0x40490000        # replay stores xmm0
            assert get(vm, health_now + 0x4) == expected_hp, (enabled, victim, context)
            assert get(vm, health_now + 0xC) == (0 if kill else CUR), (enabled, victim, context)
            preserved(vm, before, [])
            cases += 1

print(f'PASS {cases} x86 execution cases including selected local Weapon clip refill, capacity and null guards')
