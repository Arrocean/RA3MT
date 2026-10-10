"""Extract rolling-XOR Cheat Engine scripts from FINAL3 without executing it."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

source = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
data = source.read_bytes()
marker = bytes(value ^ (index + 1) for index, value in enumerate(b'[ENABLE]'))
scripts = []
for match in re.finditer(re.escape(marker), data):
    offset = match.start()
    if offset < 4:
        continue
    length = struct.unpack_from('<I', data, offset - 4)[0]
    if length < 8 or offset + length > len(data):
        continue
    raw = bytes(value ^ ((index + 1) & 255) for index, value in enumerate(data[offset:offset + length]))
    text = raw.decode('utf-8', errors='replace').replace('\r\r\n', '\n').replace('\r\n', '\n')
    if not text.startswith('[ENABLE]') or '[disable]' not in text.lower():
        continue
    name = f'script_{len(scripts):02d}_{offset:08X}.cea'
    (out / name).write_text(text, encoding='utf-8')
    scripts.append({'offset': hex(offset), 'encodedLength': length, 'file': name})
report = {'source': str(source), 'sha256': hashlib.sha256(data).hexdigest(),
          'size': len(data), 'scripts': scripts}
(out / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
