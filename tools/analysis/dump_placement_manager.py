"""Wait for the game process, then dump the placement-manager singleton's
vtable methods (runtime-only data) and disassemble them from the on-disk image.

The manager global (1.13 VA 0xCF2410 / 1.12 0xCEBxxx) is created during engine
init, so the main menu is enough — no skirmish needed. Slots of interest:
  +0x48  placement rule check used by the UI can-place predicate (0x307880)
  +0x20  coordinate query used by the map-start spawn caller
Run as admin. Never writes to the game process.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time
from pathlib import Path

k32 = ctypes.windll.kernel32

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

MANAGER_VA = {  # .data VA of the manager singleton pointer (UI predicate reader)
    'ra3_1.13.game': 0xCF2410,
    'ra3_1.12.game': 0xCEE0F0,  # symmetric predicate at 0x31CBC0 reads this
}

SLOTS = [('+0x20', 0x20, 'coord query (map-start caller)'),
         ('+0x48', 0x48, 'placement rule check (UI predicate)'),
         ('+0x28', 0x28, 'misc'),
         ('+0x50', 0x50, 'misc')]


class PE(ctypes.Structure):
    _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong),
                ('th32ProcessID', ctypes.c_ulong), ('th32ModuleID', ctypes.c_ulong),
                ('cntThreads', ctypes.c_ulong), ('th32ParentProcessID', ctypes.c_ulong),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong),
                ('szExeFile', ctypes.c_char * 260)]


def find_game():
    procs = []
    lppe = PE()
    lppe.dwSize = ctypes.sizeof(PE)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    while k32.Process32Next(snap, ctypes.byref(lppe)):
        name = lppe.szExeFile.decode(errors='replace')
        if name in MANAGER_VA:
            procs.append((lppe.th32ProcessID, name))
    k32.CloseHandle(snap)
    return procs


def read_u32(h, addr):
    buf = ctypes.c_uint32()
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), ctypes.byref(buf), 4, ctypes.byref(got)) or got.value != 4:
        raise OSError(f'read failed at 0x{addr:X}')
    return buf.value


def main():
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 1800
    print('等待游戏进程（主菜单即可，无需进对局）…', flush=True)
    deadline = time.time() + timeout
    found = None
    while time.time() < deadline:
        procs = find_game()
        if procs:
            found = procs[0]
            break
        time.sleep(2)
    if not found:
        raise SystemExit('timeout: game not started')
    pid, module = found
    print(f'found {module} PID {pid}', flush=True)
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        raise OSError('OpenProcess failed (run as admin?)')
    try:
        manager_va = MANAGER_VA[module]
        obj = read_u32(h, manager_va)
        print(f'manager global [0x{manager_va:X}] = 0x{obj:X}')
        if obj < 0x10000:
            raise SystemExit('manager singleton not initialized yet — wait for main menu')
        vt = read_u32(h, obj)
        print(f'object vtable = 0x{vt:X}')
        for label, off, desc in SLOTS:
            fn = read_u32(h, vt + off)
            print(f'  vf{label} ({desc}): 0x{fn:X}')
        # ThePlacementGrid singleton for reference
        grid_va = 0xCE21CC if '1.13' in module else 0xCDDEAC
        grid = read_u32(h, grid_va)
        print(f'ThePlacementGrid [0x{grid_va:X}] = 0x{grid:X}')
        grid_vt = read_u32(h, grid) if grid >= 0x10000 else 0
        if grid_vt:
            print(f'ThePlacementGrid vtable = 0x{grid_vt:X}')
    finally:
        k32.CloseHandle(h)


if __name__ == '__main__':
    main()
