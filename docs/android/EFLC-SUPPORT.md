# Episodes from Liberty City: compatibility investigation

Status: **private ARM64 EFLC start-test APK built and signed; gameplay, saving, rendering and frame times remain unverified on Thor**.
Reviewed against Android v0.5.9 and Thor source commit 79a10df3083264cf6d9ee2bf8cf6a51f034149bc on 2026-10-13.

## Confirmed source constraints

The reported source has Media ID `06759F9C`, region-free flags and XEX version `0.0.0.10`.
The user supplied an inspection ZIP containing the complete 12,861,440-byte executable and a
300-entry disc inventory. Its SHA-256 was recomputed and agrees with the report:
`590accf1a74b70ff3b4181090367fe702aa6a7a12059a04414d55c8ca514a140`.
The image decodes successfully using the existing loader's AES/basic-compression algorithm.
It has base `82000000`, entrypoint `82A10E90` and code range `82140000`–`82A85F5C`.
The existing GTA IV generated code ends at `82A8635C`. Sharing a base address is insufficient.
The updated 126,284,317-byte asset evidence ZIP has also been supplied. It contains the four requested RPF archives, both episode script archives and update shaders; the full world/audio data remains on the user's ISO.

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
The original GTA IV installation path remains separate. The new experimental EFLC installer accepts only the inspected executable SHA-256; packaging is not proof of gameplay compatibility.

## Executable translation and hook comparison

The [SDK 0.9.0 release](https://github.com/rexglue/rexglue-sdk/releases/tag/v0.9.0) was used
to analyze the supplied executable. The first unconfigured analysis found five unresolved tail-call
targets. The executable was disassembled at those locations; two also contain embedded switch
tables. `tools/eflc_codegen/eflc_config.toml` records the explicit code ranges and verified table
labels. `tools/stage_eflc_codegen.py` enforces the exact input SHA-256 and stages inputs outside
this public repository. Its strict run does not use `--force` to ignore analysis errors.

The strict generated CPU code was compiled into a separate ARM64 `libmain.so` with 89 compilation units and a successful no-undefined-symbol link. The host uses the generic `xenos` renderer. GTA IV TU8 title hooks are not registered; this does not complete their EFLC migration or establish working gameplay.
No user executable, decoded image, game-derived generated source or game assets are published
to the repository by these tools.

`tools/audit_eflc_xex.py` compares the first 24 instruction comments of the original title hooks
against the generated alternate executable. It found 525 address-specific hook functions:

| Comparison result | Count |
| --- | ---: |
| Unique candidate with instruction shape matching after masking all immediates | 402 |
| Multiple candidates | 34 |
| No candidate / insufficient prefix | 89 |
| Identical raw 24-instruction prefix at the original hook address | 0 |

These are **unvalidated candidates**. Masking all immediates also masks semantic constants;
an apparently unique prefix is not evidence that the complete function, calling convention,
structure layouts or data globals are equivalent. No candidates are automatically applied.
See `eflc-executable-audit.json` for reproducible metadata and the full candidate list.

In particular, the original quicksave hook `82846AE8` matches a candidate at `82846648`, and
`828453F8` matches one at `828450C8`. At the old addresses the supplied executable contains
different instructions. Save transaction globals and phone script digests still need validation.

## Obtain evidence on Android without a PC

Open `tools/eflc-inspect.html` in a browser that executes local HTML, select the user's own ISO,
press **Maak onderzoeksbestand**, then download **EFLC-onderzoek.zip**.
The page uses the same five known partition offsets and GDFX directory entry structure as the
SDK's `src/filesystem/devices/disc_image_device.cpp`. It reads bounded file slices, checks offsets,
blocks directory cycles and unsafe paths, and never reads the entire ISO into memory.
Network access is blocked by Content Security Policy; nothing is uploaded automatically.
The updated helper enables **Ook episode-, script- en shaderbestanden meenemen** by default.
It includes `common.rpf`, `xbox360.rpf`, both `DLC.rpf` files, both episode `script.img` files
and the small `update/shaders` files, alongside the executable and disc inventory. For the user's
inventory the payload is 126,239,310 bytes (about 120.4 MiB), excluding the small ZIP/report overhead.
The full ISO and large audio/map/texture archives are not included. The result is named
`EFLC-assets-onderzoek.zip`. The executable-only mode is still available by clearing the checkbox.
Files are bounded at 64 MiB each and 128 MiB combined. SHA-256 is recorded for executables when Web Crypto is available.
Some Android file viewers show HTML as text instead of executing it: use a browser in that case.
Browser operation on the user's Thor has not yet been tested.

Both helper modes have now produced evidence on the user's Thor. The four RPF tables and both script IMG tables were decoded. TBoGT spcellphonemain code matches the existing profile digest, while TLAD differs. No unverified TLAD phone offsets or quicksave hooks were applied.

## Next implementation gates

1. Completed: receive the asset ZIP, decode the two script archives and four RPF tables, generate and compile the exact EFLC executable, and package a signed start-test APK.
2. Validate each necessary function/global mapping, calling convention and renderer structure.
   Resolve the ambiguous/missing candidates. Validate phone/SCO script profiles against disc data.
3. Implement a separate executable-specific route with revision-specific validation; update installer,
   launch mapping, assets and save profiles as needed. Build the actual title library if changed.
4. Verify packaging, hooks and save paths. Test on Thor: both episode intros, gameplay, audio,
   manual save, app close/reopen/load, autosave, episode switching and representative frame times.

Until these gates pass, neither functional support nor stable 60 FPS is established.

## Helper checks

Run `node tools/test_eflc_inspect.cjs` (18 checks) and
`python -m unittest discover -s tools -p test_audit_eflc_xex.py -v` (7 checks).
Tests use synthetic discs with multiple executables,
all partition offsets, a virtual 8 GiB image, malformed trees and out-of-bounds data.
The emitted test ZIPs are checked with Python's `zipfile` for CRCs, paths and payloads.
The decoder tests cover continuous AES chaining across blocks, bounds checks and PE/XEX consistency.

## Private start-test build

`tools/build_eflc_native_local.py` compiles generated code stored outside the repository with NDK r29, retaining the pinned original runtime libraries. `tools/package_eflc_local.py` packages Java/SDL code with Android build-tools 35.0.0, JDK 17 and the checksum-verified v0.5.9 APK resources/libraries. The generated game source, executable, game assets, APK and signing key are not published to GitHub.

The package is `com.libertyrecomp.eflctest`, version `0.5.9-eflc-start-test.2`. The installer copies the user's own disc using bounded reads, validates the exact executable, and commits staged game files only after validation. It requires additional free space for the extracted disc. Save data lives outside the replaceable game directory in the separate application's EFLC/saves folder. These paths and synthetic preservation tests do not prove game-level saving works.

Verified: 14 synthetic installer checks, all Java compilation, native linking, APK ZIP CRCs, matching staged libmain checksum, ARM64/launcher metadata and apksigner signature verification. No disc executable/RPF/IMG/SCO assets are bundled.

APK SHA-256: `29f69d8f4f152fc3b158a32530dc0501933afbd184e9a52ae44f88009b8a4435` (44,129,060 bytes).

Thor acceptance is still required: launch both episodes, verify picture/audio/controller behavior, save normally, fully close/reopen the app and load the save. On failure, use **Exporteer debuglog**. Stable 60 FPS and sharp rendering remain unestablished.

### Installation packaging correction (test.2)

The first manual package incorrectly compressed resources.arsc. Android 11+ rejects compressed or non-4-byte-aligned resource tables for target API 30+. Signature verification alone did not detect this. The corrected packager preserves aapt2 ZIP storage metadata, retains the signing key/package ID, increments versionCode to 20002, and checks final APK table compression, actual local-entry data offset, ZIP CRCs and zipalign. This is a packaging fix only; Thor gameplay acceptance is still pending.
