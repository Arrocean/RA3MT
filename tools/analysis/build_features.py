# -*- coding: utf-8 -*-
"""Emit the definitive assets/features.json consumed by the C# trainer.

Data model:
  hooks    : per hook site — exact RVA per version (primary), displaced bytes
             (what our detour overwrites/replays), optional cross-version AOB
             pattern (verification / unknown-build fallback) and a sibling
             anchor for fallback disambiguation.
  globals  : selection list holder, player-context root (local player idx at
             +0x28).
  features : the 24 features, wired to hooks or selection actions.
"""
import json
import struct

import pefile

D = json.load(open(r"D:\RiderProject\RA3MT\assets\hookdata.json", encoding="utf-8"))
hooks_in = D["hooks"]

ROOT112 = 0x8DDE84
ROOT113 = None


def find_root113():
    P = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game"
    data = open(P, "rb").read()
    pe = pefile.PE(P, fast_load=True)
    text = None
    tva = None
    for s in pe.sections:
        if s.Name.decode().strip("\x00") == ".text":
            text = data[s.PointerToRawData:s.PointerToRawData + s.Misc_VirtualSize]
            tva = s.VirtualAddress
    movs = [b"\xa1", b"\x8b\x1d", b"\x8b\x0d", b"\x8b\x15", b"\x8b\x35", b"\x8b\x3d", b"\x8b\x2d"]
    plus28 = [b"\x8b\x48\x28", b"\x8b\x58\x28", b"\x8b\x40\x28", b"\x8b\x50\x28",
              b"\x8b\x70\x28", b"\x8b\x78\x28", b"\x8b\x68\x28"]
    # 1) try single-root hypothesis: most-referenced disp32 whose +28 access exists
    from collections import Counter
    cnt = Counter()
    i = 0
    while True:
        i = text.find(b"\x28", i)  # dummy to keep loop cheap; real scan below
        break
    # scan candidate roots: all disp32 dwords in .data range referenced >=100 times
    lo, hi = 0x8B3000 + 0x400000, 0x931000 + 0x400000
    cands = Counter()
    n = len(text) - 6
    for j in range(n):
        v = struct.unpack_from("<I", text, j)[0]
        if lo <= v < hi:
            cands[v] += 1
    # test the top referenced ones for the +28 pattern
    best = None
    for v, c in cands.most_common(40):
        needle = struct.pack("<I", v)
        i = 0
        while True:
            i = text.find(needle, i)
            if i < 0:
                break
            for m in movs:
                if text[i - len(m):i] == m:
                    win = text[i + 4:i + 14]
                    for p in plus28:
                        j = win.find(p)
                        if 0 <= j <= 4:
                            best = (v, c)
                            break
                    break
            i += 1
        if best:
            break
    return best[0] - 0x400000 if best else None


ROOT113 = find_root113()
print("playerRoot: 1.12 =", hex(ROOT112), " 1.13 =", hex(ROOT113) if ROOT113 else "NOT FOUND")
assert ROOT113

sel = D["selectionGlobal"]
tf = D.get("threatFn", {})

SIB = {  # fallback anchors: resolve by displaced-byte search, pick hit nearest this site
    "money_h3": "money_h2", "build_hp_a": "build_hp_b", "sidebar_pts": "proto_cool_b",
    "fast_build": None, "unit_lv": None, "power_cool": None,
}

hooks_out = {}
for hid, h in hooks_in.items():
    e = {
        "rva": {"1.12": h["rva112"], "1.13": h["rva113"]},
        "displaced": h["displaced"],
        "displacedLen": h["displacedLen"],
        "asm": h.get("asm112"),
    }
    if h.get("pattern"):
        e["pattern"] = h["pattern"]
        e["patternSiteOffset"] = h.get("siteOffset", 0)
    if SIB.get(hid):
        e["sibling"] = SIB[hid]
    hooks_out[hid] = e

features = [
    # ---- hook-toggled (MasterCode-style flags) ----
    {"id": "money",   "no": "01", "name": "无限资金", "group": "资源", "kind": "toggle",
     "hotkey": "Ctrl+F1", "hooks": ["money_h2"], "flag": "money",
     "desc": "每次资金结算额外 +100000，且电力上限拉满", "src": "orig[01]"},
    {"id": "power",   "no": "02", "name": "无限电力", "group": "资源", "kind": "toggle",
     "hotkey": "Ctrl+F2", "hooks": ["money_h1"], "flag": "power",
     "desc": "资金恒为 10 万、电力消耗归零（不缺电）", "src": "orig[02]"},
    {"id": "scpoints","no": "03", "name": "无限协议点数", "group": "资源", "kind": "toggle",
     "hotkey": "Ctrl+F3", "hooks": ["money_h3"], "flag": "scpoints",
     "desc": "秘密协议点数恒为 99", "src": "orig[03]"},
    {"id": "allproto","no": "04", "name": "解锁全部协议", "group": "资源", "kind": "toggle",
     "hotkey": "Ctrl+F4", "hooks": ["money_h4"], "flag": "allproto",
     "desc": "解锁全部秘密协议技能", "src": "orig[04]"},
    {"id": "fastbuild","no": "05", "name": "快速建造", "group": "建造", "kind": "toggle",
     "hotkey": "Ctrl+F5", "hooks": ["proto_cool_a", "proto_cool_b", "power"], "flag": "fastbuild",
     "desc": "建筑/单位生产速度大幅加快，且建造期间不断电", "src": "orig[05]"},
    {"id": "instantready","no": "06", "name": "协议/超武立即就绪", "group": "建造", "kind": "toggle",
     "hotkey": "Ctrl+F6", "hooks": ["build_power", "build_hp_a"], "flag": "instantready",
     "desc": "己方协议技能与超级武器冷却立即归零", "src": "orig[06]"},
    {"id": "freezeenemy","no": "07", "name": "冻结敌方技能", "group": "建造", "kind": "toggle",
     "hotkey": "Ctrl+F7", "hooks": ["build_power", "build_hp_a", "build_hp_b", "sidebar_pts"],
     "flag": "freezeenemy",
     "desc": "敌方协议技能、超级武器与生产永不就绪", "src": "orig[07]"},
    {"id": "cooldown","no": "08", "name": "技能零冷却", "group": "建造", "kind": "toggle",
     "hotkey": "Ctrl+F8", "hooks": ["power_cool"], "flag": "cooldown",
     "desc": "技能冷却字段写零/分支控制（老版[08]缩放同源钩子，进游戏验证）", "src": "orig[06/08]"},
    {"id": "revealmap","no": "09", "name": "地图全开", "group": "视野", "kind": "toggle",
     "hotkey": "Ctrl+F9", "hooks": ["unit_lv"], "flag": "revealmap",
     "desc": "战争迷雾消散（视野半径拉满）", "src": "orig[09]"},
    {"id": "xp999",   "no": "10", "name": "选中单位瞬升三星", "group": "选中单位", "kind": "toggle",
     "hotkey": "Ctrl+P", "hooks": ["zoom_unit_xp"], "flag": "xp999",
     "desc": "选中列表中的单位经验值置 999（杀一敌即升星）", "src": "orig[10]"},
    {"id": "ammo",    "no": "18", "name": "选中单位无限弹药", "group": "选中单位", "kind": "toggle",
     "hotkey": "Ctrl+;", "hooks": ["ammo"], "flag": "ammo",
     "desc": "选中单位弹药/炸弹恒为 50000", "src": "orig[18]"},
    {"id": "instadone","no": "--", "name": "瞬间完成当前生产", "group": "建造", "kind": "toggle",
     "hotkey": "Ctrl+G", "hooks": ["fast_build"], "flag": "instadone",
     "desc": "触发一次后当前生产/建造进度立即完成（桩自复位）", "src": "extra"},

    # ---- selection actions (C# walks the selection list) ----
    {"id": "sel_lv",   "no": "10", "name": "选中单位等级拉满", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+P", "action": "lv", "desc": "遍历选中列表写 [unit+3CC]→[+C]=999999", "src": "orig[10]"},
    {"id": "sel_speed","no": "11", "name": "选中单位高速移动", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+-", "action": "speed1", "desc": "[+37C]→[+374]+200→[+8]=500", "src": "orig[11]"},
    {"id": "sel_speed2","no": "12", "name": "选中单位高速移动2", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+=", "action": "speed2", "desc": "同上但走 [+4] 节点（两栖单位）", "src": "orig[12]"},
    {"id": "sel_freeze","no": "13", "name": "冻结选中单位", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+PgUp", "action": "freeze1", "desc": "速度置 0（普通单位）", "src": "orig[13]"},
    {"id": "sel_freeze2","no": "14", "name": "冻结选中单位2", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+PgDn", "action": "freeze2", "desc": "速度置 0（两栖节点）", "src": "orig[14]"},
    {"id": "sel_hpmax","no": "15", "name": "选中目标生命拉满", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+[", "action": "hpmax", "desc": "[+33C]→[+4]=[+C]=999999", "src": "orig[15]"},
    {"id": "sel_hpmin","no": "16", "name": "选中目标生命归一", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+]", "action": "hpmin", "desc": "[+4]=1（濒死）", "src": "orig[16]"},
    {"id": "sel_hpnormal","no": "17", "name": "选中目标恢复生命", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+\\", "action": "hpnormal", "desc": "[+10]（上限）写回当前值", "src": "orig[17]"},
    {"id": "sel_capture","no": "19", "name": "俘虏选中目标", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+O", "action": "capture", "desc": "[+418] 改写为本地玩家索引", "src": "orig[19]"},
    {"id": "sel_destroy","no": "20", "name": "摧毁选中目标", "group": "选中单位", "kind": "action",
     "hotkey": "Alt+Del", "action": "destroy", "desc": "生命置 0（安全实现，替代老版危险 call）", "src": "orig[20]"},

    # ---- deferred (need more RE) ----
    {"id": "threat_max",   "no": "21", "name": "威胁等级最大", "group": "其他", "kind": "pending",
     "hotkey": "", "desc": "需定位威胁等级全局（老版 LM MAX）", "src": "orig[21]"},
    {"id": "threat_zero",  "no": "22", "name": "威胁等级归零", "group": "其他", "kind": "pending",
     "hotkey": "", "desc": "同上", "src": "orig[22]"},
    {"id": "threat_normal","no": "23", "name": "威胁等级恢复", "group": "其他", "kind": "pending",
     "hotkey": "", "desc": "同上", "src": "orig[23]"},
    {"id": "oremine",      "no": "24", "name": "矿脉恢复满量", "group": "其他", "kind": "pending",
     "hotkey": "", "desc": "需定位矿脉对象链（老版 #222）", "src": "orig[24]"},
]

out = {
    "schema": 1,
    "game": {
        "moduleNames": ["ra3_1.12.game", "ra3_1.13.game"],
        "processName": "ra3_1.12.game",
        "imageBase": "0x400000",
        "bits": 32,
    },
    "hooks": hooks_out,
    "globals": {
        "selectionList": {"rva": {"1.12": sel["rva112"], "1.13": sel["rva113"]},
                          "note": sel["note"]},
        "playerRoot": {"rva": {"1.12": hex(ROOT112), "1.13": hex(ROOT113)},
                       "note": "[root+0x28] = 本地玩家索引（俘掳/敌我判定）"},
    },
    "features": features,
    "references": {
        "threatFn": {"rva": {"1.12": tf.get("rva112"), "1.13": tf.get("rva113")},
                     "status": tf.get("status", "unverified")},
    },
}
json.dump(out, open(r"D:\RiderProject\RA3MT\assets\features.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
n_sig = sum(1 for h in hooks_out.values() if h.get("pattern"))
print(f"features.json written: {len(features)} features, {len(hooks_out)} hook sites, {n_sig} with AOB sigs")
