"""Offline regression checks against C# stubdump; no process access or writes.
Run: dotnet run --project src/RA3MT.SelfCheck -c Release -- stubdump artifacts/stubs_semantic
     py tools/harness/test_semantic_stubs.py
Requires capstone. Tests encodings/control flow, not live gameplay.
"""
from pathlib import Path
import struct
import capstone

root = Path(__file__).resolve().parents[2]
out = root / 'artifacts/stubs_semantic'
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)

def instructions(name):
    code = (out / (name + '.bin')).read_bytes()
    ins = list(cs.disasm(code, 0x40000040))
    assert sum(i.size for i in ins) == len(code), name
    starts = {i.address for i in ins}
    for i in ins:
        if i.mnemonic in ('je', 'jne', 'jae'):
            assert int(i.op_str, 16) in starts, (name, i.op_str)
    return code, ins

for name, replay in [('build_hp_b','8b51503b500c'), ('sidebar_pts','8b48503b4e20')]:
    code, ins = instructions(name)
    assert code[:-5] == bytes.fromhex(replay), name
    assert ins[-1].mnemonic == 'jmp'

code, ins = instructions('power_cool')
assert bytes.fromhex('830c24409d') in code  # saved EFLAGS |= ZF; popfd
assert bytes.fromhex('6a009d') not in code
assert code[0] == 0x9c
assert sum(i.mnemonic == 'popfd' for i in ins) == 2

code, ins = instructions('build_power')
assert code.count(bytes.fromhex('8b1d00004000')) == 2  # synthetic root global
assert code.count(bytes.fromhex('8b4b28')) == 2
assert code[-14:-5] == bytes.fromhex('8b7e208b9818040000')  # reload cached deadline
assert bytes.fromhex('88110000') not in code  # obsolete +1188 anchor

code, ins = instructions('zoom_unit_xp')
assert code[:6] == bytes.fromhex('8b0cba85c99c')  # save TEST before capture comparisons
assert bytes.fromhex('c7411ce7030000') not in code  # unsafe XP write removed
assert code[-6] == 0x9d
code, ins = instructions('build_hp_a')
assert code[:7] == bytes.fromhex('8b70508b019c60')
assert bytes.fromhex('bb00100000') in code  # bounded search
assert bytes.fromhex('395008') in code  # exact game's power key comparison
assert bytes.fromhex('3b8c2428000000') in code  # JMP-correct saved owner slot
assert bytes.fromhex('89700c') in code  # only matched deadline=current frame
assert bytes.fromhex('83400c01') in code
assert code[-7:-5] == bytes.fromhex('619d')
assert bytes.fromhex('c7400c00000000') not in code
for name in ['ammo'] + ['ammo_' + str(i) for i in range(2, 7)]:
    code, ins = instructions(name)
    assert bytes.fromhex('c7400850c30000') not in code  # threat is not ammunition
    assert code[:6] == bytes.fromhex('8b8178120000')
    assert len(ins) == 3 and [i.mnemonic for i in ins] == ['mov', 'mov', 'jmp']
    assert ins[1].op_str == 'dword ptr [0x4000002c], eax'  # diagnostics only
code, ins = instructions('weapon_clip')
assert code[:8] == bytes.fromhex('83c8ff01461c9c60')
assert bytes.fromhex('f6823d01000040') in code
assert bytes.fromhex('3b8b18040000') in code
assert bytes.fromhex('89461c') in code
assert bytes.fromhex('894624') not in code and bytes.fromhex('89462c') not in code
assert code[-7:-5] == bytes.fromhex('619d')
print('PASS: protocol search, zoom, owner root, XP flags, six harmless threat accessors and selected weapon refill')
