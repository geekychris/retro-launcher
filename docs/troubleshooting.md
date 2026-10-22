# Troubleshooting

* [A card says MISSING](#a-card-says-missing)
* [A card says FAILED](#a-card-says-failed)
* [A machine boots the wrong way](#a-machine-boots-the-wrong-way)
* [The emulator doesn't come to the front](#the-emulator-doesnt-come-to-the-front)
* [The menu doesn't come back](#the-menu-doesnt-come-back)
* [A machine shows RUNNING when it isn't](#a-machine-shows-running-when-it-isnt)
* [The fullscreen menu shows the menu bar and Dock](#the-fullscreen-menu-shows-the-menu-bar-and-dock)
* [Gamepads](#gamepads)
* [Windows](#windows)
* [Linux](#linux)

## A card says MISSING

The pill lists the `[paths]` entries that don't exist. Press **C**, go to the
machine's tab, and fix the rows marked ✗. Each row shows what it expands to,
which makes a wrong `{projects}` or a typo easy to spot. Values without a
slash, such as `xdftool` or `ste`, aren't checked as files. A bare program
name gets ✓ when it's on `PATH`.

If all four machines are MISSING, **General → Projects folder** probably
doesn't point at the folder holding the sister projects.

## A card says FAILED

Press **L**. The log shows each prepare step, each command line, and the
emulator's own output, with the exit code at the end. Common causes:

| In the log | Fix |
|---|---|
| `not found: …` | The program in the command doesn't exist; check its path on the machine's tab |
| `[exit …]` after `hdf-flag` | `xdftool` isn't installed (`pip install amitools`) or isn't at the configured path |
| The emulator's own error | Run the command from **Preview commands** in a terminal to see it in full |

## A machine boots the wrong way

* Check the card's boot line, and press **B** if it's the wrong mode.
  **Boot into** on the machine's tab can be `default`, which follows
  **General → Boot into game selectors**.
* **Amigas:** the switch is a `launcher.skip` file. Check that the boot
  script edit is in place (see [The machines](machines.md)), and look in the
  log for `created`, `removed`, `wrote` or `deleted`.
* **AmigaOS 4:** the flag is written into the hard file only while QEMU is
  stopped. If QEMU was already running, the launcher switched to it instead
  of launching, so the mode didn't change. Stop it (S, S) and launch again.

## The emulator doesn't come to the front

* **macOS:** the launcher asks System Events to raise the emulator. The
  first time, macOS asks whether the app (or your terminal, when running
  from source) may control System Events. If that was denied, allow it in
  System Settings → Privacy & Security → Automation. Un-minimising a
  minimised emulator window also needs Accessibility permission. Without it,
  the window comes forward only if it isn't minimised.
* **Linux:** install `wmctrl` or `xdotool`. Under Wayland, raising another
  app's window may not be allowed. Use an X11 session or XWayland emulators.
* **Windows:** `AppActivate` can be refused while you are typing in another
  window. Windows may flash the emulator's taskbar button instead.

If none of this works, the menu shows "… is running, but its window couldn't
be brought forward".

## The menu doesn't come back

The menu returns once the emulator's processes are gone, that is, once the
launch has ended *and* the process watcher no longer matches anything. If
something matching `process_match` is still running, such as a leftover
helper, the menu waits for it. Check with:

```sh
ps -axo pid,command | grep qemu-system-ppc
```

You can always click the menu (with **While playing = background**) or
reopen the app.

## A machine shows RUNNING when it isn't

Some other process matches `process_match`. Make the match more specific:
the 3DO uses `{tdo} --bios` rather than `{tdo}`, so other `tdo` commands
don't count. Leaving the match empty turns detection off.

## The fullscreen menu shows the menu bar and Dock

This is deliberate on macOS. The menu's fullscreen window sits at the normal
window level, so that emulator windows can come in front of it, and the
menu bar and Dock appear over it. See
[How it works](how-it-works.md#the-menu-while-you-play).

## Gamepads

Pads are picked up at start and when plugged in. The mapping follows the
SDL layout (A=0, B=1, X=2, Y=3, Back/Start=6/7, or 9 on some pads). If the
buttons seem swapped, the pad reports a different layout. Keyboard and
mouse always work.

## Windows

* `start-qemu-os4.sh` is a bash script. Set the AmigaOS 4 commands to run
  `qemu-system-ppc.exe` directly, with the arguments the script prints when
  it starts, or run the script through Git Bash or WSL.
* The 3DO's `tdo` lives in `3do_dev\.venv\Scripts\tdo.exe`.
* The defaults look for `hatari.exe` in `hatari_augmented\build\src\`.

## Linux

* The defaults expect `fs-uae` and `xdftool` on `PATH`, QEMU's `gtk` display
  for fullscreen OS4, and Hatari in `hatari_augmented/build/src/hatari`.
* Raising windows needs `wmctrl` or `xdotool` (see above).
