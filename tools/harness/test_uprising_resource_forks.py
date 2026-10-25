"""Differential execution of real PE resource forks with/without the detours.

Covers both power branches, missing player/protocol components, enabled/disabled
features and the full power bridge's stack behavior. No game process is opened.
"""
import json
import struct
import sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
from game_fixture import STUBS,BUILD,UPRISING

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/analysis'))
from uprising_probe import load
assert UPRISING
_,image=load({'uprising-1.0ea':'ea','uprising-1.0':'s0','uprising-1.01':'s1'}[BUILD])
catalog=json.loads((ROOT/'assets/uprising.json').read_text(encoding='utf8'))
BLOCK,STUB,SITE,DATA,STACK=0x40000000,0x40000040,0x452100,0x300000,0x200000
REGS=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
      UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EFLAGS]

def put(vm,a,v):vm.mem_write(a,struct.pack('<I',v))

def machine(name,branch,amount,enabled,flags,hooked,bridge=False):
    vm=Uc(UC_ARCH_X86,UC_MODE_32)
    for a,n in [(BLOCK,0x2000),(SITE&~0xfff,0x2000),(DATA,0x10000),(STACK,0x4000)]:vm.mem_map(a,n)
    obj=catalog['hooks'][name];r=int(obj['rva'][BUILD],16);n=obj['displacedLen']
    # Include the real earlier player-null bypass and the shared MOV ECX.
    prefix=14 if name=='money_h3' else 0
    tail=3 if name=='money_h3' else 6
    vm.mem_write(SITE-prefix,image[r-prefix:r+n+tail])
    for i,reg in enumerate(REGS[:7]):vm.reg_write(reg,DATA+i*0x1000)
    vm.reg_write(UC_X86_REG_ESP,STACK+0x2000);vm.reg_write(UC_X86_REG_EFLAGS,flags)
    put(vm,STACK+0x2000,0x12345678)
    if name=='money_h1':
        put(vm,DATA+0x2000,DATA+0x2000 if branch=='available' else 0)
        put(vm,DATA+4,amount);put(vm,DATA+8,50)
        put(vm,DATA+0x4000+0x3e0,0x123456)
        if enabled and branch=='available' and not hooked:put(vm,DATA+4,100000);put(vm,DATA+8,0)
        vm.mem_write(BLOCK+1,bytes([enabled]))
    else:
        vm.reg_write(UC_X86_REG_EAX,0 if branch=='no_player' else DATA+0x8000)
        put(vm,DATA+0x8000+0x1320,0 if branch=='no_component' else DATA)
        put(vm,DATA+0x34,amount)
        put(vm,DATA+0x4000+0x3c,0x123456)
        if enabled and branch=='available' and not hooked:put(vm,DATA+0x34,15)
        vm.mem_write(BLOCK+2,bytes([enabled]))
    if hooked:
        blob=(STUBS/('money_h1_full_bridge.bin' if bridge else name+'.bin')).read_bytes()
        vm.mem_write(STUB,blob)
        vm.mem_write(SITE,b'\xe9'+struct.pack('<i',STUB-SITE-5)+b'\x90'*(n-5))
        for off in [0x1100,0x1280,0x1400,0x1580]:vm.mem_write(BLOCK+off,b'\xc3')
    vm.emu_start(SITE-prefix,SITE+n+tail,count=10000)
    require=vm.reg_read(UC_X86_REG_EIP)==SITE+n+tail
    assert require,'did not reach shared renderer continuation'
    return tuple(vm.reg_read(r) for r in REGS),bytes(vm.mem_read(DATA,0x10000)),bytes(vm.mem_read(vm.reg_read(UC_X86_REG_ESP),0x100))

cases=0
for name,branches in [('money_h1',['available','unavailable']),('money_h3',['available','no_component','no_player'])]:
    for branch in branches:
        for amount in [0,99]:
            for enabled in [0,1]:
                for flags in [0x202,0x893,0x647]:
                    original=machine(name,branch,amount,enabled,flags,False)
                    for bridge in ([False,True] if name=='money_h1' else [False]):
                        actual=machine(name,branch,amount,enabled,flags,True,bridge)
                        assert actual==original,(BUILD,name,branch,amount,enabled,flags,bridge)
                        cases+=1
print(f'PASS {cases} actual resource-fork equivalence cases ({BUILD}): null/bypass paths, feature writes, full power bridge stack')
