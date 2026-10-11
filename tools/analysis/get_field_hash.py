"""Read WBStringHashes.big and print the WB hash of placement-related names."""
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

BIG = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\WBStringHashes.big')
WANTED = {
    'BuildingPlacementDistance', 'AssistedPlacementInfoBehavior', 'PlacementRestriction',
    'StructurePlacementBehavior', 'GameData', 'BuildingPlacement',
}


def main():
    with BIG.open('rb') as f:
        header = f.read(16)
        if header[:4] != b'BIG4':
            raise SystemExit('not BIG4')
        count, _ = struct.unpack('>II', header[8:16])
        payload = None
        for _ in range(count):
            offset, size = struct.unpack('>II', f.read(8))
            name = bytearray()
            while True:
                c = f.read(1)
                if c == b'\x00':
                    break
                name.extend(c)
            if name.decode('ascii', 'replace').replace('\\', '/').lower() == 'data/stringhashes.xml':
                f.seek(offset)
                payload = f.read(size)
                break
        if payload is None:
            raise SystemExit('stringhashes.xml not found')
    root = ET.fromstring(payload)
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] == 'StringAndHash' and node.attrib.get('Text') in WANTED:
            print(f"{node.attrib['Text']} = 0x{int(node.attrib['Hash']):08X}")


if __name__ == '__main__':
    main()
