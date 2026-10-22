# SPDX-License-Identifier: MIT
"""Small helpers the launch steps call (python -m retro_launcher.hooks ...).

Both Amiga boots start their on-machine game launcher unless a
"launcher.skip" file exists on the drive the boot script checks:

  flag on|off PATH                    a file on the host (FS-UAE shared folder)
  hdf-flag on|off HDF NAME [--xdftool X]
                                      a file inside an Amiga hardfile, via
                                      amitools' xdftool (only while the
                                      emulator using the HDF is stopped)
"""
import argparse
import os
import subprocess
import sys
import tempfile


def flag(state, path):
    if state == "on":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write("retro-launcher: boot without the game launcher\n")
        print("created", path)
    elif os.path.exists(path):
        os.remove(path)
        print("removed", path)
    else:
        print("already absent:", path)
    return 0


def hdf_flag(state, hdf, name, xdftool):
    base = [xdftool]
    listing = subprocess.run(base + ["-r", hdf, "open", "part=0", "+", "list"],
                             capture_output=True, text=True)
    if listing.returncode:
        sys.stderr.write(listing.stdout + listing.stderr)
        return listing.returncode
    present = any(line.split()[:1] == [name] for line in listing.stdout.splitlines())
    if state == "on":
        if present:
            print("already present:", name)
            return 0
        with tempfile.NamedTemporaryFile("w", suffix=".skip", delete=False) as t:
            t.write("retro-launcher: boot without the game launcher\n")
        try:
            r = subprocess.run(base + ["-f", hdf, "open", "part=0", "+", "write", t.name, name])
        finally:
            os.unlink(t.name)
        print("wrote", name, "to", hdf)
        return r.returncode
    if not present:
        print("already absent:", name)
        return 0
    r = subprocess.run(base + [hdf, "open", "part=0", "+", "delete", name])
    print("deleted", name, "from", hdf)
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(prog="retro_launcher.hooks", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("flag")
    f.add_argument("state", choices=["on", "off"])
    f.add_argument("path")
    h = sub.add_parser("hdf-flag")
    h.add_argument("state", choices=["on", "off"])
    h.add_argument("hdf")
    h.add_argument("name")
    h.add_argument("--xdftool", default="xdftool")
    a = ap.parse_args(argv)
    if a.cmd == "flag":
        return flag(a.state, a.path)
    return hdf_flag(a.state, a.hdf, a.name, a.xdftool)


if __name__ == "__main__":
    sys.exit(main())
