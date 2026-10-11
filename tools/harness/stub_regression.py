#!/usr/bin/env python
"""Zero-regression gate for the refactor: re-dump the stubs and compare every
byte against the frozen baseline in artifacts/baseline_stubs.

Usage:
  py tools/harness/stub_regression.py            # dump to artifacts/stubs_check and compare
  py tools/harness/stub_regression.py --freeze   # refresh the baseline (only when a change is intended)
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'artifacts' / 'baseline_stubs'
CHECK = ROOT / 'artifacts' / 'stubs_check'


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--freeze', action='store_true')
    args = ap.parse_args()

    target = BASELINE if args.freeze else CHECK
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    r = subprocess.run(['dotnet', 'run', '--project', 'src/RA3MT.SelfCheck', '-c', 'Release',
                        '--no-build', '--', 'stubdump', str(target)],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:], file=sys.stderr)
        return 2

    new = sorted(target.glob('*.bin'))
    if args.freeze:
        (BASELINE / 'MANIFEST.txt').write_text(
            '\n'.join(f'{f.name} {digest(f)[:16]} {f.stat().st_size}' for f in new), encoding='utf-8')
        print(f'frozen {len(new)} stubs into {BASELINE}')
        return 0

    base = sorted(BASELINE.glob('*.bin'))
    if not base:
        print('no baseline; run with --freeze first', file=sys.stderr)
        return 2

    base_map = {f.name: digest(f) for f in base}
    new_map = {f.name: digest(f) for f in new}

    missing = sorted(set(base_map) - set(new_map))
    added = sorted(set(new_map) - set(base_map))
    changed = sorted(n for n in set(base_map) & set(new_map) if base_map[n] != new_map[n])

    ok = True
    if missing:
        ok = False
        print(f'REGRESSION missing stubs: {missing}')
    if added:
        print(f'note: new stubs (not in baseline): {added}')
    for n in changed:
        b = (BASELINE / n).read_bytes()
        c = (CHECK / n).read_bytes()
        diff = [i for i in range(min(len(b), len(c))) if b[i] != c[i]]
        print(f'REGRESSION {n}: {len(b)}B -> {len(c)}B, {len(diff)} bytes differ '
              f'at {[hex(i) for i in diff[:8]]}')
        ok = False

    print(f'{"PASS" if ok else "FAIL"}: {len(new)} stubs compared, '
          f'{len(changed)} changed, {len(missing)} missing')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
