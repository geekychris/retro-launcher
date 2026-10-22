# Building and packaging

* [Running from source](#running-from-source)
* [Installing as a command](#installing-as-a-command)
* [Stand-alone apps](#stand-alone-apps)
* [A desktop entry on Linux](#a-desktop-entry-on-linux)
* [The icon](#the-icon)
* [The doc screenshots](#the-doc-screenshots)

## Running from source

You need Python 3.9 or later.

```sh
./run.sh          # macOS / Linux
run.bat           # Windows
```

The first run creates `.venv` and installs the package into it in editable
mode (`pip install -e .`, which brings in pygame-ce). Later runs start
straight away. Any arguments are passed on, for example
`./run.sh --windowed --launch atari`.

## Installing as a command

```sh
python3 -m pip install .            # or: pipx install .
retro-launcher --windowed
```

## Stand-alone apps

```sh
./build-app.sh                      # macOS and Linux
build-app.bat                       # Windows
```

These scripts install PyInstaller into `.venv` and build:

| OS | Output |
|---|---|
| macOS | `dist/Retro Launcher.app` (with `icon.icns`, bundle id `com.geekychris.retrolauncher`) |
| Linux | `dist/retro-launcher/retro-launcher` |
| Windows | `dist\retro-launcher\retro-launcher.exe` (with `icon.ico`) |

On macOS, copy the app to `/Applications` or `~/Applications` so Spotlight
and Launchpad find it. The build isn't signed, so the first time you open
it, macOS may ask you to confirm (Control-click → Open). It may also ask
whether Retro Launcher may control System Events. Allow that: it's how the
launcher brings emulator windows to the front.

A frozen build runs its own helper (`<app> --hooks`). It finds `python3` on
`PATH` for the Atari's `make_drive.py`. See
[How it works](how-it-works.md#stand-alone-builds).

## A desktop entry on Linux

```ini
# ~/.local/share/applications/retro-launcher.desktop
[Desktop Entry]
Type=Application
Name=Retro Launcher
Comment=Boot the Amiga, AmigaOS 4, Atari and 3DO emulators
Exec=/path/to/retro-launcher/run.sh
Icon=/path/to/retro-launcher/retro_launcher/assets/icon.png
Categories=Game;Emulator;
```

## The icon

![The icon](images/icon-256.png)

`tools/make_icon.py` draws the icon with pygame at four times its size and
scales it down to smooth the edges: a synthwave sun with a play arrow over a
neon grid, with one dot per machine in its card's colour. It writes:

* `retro_launcher/assets/icon.png`: 1024×1024, used for the window and Dock
  icon at run time;
* `retro_launcher/assets/icon.icns`: macOS (needs `iconutil`, so macOS only);
* `retro_launcher/assets/icon.ico`: Windows, 16–256 px.

```sh
.venv/bin/python tools/make_icon.py
```

## The doc screenshots

`tools/docshots.py` renders the menu and settings screenshots in
`docs/images/` off-screen, with SDL's dummy video driver, at 1600×900. It
reads your config without changing it and launches nothing, but the cards
show which emulators are really running at the time.

```sh
.venv/bin/python tools/docshots.py              # or --size 1920x1080, --config FILE
```

The `machine-*.png` images, from inside the emulators, were captured by
hand.
