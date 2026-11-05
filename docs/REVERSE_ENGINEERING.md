# How the protocol was derived (and how to do it again)

Everything in `docs/PROTOCOL.md` came from 8BitDo Ultimate Software V2 for Windows,
v1.35 (`resources/8BitDo_Ultimate_Software_V2_Windows_V1.35.zip`), and was then
confirmed on real hardware. The decompiled sources are 8BitDo's code, so they are
not in the repository and must not be committed; this page regenerates them in
about 15 minutes.
Scripts live in `tools/reverse/`.

## 1. Unpack the app

```
unzip resources/8BitDo_Ultimate_Software_V2_Windows_V1.35.zip -d $SCRATCH/sw
cd "$SCRATCH/sw/8BitDo_Ultimate_Software_V2_Windows_V1.35"
```

`8BitDo Ultimate Software V2.exe` (218 MB) is a .NET single-file bundle. Extract it:

```
python3 tools/reverse/bundle_extract.py "8BitDo Ultimate Software V2.exe" $SCRATCH/bundle
```

That yields `8BitDo Ultimate Software V2.dll` (the WPF app, 100 MB, mostly images) and
`GenericHid.dll` among framework assemblies. `8BitDoAdvance.dll` next to the exe is a
**native** 32-bit MFC debug build (with `.msvcjmc`) that builds every HID packet; the
C# only shapes buffers and P/Invokes it. `RTKHIDKit.dll` is Realtek's HID DFU kit (used
for mouse firmware updates), `dfu4.exe` reads the keyboard firmware version.

## 2. Decompile the C# (ilspycmd)

```
nix-shell -p ilspycmd --run "ilspycmd -p -o $SCRATCH/src/App '$SCRATCH/bundle/8BitDo Ultimate Software V2.dll'"
```

Where to look (namespace `AdvanceSuper`):

- `Hid/VIDPID.cs` - every product ID. In the app's vocabulary **JP = keyboard**
  (`PID_JP` 0x5200, `PID_JPUSB` 0x5201 receiver), **Mouse = Retro R8** (0x5205, `MouseRR`
  0x5206 receiver), `RR` = 2.4 GHz receiver, `Advance` = the settings feature.
- `Hid/HIDManage.cs` - device detection; the mouse version (`01 04 04 01`) and colour
  (`01 06 25 01`) queries are built inline here.
- `Hid/SHid.cs` - the P/Invoke surface into `8BitDoAdvance.dll`.
- `Advances/JPAdvance.cs`, `Advances/MouseAdvance.cs` - the read/write sequences and the
  buffer layouts each native call expects (`MOUSE_*` structs live next to them).
- `AdvancesUI/BasicJPAdvanceUIData.cs`, `AdvancesUI/BasicMouseAdvanceUIData.cs` - the
  `*_MAP` constants (key indices), `Mouse_Enum` (button functions, ordinal = value) and
  the mapping/macro decoders (`getMapping`, `getMacro`, `setMacro`).
- `Tools/KeyBoardTools.cs` - `getuint(...)` (remap value bytes) and `getdata(...)`
  (macro record bytes).
- `Data/LanguageTools.cs` - product names per colour/edition.

## 3. Decompile the native DLL (Ghidra headless)

```
python3 tools/reverse/pe_exports.py 8BitDoAdvance.dll > $SCRATCH/exports.txt
AH=$(nix-shell -p ghidra-bin --run 'echo $(dirname $(readlink -f $(command -v ghidra)))/../lib/ghidra/support/analyzeHeadless')
MAXMEM=8G nix-shell -p ghidra-bin --run "$AH $SCRATCH/proj adv -import 8BitDoAdvance.dll \
    -scriptPath tools/reverse -postScript DecompExports.java $SCRATCH/dump.c 4 4000 -max-cpu 16"
python3 tools/reverse/rename_dump.py 8BitDoAdvance.dll $SCRATCH/exports.txt $SCRATCH/dump.c $SCRATCH/named.c
python3 tools/reverse/fnview.py $SCRATCH/named.c WriteHidJP GetMappingValue WriteDpi FUN_10408c40
```

Notes:

- Analysis of the 9 MB DLL takes a few minutes; re-run the script on the saved project
  with `-process 8BitDoAdvance.dll -noanalysis` instead of `-import`.
- The exports are `jmp` stubs (incremental linking), so Ghidra names the real bodies
  `FUN_<addr>`; `rename_dump.py` maps both stub and target to the export name so call
  sites read naturally. `DecompExports.java` seeds from the exports and follows callees
  (`SEED_NAMED=1` also seeds every named function, which is mostly MFC noise).
- `fnview.py` strips the debug-build boilerplate (JMC checks, `0xcccccccc` fills, RTC).
- Ghidra writes `~/.config/ghidra` and `/var/tmp/<user>-ghidra`; delete them afterwards.

Functions that define the protocol: keyboard `WriteHidJP` / `ReadHidJP` (report IDs
0x52 / 0x54), `Get*` (0x80-0x89), `SetMapping` / `SetShortCut` / `SetMouse` (0xFA wrapper),
`writeName` (0x70), `writeMacroName` (0x74), `writeMacroJP` (0x76), `ClearMacro` (0x77),
`SetFeature` (0x78), `setVoice` (0x79), `SwitchReport` (0x76 with key 0xFF); mouse
`FUN_10408c40` (send: `[1, class, cmd, op, payload]`) and `FUN_1040c710` (receive and
validate), then `ReadProfile` / `WriteProfile`, `ReadMapKey` / `WriteMapKey`, `Read*` /
`Write*` for lod, wheel, DPI, rate, macros, `ClearProfile`; `Open_MouseHid` shows how the
receiver's `0xFF0B`/`0x0104` collection is selected.

## 4. Verify on hardware

Every command was exercised with a reversible round-trip (write, read back, restore)
using scratch targets that do not disturb normal use: the keyboard's `scroll_lock` key and
a benign remap of a mouse side button. Findings that only hardware revealed: the mouse
only commits a profile name when both 10-byte chunks are written; the keyboard stores a
macro's repeat interval as a trailing delay record that `count` includes; and the mouse
button table is bigger than the app knows (below).

### Which table entry drives which input

A read-back proves that a write landed, not what the entry controls. The app's own
`ReadMapKey` loop (positions 1..6, index byte ignored) turned out to hide two things:
positions 5/6 are the right-side buttons ("R4"/"R5" in `Mouse_Enum_Index`), shipped with
function 255 = disabled, and positions 7/8 are the wheel's two directions, which the app
never reads. To map an entry to a physical input:

1. Write a distinctive test function to the entries in question with
   `R8Mouse.set_button` - a keyboard key (F13 = 241, F14 = 242) or a horizontal scroll
   (34/35) shows up unmistakably and does nothing harmful.
2. Run `python3 tools/reverse/hid_capture.py 120 /dev/hidraw0 /dev/hidraw1` (mouse
   interface 0 and keyboard interface 1 of the R8; `8bitdo-cfg list` shows the nodes) and
   have the owner press each input once with a pause in between.
3. Decode: iface 0 `[1, buttons, x, x, y, y, wheel, pan]`, iface 1 `[1, mods, 0, usages]`.
4. Restore the original functions in the same session.

That is how the entries were assigned and how the two wheel functions were found to be
named backwards in the app (`WHEEL_UP` = 32 sends wheel -1). The full evidence table is
in `docs/PROTOCOL.md`.

## Ideas not done

- 2.4 GHz receiver support for both devices (PIDs 0x5201 / 0x5206).
- Other 8BitDo devices: `VIDPID.cs` lists ~60 product IDs; the "Advance" read/write
  functions for each model (`writeUltimate2`, `readXboxJP`, ...) are all in the same DLL.
- Firmware updates (`dfu4.exe` for the keyboard, RTKHIDKit CFU for the mouse).
