# -*- coding: utf-8 -*-
r"""Generate assets/reinforcement_codes.json — the built-in unit code table.

The "reinforcement code" the trainer accepts is the game's WB string hash of a
GameObject's internal name (verified live: AlliedMCV=0x28DA574E etc.). Instead
of making users dig through .big archives with C&C BIG/Asset Extractor (the
manual method documented in community posts), this tool extracts the whole
table from the installed game once, and the trainer embeds the result.

Sources (all from <gamedir>/Data):
  WBStringHashes.big  -> data\stringhashes.xml   plain XML, name -> hash
  Core*.big           -> data\static.N.manifest  RefPack-compressed, contains
                         every "GameObject:<Name>" asset entry (highest N wins)
  ChineseT.big        -> data\gamestrings.csf    RefPack + CSF, localized
                         display names ("NAME:<UPPERNAME>")

Curation: an object ships when it has a localized display name (the game does
not localize helper objects like projectiles/collapse states) and survives the
junk filter. Neutral crates make the fun category.

Usage: py tools/analysis/gen_reinforce_table.py [--game-dir D:\\...\\Red Alert 3]
"""
import argparse
import json
import re
import struct
import os

DEFAULT_GAME = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3"

# Objects that are spawn-safe fun / utility even without a faction prefix.
# Anything matching JUNK is dropped even when localized.
JUNK = re.compile(
    r'Projectile|_Collapse|_Dying|_Debris|_Veteran|_Leeched|CrateSpawner|'
    r'Spawner|Effect|_Die$|OCL$|Beacon|Marker|Shroud|MicroManager|AIState')


# ---------- BIG4 archive ----------
def big_entries(path):
    """Yield (name, offset, size) for a BIG4 archive. Index fields are
    big-endian u32 pairs followed by null-terminated names."""
    with open(path, 'rb') as f:
        head = f.read(16)
        if head[:4] != b'BIG4':
            raise ValueError(f"{path}: not a BIG4 archive")
        count = struct.unpack_from('>I', head, 8)[0]
        idx = f.read(struct.unpack_from('>I', head, 12)[0])
    pos, out = 0, []
    for _ in range(count):
        off, size = struct.unpack_from('>II', idx, pos)
        pos += 8
        end = idx.index(b'\0', pos)
        out.append((idx[pos:end].decode('utf-8', 'replace'), off, size))
        pos = end + 1
    return out


def big_read(path, entry):
    with open(path, 'rb') as f:
        f.seek(entry[1])
        return f.read(entry[2])


# ---------- RefPack ----------
def refpack_decompress(data):
    """Public-domain reference decompression (Niotso wiki implementation)."""
    sig = (data[0] << 8) | data[1]
    pos = 2
    if sig & 0x0100:
        pos += 3
    pos += 3  # decompressed size (trusted from the archive index instead)
    out = bytearray()
    while True:
        b0 = data[pos]; pos += 1
        if not (b0 & 0x80):                                   # 2-byte command
            b1 = data[pos]; pos += 1
            out += data[pos:pos + (b0 & 3)]; pos += b0 & 3
            dis = ((b0 & 0x60) << 3) + b1 + 1
            for _ in range(((b0 >> 2) & 7) + 3):
                out.append(out[-dis])
        elif not (b0 & 0x40):                                 # 3-byte command
            b1, b2 = data[pos:pos + 2]; pos += 2
            out += data[pos:pos + (b1 >> 6)]; pos += b1 >> 6
            dis = ((b1 & 0x3f) << 8) + b2 + 1
            for _ in range((b0 & 0x3f) + 4):
                out.append(out[-dis])
        elif not (b0 & 0x20):                                 # 4-byte command
            b1, b2, b3 = data[pos:pos + 3]; pos += 3
            out += data[pos:pos + (b0 & 3)]; pos += b0 & 3
            dis = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            for _ in range(((b0 & 0x0c) << 6) + b3 + 5):
                out.append(out[-dis])
        else:                                                 # 1-byte command
            plen = (b0 & 0x1f) * 4 + 4
            if plen <= 0x70:
                out += data[pos:pos + plen]; pos += plen
            else:
                out += data[pos:pos + (b0 & 3)]; pos += b0 & 3
                break
    return bytes(out)


# ---------- CSF localized strings ----------
def parse_csf(data):
    """CSF: 24-byte header, then ' LBL' + name + ' RTS' + XOR-0xFF UTF-16LE."""
    pos, out = 24, {}
    while pos < len(data) - 8:
        if data[pos:pos + 4] != b' LBL':
            break
        _, nlen = struct.unpack_from('<II', data, pos + 4)
        name = data[pos + 12:pos + 12 + nlen].decode('latin1')
        pos2 = pos + 12 + nlen
        if data[pos2:pos2 + 4] == b' RTS':
            slen = struct.unpack_from('<I', data, pos2 + 4)[0]
            w = data[pos2 + 8:pos2 + 8 + slen * 2]
            out[name] = bytes(b ^ 0xFF for b in w).decode('utf-16-le', 'replace')
            pos2 += 8 + slen * 2
        pos = pos2
    return out


# ---------- assembly ----------
def load_hashmap(data_dir):
    if not os.path.exists(os.path.join(data_dir, 'WBStringHashes.big')):
        # Uprising ships the same registry as a compiled StringHashes asset.
        # Its serialized offsets are relative to the 8-byte asset header.
        path = os.path.join(data_dir, 'Misc.big')
        entry = next(e for e in big_entries(path) if e[0].endswith('stringhashes.bin'))
        raw = refpack_decompress(big_read(path, entry))
        count = struct.unpack_from('<I', raw, 16)[0]
        if count > 1_000_000 or 24 + count*12 > len(raw):
            raise ValueError('invalid compiled string hash table')
        hmap = {}
        for i in range(count):
            h, size, offset = struct.unpack_from('<III', raw, 24+i*12)
            if size == 0 or offset+8+size > len(raw):
                raise ValueError('invalid compiled string hash entry')
            text = raw[offset+8:offset+8+size].rstrip(b'\0').decode('utf8')
            hmap[text] = h
        return hmap
    entries = big_entries(os.path.join(data_dir, 'WBStringHashes.big'))
    xml_name = next(n for n, _, _ in entries if n.endswith('stringhashes.xml'))
    xml = big_read(os.path.join(data_dir, 'WBStringHashes.big'),
                   next(e for e in entries if e[0] == xml_name))
    hmap = {}
    for h, t in re.findall(r'<StringAndHash Hash="(\d+)" Text="([^"]+)"', xml.decode('utf-8-sig')):
        hmap[t] = int(h)  # later duplicates win; object names never conflict
    return hmap


def load_gameobject_names(data_dir):
    """Highest Core*.big static manifest = the full object list for the
    newest installed patch."""
    best = None
    for fn in os.listdir(data_dir):
        m = re.fullmatch(r'Core(\d+)\.big', fn)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), fn)
    if best is None:
        path = os.path.join(data_dir, 'StaticStream.big')
        entries = big_entries(path)
        entry = next(e for e in entries if e[0].lower() == 'data\\static.manifest')
        raw = refpack_decompress(big_read(path, entry))
        return set(x.decode() for x in re.findall(rb'GameObject:([A-Za-z0-9_]+)\x00', raw))
    core = os.path.join(data_dir, best[1])
    entries = big_entries(core)
    man_entry = next(e for e in entries if e[0].endswith(f'static.{best[0]}.manifest'))
    raw = refpack_decompress(big_read(core, man_entry))
    return set(x.decode() for x in re.findall(rb'GameObject:([A-Za-z0-9_]+)\x00', raw))


def load_zh_names(data_dir, lang_big):
    entries = big_entries(os.path.join(data_dir, lang_big))
    csf_entry = next(e for e in entries if e[0].endswith('gamestrings.csf'))
    raw = refpack_decompress(big_read(os.path.join(data_dir, lang_big), csf_entry))
    strings = parse_csf(raw)
    return {k[5:].upper(): v.strip() for k, v in strings.items() if k.startswith('NAME:')}


CATEGORIES = [
    ('allied', '盟军', ('Allied',)),
    ('soviet', '苏军', ('Soviet',)),
    ('japan', '升阳帝国', ('Japan',)),
    ('neutral', '中立与趣味', ()),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game-dir', default=DEFAULT_GAME)
    ap.add_argument('--lang-big', default='ChineseT.big',
                    help='localization archive holding gamestrings.csf')
    ap.add_argument('-o', '--out', default=r'D:\RiderProject\RA3MT\assets\reinforcement_codes.json')
    args = ap.parse_args()
    data_dir = os.path.join(args.game_dir, 'Data')

    hmap = load_hashmap(data_dir)
    objects = load_gameobject_names(data_dir)
    zh = load_zh_names(data_dir, args.lang_big)
    print(f"hashes={len(hmap)} objects={len(objects)} zh-names={len(zh)}")

    registry = 'WBStringHashes.big' if os.path.exists(os.path.join(data_dir,'WBStringHashes.big')) else 'Uprising Misc.big/stringhashes.bin'
    out = {"source": registry + " + static manifest + "
                     f"{args.lang_big}（自动提取，与手动解包法等价）",
           "categories": []}
    faction_prefixes = ('Allied', 'Soviet', 'Japan')
    neutral = []
    for cid, cname, prefixes in CATEGORIES:
        items = []
        for n in sorted(objects):
            if prefixes:
                if not n.startswith(prefixes):
                    continue
            elif n.startswith(faction_prefixes):
                continue  # neutral bucket: everything without a faction prefix
            zh_name = zh.get(n.upper())
            if not zh_name or JUNK.search(n):
                continue
            if n not in hmap:
                continue
            row = {"n": n, "zh": zh_name, "code": f"{hmap[n]:08X}"}
            (items if prefixes else neutral).append(row)
        if prefixes:
            out["categories"].append({"id": cid, "name": cname, "items": items})
    out["categories"].append({"id": "neutral", "name": "中立与趣味", "items": neutral})

    total = sum(len(c["items"]) for c in out["categories"])
    by = {c["name"]: len(c["items"]) for c in out["categories"]}

    # spot-check against values verified live against the running game
    expect = {"AlliedMCV": 0x28DA574E, "SovietMCV": 0xAF4C0DA5,
              "JapanMCV": 0x1C2EF767, "JapanCommandoTech1": 0x6586A5A0,
              "JapanEmperorMecha": 0xCC023E30}
    for n, want in expect.items():
        assert hmap.get(n) == want, f"hash table {n}: {hmap.get(n)} != 0x{want:08X}"
    flat = {r["n"]: int(r["code"], 16) for c in out["categories"] for r in c["items"]}
    for n in ("AlliedMCV", "SovietMCV", "JapanMCV"):
        assert n in flat, f"{n} missing from curated table"

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {args.out}: {total} entries {by}; spot checks OK")


if __name__ == '__main__':
    main()
