"""Disk-only identity and mocked x86 ABI tests for map-start spawn wrapper.
Never opens or modifies a game process. Helpers are mocked, not gameplay proof.
Run: py tools/analysis/verify_spawn_wrapper.py [Data directory]
"""
from pathlib import Path
import argparse
import struct
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP

DEFAULT = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data')
REFERENCE = bytes.fromhex('8b4c240883ec3c5333db33c03bcb0f841701000056578b7c24588944240c894424108944241489442418894424208944242483c840894c24288bcf8944241c895c242c895c2430895c2434895c2438895c243c895c2440895c2444e8606323008944242c8d4c24288d44240c5189442434e8ba3fedff8bf083c4043bf30f84a40000008b56048b4214d9406455518bced91c24e8b8df1d008b6c2458558bcee83ceb1d008b4c24546aff5357e80fa61d00f30f2ac08bcff30f118630040000e8fc6223008bce8bf8e8232912003bfb74078bcfe8487b23008b0db81dcf0056e83ca51e008b86740300003bc374388b4e048b91c0000000c1ea04f6c20175275505fc0100005056e8e4bc080083c40c84c07413536a01558bcee8627f0d00558bcee8baea1d005d5f8bc65e5b83c43cc3')
CALL_OFFSETS = (0x5B, 0x71, 0x93, 0x9F, 0xAC, 0xBF, 0xC8, 0xD3, 0xDF, 0x107, 0x119, 0x121)
PAIRS = {
 '1.13': (0x22E3E0, (0x4647A0,0x102410,0x40C430,0x40CFC0,0x408AA0,0x4647A0,0x350DD0,0x466000,0x418A00,0x2BA1D0,0x306460,0x40CFC0), 0xCF1DB8),
 '1.12': (0x2440F0, (0x4793B0,0x11A210,0x421450,0x421FE0,0x41DB00,0x4793B0,0x365670,0x47AC10,0x42D720,0x2CFAF0,0x31B790,0x421FE0), 0xCEDA98),
}


def verify(image, pair):
    rva, calls, manager = pair
    code = bytes(image[rva:rva + len(REFERENCE)])
    expected = bytearray(REFERENCE)
    for offset, target in zip(CALL_OFFSETS, calls):
        struct.pack_into('<i', expected, offset+1, target-(rva+offset+5))
    struct.pack_into('<I', expected, 0xDA, manager)
    if code != expected:
        raise ValueError('Spawn wrapper full byte/call/global contract mismatch')
    return code


def emulate(code, pair, null_template=False, null_body=False, ignored=0):
    rva, calls, manager = pair
    base=0x400000; entry=base+rva
    vm=Uc(UC_ARCH_X86, UC_MODE_32)
    data=0x2000000; stack=0x2100000; stop=0x2200000
    for page in {entry & ~0xFFF, manager&~0xFFF, data, data+0x1000, stack, stop} | {((base+t)&~0xFFF)+delta for t in calls for delta in (0,0x1000)}:
        vm.mem_map(page, 0x1000)
    vm.mem_write(entry, code)
    def put(a,v): vm.mem_write(a,struct.pack('<I',v))
    def get(a): return struct.unpack('<I',vm.mem_read(a,4))[0]
    body=data; template=data+0x800; owner=data+0x900; pos=data+0xA00; context=data+0xB00; descriptor=data+0xC00
    put(body+4,template); put(template+0x14,descriptor)
    vm.mem_write(descriptor+0x64,struct.pack('<f',1.25))
    vm.mem_write(pos,struct.pack('<fff',100.,200.,3.))
    put(manager,context)
    sp=stack+0x800; put(sp,stop)
    args=(ignored,0 if null_template else template,pos,owner,ignored ^ 0xFEED)
    for n,v in enumerate(args,1): put(sp+4*n,v)
    vm.reg_write(UC_X86_REG_ESP,sp)
    saved={UC_X86_REG_EBX:0x1234,UC_X86_REG_ESI:0x2345,UC_X86_REG_EDI:0x3456,UC_X86_REG_EBP:0x4567}
    for reg,value in saved.items(): vm.reg_write(reg,value)
    seen=[]
    def hook(machine,address,size,user):
        if address not in {base+t for t in calls}: return
        esp=vm.reg_read(UC_X86_REG_ESP); ecx=vm.reg_read(UC_X86_REG_ECX); target=address-base
        cleanup=0; result=0
        if target==calls[0]:
            assert ecx==owner; result=context; seen.append('owner')
        elif target==calls[1]:
            request=get(esp+4)
            assert get(request)==template and get(request+4)==context
            blob=get(request+8)
            assert [get(blob+4*i) for i in range(7)]==[0,0,0,0,0x40,0,0]
            assert [get(request+4*i) for i in range(3,8)]==[0]*5
            result=0 if null_body else body; seen.append('factory')
        elif target==calls[2]:
            assert ecx==body and struct.unpack('<f',vm.mem_read(esp+4,4))[0]==1.25
            cleanup=4; seen.append('yaw')
        elif target==calls[3]:
            assert ecx==body and get(esp+4)==pos
            cleanup=4; seen.append('position')
        elif target==calls[4]:
            assert ecx==template and [get(esp+4*i) for i in range(1,4)]==[owner,0,0xFFFFFFFF]
            cleanup=12; result=500; seen.append('value')
        elif target==calls[6]:
            assert ecx==body; seen.append('activate')
        elif target==calls[7]:
            assert ecx==context; seen.append('context')
        elif target==calls[8]:
            assert ecx==context and get(esp+4)==body
            cleanup=4; seen.append('register')
        else: raise AssertionError(f'Unexpected optional branch {target:X}')
        vm.reg_write(UC_X86_REG_EAX,result)
        vm.reg_write(UC_X86_REG_ESP,esp+4+cleanup)
        vm.reg_write(UC_X86_REG_EIP,get(esp))
    vm.hook_add(UC_HOOK_CODE,hook)
    try:
        vm.emu_start(entry,stop,count=2000)
    except Exception:
        print('FAILED',hex(vm.reg_read(UC_X86_REG_EIP)),hex(vm.reg_read(UC_X86_REG_ESP)),seen)
        raise
    assert vm.reg_read(UC_X86_REG_EIP)==stop
    assert vm.reg_read(UC_X86_REG_ESP)==sp+4  # cdecl: five args untouched
    assert vm.reg_read(UC_X86_REG_EAX)==(0 if null_template or null_body else body)
    assert all(vm.reg_read(r)==v for r,v in saved.items())
    expected=[] if null_template else ['owner','factory']
    if not null_template and not null_body:
        expected+=['yaw','position','value','owner','activate','context','register']
        assert struct.unpack('<f',vm.mem_read(body+0x430,4))[0]==500.
    assert seen==expected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data',nargs='?',type=Path,default=DEFAULT)
    args=parser.parse_args()
    cases=0
    for version,pair in PAIRS.items():
        image=pefile.PE(str(args.data/f'ra3_{version}.game')).get_memory_mapped_image()
        code=verify(image,pair)
        for offset in (0,0x19,0x98,0xA7,0xDA,0x12F)+tuple(o+1 for o in CALL_OFFSETS):
            bad=bytearray(image); bad[pair[0]+offset]^=1
            try: verify(bad,pair)
            except ValueError: pass
            else: raise AssertionError('Mutated wrapper accepted')
        for null_template,null_body in [(False,False),(True,False),(False,True)]:
            for ignored in [0,0xFFFFFFFF]:
                emulate(code,pair,null_template,null_body,ignored); cases+=1
        print(f'PASS {version} full 304-byte wrapper and 18 mutation refusals')
    print(f'PASS {cases} mocked cdecl ABI cases: arg2 template, arg3 xyz, arg4 owner; arg1/5 ignored')
    print('Mocks exclude real allocation, callbacks, optional locomotor paths and gameplay/thread safety.')

if __name__=='__main__': main()
