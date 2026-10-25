"""Read-only semantic audit of all three local Uprising PE images.

Unlike contract regeneration, this never updates expected bytes. It checks
instruction boundaries, relative control flow, caller/callee edges, per-build
format pointers, independent object-field evidence and incoming detour edges.
Writes a report only under artifacts/uprising. No process handles are opened.
"""
import hashlib
import json
import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM
from uprising_probe import load, PATHS

ROOT=Path(__file__).resolve().parents[2]
CAT=json.loads((ROOT/'assets/uprising.json').read_text(encoding='utf8'))
BUILDS={'ea':'uprising-1.0ea','s0':'uprising-1.0','s1':'uprising-1.01'}
CS=Cs(CS_ARCH_X86,CS_MODE_32);CS.detail=True

def require(value,message):
    if not value:raise AssertionError(message)

def normalized(code,start):
    """Mask relocatable addresses/callees; KEEP conditional-branch distances."""
    result=[]
    for ins in CS.disasm(code,start):
        b=bytearray(ins.bytes)
        for op in ins.operands:
            address=(op.type==X86_OP_MEM and op.mem.base==0 and op.mem.disp>=0x400000)
            immediate=(op.type==X86_OP_IMM and ins.imm_size==4 and
                       (ins.mnemonic=='call' or (not ins.mnemonic.startswith('j') and op.imm>=0x400000)))
            if address:b[ins.disp_offset:ins.disp_offset+ins.disp_size]=bytes(ins.disp_size)
            if immediate:b[ins.imm_offset:ins.imm_offset+ins.imm_size]=bytes(ins.imm_size)
        result.append(bytes(b))
    return b''.join(result)

def calls(code,start):
    return [(i.address-start,i.operands[0].imm) for i in CS.disasm(code,start)
            if i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM]

def main():
    images={};reports={};comparisons={};incoming=[]
    for key,version in BUILDS.items():
        pe,im=load(key);images[version]=im
        require(pe.OPTIONAL_HEADER.Magic==0x10b and pe.FILE_HEADER.Machine==0x14c,'not x86 PE')
        require(pe.OPTIONAL_HEADER.ImageBase==0x400000,'unsupported image base')
        text=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text')
        lo,hi=text.VirtualAddress,text.VirtualAddress+text.Misc_VirtualSize
        spans=[];contexts={};hooks={}
        for name,definition in CAT['hooks'].items():
            r=int(definition['rva'][version],16)
            displaced=bytes.fromhex(definition.get('displacedByVersion',{}).get(version,definition['displaced']))
            require(lo<=r<r+len(displaced)<=hi,(version,name,'outside executable section'))
            require(im[r:r+len(displaced)]==displaced,(version,name,'displaced mismatch'))
            instructions=list(CS.disasm(displaced,r))
            require(sum(i.size for i in instructions)==len(displaced),(version,name,'split instruction'))
            require(name in ('money_h1','money_h3') or not any(i.mnemonic=='call' or i.mnemonic.startswith('j') for i in instructions),
                    (version,name,'relative instruction replay needs relocation'))
            require(not any(max(r,a)<min(r+len(displaced),b) for a,b,_ in spans),'overlapping hooks')
            spans.append((r,r+len(displaced),name))
            # sidebar_pts ends before an adjacent EA-protected function. Never
            # suppress a difference inside the function just to match a window.
            n=21 if name=='sidebar_pts' else 96
            contexts[name]=normalized(im[r:r+n],r).hex()
            hooks[name]={'rva':hex(r),'bytes':len(displaced),'continuation_window':n}
        build=CAT['apis'][version];addresses={n:int(v,16) for n,v in build['addresses'].items()}
        apis={}
        for name,contract in build['contracts'].items():
            r=int(contract['rva'],16);expected=bytes.fromhex(contract['bytes'])
            require(im[r:r+len(expected)]==expected,(version,name,'contract mismatch'))
            require(sum(i.size for i in CS.disasm(expected,r))==len(expected),(version,name,'contract cuts an instruction'))
            apis[name]=normalized(expected,r).hex()
        for name,cleanup in [('rank',12),('capture',8),('adjust',8),('marker',4),
                             ('damage',12),('spawn',0),('lookup',4),('find',8),('owner',0),('predicate',0),('mouse',0)]:
            contract=build['contracts'][name];r=int(contract['rva'],16)
            returns=[i for i in CS.disasm(bytes.fromhex(contract['bytes']),r) if i.mnemonic=='ret']
            require(returns and all((i.operands[0].imm if i.operands else 0)==cleanup for i in returns),
                    (version,name,'callee stack cleanup mismatch'))
        def edge(name,offset,destination):
            code=bytes.fromhex(build['contracts'][name]['bytes']);r=int(build['contracts'][name]['rva'],16)
            require((offset,addresses[destination]) in calls(code,r),(version,name,destination,'wrong call edge'))
        edge('lookup',0x13,'find')
        edge('owner',9,'predicate')
        edge('hashCaller',7,'lookup')
        read=lambda r:struct.unpack_from('<I',im,r)[0]
        require(read(addresses['capture']+0x48)==0x400000+addresses['playerRoot'],'capture root mismatch')
        require(read(addresses['owner']+5)==0x400000+addresses['gameLogic'],'owner-kind/game-logic global mismatch')
        require(addresses['gameLogic']!=addresses['playerRoot'],'different object globals must not be conflated')
        require(read(int(build['contracts']['selectionRegister']['rva'],16)+2)==0x400000+addresses['selectionList'],'selection global mismatch')
        require(read(int(build['contracts']['hashCaller']['rva'],16)+2)==0x400000+addresses['hashTable'],'hash global mismatch')
        require(read(int(build['contracts']['mouseRegister']['rva'],16)+2)==0x400000+addresses['mouseObject'],'mouse global mismatch')
        gate=int(CAT['buildAnywhere'][version],16)
        require(im[gate:gate+21]==bytes.fromhex('750cb8020000005b83c40cc2100033c0384424075b0f')[:21], 'placement branch context changed')
        if key=='ea':
            require(im[addresses['mouse']:addresses['mouse']+2]==b'\xff\x25','EA protected mouse entry changed')
        else:
            # Actual bool-returning epilogue writes only AL. High EAX is not
            # a valid success indicator for the mouse conversion.
            mouse=im[addresses['mouse']:addresses['mouse']+0x47e]
            require(mouse[-10:]==bytes.fromhex('32c05d81c4d0000000c3'),'mouse bool return contract changed')
        # Scan direct control flow for branches into the middle of detours.
        lite=Cs(CS_ARCH_X86,CS_MODE_32);lite.skipdata=True
        for source,size,mnemonic,operands in lite.disasm_lite(im[lo:hi],lo):
            if mnemonic=='call' or mnemonic.startswith('j') or mnemonic.startswith('loop'):
                if not operands.startswith('0x'):continue
                target=int(operands,16)
                for begin,end,name in spans:
                    if begin<target<end and not begin<=source<end:incoming.append((version,name,hex(source),hex(target)))
        comparisons[version]={'hook_contexts':contexts,'contracts':apis}
        reports[version]={'file':PATHS[key],'sha256':hashlib.sha256(Path(PATHS[key]).read_bytes()).hexdigest(),
                          'hooks':hooks,'contracts':len(apis),'global_and_call_edges':'passed'}
    reference=comparisons['uprising-1.01']
    for version,items in comparisons.items():
        require(items['hook_contexts']==reference['hook_contexts'],(version,'hook continuation/control-flow difference'))
        for name,code in items['contracts'].items():
            if name=='mouse' and version=='uprising-1.0ea':
                # EA replaces the six-byte stack-allocation entry with its
                # protected FF25 thunk. The remaining 1144 bytes agree.
                require(code[12:]==reference['contracts'][name][12:],(version,name,'protected continuation mismatch'))
                continue
            require(code==reference['contracts'][name],(version,name,'structural/control-flow difference'))
    require(not incoming,('branches into overwritten instructions',incoming))
    result={'builds':reports,'incoming_middle_edges':incoming,
            'scope':'static identity/control-flow/data-field evidence; not 36-feature live acceptance',
            'remaining_live_boundary':'EA protected entry thunk execution and all 36 gameplay effects need live acceptance'}
    out=ROOT/'artifacts/uprising/static-audit.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'PASS static semantic audit: {len(BUILDS)} builds, {28*3} hook boundaries/contexts, '
          f'{len(reference["contracts"])*3} contracts; call/global edges and placement gates; no incoming middle edges')
    print('EA protected mouse entry: original thunk and 1144-byte continuation verified; thunk execution needs live observation')
    print('Report:',out)

if __name__=='__main__':main()
