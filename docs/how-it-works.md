# How it works

* [Layout](#layout)
* [Drawing the menu](#drawing-the-menu)
* [The launch lifecycle](#the-launch-lifecycle)
* [Detecting running emulators](#detecting-running-emulators)
* [Bringing a window to the front](#bringing-a-window-to-the-front)
* [The menu while you play](#the-menu-while-you-play)
* [Stopping](#stopping)
* [Stand-alone builds](#stand-alone-builds)

## Layout

```text
retro-launcher/
├── launch.py                 entry point for PyInstaller
├── run.sh / run.bat          run from source (make .venv on first use)
├── build-app.sh / .bat       stand-alone app with PyInstaller
├── retro_launcher/
│   ├── __main__.py           command line: --config --windowed --launch --print --hooks
│   ├── app.py                the UI: App (menu, input, drawing), Settings, Field
│   ├── config.py             defaults, Config (load/save, template expansion, plan())
│   ├── procs.py              Launch, Watcher, find_processes, descendants, focus_pids, kill_pids
│   ├── hooks.py              the {helper}: flag / hdf-flag
│   ├── tomlio.py             TOML reading (tomllib / tomli) and a small writer
│   └── assets/               card screenshots per machine, icon.png / .icns / .ico
├── tools/
│   ├── make_icon.py          draws the icon
│   └── docshots.py           renders the screenshots in docs/images
└── docs/
```

The only dependency is [pygame-ce](https://pyga.me/), plus `tomli` on
Python older than 3.11.

## Drawing the menu

The menu is drawn with pygame-ce at the display's own resolution, scaled by
its height. Everything is drawn onto an opaque 24-bit canvas, which is then
copied to the window in one go. Some display surfaces carry an alpha
channel, and drawing translucent layers straight onto those replaces pixels
instead of blending them.

A frame is built from these layers:

1. the selected machine's screenshot, scaled to cover the screen, blurred
   (shrunk and scaled back up), darkened and cached;
2. a field of stars and a perspective grid;
3. the title with a glow, the subtitle and the clock;
4. the cards. Each one has a drop shadow, a rounded screenshot with an
   accent glow that pulses when it's selected, and a title sized with
   `fit_font` so long names shrink instead of being cut off. The selection
   eases between cards;
5. the footer of clickable key buttons, and overlays (toast, log box,
   preview).

Symbols that fonts often lack (▶, ✓, ✗) are drawn as shapes. Screenshots
cross-fade every 4.2 seconds.

The menu runs at 60 fps. Behind an emulator it drops to 10 fps, and when
hidden to 4.

## The launch lifecycle

`Config.plan(key, selector)` turns a machine's settings into
`(prepare, argv, cwd, env)`: lists of argument lists with every template
expanded (see [Configuration](configuration.md#command-templates)).

`Launch.start()` then runs on a background thread, so the menu keeps
animating:

```text
idle ──start──▶ preparing ──every prepare step exits 0──▶ running ──exit──▶ exited
                    │                                         │
                    └─ a step fails / not found ─▶ failed ◀───┘ non-zero exit (not stopped by us)
```

* Every step and the emulator get a fresh log section
  (`<config dir>/logs/<key>.log`), with stdout and stderr both going there
  and stdin set to `/dev/null`.
* The emulator starts in a new session (POSIX `start_new_session`) or a new
  process group (Windows), so it can be stopped as a group, start script and
  all. It also keeps running after the launcher quits.

## Detecting running emulators

A `Watcher` thread lists processes every two seconds (`ps -axo
pid=,command=`, or `Win32_Process` through PowerShell on Windows). It
matches each machine's expanded `process_match` against them:

* the match text must be in the command line;
* the match's first word must be in the program or its first argument, so a
  shell or an editor whose command line mentions `qemu-system-ppc` doesn't
  count (one did, while the launcher was being written);
* the launcher's own process never counts.

A card is RUNNING if the launcher's own launch is running *or* the watcher
found a match. That is how emulators started elsewhere show up.

## Bringing a window to the front

To switch to a machine, the launcher collects candidate process IDs: the
watcher's matches, then the launched process and all of its descendants
(from a `ps -axo pid=,ppid=` walk), because the window often belongs to a
child, as with QEMU started by `start-qemu-os4.sh`. It tries each one in turn
until one works:

| OS | How |
|---|---|
| macOS | AppleScript via `osascript`: System Events un-minimises the process's windows and sets it frontmost |
| Windows | `(New-Object -ComObject WScript.Shell).AppActivate(pid)` in PowerShell |
| Linux (X11) | `wmctrl -lp` to find the window by PID, then `wmctrl -ia`; failing that, `xdotool search --pid … windowactivate` |

## The menu while you play

After a launch, once the emulator has been running for 1.5 seconds, or
straight away when switching to a running machine, the launcher:

* with **while_playing = background**, brings the emulator to the front and
  leaves the menu where it is;
* with **while_playing = hide**, hides the menu first. On macOS, and for a
  fullscreen menu anywhere, the window is hidden rather than minimised. In a
  window on Windows and Linux, it is minimised.

When the emulator's processes are gone (the launch has ended *and* the
watcher no longer sees it), the menu shows itself again if it was hidden and
asks the OS to bring its own process to the front. An app in the background
isn't allowed to raise itself on macOS, so it uses the same mechanism as
above.

On macOS, three SDL settings make the fullscreen menu behave as a backdrop:

| Setting | Why |
|---|---|
| `SDL_VIDEO_MAC_FULLSCREEN_SPACES=0` | No separate Space for the fullscreen menu. Otherwise hiding it left an empty black Space in front of the emulator |
| `SDL_ALLOW_TOPMOST=0` | The fullscreen window sits at the normal level, so emulator windows can come in front of it |
| `SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS=0` | The menu doesn't minimise itself when the emulator takes focus |

As a result, the macOS menu bar and Dock stay visible over the fullscreen
menu.

## Stopping

S asks once and stops on the second press:

* **Launched here:** `SIGTERM` to the whole process group, then `SIGKILL`
  after four seconds if it is still there. On Windows, `CTRL_BREAK_EVENT`,
  then `kill()`.
* **Started elsewhere:** `SIGTERM` to the matched PIDs
  (`taskkill /PID … /T` on Windows).

## Stand-alone builds

PyInstaller freezes the launcher into one app (`build-app.sh`). In a frozen
build:

* `{helper}` becomes `<app executable> --hooks …`. `__main__` passes
  `--hooks` straight on to `hooks.main()`, so the helper works without a
  Python installation;
* `{python}`, which the Atari's `make_drive.py` needs, is the first `python3`
  or `python` on `PATH`, because the frozen app has no interpreter to lend.
