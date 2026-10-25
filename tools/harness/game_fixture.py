"""Independent object fixtures for executing the two games' emitted x86.

Set RA3MT_TEST_UPRISING=1 after `SelfCheck uprising-stubdump
artifacts/uprising_stubs` to exercise the Uprising layouts with the same gates.
"""
import os
from pathlib import Path

BUILD = os.environ.get('RA3MT_GAME_BUILD', 'uprising-1.01' if os.environ.get('RA3MT_TEST_UPRISING') == '1' else '1.13')
UPRISING = BUILD.startswith('uprising-')
STUBS = Path(os.environ.get('RA3MT_STUBS_DIR', Path(__file__).resolve().parents[2] /
                          ('artifacts/uprising_stubs' if UPRISING else 'artifacts/stubs_semantic')))
OWNER = 0x428 if UPRISING else 0x418
HEALTH = 0x34C if UPRISING else 0x33C
TRACKER = 0x3DC if UPRISING else 0x3CC
ELIGIBILITY = 0x24D if UPRISING else 0x245
CAPACITY = 0x78 if UPRISING else 0x70
BODY_DRAWABLE = 0xF8 if UPRISING else 0xF4
