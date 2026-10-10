# -*- coding: utf-8 -*-
"""验证 pystubs.py 与 C# StubGen 输出逐字节一致（相同合成参数）。"""
import subprocess, os, sys, glob
sys.path.insert(0, os.path.dirname(__file__))
import pystubs

# 1) 用 C# 重新导出（合成基址）
out = r"D:\RiderProject\RA3MT\artifacts\stubs_pycheck"
subprocess.run(["dotnet", "run", "--project", r"D:\RiderProject\RA3MT\src\RA3MT.SelfCheck",
                "-c", "Release", "--", "stubdump", out],
               capture_output=True, cwd=r"D:\RiderProject\RA3MT")

FAKE_BLOCK = 0x40000000
FAKE_SITE = 0x452100
ok = bad = 0
for f in sorted(glob.glob(os.path.join(out, "*.bin"))):
    name = os.path.basename(f)[:-4]
    stub_id = "ammo" if name.startswith("ammo") else name
    csharp = open(f, "rb").read()
    meta = dict(l.split("=", 1) for l in open(f[:-4] + ".meta").read().splitlines())
    stub_va = int(meta["stubVa"], 16)
    site_end = int(meta["siteEnd"], 16)
    # c# 版的块基址
    cs_block = 0x40000000
    mine = pystubs.emit(stub_id, stub_va, site_end, cs_block, cs_block + pystubs.DIAG["player"])
    if mine == csharp:
        ok += 1
    else:
        bad += 1
        print(f"✗ {name}: C# {len(csharp)}B vs py {len(mine)}B")
        for i, (x, y) in enumerate(zip(csharp, mine)):
            if x != y:
                print(f"   首个差异 @0x{i:X}: cs={x:02X} py={y:02X}")
                break
print(f"\n一致 {ok} / 不一致 {bad}")
