# -*- coding: utf-8 -*-
"""
RA3 trainer feature-data generator.

1) Build cross-version (1.12 vs 1.13) unique AOB signatures for all code hook
   sites.  For sites the first pass (D:\\RA3TrainerWork\\sigs_generated.json)
   could not pin down, use a diff-mask approach: bytes that differ between the
   two versions around the anchor-vote candidate are wildcarded, guaranteeing a
   hit at both locations by construction; uniqueness is then enforced by
   growing the window.
2) Resolve the two .data globals (0x8DB73C, 0x8E8C9C in 1.12) into 1.13 via
   cross-reference: find instructions in 1.12 .text that use the absolute
   address, signature-match the surrounding code into 1.13, read the new
   displacement.
3) Find the "selection list pointer" global used by the old trainer's table at
   ra3+0x10A0C: disassemble the function containing hook 0x128735 in 1.12 to
   see where its edx (selection array source) is loaded from; map that global
   into 1.13 the same way.
"""
import json
import re
import struct
import sys

import capstone
import pefile

P112 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game"
P113 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game"
IMG_BASE = 0x400000

HOOKS = [  # id, rva112, label, anchor-vote candidate rva113
    ("zoom_unit_xp", 0x128735, "单位经验/缩放钩子", 0x111315),
    ("power_cool",   0x1EC7CD, "缩放/冷却钩子",     0x1D5ADD),
    ("fast_build",   0x2D4933, "一键完成建造钩子",  0x2BF023),
    ("build_power",  0x2EBB69, "建造进度+电力钩子", 0x2D6349),
    ("power",        0x2F6CFF, "电力维持钩子",      0x2E150F),
    ("sidebar_pts",  0x30A5F6, "侧栏冷却钩子",      0x2F52C6),
    ("proto_cool_a", 0x30F38C, "生产冷却A钩子",     0x2FA0BC),
    ("proto_cool_b", 0x30F42E, "生产冷却B钩子",     0x2FA15E),
    ("threat",       0x39ECB0, "摧毁单位函数",      0x39E3E0),
    ("unit_lv",      0x3C226C, "战争迷雾/地图钩子", 0x3A856C),
    ("ammo",         0x438ED0, "弹药钩子",          0x4240D0),
    ("build_hp_a",   0x43EC19, "建筑进度A钩子",     0x429EB9),
    ("build_hp_b",   0x43ECA6, "建筑进度B钩子",     0x429F46),
    ("money_h1",     0x6CFD0D, "资金/电力钩子1",    0x6D7C8D),
    ("money_h2",     0x6CFDFE, "资金/电力钩子2",    0x6D7D7E),
    ("money_h3",     0x6CFE6C, "协议点数钩子",      0x6D7DEC),
    ("money_h4",     0x6CFEB5, "解锁协议钩子",      0x6D7E35),
]


def load(path):
    data = open(path, "rb").read()
    pe = pefile.PE(path, fast_load=True)
    secs = []
    for s in pe.sections:
        name = s.Name.decode(errors="replace").strip("\x00")
        raw = data[s.PointerToRawData:s.PointerToRawData + max(s.Misc_VirtualSize, s.SizeOfRawData)]
        secs.append((name, s.VirtualAddress, raw))
    return secs


S112 = load(P112)
S113 = load(P113)


def locate(secs, rva):
    for name, va, buf in secs:
        if va <= rva < va + len(buf):
            return name, buf, rva - va
    return None, None, None


def scan(secs, pattern_bytes, mask):
    rx = b"".join(re.escape(pattern_bytes[i:i+1]) if mask[i] else b"." for i in range(len(pattern_bytes)))
    hits = []
    for name, va, buf in secs:
        for m in re.finditer(rx, buf, re.DOTALL):
            hits.append(va + m.start())
    return hits


def base_mask(buf, off, length):
    """Wildcards: rel32 of E8/E9/EBr and image-range dword immediates."""
    length = min(length, len(buf) - off)
    pat = bytearray(buf[off:off+length])
    mask = bytearray(b"\x01" * length)
    i = 0
    while i < length - 5:
        b = buf[off+i]
        if b in (0xE8, 0xE9):
            for k in range(i+1, min(i+5, length)):
                mask[k] = 0
            i += 5
            continue
        if b == 0x0F and 0x80 <= buf[off+i+1] <= 0x8F:
            for k in range(i+2, min(i+6, length)):
                mask[k] = 0
            i += 6
            continue
        i += 1
    for j in range(length-4):
        if all(mask[j:j+4]):
            v = struct.unpack_from("<I", pat, j)[0]
            if IMG_BASE <= v < 0x980000:
                for k in range(j, j+4):
                    mask[k] = 0
    return pat, mask


def diff_mask(buf12, off12, buf13, off13, length):
    """Pattern from 1.12 bytes; wildcard every byte that differs in 1.13."""
    length = min(length, len(buf12) - off12, len(buf13) - off13)
    pat, mask = base_mask(buf12, off12, length)
    for i in range(length):
        if pat[i] != buf13[off13+i]:
            mask[i] = 0
    return pat, mask


def pat_str(pat, mask):
    return " ".join("%02X" % p if m else "??" for p, m in zip(pat, mask))


def gen_sig(rva12, rva13, prefer_site_offset=True):
    """Try window sizes; return best (pattern, mask, site_offset, len, score)."""
    n12, b12, o12 = locate(S112, rva12)
    n13, b13, o13 = locate(S113, rva13)
    if b12 is None or b13 is None:
        return None
    best = None
    for pre in (0x18, 0x20, 0x28, 0x30, 0x40, 0x50, 0x60, 0x80, 0xA0):
        if o12 < pre:
            continue
        for ln in (64, 80, 96, 112, 128, 144, 160, 192, 224, 256):
            pat, mask = diff_mask(b12, o12 - pre, b13, o13 - pre, ln)
            concrete = sum(mask)
            if concrete < 24:
                continue
            h12 = scan(S112, pat, mask)
            h13 = scan(S113, pat, mask)
            if len(h12) != 1 or len(h13) != 1:
                continue
            if h12[0] + pre != rva12 or h13[0] + pre != rva13:
                continue
            # shorter + denser is better
            score = concrete * 1000 - ln
            if best is None or score > best[4]:
                best = (pat, mask, pre, ln, score)
        if best:
            break  # prefer smallest pre that produced a unique sig
    return best


results = []
pending_prev = json.load(open(r"D:\RA3TrainerWork\sigs_generated.json", encoding="utf-8"))
prev_by_id = {s["id"]: s for s in pending_prev}

for hid, rva12, label, rva13 in HOOKS:
    prev = prev_by_id.get(hid)
    if prev and prev.get("pattern"):
        results.append({
            "id": hid, "label": label,
            "rva112": hex(rva12), "rva113": hex(rva13),
            "pattern": prev["pattern"], "siteOffset": prev["siteOffset"],
            "len": prev["len"],
            "hit112": prev["hit112"], "hit113": prev["hit113"],
            "origin": "pass1",
        })
        print(f"  [keep] {hid:<14} 1.12={prev['hit112']} 1.13={prev['hit113']}")
        continue
    g = gen_sig(rva12, rva13)
    if g:
        pat, mask, pre, ln, _ = g
        h12 = scan(S112, pat, mask)[0] + pre
        h13 = scan(S113, pat, mask)[0] + pre
        results.append({
            "id": hid, "label": label,
            "rva112": hex(rva12), "rva113": hex(rva13),
            "pattern": pat_str(pat, mask), "siteOffset": pre, "len": ln,
            "hit112": hex(h12), "hit113": hex(h13),
            "origin": "diff-mask",
        })
        print(f"  [NEW ] {hid:<14} 1.12={hex(h12)} 1.13={hex(h13)} pre={pre} len={ln}")
    else:
        results.append({"id": hid, "label": label, "rva112": hex(rva12),
                        "rva113": hex(rva13), "pattern": None, "pending": True})
        print(f"  [FAIL] {hid:<14} no unique cross-version sig")

# ---------------------------------------------------------------- data globals
DATA_GLOBALS_112 = {
    "player_mgr": 0x8E8C9C,   # [g+8E8C9C]+28 = local player index (capture/change-id)
    "money_ptr":  0x8DB73C,   # trainer-table stored pointer
}


def find_xrefs_112(rva, maxhits=8):
    absaddr = IMG_BASE + rva
    needle = struct.pack("<I", absaddr)
    hits = []
    for name, va, buf in S112:
        start = 0
        while True:
            i = buf.find(needle, start)
            if i < 0:
                break
            hits.append((name, va + i))
            start = i + 1
            if len(hits) >= maxhits:
                return hits
    return hits


def map_xref_to_113(secs112_off, disp_rva, pre=0x20, ln=64):
    """Given a 1.12 .text offset containing disp32=deref, sig-match into 1.13,
    return the 1.13 disp32 found at the same position."""
    n12, b12, o12 = locate(S112, secs112_off)
    n13, b13, o13 = locate(S113, secs112_off)
    if b12 is None or b13 is None:
        return None
    # offset of the disp32 dword inside the window
    disp_pos_in_file = o12
    win_off = max(0, disp_pos_in_file - pre)
    pre2 = disp_pos_in_file - win_off
    pat, mask = base_mask(b12, win_off, ln)
    for k in range(pre2, min(pre2 + 4, len(mask))):
        mask[k] = 0  # the displacement itself
    h12 = scan(S112, pat, mask)
    h13 = scan(S113, pat, mask)
    if len(h12) == 1 and len(h13) == 1:
        pos = h13[0] + pre2
        newdisp = struct.unpack_from("<I", b13, pos)[0]
        return newdisp
    return None


print("\n== data globals ==")
globals_out = {}
for gname, rva in DATA_GLOBALS_112.items():
    xrefs = find_xrefs_112(rva)
    mapped = []
    for name, off in xrefs:
        newdisp = map_xref_to_113(off, rva)
        if newdisp:
            mapped.append((hex(off), hex(newdisp - IMG_BASE)))
    globals_out[gname] = {"rva112": hex(rva), "xrefs": [{"off112": h[0], "disp113": m[0], "rva113": m[1]}
                                                        for h, m in zip(xrefs, mapped)]}
    print(f"  {gname}: 1.12 rva={hex(rva)} xrefs={len(xrefs)} -> " +
          ", ".join(f"{m[1]}" for m in mapped[:4]))

# ------------------------------------------------- selection pointer discovery
print("\n== selection-list pointer (hook 0x128735 fn, 1.12) ==")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = False


def find_func_start(secs, rva):
    n, buf, off = locate(secs, rva)
    if buf is None:
        return None
    i = off
    while i > 0:
        if buf[i] == 0xCC and buf[i-1] != 0xCC:
            return n, buf, i + 1  # first byte after int3 padding run end
        i -= 1
    return None


def disasm_range(buf, start_off, end_off, maxins=400):
    out = []
    for ins in md.disasm(buf[start_off:end_off], start_off):
        out.append(ins)
        if len(out) >= maxins:
            break
    return out


fs = find_func_start(S112, 0x128735)
if fs:
    n, buf, foff = fs
    site_off = 0x128735 - 0x400000 - 0x400000  # placeholder, fix below
# rva vs file: locate() gave offset inside section buffer; redo cleanly
n, buf, site_in_sec = locate(S112, 0x128735)
fs2 = find_func_start(S112, 0x128735)
sel_globals = []
if fs2:
    n, buf, fstart = fs2
    print(f"  function start ~ {hex(0x400000 + n + fstart)} (section {n})")
    ins_list = list(md.disasm(buf[fstart:site_in_sec + 16], 0x400000 + n + fstart))
    # find 'mov ecx,[edx+edi*4]' (8B 0C BA) then walk back for edx source
    for idx, ins in enumerate(ins_list):
        if ins.address >= 0x400000 + 0x128735:
            break
    pre_ctx = ins_list[max(0, idx-30):idx]
    print("  context before hook site:")
    edx_srcs = []
    for ins in pre_ctx:
        print(f"    {ins.address:08X}  {ins.mnemonic} {ins.op_str}")
        if "edx" in ins.op_str.split(",")[0] and "[" in ins.op_str:
            edx_srcs.append(ins)
    sel_globals = [(ins.mnemonic + " " + ins.op_str) for ins in edx_srcs[-3:]]
print("  edx sources:", sel_globals)

out = {
    "hooks": results,
    "dataGlobals": globals_out,
    "selectionPointerCtx112": sel_globals,
    "hookOriginals": {  # original instruction bytes replaced at each site (from trainer's [DISABLE] dump)
        "money_h2": ["add edi,[eax+04]", "mov edx,[ecx]"],
        "money_h1": ["mov eax,[eax+04]", "mov ecx,[esi+000003b0]"],
        "money_h3": ["mov edi,[eax+34]", "mov ecx,[esi+3c]"],
        "money_h4": ["movss xmm0,[edi+2c]"],
        "proto_cool_b": ["cvttss2si eax,[esi+1c]"],
        "proto_cool_a": ["fld dword ptr [esi+1c]", "mov [esi+5c],eax"],
        "power": ["fld dword ptr [esi+000001bc]"],
        "build_power": ["mov ebx,[eax+00000418]"],
        "build_hp_a": ["mov esi,[eax+50]", "mov eax,[ecx]"],
        "build_hp_b": ["mov edx,[ecx+50]", "cmp edx,[eax+0c]"],
        "sidebar_pts": ["mov ecx,[eax+50]", "cmp ecx,[esi+20]"],
        "unit_lv": ["movss [ebp+00000260],xmm0"],
        "zoom_unit_xp": ["mov ecx,[edx+edi*4]", "test ecx,ecx"],
        "ammo": ["mov eax,[ecx+00001278]"],
        "fast_build": ["mov eax,[eax+08]", "sub eax,[ecx+14]"],
        "power_cool": ["movss [esi+44],xmm0"],
    },
}
json.dump(out, open(r"D:\RiderProject\RA3MT\assets\hookdata.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
n_ok = sum(1 for r in results if r.get("pattern"))
print(f"\n{n_ok}/{len(results)} hooks have unique cross-version signatures")
print("saved assets/hookdata.json")
