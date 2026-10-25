"""Reproduce the audited Uprising address/byte contracts from local PE images.

EA hook/API anchors were cross-checked with Ken22265's extracted FINAL script.
The Steam matches use full instruction context, never a constant RVA delta.
This tool only reads game files and writes project metadata.
"""
import json
import struct
from pathlib import Path
from uprising_probe import load, scan, signature

VERSIONS = {'ea': 'uprising-1.0ea', 's0': 'uprising-1.0', 's1': 'uprising-1.01'}
HOOKS = {
    'ea': [0x6e7c0a,0x6e7b08,0x321d2e,0x321c8c,0x321e3d,0x13587f,0x379a9e,0x40c364,0x2f2663,0x44d716,0x12f715,0x6e7c78,0x44d689,0x31d066,0x3ccd6f,0x1f993d,0x2fd1e9,0x447ca0,0x30388f,0x6e7cc1,0x447c80,0x447cc0,0x44a980,0x44a9a0,0x3a6391,0x44a9c0],
    's0': [0x67c7fa,0x67c6f8,0x36090e,0x36086c,0x360a1d,0x17772f,0x3b86fe,0x44b054,0x3311b3,0x48c456,0x171525,0x67c868,0x48c3c9,0x35bc06,0,0x2395ed,0x33bb19,0x486960,0x34221f,0x67c8b1,0x486940,0x486980,0x489600,0x489620,0x3e4fb1,0x489640],
    's1': [0x664a3a,0x664938,0x34889e,0x3487fc,0x3489ad,0x15d31f,0x3a048e,0x432c44,0x319173,0x473ef6,0x157125,0x664aa8,0x473e69,0x343bb6,0,0x22081d,0x323c59,0x46e480,0x32a36f,0x664af1,0x46e460,0x46e4a0,0x471140,0x471160,0x3ccd31,0x471180],
}
APIS = {
    'ea': [0x371c60,0x3a3440,0x379a80,0x33bb90,0x3e4e40,0x2111f0,0x2d9470,0x69ebb0,0x449f60,0xdbce0,0x1f1cb0],
    's0': [0x3b0680,0x3e2060,0x3b86e0,0x37a690,0x423a90,0x2510b0,0x318070,0x1257b0,0x488be0,0x11d980,0x231730],
    's1': [0x3985c0,0x3c9de0,0x3a0470,0x362680,0x40b690,0x238220,0x2fffe0,0x4787e0,0x470720,0x103500,0x218680],
}
API_NAMES = ['rank','capture','adjust','marker','damage','spawn','lookup','find','owner','predicate','mouse']
API_LENGTHS = [99,0x288,0xc9,0x9d,0xba,308,57,93,41,33,0x47e]

def only(image, pattern):
    hits = scan(image[0x1000:0x7d7000], pattern)
    assert len(hits) == 1, (pattern, [hex(x+0x1000) for x in hits])
    return hits[0]+0x1000

def u32(image, r):
    return struct.unpack_from('<I', image, r)[0]

def main():
    source = json.loads(Path('assets/features.json').read_text(encoding='utf8'))
    _, ea = load('ea')
    _, steam101 = load('s1')
    # Feature/card metadata is hand-maintained in the target JSON. Regeneration
    # updates only audited addresses/contracts, never replaces the UI catalog.
    features = json.loads(Path('assets/uprising.json').read_text(encoding='utf8'))['features']
    out = {'features':features, 'hooks':{}, 'globals':{}, 'buildAnywhere':{}, 'apis':{}}
    for key, version in VERSIONS.items():
        _, im = load(key)
        for (id, orig), r in zip(source['hooks'].items(), HOOKS[key]):
            expected = orig['displaced'].replace('3C03','4C03') if id in ('onekill_a','onekill_b') else orig['displaced']
            if id == 'money_h1':
                r -= 9
                expected = '39095B740433C0EB038B4004'
            if id == 'money_h3':
                r -= 8
                expected = '85C0750433FFEB038B7834'
            if id == 'build_power': expected = '8B9828040000'
            if id == 'unit_lv':
                expected = 'F30F118564020000'
                r = only(im, signature(ea, 0x3ccd6f, 40))
            want = bytes.fromhex(expected)
            assert im[r:r+len(want)] == want, (version,id,hex(r))
            h = out['hooks'].setdefault(id, {'rva':{},'displaced':expected,'displacedLen':len(want)})
            if orig.get('stub'): h['stub'] = orig['stub']
            h['rva'][version] = hex(r)
        # Strong unique contexts for the two challenge hooks, including their
        # surrounding formatting calls. Money's PUSH imm32 is replayed verbatim.
        for id, ref, length in [('challenge_time',0x6e3daa,5),('challenge_money',0x6e3ef7,8)]:
            r = only(im, signature(ea,ref,48))
            h = out['hooks'].setdefault(id, {'rva':{},'displaced':ea[ref:ref+length].hex(),'displacedLen':length,'displacedByVersion':{}})
            h['rva'][version] = hex(r)
            h['displacedByVersion'][version] = im[r:r+length].hex()
        a = dict(zip(API_NAMES, APIS[key]))
        # Exact function contracts include every relative CALL and absolute
        # operand. The EA mouse entry is SecuROM's original FF25 thunk; its
        # continuation and pointer slot are retained, never patched/unpacked.
        contracts = {name:{'rva':hex(a[name]),'bytes':im[a[name]:a[name]+n].hex()} for name,n in zip(API_NAMES,API_LENGTHS)}
        caller = a['spawn']+0x1da
        contracts['hashCaller'] = {'rva':hex(caller),'bytes':im[caller:caller+12].hex()}
        mouseRegister = only(im, '89 35 ?? ?? ?? ?? 80 BE 8C 00 00 00 00 74 32 80 BE 8D 00 00 00 00')
        contracts['mouseRegister'] = {'rva':hex(mouseRegister),'bytes':im[mouseRegister:mouseRegister+22].hex()}
        # The selected-unit list setter is proven by the exact EA address from
        # FINAL, and its following complete getter block (the short setter alone
        # also matches an unrelated registry, so it is deliberately insufficient).
        r = only(im, signature(ea,0x12b580,64))
        contracts['selectionRegister']={'rva':hex(r),'bytes':im[r:r+64].hex()}
        for name,reference,rva,size in [
            ('layoutLocomotor',steam101,0x2b8537,37),
            ('layoutOre',ea,0x72f890,40),
            ('layoutVeterancy',steam101,0x380ca9,48),
            ('layoutBodyDrawable',steam101,0x66b0da,49),
            ('layoutUnpackSchedule',steam101,0x32a366,28),
            ('layoutVision',steam101,0x3f35da,43),
            ('layoutWeaponCapacity',steam101,0x3dc71b,90),
        ]:
            location=only(im,signature(reference,rva,size))
            contracts[name]={'rva':hex(location),'bytes':im[location:location+size].hex()}
        globals = {'playerRoot':u32(im,a['capture']+0x48)-0x400000,
                   'gameLogic':u32(im,a['owner']+5)-0x400000,
                   'selectionList':u32(im,r+2)-0x400000,
                   'hashTable':u32(im,caller+2)-0x400000,
                   'mouseObject':u32(im,mouseRegister+2)-0x400000}
        assert globals['selectionList'] == (0x8eefe4 if key=='ea' else globals['selectionList'])
        for name in ['playerRoot','selectionList']:
            out['globals'].setdefault(name,{'rva':{}})['rva'][version]=hex(globals[name])
        a.update(globals)
        out['apis'][version]={'addresses':{k:hex(v) for k,v in a.items()},'contracts':contracts}
        gate = only(im,'5F5E5D84DB750CB8020000005B83C40CC2100033C0384424075B0F95C083C40CC21000')+5
        out['buildAnywhere'][version]=hex(gate)
        print(version, 'hooks',len(out['hooks']), 'globals', {k:hex(v) for k,v in globals.items()},'gate',hex(gate))
    Path('assets/uprising.json').write_text(json.dumps(out,ensure_ascii=False,indent=1)+'\n',encoding='utf8')

if __name__=='__main__': main()
