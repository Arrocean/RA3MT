"""Compare every disabled hook against its original displaced instructions.
Game data, stack, GPRs, flags, x87 and SSE must agree. Diagnostic writes inside
the trainer's private block are excluded. No game process is opened.
"""
import json
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *
from game_fixture import STUBS, UPRISING, BUILD

ROOT=Path(__file__).resolve().parents[2]
DATA,STACK,BLOCK,START,GLOBAL=0x300000,0x200000,0x40000000,0x40000040,0x400000
REGS=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
      UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EFLAGS]
catalog=json.loads((ROOT/'assets'/('uprising.json' if UPRISING else 'features.json')).read_text(encoding='utf8'))
version=BUILD

def put(vm,address,value):vm.mem_write(address,struct.pack('<I',value))
def machine(name,code,flags,variant):
    vm=Uc(UC_ARCH_X86,UC_MODE_32)
    for address,size in [(DATA,0x10000),(STACK,0x4000),(BLOCK,0x2000),(GLOBAL,0x1000),(0x452000,0x2000)]:
        vm.mem_map(address,size)
    vm.mem_write(START,code)
    for i,reg in enumerate(REGS[:7]):vm.reg_write(reg,DATA+i*0x1000)
    vm.reg_write(UC_X86_REG_ESP,STACK+0x2000)
    vm.reg_write(UC_X86_REG_EFLAGS,flags)
    vm.reg_write(UC_X86_REG_FPCW,0x37f)
    vm.reg_write(UC_X86_REG_XMM0,0x3f000000 if variant else 0x3f800000)
    vm.reg_write(UC_X86_REG_XMM1,0x41400000)
    for base in range(DATA,DATA+0xc000,0x1000):
        for off in [4,8,0xc,0x1c,0x20,0x2c,0x34,0x38,0x3c,0x44,0x50,0x1bc,0x260,0x264]:
            put(vm,base+off,variant+100)
    if name=='build_hp_a':put(vm,vm.reg_read(UC_X86_REG_ECX),0)
    if name=='build_power':
        # The actual prefix caches [ESI+20] into EDI immediately before the site.
        put(vm,vm.reg_read(UC_X86_REG_ESI)+0x20,vm.reg_read(UC_X86_REG_EDI))
    if name=='zoom_unit_xp':
        vm.reg_write(UC_X86_REG_EDI,variant)
        put(vm,vm.reg_read(UC_X86_REG_EDX)+4*variant,DATA+0x8000 if variant else 0)
    return vm

def state(vm):
    game=bytes(vm.mem_read(DATA,0xe000))
    stack=bytes(vm.mem_read(STACK,0x4000))
    regs=tuple(vm.reg_read(reg) for reg in REGS)
    # PUSHFD/PUSHAD may leave dead scratch bytes below ESP; only live stack
    # contents at/above the final ESP belong to the game continuation.
    live_stack=stack[vm.reg_read(UC_X86_REG_ESP)-STACK:]
    vm.mem_write(GLOBAL,b'\x0f\xae\x05'+struct.pack('<I',DATA+0xe000))
    vm.emu_start(GLOBAL,GLOBAL+7,count=1)
    fx=bytearray(vm.mem_read(DATA+0xe000,416));fx[8:16]=bytes(8)
    return regs,game,live_stack,bytes(fx)

cases=0
for name,definition in catalog['hooks'].items():
    replay=bytes.fromhex(definition.get('displacedByVersion',{}).get(version,definition['displaced']))
    stub=(STUBS/(name+'.bin')).read_bytes()
    meta=dict(line.split('=') for line in (STUBS/(name+'.meta')).read_text().splitlines())
    for flags in [0x202,0x893,0x647]:
        for variant in [0,1]:
            original=machine(name,replay,flags,variant)
            hooked=machine(name,stub,flags,variant)
            original.emu_start(START,START+len(replay),count=10000)
            hooked.emu_start(START,int(meta['siteEnd'],16),count=10000)
            expected,actual=state(original),state(hooked)
            for label,left,right in zip(['registers/flags','game data','live stack','x87/SSE'],expected,actual):
                assert left==right,(name,flags,variant,label)
            cases+=1
print(f'PASS {cases} disabled-hook equivalence cases ({"Uprising" if UPRISING else "RA3"}): original game writes, registers, flags, stack and floating-point state')
