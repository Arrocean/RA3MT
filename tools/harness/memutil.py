# -*- coding: utf-8 -*-
"""RA3 活体内存工具：区域遍历 + 差分扫描。"""
import ctypes, ctypes.wintypes as wt, struct

k32 = ctypes.windll.kernel32
PVM_READ, VM_WRITE, VM_OP, PQI = 0x10, 0x20, 0x8, 0x400
MEM_COMMIT = 0x1000
IMG, MAPPED, PRIVATE = 0x1000000, 0x400000, 0x20000


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def open_game(pid):
    h = k32.OpenProcess(PVM_READ | VM_WRITE | VM_OP | PQI, False, pid)
    assert h, "OpenProcess 失败"
    return h


def iter_regions(h, writable_only=True):
    addr = 0
    mbi = MBI()
    size = ctypes.sizeof(mbi)
    while addr < 0x80000000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), size):
            addr += 0x1000
            continue
        rsize = mbi.RegionSize
        if mbi.State == MEM_COMMIT and (not writable_only or mbi.Protect in (0x04, 0x40, 0x08)):
            yield addr, rsize
        addr += rsize


def read(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def write(h, addr, data):
    buf = ctypes.create_string_buffer(bytes(data), len(data))
    got = ctypes.c_size_t()
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), buf, len(data), ctypes.byref(got))
    if ok:
        k32.FlushInstructionCache(h, ctypes.c_void_p(addr), len(data))
    return ok


def scan_value(h, value, label="scan"):
    """扫描全部可写区域，返回值==value 的地址列表（4 对齐）。"""
    needle = struct.pack("<i", value)
    hits = []
    for base, rsize in iter_regions(h):
        if rsize > 0x2000000:  # 跳过 >32MB 的巨型区域（一般是主堆，单独处理）
            # 分块读
            off = 0
            while off < rsize:
                chunk = min(0x400000, rsize - off)
                buf = read(h, base + off, chunk)
                if buf:
                    i = 0
                    while True:
                        i = buf.find(needle, i)
                        if i < 0:
                            break
                        hits.append(base + off + i)
                        i += 4
                off += chunk
            continue
        buf = read(h, base, rsize)
        if not buf:
            continue
        i = 0
        while True:
            i = buf.find(needle, i)
            if i < 0:
                break
            hits.append(base + i)
            i += 4
    print(f"[{label}] {len(hits)} 命中")
    return hits
