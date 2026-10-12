# RA3MT — Modern Red Alert 3 Trainer

A modern rebuild of Ken22265's FINAL3 trainer (2009, EA retail 1.12, 31 features):
**C# / .NET 10 + WPF**, supports **1.12 and 1.13 (2024 Ultimate Collection)**,
33 features, four game-thread bridge architecture.

[English](README.md) | [简体中文](README-zh_CN.md)

> Single-player only; does not work in online multiplayer. For educational
> research purposes.

## Current release v20 (2026-10-12)

- **Verified in-game**: infinite money/power/protocol points, unlock all
  protocols, fast build, reveal map, rank bridge (multi-target), capture
  bridge, spawn bridge (three MCVs / copy selection / arbitrary-hash
  reinforcements), **build anywhere** (FINAL3-equivalent 2-byte branch
  patch — placing on grey cells verified live)
- **New in v20, pending live test**: destroy v3 — the kill bridge now routes
  through the game's FULL damage entry (FINAL3's exact call), so the death
  decision, animation dispatch and model recycling run inside the game's own
  pipeline (previously a bottom-level HP write with no death animation)
- **Behavior-level audit against FINAL3 complete**: all 31 features compared;
  4 remain to port (forbid AI building / player god mode / one-hit kills /
  direct three-star rank-up), roadmap in docs/NOTES.md v19c

## Build

- Requires .NET 10 SDK + Windows Desktop runtime
- `dotnet build RA3MT.slnx -c Release`
- Publish: `dotnet publish src/RA3MT.UI -c Release -r win-x86 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o publish-vN`
  (in Git Bash use `-p:` not `/p:`; version numbers are plain increasing
  integers since v19)
- Output is **x86** and requires admin (manifest) — mandatory for writing a
  32-bit game process

## Project layout

```
assets/features.json      All data: 33 feature definitions + 21 hook sites
                          (per-version RVA, displaced bytes, AOB patterns)
                          + globals / feature-private offsets (embedded resource)
src/RA3MT.Core            Layered engine (see docs/ARCHITECTURE.md):
                          Abstractions (feature contracts) / Host (capability
                          services) / feature folders (one class per feature) /
                          Engine (attach, hooks, block layout, bridges, API
                          resolvers with byte contracts)
src/RA3MT.SelfCheck       13 offline suites (hook bytes / action writes /
                          install recovery / asm boundaries / selection chain /
                          bridge mailboxes / spawn contracts / feature catalog /
                          block layout / resolvers)
src/RA3MT.UI              WPF app (metadata-driven cards, MVVM, global hotkeys)
tools/harness/            Unicorn stub-execution suites + stub baseline
                          regression (baseline in artifacts/baseline_stubs)
tools/analysis/           Resident reverse-engineering tools (trampoline
                          tracer, .text diff monitor, temporary-patch test
                          template, FINAL3 extractor, features generators);
                          exploration scripts are deleted once their
                          conclusions land in NOTES
docs/NOTES.md             Reverse-engineering notes — the primary knowledge
                          base: locating process, contracts, lessons learned
docs/ARCHITECTURE.md      Layering and extension guide after the M1–M7 refactor
docs/FINAL3_*.md          FINAL3 teardown and cross-reference audit (historical
                          deliverables; NOTES supersedes their conclusions)
artifacts/final3/         All 13 FINAL3 CE scripts (.cea) + manifest
```

## Verification (run all on every change)

```
Hook sites   42/42 (byte-level, 1.12 + 1.13)
SelfCheck    13 suites green (actiontest 24 / installertest 132 / bridgetest 30
             / spawntest 46 / featuretest 101 / layouttest 14 / ranktest /
             selectiontest / asmtest / resolvertest …)
Unicorn      stub execution 197+197 / bridge dispatch 60+218+20 / stub
             baseline regression 28 stubs, zero drift
```

## Usage

1. Launch RA3 via Steam (main menu is enough), run the trainer as admin
2. Attach: every displaced instruction is byte-verified; any mismatch refuses
   the hook (fail-closed). The three game-thread bridges (rank /
   capture+destroy / spawn) are on by default; set RA3MT_RANK_BRIDGE=0,
   RA3MT_BRIDGES=0 or RA3MT_SPAWN=0 to disable one for troubleshooting
3. Toggles = MasterCode flag bytes (stubs run on the game thread) or pure
   byte patches (build anywhere); actions = selection-chain walks or
   game-thread bridges
4. Detach restores every original byte (including the build-anywhere patch)

## Technical notes

- Game is 32-bit, ImageBase 0x400000, no ASLR; the repacked builds are
  region-shifted vs EA retail, so FINAL3's absolute addresses do not apply —
  every RVA is re-located by byte contracts on both builds with
  tamper-refusing verification
- **Four-bridge architecture**: the money/power settlement sites are the
  game-thread entry; each bridge has its own mailbox (payload published
  first, state last — atomic claim), so cross-thread calls into game
  functions always execute on the game thread
- **Build-anywhere patch**: the placement gate's "out of range → failure
  code" branch, `75 0C → EB 0C` (EA 0x4E7565 ↔ 1.13 0x511955 ↔ 1.12
  0x528DF5, identical bytes in all three; the gate is shared by player
  placement and AI site-picking)
- Site-location ironclad rule: a static address must be confirmed live via a
  trampoline before patching; VA/RVA differ by 0x400000 — check the
  convention before reusing any address from the notes (three historical
  misdiagnoses trace back to this, see NOTES v18o)
- Semantic counterparts of legacy EA addresses are located by **instruction
  signatures + structural isomorphism** — a runnable reference beats
  reasoning (FINAL3 on a pirated 1.12 is the ground truth)

## Feature status at a glance

| Group | Features | Status |
|---|---|---|
| Resources | money / power / protocol points / unlock protocols | ✅ verified |
| Build | fast build / instant ready / freeze enemy skills / unlimited zoom | ✅ stubbed (instant/freeze pending re-test) |
| Vision | reveal map | ✅ verified |
| Selection (14) | 3-star / ammo / XP / speed ×2 / freeze / HP ×3 / heal / capture / destroy / copy | ✅ verified (destroy animation pending in v20) |
| Misc (5) | threat ×3 / ore restore / diagnostics | ✅ verified |
| Reinforcements (5) | three MCVs / arbitrary-hash spawn / build anywhere | ✅ verified |
| FINAL3 gaps | forbid AI building / god mode / one-hit kills / direct 3-star | ⏳ located, to port (NOTES v19c) |

Original author: Ken22265 (FINAL3, 2009). This project is a modern rebuild
and extension of its features.
