import struct
from pathlib import Path

blob = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game').read_bytes()
pat = struct.pack('<I', 0x8F2CAC)
i = 0
hits = []
while True:
    i = blob.find(pat, i)
    if i < 0:
        break
    hits.append(i)
    i += 1
print('file-offset hits for 8F2CAC:', [hex(x) for x in hits])
for off in hits:
    ctx = blob[off - 8:off + 24]
    print('  off 0x%X  %s' % (off, ctx.hex(' ')))
