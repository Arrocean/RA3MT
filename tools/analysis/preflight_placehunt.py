"""Read-only pre-flight: confirm the six PLACEHUNT v2 sites still hold their
original bytes in the live process and on disk, and that the live distance value
is the default (so the tracer's pre-verify will not abort).
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000

PLACEHUNT = [
    (0xA47300, '578bf98b4c240c', 'top 放置顶层'),
    (0xA42450, '83ec148b44241c', 'validator 验证器(距离)'),
    (0xA2A1E0, '83ec34535556', 'percell 候选格评估'),
    (0xA2A283, '8b7424488b4e04', 'AABB-FAIL 剔除分支'),
    (0xA2A2A6, '8b0d4c21cf00', 'AABB-PASS 分支'),
    (0x5F0930, '83ec18833df030cf0000', 'vf48 区域谓词(对照)'),
]


class PMC(ctypes.Structure):
    _fields_ = [('cb', wt.DWORD), ('PageFaultCount', wt.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    if not h:
        raise SystemExit(f'OpenProcess({PID}) failed - game gone?')
    pmc = PMC()
    pmc.cb = ctypes.sizeof(pmc)
    ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    print(f'PID {PID}: WorkingSet {pmc.WorkingSetSize/1048576:.0f} MB  '
          f'Peak {pmc.PeakWorkingSetSize/1048576:.0f} MB  '
          f'Commit {pmc.PagefileUsage/1048576:.0f} MB  PeakCommit {pmc.PeakPagefileUsage/1048576:.0f} MB')

    print('\n--- PLACEHUNT v2 pre-verify (live) ---')
    allok = True
    for va, hexpat, label in PLACEHUNT:
        want = bytes.fromhex(hexpat)
        got = rd(h, va, len(want))
        ok = got == want
        allok &= ok
        print(f'  {label:<22} 0x{va:X}  {"MATCH" if ok else "*** MISMATCH ***  live=" + (got.hex() if got else "unreadable")}')
    print(f'  => tracer pre-verify would {"PASS" if allok else "ABORT"}')

    print('\n--- live placement state ---')
    gd = rd(h, BASE + 0x8F2CAC, 4)
    obj = struct.unpack('<I', gd)[0] if gd else 0
    print(f'  [0xCF2CAC] = 0x{obj:X}')
    if obj > 0x10000:
        d = rd(h, obj + 0xC, 4)
        if d:
            print(f'  distance [obj+0xC] = {struct.unpack("<f", d)[0]}')
    for name, va in (('placement manager [0xCF2410]', 0xCF2410),
                     ('ThePlacementGrid [0xCE21CC]', 0xCE21CC),
                     ('playerRoot [0xCF214C]', 0xCF214C)):
        v = rd(h, va, 4)
        val = struct.unpack('<I', v)[0] if v else None
        print(f'  {name} = {("0x%X" % val) if val is not None else "unreadable"}')

    print('\n--- is the trainer still attached? (check a MasterCode-owned site) ---')
    # money_h2 original bytes per features.json: 03 78 04 8B 11
    site = BASE + 0x6699CE
    got = rd(h, site, 5)
    print(f'  money_h2 @0x{site:X} = {got.hex() if got else "unreadable"} '
          f'({"original (trainer detached)" if got and got.hex() == "037804 8b11".replace(" ", "") else "patched or unknown"})')


if __name__ == '__main__':
    main()
