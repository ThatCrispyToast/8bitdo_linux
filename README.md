# 8bitdo-cfg

Configure the 8BitDo Retro 87 keyboard and Retro R8 mouse on Linux.

<p align="center">
  <img src="docs/screenshot-keyboard.png" width="49%" alt="Keyboard">
  <img src="docs/screenshot-mouse.png" width="49%" alt="Mouse">
</p>

## Quickstart

```sh
# Install
uv tool install git+https://github.com/ThatCrispyToast/8bitdo_linux

# Allow access without root (skipped if a udev rule, e.g. Steam's, already does)
8bitdo-cfg udev --install

# Open the web UI
8bitdo-cfg ui
```

## Features

- Key remapping, including the red A/B keys and Super Buttons
- Keyboard and mouse macros
- Mouse DPI, polling rate, lift-off, wheel and 250+ button functions
- JSON backup and restore
- Web UI and CLI

## Supported Devices

| Device | USB ID | Status |
| --- | --- | --- |
| Retro 87 keyboard | `2dc8:5200` | Supported |
| Retro 87 receiver | `2dc8:5201` | Untested |
| Retro R8 mouse | `2dc8:5205` | Supported |
| Retro R8 adapter | `2dc8:5206` | Unsupported |

## Installation

**uv:** `uv tool install git+https://github.com/ThatCrispyToast/8bitdo_linux`

**pipx:** `pipx install git+https://github.com/ThatCrispyToast/8bitdo_linux`

**Nix:** `nix run github:ThatCrispyToast/8bitdo_linux -- ui`

**udev rule** (needed for all of the above): `8bitdo-cfg udev --install`, or
`nix run github:ThatCrispyToast/8bitdo_linux -- udev --install`. It uses sudo,
and does nothing if a rule (e.g. Steam's) already grants access.

**NixOS:** installs the tool and udev rule.

```nix
inputs.eightbitdo.url = "github:ThatCrispyToast/8bitdo_linux";
# nixosSystem modules:
[ eightbitdo.nixosModules.default { hardware.eightbitdo.enable = true; } ]
```

## Usage

```sh
# Web UI
8bitdo-cfg ui                                                 # http://127.0.0.1:8765

# Keyboard
8bitdo-cfg keyboard show                                      # remaps, macros and settings
8bitdo-cfg keyboard map caps_lock left_ctrl                   # Caps Lock acts as Ctrl
8bitdo-cfg keyboard map scroll_lock media:play_pause          # a key as a media key
8bitdo-cfg keyboard map k1 mouse:left                         # Super Button as left click
8bitdo-cfg keyboard map f12 shift+f12                         # a key as a combo
8bitdo-cfg keyboard macro f24 tap:ctrl+c delay:50 tap:ctrl+v  # copy, wait 50 ms, paste
8bitdo-cfg keyboard unmap caps_lock                           # back to default

# Mouse
8bitdo-cfg mouse show                                         # DPI, rate, buttons and macros
8bitdo-cfg mouse dpi 400 800 1600 3200 6400 12800             # the six DPI slots
8bitdo-cfg mouse rate 1000                                    # polling rate in Hz
8bitdo-cfg mouse button side_back play_pause                  # any of 250+ functions
8bitdo-cfg mouse macro side_front click:left click:left       # double click

# Backup and restore
8bitdo-cfg keyboard dump > keyboard.json                      # save to JSON
8bitdo-cfg keyboard apply keyboard.json                       # write it back
8bitdo-cfg mouse dump > mouse.json                            # same for the mouse

# Name lists
8bitdo-cfg keyboard keys                                      # key names
8bitdo-cfg keyboard targets                                   # remap targets
8bitdo-cfg mouse functions                                    # button functions
```

All commands, macro steps and key names @ [docs/USAGE.md](docs/USAGE.md)

## Development

```sh
git clone https://github.com/ThatCrispyToast/8bitdo_linux && cd 8bitdo_linux
python3 -m eightbitdo list                       # run from the checkout, no install
python3 -m unittest discover -s tests            # offline, against fake devices
python3 -m eightbitdo.server --export demo.html  # UI with sample data, no devices
nix develop                                      # shell with Python and pytest
nix build                                        # package, runs the tests
```

### Layout

| Path | Contents |
| --- | --- |
| `eightbitdo/hidraw.py` | Device discovery (sysfs) and hidraw I/O |
| `eightbitdo/retro87.py` | Keyboard protocol |
| `eightbitdo/r8mouse.py` | Mouse protocol |
| `eightbitdo/usage_tables.py` | Key, media and button-function names |
| `eightbitdo/cli.py` | Command line |
| `eightbitdo/server.py`, `eightbitdo/ui/` | Web UI: JSON API and single-file front end |
| `eightbitdo/udev/` | udev rule |
| `tests/` | Unit tests; `fake_hid.py` emulates both devices |
| `tools/reverse/` | Scripts for re-deriving the protocol |

### Guidelines

- Standard library only; no runtime dependencies.
- New commands should follow [Protocol](docs/PROTOCOL.md) or a fresh
  [decompile](docs/REVERSE_ENGINEERING.md), ideally get a test
  that pins the exact packet.

## License

MIT. Bundled fonts are SIL OFL. Not affiliated with 8BitDo.
