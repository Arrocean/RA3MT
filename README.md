# RA3MT — Red Alert 3 Modern Trainer

[English](README.md) | [简体中文](README-zh_CN.md)

A modern rebuild of Ken22265's FINAL3 trainer (2009, EA retail 1.12, 31 features):
**C# / .NET 10 + WPF**. All 31 FINAL3 features are ported at parity and
live-tested; the trainer ships **34 features** on the four game-thread bridge
architecture. UI curated by WhiteSprite.

**One trainer, three game builds (auto-detected at attach):**

| Build | Notes |
|---|---|
| Steam Ultimate Collection **1.13** | primary live-test platform |
| Steam Ultimate Collection **1.12** | same byte-level verification |
| **EA retail 1.12** | classic retail layout (FINAL3's native target), since v261013-2 |

> Single-player only; does not work in online multiplayer. For educational
> research purposes.

## Current release v261013-9 (2026-10-13)

Version scheme: `vYYMMDD-N` (date + sequence of that day). The distribution
artifact is a **single-file exe**: `Red Alert 3 Modern Trainer v<version>.exe`
(~58 MB, x86, embedded icon, **no sidecar files**).

Recent highlights (details in docs/NOTES.md, v261013 section):

- **Built-in reinforcement table**: 125 common units (Allies 36 / Soviets 40 /
  Empire 42 / neutral fun crates 7) with Traditional-Chinese display names and
  a searchable picker (📋 on the reinforcement card). Extracted automatically
  from the game's own archives and cross-checked against live-verified codes;
  raw hex codes and internal unit names still work
- **WeMod-style single button**: "Start Game" launches the game and attaches
  as soon as the process appears; attaches immediately when the game already
  runs; cancellable while waiting
- The four game-thread bridges (rank / capture+destroy / spawn) are **on by
  default**; disable individually for troubleshooting via
  `RA3MT_RANK_BRIDGE=0`, `RA3MT_BRIDGES=0`, `RA3MT_SPAWN=0`
- Stale single-file extraction caches in %TEMP% are cleaned at startup, so
  releases no longer accumulate disk usage
- 7 user-facing groups, 34 player-oriented descriptions, date versioning,
  application icon

## Build

- Requires .NET 10 SDK + Windows Desktop runtime
- `dotnet build RA3MT.slnx -c Release`
- Publish: `dotnet publish src/RA3MT.UI -c Release -r win-x86 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o publish-v<version>`
  (in Git Bash use `-p:` not `/p:`; bump the version string in TWO places each
  release: `MainVM.AppVersion` and the UI csproj `AssemblyName`)
- Output is a single **x86** exe and requires admin (manifest) — mandatory
  for writing a 32-bit game process

## Project layout

```
assets/features.json             Hand-maintained source data: 34 features +
                                 26 hook sites (per-build RVA, displaced bytes,
                                 AOB patterns) + globals / feature-private
                                 offsets (embedded resource)
assets/reinforcement_codes.json  Built-in unit code table (generated from the
                                 game files by gen_reinforce_table.py)
src/RA3MT.Core                   Layered engine (see docs/ARCHITECTURE.md):
                                 Model (data shapes + ISymbols) / Target (byte-
                                 contract resolvers) / Engine (MasterCode
                                 lifecycle, StubGen stub factory, four bridge
                                 dispatchers) / Features (FeatureCatalog
                                 registration, 34 feature implementations,
                                 BridgeCoordinator, TrainerEngine orchestrator)
src/RA3MT.SelfCheck              12 offline suites + stubdump + livetest
                                 (read-only live verification)
src/RA3MT.UI                     WPF app (metadata-driven cards, one-button
                                 start+attach, reinforcement picker)
tools/harness/                   Unicorn stub-execution suites + stub baseline
                                 regression (baseline in artifacts/baseline_stubs)
tools/analysis/                  Resident reverse-engineering tools (trampoline
                                 tracer, .text diff, FINAL3 extractor,
                                 reinforcement-table generator — 7 items);
                                 exploration scripts are deleted once their
                                 conclusions land in NOTES
docs/NOTES.md                    Reverse-engineering notes — the primary
                                 knowledge base
docs/ARCHITECTURE.md             Layering and extension guide (including which
                                 data is hand-maintained vs generated)
docs/FINAL3_*.md                 FINAL3 teardown and cross-reference audit
                                 (historical deliverables; NOTES supersedes)
artifacts/final3/                All 13 FINAL3 CE scripts (.cea) + manifest
```

## Verification (run all on every change)

```
Hook sites   78/78 (byte-level displaced check, 1.12 + 1.13 + EA 1.12)
SelfCheck    12 suites green (featuretest 108 / installertest 162 /
             actiontest 24 / bridgetest / ranktest / spawntest 69 /
             selectiontest / layouttest / rankmailboxtest / asmtest /
             resolvertest / reinforcetest)
livetest     read-only live verification against the running game (build
             classification + all hooks + four bridges, no hooks installed)
Stub gate    33 stubs byte-identical (py tools/harness/stub_regression.py)
Unicorn      Python-side stub semantic suites (tools/harness/)
```

## Usage

1. Run the single-file exe as admin; click "Start Game" — the Steam build is
   launched via Steam and attached automatically; for the EA retail build,
   start the game yourself and click (it attaches the same way)
2. Attach auto-detects the build (Steam and EA 1.12 share the module name;
   a 14-byte in-memory fingerprint discriminates them) and byte-verifies
   every displaced instruction — any mismatch refuses the hook (fail-closed)
3. Toggles = MasterCode flag bytes (stubs run on the game thread) or pure
   byte patches (build anywhere); actions = selection-chain walks or
   game-thread bridges
4. Detach restores every original byte (including the build-anywhere patch)

## Technical notes

- Game is 32-bit, ImageBase 0x400000, no ASLR; the three builds are
  region-shifted against each other, so every RVA is re-located by byte
  contracts on its own image with tamper-refusing verification —
  **onboarding a new build = one resolver row + one features.json key,
  zero code forks** (EA 1.12 was added exactly this way)
- Same-name dual builds: `ra3_1.12.game` is the module of both the Steam
  repack and EA retail; a dual-anchor memory fingerprint classifies them,
  and a misclassification still fails loudly in the byte verifier
- **Four-bridge architecture**: the money/power settlement sites are the
  game-thread entry; each bridge has its own mailbox (payload published
  first, state last — atomic claim), so cross-thread calls into game
  functions always execute on the game thread
- **Build-anywhere patch**: the placement gate's "out of range → failure
  code" branch, `75 0C → EB 0C` (EA 0x4E7565 ↔ 1.13 0x511955 ↔ 1.12
  0x528DF5, identical bytes in all three; the gate is shared by player
  placement and AI site-picking)
- **Reinforcement code = WB string hash**: the game's own archives
  (WBStringHashes.big / Core*.big / language packs) yield the complete
  unit→code table programmatically — no manual unpacking
- Site-location ironclad rule: a static address must be confirmed live via
  a trampoline before patching; VA/RVA differ by 0x400000 — check the
  convention before reusing any address from the notes (three historical
  misdiagnoses trace back to this, see NOTES v18o)
- Semantic counterparts of legacy EA addresses are located by **instruction
  signatures + structural isomorphism** — a runnable reference beats
  reasoning (FINAL3 on a pirated 1.12 is the ground truth)

## Feature status at a glance (34 / 7 groups)

| Group | Features | Status |
|---|---|---|
| Resources (4) | money / power / protocol points / unlock protocols | ✅ verified |
| Build & production (3) | fast build / build anywhere / forbid AI building | ✅ verified |
| Combat (4) | god mode / one-hit kills / freeze enemy skills / instant ready | ✅ verified |
| Vision & camera (2) | reveal map / unlimited zoom | ✅ verified |
| Selection (13) | 3-star / ammo / speed ×2 / freeze / HP ×3 / heal / capture / destroy / copy … | ✅ verified |
| Reinforcements (4) | three MCVs / reinforcement code (📋 built-in table) | ✅ verified |
| Misc (4) | threat ×3 / ore restore | ✅ verified |

All of the above closed out on Steam 1.13 (FINAL3 31/31 parity + 3
extensions). **EA retail 1.12** landed in v261013-2 with triple-verified
addresses (offline contracts + 78/78 static + livetest); in-game feature
testing is in progress.

Original author: Ken22265 (FINAL3, 2009). This project is a modern rebuild
and extension of its features, by WhiteSprite.
