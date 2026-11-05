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
- Web UI and CLI, no dependencies

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
8bitdo-cfg keyboard map caps_lock left_ctrl
8bitdo-cfg keyboard macro f24 --name copy tap:ctrl+c delay:50 tap:ctrl+v
8bitdo-cfg mouse dpi 400 800 1600 3200 6400 12800
8bitdo-cfg mouse button side_back play_pause
8bitdo-cfg mouse dump > mouse.json
```

Full reference: [docs/USAGE.md](docs/USAGE.md)

## Development

```sh
python3 -m unittest discover -s tests
```

[Protocol](docs/PROTOCOL.md) · [Reverse Engineering](docs/REVERSE_ENGINEERING.md)

## License

MIT. Bundled fonts are SIL OFL. Not affiliated with 8BitDo.
