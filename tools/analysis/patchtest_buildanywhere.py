"""Temporary build-anywhere patch test — FINAL3-exact, 2 bytes, auto-revert.

THE FIND (2026-10-12): FINAL3's Free Build patches EA 1.12 RVA 0xE7565
(75 0C -> EB 0C) — the 'return 2 = outside buildable range' epilogue branch
of a shared placement-gate function (loop + per-item predicate + fail code).
The function was located in BOTH Steam repacks by signature
(test edx,0x8000 is unique in .text; sete-triple and mov eax,2/ret 0x10
cluster in the same function; verified instruction-by-instruction identical
to the EA original from the pirated copy):

    EA 1.12 (FINAL3)  0x4E7565   75 0C -> EB 0C   (verified on disk)
    Steam 1.12        0x528DF5   75 0C -> EB 0C   (verified on disk)
    Steam 1.13        0x511955   75 0C -> EB 0C   (verified on disk)

Same 2 bytes everywhere. The gate function is SHARED by player placement
and AI site-picking (it sits right next to the AI worker 0x511980), which
is why one patch flips both.

JUDGING CRITERIA (matches FINAL3's actual behavior, per the user): the
ghost cells do NOT turn green — you place on GREY cells. Just click.

Usage: py tools/analysis/patchtest_buildanywhere.py [seconds=120] [pid]
"""
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_trampoline as t  # noqa: E402  (read_mem/write_mem/suspend)

SITES = {
    'ra3_1.13.game': 0x511955,
    'ra3_1.12.game': 0x528DF5,
}
ORIG = bytes.fromhex('750c')     # 75 0C (jne +0xC)
PATCH = bytes.fromhex('eb0c')    # EB 0C (jmp +0xC)


def find_game_named():
    """Return (pid, process_name) for whichever ra3 game is running."""
    for name in SITES:
        try:
            out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}',
                                  '/FO', 'CSV', '/NH'],
                                 capture_output=True, timeout=10).stdout
        except Exception:
            continue
        for line in out.splitlines():
            if line.lower().startswith(b'"ra3_'):
                try:
                    return int(line.split(b'","')[1]), name
                except (ValueError, IndexError):
                    pass
    return None, None


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    pid = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    pname = None
    if not pid:
        pid, pname = find_game_named()
        if not pid:
            raise SystemExit('未找到游戏进程——红警3要开到对局里。也可带 PID 运行。')
    if not pname:
        # explicit pid given: probe both sites to identify the version
        h0 = t.k32.OpenProcess(0x10, False, pid)
        if not h0:
            raise SystemExit('OpenProcess failed（用管理员身份开命令行再试）')
        for name, site in SITES.items():
            if t.read_mem(h0, site, 2) == ORIG:
                pname = name
                break
        t.k32.CloseHandle(h0)
        if not pname:
            raise SystemExit('两个候选点的字节都不是 75 0C——无法识别版本，拒绝继续')

    site = SITES[pname]
    h = t.k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed（用管理员身份开命令行再试）')

    cur = t.read_mem(h, site, 2)
    if cur != ORIG:
        raise SystemExit(f'{pname} 0x{site:X} 字节不是预期的 75 0C（当前 {cur.hex() if cur else None}）——拒绝继续')

    print(f'游戏版本：{pname}（Steam 重打包）')
    print(f'补丁点：0x{site:X}  75 0C -> EB 0C（FINAL3 同款 2 字节，还原 EA 版 0x4E7565 的语义）')
    print()
    print('临时随地建造实验（{} 秒后自动还原）：'.format(secs))
    print('  ★ 判定标准（和 FINAL3 的真实效果一致）：格子【不会变绿】！')
    print('    1) 拿起一个建筑虚影（比如电厂）')
    print('    2) 移到远离基地的空地——格子可能显示灰色')
    print('    3) 【直接按左键】试着放下！')
    print('    4) 放下成功 = 成功；游戏提示不能建造 = 还有别的检查层')
    print('  就算你关掉这个窗口，游戏进程退出前字节也会保持——但请等它自己还原', flush=True)

    frozen = t.suspend_all(pid)
    time.sleep(0.08)
    ok = t.write_mem(h, site, PATCH) and t.read_mem(h, site, 2) == PATCH
    t.resume_all(frozen)
    if not ok:
        raise SystemExit('写入失败，未生效')
    print(f'[patched] 0x{site:X}: 75 0C -> EB 0C', flush=True)

    try:
        t0 = time.time()
        while time.time() - t0 < secs:
            time.sleep(1)
            left = int(secs - (time.time() - t0))
            if left in (60, 30, 10):
                print(f'  ...还剩 {left} 秒', flush=True)
    finally:
        frozen2 = t.suspend_all(pid)
        time.sleep(0.08)
        t.write_mem(h, site, ORIG)
        verify = t.read_mem(h, site, 2)
        t.resume_all(frozen2)
        time.sleep(0.1)
        t.k32.CloseHandle(h)
        print(f'[restored] 0x{site:X} = {verify.hex()} '
              f'({"OK 已还原" if verify == ORIG else "*** 还原异常！手动检查！ ***"})', flush=True)


if __name__ == '__main__':
    main()
