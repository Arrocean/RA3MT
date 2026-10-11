"""Verify paired FINAL3-style rank increment API using static binaries and Unicorn.
No process access or live game writes. Helpers are mocked, not full gameplay.
Run: py tools/analysis/verify_final3_rank.py
"""
from pathlib import Path
import hashlib
import json
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
import pefile

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data')
PATTERN = '''55 8B 6C 24 08 85 ED 57 8B F9 7F 07 5F 32 C0 5D C2 0C 00 53 56 32 DB 33 F6 85 ED 7E 3D 8D 49 00 8B 0D ?? ?? ?? ?? 6A 00 57 E8 ?? ?? ?? ?? 85 C0 7E 28 8B 4C 24 1C 8B 54 24 18 51 52 6A 00 6A 00 51 F3 0F 2A C0 8B CF F3 0F 11 04 24 E8 ?? ?? ?? ?? 83 C6 01 3B F5 B3 01 7C C6 5E 8A C3 5B 5F 5D C2 0C 00'''.split()
PAIRS = {'1.12': (0x79A840, 0x538F90, 0x781EB0, 0xCDDE7C),
         '1.13': (0x785600, 0x5213C0, 0x76DF90, 0xCE219C)}
TRACKER, STACK, STOP, CONTEXT = 0x200000, 0x300000, 0x40000000, 0x210000


def u32(vm, address):
    return struct.unpack('<I', vm.mem_read(address, 4))[0]


def put(vm, address, value):
    vm.mem_write(address, struct.pack('<I', value & 0xffffffff))


def run_case(code, entry, threshold, award, global_address, count, flags, needed):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for address in {entry & ~0xfff, threshold & ~0xfff, award & ~0xfff,
                    global_address & ~0xfff, TRACKER, STACK, STOP}:
        vm.mem_map(address, 0x1000)
    vm.mem_write(entry, code)
    vm.mem_write(threshold, bytes.fromhex('C2 08 00'))
    vm.mem_write(award, bytes.fromhex('C2 14 00'))
    put(vm, global_address, CONTEXT)
    sp = STACK + 0x800
    put(vm, sp, STOP)
    put(vm, sp + 4, count)
    put(vm, sp + 8, flags[0])
    put(vm, sp + 12, flags[1])
    vm.reg_write(UC_X86_REG_ESP, sp)
    vm.reg_write(UC_X86_REG_ECX, TRACKER)
    saved = {UC_X86_REG_EBX: 0x1234, UC_X86_REG_ESI: 0x5678,
             UC_X86_REG_EDI: 0x6789, UC_X86_REG_EBP: 0x789a}
    for reg, value in saved.items():
        vm.reg_write(reg, value)
    awards = []
    thresholds = []

    def return_from_helper(machine, bytes_to_pop):
        current_sp = machine.reg_read(UC_X86_REG_ESP)
        target = u32(machine, current_sp)
        machine.reg_write(UC_X86_REG_ESP, current_sp + 4 + bytes_to_pop)
        machine.reg_write(UC_X86_REG_EIP, target)

    def hook(machine, address, size, user):
        if address == threshold:
            current_sp = machine.reg_read(UC_X86_REG_ESP)
            assert machine.reg_read(UC_X86_REG_ECX) == CONTEXT
            assert u32(machine, current_sp + 4) == TRACKER
            assert u32(machine, current_sp + 8) == 0
            value = needed[len(thresholds)] if len(thresholds) < len(needed) else 0
            thresholds.append(value)
            machine.reg_write(UC_X86_REG_EAX, value & 0xffffffff)
            return_from_helper(machine, 8)
        elif address == award:
            current_sp = machine.reg_read(UC_X86_REG_ESP)
            assert machine.reg_read(UC_X86_REG_ECX) == TRACKER
            args = [u32(machine, current_sp + i * 4) for i in range(1, 6)]
            xp = struct.unpack('<f', struct.pack('<I', args[0]))[0]
            assert args[1:] == [0, 0, flags[0], flags[1]]
            awards.append(xp)
            machine.reg_write(UC_X86_REG_EAX, 0xdeadbeef)
            machine.reg_write(UC_X86_REG_ECX, 0xbad)
            machine.reg_write(UC_X86_REG_EDX, 0xbad)
            return_from_helper(machine, 20)

    vm.hook_add(UC_HOOK_CODE, hook)
    try:
        vm.emu_start(entry, STOP, count=10000)
    except Exception:
        print('failed case', hex(entry), count, flags, needed, 'eip', hex(vm.reg_read(UC_X86_REG_EIP)), 'esp', hex(vm.reg_read(UC_X86_REG_ESP)))
        raise
    assert vm.reg_read(UC_X86_REG_EIP) == STOP
    assert vm.reg_read(UC_X86_REG_ESP) == sp + 16
    assert all(vm.reg_read(reg) == value for reg, value in saved.items())
    assert vm.reg_read(UC_X86_REG_EAX) & 0xff == bool(awards)
    expected = []
    for value in needed[:max(count, 0)]:
        if value <= 0:
            break
        expected.append(float(value))
    assert awards == expected


report = {'scope': 'Static paired bytes and mocked-helper x86 execution; no gameplay proof',
          'contract': {'this': 'ExperienceTracker', 'argument1': 'positive rank increment count',
                       'argument2': 'XP award multiplier flag', 'argument3': 'rank refresh flag',
                       'calleeStackPopBytes': 12}, 'versions': {}}
cases = 0
for version, (entry, threshold, award, global_address) in PAIRS.items():
    file = DATA / f'ra3_{version}.game'
    raw = file.read_bytes()
    image = pefile.PE(data=raw)
    mapped = image.get_memory_mapped_image()
    code = image.get_data(entry - 0x400000, len(PATTERN))
    assert len(code) == 99
    assert all(token == '??' or byte == int(token, 16) for byte, token in zip(code, PATTERN))
    exact = bytes.fromhex('55 8B 6C 24 08 85 ED 57 8B F9 7F 07 5F 32 C0 5D C2 0C 00 53 56')
    assert mapped.count(exact) == 1
    assert struct.unpack_from('<I', code, 0x22)[0] == global_address
    assert entry + 0x2e + struct.unpack_from('<i', code, 0x2a)[0] == threshold
    assert entry + 0x51 + struct.unpack_from('<i', code, 0x4d)[0] == award
    for count in [0, -1, 1, 3, 4]:
        for flags in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            for needed in [[100, 250, 500, 800], [100, 0, 500], [0], [-1]]:
                run_case(code, entry, threshold, award, global_address, count, flags, needed)
                cases += 1
    report['versions'][version] = {'sha256': hashlib.sha256(raw).hexdigest(),
        'rva': hex(entry - 0x400000), 'va': hex(entry), 'length': len(code),
        'thresholdHelper': hex(threshold), 'awardHelper': hex(award), 'global': hex(global_address),
        'uniqueGuardMatches': 1}
report['executionCases'] = cases
output = ROOT / 'artifacts' / 'final3' / 'rank_pair.json'
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'PASS paired 99-byte rank increment function; {cases} mocked-helper x86 execution cases')
print(output)
