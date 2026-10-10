"""Read-only RA3 selected-unit diagnostics. No hooks or game writes.
Run: py tools/analysis/inspect_selection.py [--pid PID]
"""
import argparse
import ctypes
from ctypes import wintypes as wt
import json
import struct

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wt.BOOL


class ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wt.DWORD),
                ('cntThreads', wt.DWORD), ('th32ParentProcessID', wt.DWORD),
                ('pcPriClassBase', wt.LONG), ('dwFlags', wt.DWORD),
                ('szExeFile', wt.WCHAR * 260)]


class ModuleEntry(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('th32ModuleID', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('GlblcntUsage', wt.DWORD), ('ProccntUsage', wt.DWORD),
                ('modBaseAddr', ctypes.c_void_p), ('modBaseSize', wt.DWORD),
                ('hModule', wt.HMODULE), ('szModule', wt.WCHAR * 256),
                ('szExePath', wt.WCHAR * 260)]


for name, cls in [('Process32FirstW', ProcessEntry), ('Process32NextW', ProcessEntry),
                  ('Module32FirstW', ModuleEntry), ('Module32NextW', ModuleEntry)]:
    fn = getattr(k32, name)
    fn.argtypes = [wt.HANDLE, ctypes.POINTER(cls)]
    fn.restype = wt.BOOL


def enumerate_snapshot(flags, pid, cls, first, next_fn):
    handle = k32.CreateToolhelp32Snapshot(flags, pid)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        item = cls()
        item.dwSize = ctypes.sizeof(cls)
        ok = first(handle, ctypes.byref(item))
        while ok:
            yield item
            ok = next_fn(handle, ctypes.byref(item))
    finally:
        k32.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    args = parser.parse_args()
    games = []
    for item in enumerate_snapshot(2, 0, ProcessEntry, k32.Process32FirstW, k32.Process32NextW):
        if item.szExeFile.lower() in ('ra3_1.12.game', 'ra3_1.13.game'):
            games.append((item.th32ProcessID, item.szExeFile.lower()))
    if args.pid:
        games = [game for game in games if game[0] == args.pid]
    if len(games) != 1:
        raise RuntimeError('Expected one running RA3 game; use --pid when multiple are running')
    pid, name = games[0]
    base = None
    for item in enumerate_snapshot(0x18, pid, ModuleEntry, k32.Module32FirstW, k32.Module32NextW):
        if item.szModule.lower() == name:
            base = item.modBaseAddr
            break
    if base is None:
        raise RuntimeError('Game module not found')
    version = '1.13' if '1.13' in name else '1.12'
    offsets = {'1.12': (0x8E08DC, 0x8EDE2C), '1.13': (0x8E4BFC, 0x8F214C)}
    selection_rva, controller_rva = offsets[version]
    handle = k32.OpenProcess(0x10 | 0x400, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        def read(address, size):
            buffer = ctypes.create_string_buffer(size)
            got = ctypes.c_size_t()
            if not k32.ReadProcessMemory(handle, address, buffer, size, ctypes.byref(got)) or got.value != size:
                raise RuntimeError(f'Unreadable address 0x{address:X}')
            return buffer.raw

        def u32(address):
            return struct.unpack('<I', read(address, 4))[0]

        def f32(address):
            return struct.unpack('<f', read(address, 4))[0]

        def ptr(address):
            value = u32(address)
            return value if value >= 0x10000 else 0

        controller = ptr(base + controller_rva)
        side = ptr(controller + 0x28) if controller else 0
        root = ptr(base + selection_rva)
        count = u32(root + 0x5C) if root else 0
        if count > 4096:
            raise RuntimeError('Corrupt selection count')
        report = {'pid': pid, 'version': version, 'base': hex(base), 'localSide': hex(side),
                  'selectionCount': count, 'selected': []}
        sentinel = root + 0x50 if root else 0
        node = u32(sentinel) if root else 0
        visited = set()
        for _ in range(count):
            if node == sentinel or node < 0x10000 or node in visited:
                raise RuntimeError('Selection changed or linked list is corrupt')
            visited.add(node)
            drawable = ptr(node + 8)
            body = ptr(drawable + 0x138) if drawable else 0
            if not body or u32(body + 0xF4) != drawable or not (read(drawable + 0x13D, 1)[0] & 0x40):
                raise RuntimeError('Selection drawable validation failed')
            row = {'body': hex(body), 'owner': hex(u32(body + 0x418))}
            hp = ptr(body + 0x33C)
            if hp:
                row['health'] = {'current': f32(hp + 4), 'effectiveMaximum': f32(hp + 0xC), 'baseMaximum': f32(hp + 0x10)}
            xp = ptr(body + 0x3CC)
            if xp:
                row['experience'] = {'value': f32(xp + 0xC), 'rank': u32(xp + 0x24)}
            ai = ptr(body + 0x374)
            active = ptr(ai + 0x21C) if ai else 0
            if active:
                row['locomotor'] = {'address': hex(active), 'baseSpeed': f32(active + 8),
                                    'cap': f32(active + 0x20), 'cachedSpeed': f32(active + 0x38)}
            weapon_set = ptr(body + 0x37C)
            row['weapons'] = []
            if weapon_set:
                begin, end = u32(weapon_set + 0x34), u32(weapon_set + 0x38)
                if end < begin or end - begin > 4096 or (end - begin) % 4:
                    raise RuntimeError('Corrupt weapon vector')
                for cursor in range(begin, end, 4):
                    weapon = ptr(cursor)
                    if not weapon:
                        continue
                    slot = ptr(weapon + 8)
                    if not slot or u32(slot + 0x10) != body:
                        raise RuntimeError('Weapon ownership validation failed')
                    wrapper = ptr(weapon + 4)
                    template = ptr(wrapper + 4) if wrapper else 0
                    row['weapons'].append({'address': hex(weapon), 'clip': u32(weapon + 0x1C),
                                           'capacity': u32(template + 0x70) if template else None})
            report['selected'].append(row)
            node = u32(node)
        if count and node != sentinel:
            raise RuntimeError('Selection list length changed')
        if root and (u32(base + selection_rva) != root or u32(root + 0x5C) != count):
            raise RuntimeError('Selection changed while reading; retry')
        print(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False))
    finally:
        k32.CloseHandle(handle)


if __name__ == '__main__':
    main()
