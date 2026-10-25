"""Execute Uprising-only behavior: challenge pulses, par time, power UI and vision.
Run SelfCheck uprising-stubdump artifacts/uprising_stubs first. No game access.
"""
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *
from game_fixture import STUBS

OUT=STUBS
BLOCK,START,END,ROOT,STACK,DATA=0x40000000,0x40000040,0x452100,0x400000,0x200000,0x300000
REGS=[UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]

def put(vm,addr,value): vm.mem_write(addr,struct.pack('<I',value))
def get(vm,addr): return struct.unpack('<I',vm.mem_read(addr,4))[0]
def machine(name):
    vm=Uc(UC_ARCH_X86,UC_MODE_32)
    for addr,size in [(BLOCK,0x2000),(END&~0xfff,0x2000),(ROOT,0x1000),(STACK,0x4000),(DATA,0x10000)]:vm.mem_map(addr,size)
    vm.mem_write(START,(OUT/(name+'.bin')).read_bytes())
    meta=dict(line.split('=') for line in (OUT/(name+'.meta')).read_text().splitlines())
    for i,reg in enumerate(REGS): vm.reg_write(reg,DATA+i*0x1000)
    vm.reg_write(UC_X86_REG_ESP,STACK+0x2000);vm.reg_write(UC_X86_REG_EFLAGS,0x893)
    return vm,int(meta['siteEnd'],16)

def run(vm,end):
    vm.emu_start(START,end,count=10000)
    assert vm.reg_read(UC_X86_REG_EIP)==end

cases=0
for enabled in [0,1]:
    for amount in [0,100,0x7fff3caf,0x7fff3cb0,0x7fffffff,0xffffffff]:
        vm,end=machine('challenge_money');put(vm,DATA+8,amount)
        vm.mem_write(BLOCK+0x39,bytes([enabled]));before={reg:vm.reg_read(reg) for reg in REGS}
        run(vm,end)
        want=amount+50000 if enabled and amount<=0x7fff3caf else amount
        assert get(vm,DATA+8)==want and vm.reg_read(UC_X86_REG_EDI)==want
        assert vm.reg_read(UC_X86_REG_EFLAGS)==0x893
        assert vm.mem_read(BLOCK+0x39,1)==b'\0'
        assert vm.reg_read(UC_X86_REG_ESP)==STACK+0x2000-4
        # Replayed PUSH must retain the version-specific absolute format pointer.
        code=(OUT/'challenge_money.bin').read_bytes();assert code[-13:-9]==bytes.fromhex('8b780868')
        assert get(vm,STACK+0x2000-4)==struct.unpack('<I',code[-9:-5])[0]
        assert all(vm.reg_read(r)==v for r,v in before.items() if r!=UC_X86_REG_EDI)
        vm.reg_write(UC_X86_REG_ESP,STACK+0x2000)
        run(vm,end)
        assert get(vm,DATA+8)==want, 'pulse must not repeat on panel refresh'
        cases+=1

for enabled in [0,1]:
    vm,end=machine('challenge_time');put(vm,DATA+0x38,struct.unpack('<I',struct.pack('<f',120.0))[0]);vm.mem_write(BLOCK+0x3a,bytes([enabled]))
    run(vm,end)
    assert vm.reg_read(UC_X86_REG_EBX)==(599999 if enabled else 120)
    assert vm.reg_read(UC_X86_REG_EFLAGS)==0x893
    cases+=1

for enabled in [0,1]:
    vm,end=machine('money_h1');vm.mem_write(BLOCK+1,bytes([enabled]));put(vm,DATA+4,100);put(vm,DATA+8,50)
    esi=vm.reg_read(UC_X86_REG_ESI);put(vm,esi+0x3e0,0x12345678);put(vm,esi+0x3b0,0x87654321)
    ecx=vm.reg_read(UC_X86_REG_ECX);put(vm,ecx,ecx) # native resource-available fork
    vm.mem_write(end,bytes.fromhex('8b8ee0030000'))
    run(vm,end+6)
    assert vm.reg_read(UC_X86_REG_ECX)==0x12345678
    assert vm.reg_read(UC_X86_REG_EAX)==(100000 if enabled else 100)
    assert get(vm,DATA+8)==(0 if enabled else 50)
    assert get(vm,esi+0x3b0)==0x87654321
    cases+=1

print(f'PASS {cases} Uprising-specific x86 cases: challenge one-shot/overflow/replay, time, power UI; vision checked with real continuation separately')
