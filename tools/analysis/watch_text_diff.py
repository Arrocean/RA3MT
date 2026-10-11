"""Watch the 1.12 game's .text section for byte patches — the FINAL3
experiment.

Takes a BASELINE snapshot of the game's code section when it starts, then
rescans every 3 seconds and prints every byte range that changed since
baseline (VA, old bytes, new bytes). Also reports when a change reverts.

This settles, without any guessing, what FINAL3's Free Build actually
patches in a live 1.12 process: start THIS monitor first, then run FINAL3
and toggle its free-build option. The printout IS the patch.

Usage: py tools/analysis/watch_text_diff.py [seconds=600] [pid]
  pid optional: auto-finds ra3_1.12.game (falls back to any ra3_*.game)
"""
import ctypes
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32

BASE = 0x400000


def find_game():
    """Prefer 1.12 (the FINAL3 experiment target), fall back to any ra3."""
    names = ('ra3_1.12.game', 'ra3_1.13.game')
    pids = {}
    for name in names:
        try:
            out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}',
                                  '/FO', 'CSV', '/NH'],
                                 capture_output=True, timeout=10).stdout
        except Exception:
            continue
        for line in out.splitlines():
            if line.lower().startswith(b'"ra3_'):
                try:
                    pids[name] = int(line.split(b'","')[1])
                except (ValueError, IndexError):
                    pass
    for name in names:
        if name in pids:
            return pids[name], name
    return None, None


def read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def text_section(h):
    """Parse the module PE headers from process memory; return (va, size)."""
    hdr = read_mem(h, BASE, 0x1000)
    if not hdr or hdr[:2] != b'MZ':
        raise SystemExit(f'0x{BASE:X} 处没有 MZ 头——模块基址不是 0x400000？')
    pe = struct.unpack_from('<I', hdr, 0x3C)[0]
    if hdr[pe:pe + 4] != b'PE\0\0':
        raise SystemExit('PE 签名不匹配')
    nsec = struct.unpack_from('<H', hdr, pe + 6)[0]
    opt = struct.unpack_from('<H', hdr, pe + 20)[0]
    for i in range(nsec):
        off = pe + 24 + opt + i * 40
        name = hdr[off:off + 8].rstrip(b'\0').decode('ascii', 'replace')
        vsize, va = struct.unpack_from('<II', hdr, off + 8)
        if name == '.text':
            return BASE + va, vsize
    raise SystemExit('没有找到 .text')


def diff_ranges(a, b):
    """Yield (start, end) index ranges where a and b differ."""
    n = min(len(a), len(b))
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            # merge gaps < 8 bytes
            while j < n and (b[j] != a[j] or all(a[k] == b[k] for k in range(j, min(j + 8, n)))):
                if b[j] != a[j]:
                    j += 1
                else:
                    break
            yield i, j
            i = j
        else:
            i += 1


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    pid = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    pname = None
    if not pid:
        pid, pname = find_game()
        if not pid:
            raise SystemExit('未找到 ra3_1.12.game 进程——先把游戏切到 1.12 并进对局，再跑本监控。')
    print(f'监控进程 PID {pid}' + (f'（{pname}）' if pname else ''), flush=True)
    h = k32.OpenProcess(0x10 | 0x20, False, pid)  # VM_READ | QUERY_INFORMATION
    if not h:
        raise SystemExit('OpenProcess failed（用管理员身份开命令行再试）')

    tva, tsize = text_section(h)
    print(f'.text VA 0x{tva:X} 大小 0x{tsize:X}（{tsize/1024/1024:.1f} MB）——正在拍基线快照...', flush=True)
    baseline = read_mem(h, tva, tsize)
    if not baseline or len(baseline) != tsize:
        raise SystemExit('基线读取失败')
    print('基线完成。现在去运行 FINAL3 并开启它的随地建造/Free Build。', flush=True)
    print('任何字节改动都会在这里打印。', flush=True)

    known = {}   # range_start -> (old, new)  (to detect reverts too)
    t0 = time.time()
    try:
        while time.time() - t0 < secs:
            time.sleep(3)
            cur = read_mem(h, tva, tsize)
            if not cur:
                print('读取失败（游戏退出？）', flush=True)
                break
            if cur == baseline:
                # everything back to baseline? report reverts of known diffs
                for start, (old, new) in list(known.items()):
                    print(f'[REVERTED] 0x{tva+start:X} 已恢复基线（曾是 {new.hex(" ")}）', flush=True)
                known.clear()
                continue
            for start, end in diff_ranges(baseline, cur):
                old, new = baseline[start:end], cur[start:end]
                va = tva + start
                key = start
                if key in known and known[key] == (old, new):
                    continue   # unchanged since last report
                if key in known:
                    print(f'[CHANGED-AGAIN] 0x{va:X}: {known[key][1].hex(" ")} -> {new.hex(" ")}', flush=True)
                else:
                    print(f'[PATCH] 0x{va:X} 长度 {end-start}: '
                          f'{old.hex(" ")} -> {new.hex(" ")}', flush=True)
                known[key] = (old, new)
    except KeyboardInterrupt:
        print('手动停止', flush=True)
    finally:
        k32.CloseHandle(h)
        print(f'监控结束（共 {len(known)} 处未还原的改动）', flush=True)


if __name__ == '__main__':
    main()
