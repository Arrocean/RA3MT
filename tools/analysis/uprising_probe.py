"""Read-only PE comparison aid for the Uprising port (RVA throughout)."""
import json
import re
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

PATHS = {
    'ra3': r'D:\BaiduNetdiskDownload\Red Alert 3\Data\ra3_1.12.game',
    'ea': r'D:\BaiduNetdiskDownload\RA3 Uprising\GAME\Data\ra3ep1_1.0.game',
    's0': r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising\Data\ra3ep1_1.0.game',
    's1': r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising\Data\ra3ep1_1.1.game',
}

def load(key):
    p = pefile.PE(PATHS.get(key, key))
    return p, p.get_memory_mapped_image()

def scan(image, pattern):
    tokens = re.findall('..', pattern.replace(' ', ''))
    regex = b''.join(b'.' if t == '??' else re.escape(bytes.fromhex(t)) for t in tokens)
    return [m.start() for m in re.finditer(regex, image, re.S)]

def disasm(image, start, size):
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(image[start:start+size], start):
        print(f'{i.address:08X} {i.bytes.hex():24} {i.mnemonic:8} {i.op_str}')

def signature(image, start, size):
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    cs.detail = True
    tokens = []
    for ins in cs.disasm(image[start:start+size], start):
        b = [f'{x:02X}' for x in ins.bytes]
        for operand in ins.operands:
            if operand.type == 2 and (ins.mnemonic.startswith('j') or ins.mnemonic == 'call'):
                b[ins.imm_offset:ins.imm_offset+ins.imm_size] = ['??']*ins.imm_size
            if operand.type == 3 and operand.mem.base == 0 and operand.mem.disp >= 0x400000:
                b[ins.disp_offset:ins.disp_offset+ins.disp_size] = ['??']*ins.disp_size
            if operand.type == 2 and operand.imm >= 0x400000 and ins.imm_size == 4:
                b[ins.imm_offset:ins.imm_offset+4] = ['??']*4
        tokens.extend(b)
    return ' '.join(tokens)

if __name__ == '__main__':
    _, image = load(sys.argv[1])
    if sys.argv[2] == 'scan':
        print(' '.join(hex(x) for x in scan(image, sys.argv[3])))
    else:
        disasm(image, int(sys.argv[2], 16), int(sys.argv[3], 16) if len(sys.argv)>3 else 0x100)
