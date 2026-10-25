"""Reproduce the challenge-mode Soviet construction scheduling regression.

Uprising's GenericUnpackUpdate+34 is the start frame; +3C is an event handle.
The selected stalled reactor had frame=2092, start=1891, event=10437,
next-update=10438. Tests execute exported machine code; no process access.
"""
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *
from game_fixture import STUBS, UPRISING

BLOCK, START, END = 0x40000000, 0x40000040, 0x452106
STACK, LOGIC, MODULE = 0x200000, 0x300000, 0x301000
REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS]

def put(vm, address, value): vm.mem_write(address, struct.pack('<I', value))
def get(vm, address): return struct.unpack('<I', vm.mem_read(address, 4))[0]

def run(enabled, ebp, start_frame=1891, next_frame=10438):
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    for address, size in [(BLOCK,0x2000),(END&~0xfff,0x1000),(STACK,0x2000),(LOGIC,0x3000)]:
        vm.mem_map(address,size)
    vm.mem_write(START,(STUBS/'power.bin').read_bytes())
    for i,reg in enumerate(REGS):vm.reg_write(reg,0x1230+i)
    vm.reg_write(UC_X86_REG_ESP,STACK+0x1000)
    vm.reg_write(UC_X86_REG_ESI,LOGIC)
    vm.reg_write(UC_X86_REG_EDI,MODULE)
    vm.reg_write(UC_X86_REG_EBP,ebp)
    vm.reg_write(UC_X86_REG_EFLAGS,0x893)
    put(vm,LOGIC+0x1bc,0x3f000000) # original FLD source = 0.5
    put(vm,MODULE+0x14,next_frame)
    put(vm,MODULE+(0x34 if UPRISING else 0x3c),start_frame)
    if UPRISING:put(vm,MODULE+0x3c,10437) # unrelated handle deliberately differs
    vm.mem_write(BLOCK+4,bytes([enabled]))
    before={reg:vm.reg_read(reg) for reg in REGS}
    vm.emu_start(START,END,count=10000)
    want=(start_frame+1)&0xffffffff if enabled and ebp!=1 else next_frame
    actual=get(vm,MODULE+0x14)
    assert actual==want, f'next update: expected {want}, got {actual}; event handle must not become a frame'
    assert all(vm.reg_read(reg)==value for reg,value in before.items()), 'register/flags/stack clobber'
    assert get(vm,MODULE+(0x34 if UPRISING else 0x3c))==start_frame
    if UPRISING:assert get(vm,MODULE+0x3c)==10437, 'event handle modified'
    # The original instruction still pushes exactly the expected x87 value.
    vm.mem_write(END,b'\xd9\x1d'+struct.pack('<I',LOGIC+0x2000))
    vm.emu_start(END,END+6,count=1)
    assert get(vm,LOGIC+0x2000)==0x3f000000

cases=0
for enabled in [0,1]:
    for ebp in [0,1,2,0xffffffff]:
        for start in [0,1891,0x7ffffffe]:
            run(enabled,ebp,start);cases+=1
print(f'PASS {cases} unpack scheduling cases ({"Uprising" if UPRISING else "RA3"}): start frame, disabled no-op, guard, handle/GPR/flags/x87 preservation')
