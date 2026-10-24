# Start-here scripts

`bin/` has a script per machine that brings up its whole development
environment in one go, plus start-all and stop-all for everything. They're
zsh scripts for macOS. Put `bin` on your PATH, or link the scripts into
`~/bin`:

```sh
for f in ~/code/claude_world/retro-launcher/bin/*; do ln -sfn "$f" ~/bin/; done
```

| Script | |
|---|---|
| `devbench-amiga68k` | Classic Amiga: FS-UAE (AmiKit) and its AmigaDevBench on :3001 |
| `devbench-amigaos4` | AmigaOS 4.1: QEMU sam460ex and its AmigaDevBench on :3000 |
| `devbench-atari` | Atari ST: Hatari with its agent API on :7777, on the ST games drive |
| `devbench-3do` | 3DO: the 3DO DevBench on :3330 and the arcade disc |
| `retro-start-all` | Docker, every machine, its devbench, and the Retro Launcher menu |
| `retro-stop-all` | Stops them all again (Docker keeps running) |
| `retro` | What they all call: see `retro help` |

## A machine's script

Run with no argument, a `devbench-*` script:

1. **checks every part is installed**: the emulator, its ROMs and disks, the
   cross-compilers (in Docker, or native), the devbench, the ports. The
   Amigas use amiga_mcp's `scripts/doctor.sh` and the 3DO uses `./3do doctor`.
   Each problem comes with the command that fixes it.
2. **starts** the emulator and its devbench (anything already running is
   left alone; Docker is started if a toolchain needs it), and
3. **lists the addresses to connect to**, with a green dot on the ones that
   answer: the web UI, the MCP endpoint and the `claude mcp add` line for it,
   debugger and monitor ports, and where to deploy.

```
$ devbench-amigaos4
AmigaOS 4.1 · PowerPC · QEMU: checking the parts
  ✓ PPC cross-compiler (walkero/amigagccondocker:os4-gcc11)
  ✓ QEMU: /opt/homebrew/bin/qemu-system-ppc (11.1.2)
  ...
AmigaOS 4.1 · PowerPC · QEMU: starting
  ✓ AmigaOS 4.1: devbench and emulator up

AmigaOS 4.1 · PowerPC · QEMU: connect to
  ● DevBench web UI        http://localhost:3000/
  ● MCP (HTTP)             http://localhost:3000/mcp  claude mcp add --transport http amiga-os4 http://localhost:3000/mcp
  ● QEMU monitor (HMP)     127.0.0.1:2348  nc 127.0.0.1 2348
  ...
```

They also take a command: `devbench-atari stop`, `restart`, `check`
(exit status 1 if anything is missing), `urls` and `status`.

## Everything at once

```sh
retro status                 # what's running, with addresses
retro check                  # every machine's parts
retro urls                   # every machine's addresses
retro-start-all              # = retro up
retro-stop-all               # = retro down
retro restart atari 3do      # some of them: amiga68k (68k) amigaos4 (os4) atari 3do launcher docker
retro restart launcher       # just the menu
```

The projects are looked for in `$RETRO_PROJECTS` (default
`~/code/claude_world`): amiga_mcp, atari_st_games, hatari_augmented (or
hatari) and 3do_dev. Logs go to `~/retro/logs`, and the Amiga devbenches
also log to `~/.amiga-devbench/logs`. Machines started this way keep running
after the terminal or ssh session that started them closes, and the menu
shows them as **RUNNING (started elsewhere)**.

Docker's VM forgets its x86 emulation when it restarts, and the 3DO's
compilers need it (32-bit x86). The 3DO script and `retro up docker`
register it again each time.
