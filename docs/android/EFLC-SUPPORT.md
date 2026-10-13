# Episodes from Liberty City: compatibility investigation

Status: **blocked on the user's disc executable and file layout; no working EFLC build yet**.
Reviewed against Android v0.5.9 and Thor source commit 79a10df3083264cf6d9ee2bf8cf6a51f034149bc on 2026-10-13.

## Confirmed source constraints

The reported source has Media ID `06759F9C`, region-free flags and XEX version `0.0.0.10`.
Only its installer screenshot is available. The actual disc and executable have not been supplied.
There are no game executables in the checked-out `gta4-recomp/assets` directory.

| Layer | Active source | Compatibility constraint |
| --- | --- | --- |
| Disc inspection | `gta4-recomp/src/install/gta4_source_inspector.cpp` | Requires Media ID `6AC07221`, exact NTSC-U flags, retail version 5, expected signature and full-file XXH3. |
| Installation / launch validation | `gta4-recomp/src/install/gta4_installer.cpp` | Base/update signatures and versions must match the pinned TU8 pair. Installed executable is revalidated. |
| Code generation | `gta4-recomp/gta4_manifest.toml` | Translates `assets/default_v8.xex`, rather than whichever executable the user selects at runtime. |
| CPU execution | `gta4-recomp/generated/gta4_init.h`, `gta4_register.cpp` | Fixed code range and address-to-native-function mapping. |
| Episodes | Installer `FindDlcPayloadRoot`, frontend and font hooks | Episode data can be mounted under the existing GTA IV program; that does not establish standalone EFLC executable compatibility. |
| Saves | `gta4-recomp/src/gta4_quicksave_hooks.cpp` | Fixed guest addresses for episode state, scripts, player table and save transactions; episode-specific script profiles. Must be validated against any replacement program. |
| Renderer/input/streaming | Title hooks and `src/graphics/gta4_native` | Guest addresses, object layouts and game-function hooks require comparison against the actual alternate executable. |
| Thor build | `os/android/scripts/build_thor_cloud.sh` | Retains the original `libmain.so` and runtime, rebuilding the GPU plugin only. Standalone alternate executable support cannot be achieved by a GPU-only rebuild. |

These are findings from the compatibility-related active build paths. This is not a claim that every generated instruction or every vendored dependency has been reviewed.

Removing the first rejection or changing the accepted ID would not address the other constraints.
No compatibility guards have been removed and no experimental game APK is labeled EFLC-compatible.

## Obtain evidence on Android without a PC

Open `tools/eflc-inspect.html` in a browser that executes local HTML, select the user's own ISO,
press **Maak onderzoeksbestand**, then download **EFLC-onderzoek.zip**.
The page uses the same five known partition offsets and GDFX directory entry structure as the
SDK's `src/filesystem/devices/disc_image_device.cpp`. It reads bounded file slices, checks offsets,
blocks directory cycles and unsafe paths, and never reads the entire ISO into memory.
Network access is blocked by Content Security Policy; nothing is uploaded automatically.
The ZIP contains the disc file list, original XEX/XEXP files (maximum 64 MiB each, 128 MiB combined)
and small episode marker files where present. SHA-256 is recorded when Web Crypto is available.
Some Android file viewers show HTML as text instead of executing it: use a browser in that case.
Browser operation on the user's Thor has not yet been tested.

The user must send the resulting ZIP back for the investigation to continue. The screenshot,
filename or Media ID alone is insufficient to generate compatible game code.

## Next implementation gates

1. Verify the supplied executable metadata, disc layout and episode payloads.
2. Load/decode the alternate executable with the existing XEX tooling and compare its code and data
   layout against the pinned program. Determine whether executable translation and hook migration
   are required, or whether a validated asset-import route is feasible. Do not assume either result.
3. Implement the established route with separate revision-specific validation; update installer,
   launch mapping, assets and save profiles as needed. Build the actual title library if changed.
4. Verify packaging, hooks and save paths. Test on Thor: both episode intros, gameplay, audio,
   manual save, app close/reopen/load, autosave, episode switching and representative frame times.

Until these gates pass, neither functional support nor stable 60 FPS is established.

## Helper checks

Run `node tools/test_eflc_inspect.cjs`. Tests use synthetic discs with multiple executables,
all partition offsets, a virtual 8 GiB image, malformed trees and out-of-bounds data.
The emitted test ZIP can be checked with Python's `zipfile` to verify CRCs, paths and payloads.
