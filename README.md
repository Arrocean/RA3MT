# RA3MT — Red Alert 3 Modern Trainer

English | [简体中文](README-zh_CN.md)

A modern rebuild and extension of Ken22265's FINAL3 trainer, using **C# / .NET 10 + WPF**, with UI by WhiteSprite. These documents describe **v261025-7**. Versions use `vYYMMDD-N`: date and release sequence for that day.

Select the game in the sidebar. **Red Alert 3 has 34 features and 26 hooks; Uprising has 36 features and 28 hooks.** Each game has its own reinforcement catalog: 125 RA3 entries and 137 Uprising entries.

Single-player research use only; online multiplayer is unsupported. Distributions are listed on [GitHub Releases](https://github.com/Arrocean/RA3MT/releases). A local build does not imply that it has been uploaded there.

## Supported builds and validation

| Game        | Build          | Evidence                                                            |
|-------------|----------------|---------------------------------------------------------------------|
| Red Alert 3 | Steam 1.13     | Primary gameplay validation platform for the original feature set   |
| Red Alert 3 | Steam 1.12     | Independent addresses, byte contracts and offline checks            |
| Red Alert 3 | EA retail 1.12 | Separate retail layout; historical live-resolution checks           |
| Uprising    | EA retail 1.0  | Independent layout/contracts; historical live attach/restore checks |
| Uprising    | Steam 1.0      | Independent fingerprint, static audit and emulated execution        |
| Uprising    | Steam 1.01     | Module `ra3ep1_1.1.game`; historical live attach/restore checks     |

Each Uprising build passes 903 offline execution cases, 2,709 total. The audit also covers 84 hook sites, 63 function/global/layout contracts and 10,302 byte-tamper refusal cases. The user has confirmed that challenge funds work with the refresh procedure below. **Complete gameplay acceptance of all 36 features on all three builds remains pending.** Historical attachment or static validation does not establish every gameplay effect. See [UPRISING.md](docs/UPRISING.md) for evidence and fixes.

## Usage

1. Start the trainer and select Red Alert 3 or Uprising.
2. For Steam, use Start Game to launch and wait for automatic attachment. For EA retail, launch the game yourself, then attach. An already running game can be attached directly.
3. Attachment fingerprints the actual build and checks original instructions. Unknown, ambiguous or modified sites are refused.
4. Game selection is locked while attached or waiting for launch. Detach or cancel waiting before switching.
5. Game exit triggers automatic detachment. Manual detach restores hooks and the build-anywhere patch. Changes already made to game state, such as funds or health, are not all undone by restoring code.

### Uprising challenge features

| Feature                 | Operation                                                                                                                                  |
|-------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| Challenge funds +50,000 | Submit once **during the battle, then press Esc to enter the menu and refresh once for it to take effect**. Hotkey: `Ctrl+Shift+F11`       |
| Extended challenge time | Set the challenge average time to **9999:99**; **press Esc to enter the menu and refresh for it to take effect**. Hotkey: `Ctrl+Shift+F12` |

Funds are a one-shot request consumed by the challenge menu path. A submitted request does not mean the display has already refreshed. Disabling the time feature stops further writes; the current mission's written value remains.

### Feature groups

| Group                         | Count | Features                                                                                    |
|-------------------------------|------:|---------------------------------------------------------------------------------------------|
| Resources                     |     4 | Money, power, protocol points, unlock protocols                                             |
| Build and production          |     3 | Fast build, build anywhere, block AI production                                             |
| Combat                        |     4 | God mode, one-hit kills, freeze enemy skills, instant readiness                             |
| Vision and camera             |     2 | Reveal map, unlimited zoom                                                                  |
| Selection                     |    13 | Rank, ammo, speed/restore, freeze, health, heal, capture, destroy, copy and related actions |
| Reinforcements                |     4 | Three faction MCVs and reinforcement code/picker                                            |
| Miscellaneous                 |     4 | Threat levels and ore restoration                                                           |
| Challenge mode, Uprising only |     2 | Challenge funds and average time                                                            |

The four game-thread bridges—rank, capture, destroy and spawn—are enabled by default. Troubleshooting switches are `RA3MT_RANK_BRIDGE=0`, `RA3MT_BRIDGES=0` and `RA3MT_SPAWN=0`. Actions report unavailable when their required bridge fails validation.

## Build and publish

Requires Windows, the .NET 10 SDK and Windows Desktop build support. Publishing produces an approximately 58 MiB, x86, self-contained executable. It requests administrator access through its manifest and does not require a separately installed .NET runtime.

From the repository root:

```powershell
dotnet build RA3MT.slnx -c Release
dotnet publish src/RA3MT.UI -c Release -r win-x86 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o publish-v261025-7
```

Output: `Red Alert 3 Modern Trainer v261025-7.exe`. Update both `MainVM.AppVersion` and the UI project's `AssemblyName` for a release. Use `-p:` in Git Bash as well.

## Repository and documentation

| Location                                         | Purpose                                                                                                      |
|--------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| `assets/features.json`                           | RA3 features, 26 hooks, three-build addresses and private offsets                                            |
| `assets/uprising.json`                           | Three Uprising profiles, exact contracts and two exclusive features; regeneration preserves feature metadata |
| `assets/*reinforcement_codes.json`               | Separate 125-entry RA3 and 137-entry Uprising catalogs                                                       |
| `src/RA3MT.Core`                                 | Products/layouts, resolvers, injection mechanisms, features and session orchestration                        |
| `src/RA3MT.UI`                                   | WPF UI, game selection, hotkeys and reinforcement picker                                                     |
| `src/RA3MT.SelfCheck`                            | Offline C# checks, machine-code exports and explicit live diagnostics                                        |
| `src/RA3MT.UI.SelfCheck`                         | WPF binding/rendering checks without a game                                                                  |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md)          | Current architecture, data ownership and extension rules                                                     |
| [TOOLS.md](docs/TOOLS.md)                        | Retained tools, dependencies, commands and cleanup inventory                                                 |
| [UPRISING.md](docs/UPRISING.md)                  | Uprising addresses, layout differences, fixes and validation limits                                          |
| [NOTES.md](docs/NOTES.md)                        | Version history, reverse-engineering evidence and corrections                                                |
| `docs/FINAL3_*.md`                               | Historical FINAL3 analysis, retaining its original conclusions                                               |
| `artifacts/final3/`, `artifacts/uprising-final/` | Extracted CE scripts and source manifests                                                                    |
| `artifacts/baseline_stubs/`                      | Current 34-file RA3 machine-code baseline                                                                    |

## Offline checks

```powershell
py -m pip install -r tools/requirements.txt
py tools/harness/run_uprising_audit.py
py tools/harness/stub_regression.py
```

The audit builds the projects, exports each Uprising profile, runs ten suites per profile and checks WPF bindings. It does not open a game process. The baseline gate compares 34 RA3 exports. Choose other checks according to the change; see [TOOLS.md](docs/TOOLS.md) for commands and the boundaries of live diagnostics.

Never regenerate expected bytes or freeze a baseline merely to hide unexplained differences. Establish the instruction, field and control-flow change first.

Original author: Ken22265 (FINAL3, 2009). Modern rebuild and extensions by WhiteSprite.
