"""Exercise actual PE continuation instructions, not just isolated trainer stubs.

The inherited sight-range branch immediately overwrites the old reveal-map
write. A successful isolated MOV test cannot detect this. No game process access.
Select a build and exported stubs via RA3MT_GAME_BUILD / RA3MT_STUBS_DIR.
"""
import json
import struct
import sys
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from game_fixture import STUBS, BUILD, UPRISING

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/analysis'))
from uprising_probe import load

assert UPRISING, 'this suite audits the three Uprising binaries'
key = {'uprising-1.0ea':'ea', 'uprising-1.0':'s0', 'uprising-1.01':'s1'}[BUILD]
_, image = load(key)
catalog = json.loads((ROOT/'assets/uprising.json').read_text(encoding='utf8'))
BLOCK, START, STACK, DATA = 0x40000000, 0x40000040, 0x200000, 0x300000

def put(vm, address, value): vm.mem_write(address, struct.pack('<I', value))
def get(vm, address): return struct.unpack('<I', vm.mem_read(address, 4))[0]
def bits(value): return struct.unpack('<I', struct.pack('<f', value))[0]

def machine(name):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for addr,size in [(BLOCK,0x2000),(0x452000,0x2000),(STACK,0x4000),(DATA,0x10000)]: vm.mem_map(addr,size)
    vm.mem_write(START,(STUBS/(name+'.bin')).read_bytes())
    meta = dict(line.split('=') for line in (STUBS/(name+'.meta')).read_text().splitlines())
    end = int(meta['siteEnd'],16)
    definition = catalog['hooks'][name]
    site = int(definition['rva'][BUILD],16)
    displaced = bytes.fromhex(definition.get('displacedByVersion',{}).get(BUILD,definition['displaced']))
    for i, reg in enumerate([UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
                              UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]): vm.reg_write(reg,DATA+i*0x1000)
    vm.reg_write(UC_X86_REG_ESP,STACK+0x2000)
    vm.reg_write(UC_X86_REG_FPCW,0x37f)
    return vm,end,image[site+len(displaced):site+len(displaced)+128]

cases = 0
for enabled in [0,1]:
    for inherited in [False,True]:
        for original_flags in [0x202,0x893]:
            vm,end,tail = machine('unit_lv')
            assert tail[:14] == bytes.fromhex('7a0cd9855c020000d99d64020000'), 'unaudited vision continuation'
            vm.mem_write(end,tail[:14])
            # PF=0 when the template contains the -1 sentinel: inherit +25C.
            flags = (original_flags & ~4) | (0 if inherited else 4)
            vm.reg_write(UC_X86_REG_EFLAGS,flags)
            vm.reg_write(UC_X86_REG_XMM0,bits(-1.0 if inherited else 600.0))
            ebp = vm.reg_read(UC_X86_REG_EBP)
            put(vm,ebp+0x25c,bits(120.0));put(vm,ebp+0x260,0x12345678)
            vm.mem_write(BLOCK+8,bytes([enabled]))
            vm.emu_start(START,end+14,count=10000)
            expected = bits(100000.0 if enabled else 120.0 if inherited else 600.0)
            assert get(vm,ebp+0x264)==expected, (BUILD,enabled,inherited,'vision overwritten by real game continuation')
            assert get(vm,ebp+0x260)==0x12345678
            assert vm.reg_read(UC_X86_REG_EFLAGS)==flags
            assert vm.reg_read(UC_X86_REG_ESP)==STACK+0x2000
            cases += 1

for enabled in [0,1]:
    for incoming_zf in [0,1]:
        vm,end,tail = machine('power_cool')
        assert tail[:2] == b'\x74\x39', 'unaudited camera clamp branch'
        vm.mem_write(end,tail)
        flags = (0x893 & ~0x40) | incoming_zf*0x40
        vm.reg_write(UC_X86_REG_EFLAGS,flags);vm.mem_write(BLOCK+7,bytes([enabled]))
        vm.reg_write(UC_X86_REG_XMM0,bits(250.0))
        reached=[]
        def stop(machine,address,size,_):
            if address in [end+2,end+2+0x39]:
                reached.append(address);machine.emu_stop()
        vm.hook_add(UC_HOOK_CODE,stop)
        vm.emu_start(START,end+128,count=10000)
        assert reached==[end+2+0x39 if enabled or incoming_zf else end+2]
        expected_flags=flags|0x40 if enabled else flags
        assert vm.reg_read(UC_X86_REG_EFLAGS)==expected_flags
        cases += 1

print(f'PASS {cases} real game continuation cases ({BUILD}): inherited/explicit vision and camera branch')
