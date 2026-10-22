# SPDX-License-Identifier: MIT
"""Read TOML with tomllib and write the small subset the config uses."""
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def load(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _str(s):
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t")
    return '"' + out + '"'


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _str(v)
    if isinstance(v, (list, tuple)):
        if not v:
            return "[]"
        items = [_value(x) for x in v]
        one = "[" + ", ".join(items) + "]"
        if len(one) < 88:
            return one
        return "[\n" + "".join("    " + i + ",\n" for i in items) + "]"
    raise TypeError("can't write %r to TOML" % (v,))


def _key(k):
    if k and all(c.isalnum() or c in "-_" for c in k):
        return k
    return _str(k)


def dumps(data, comments=None):
    """data: {table: {key: value or {subtable...}}}. comments: {table: text}."""
    comments = comments or {}
    lines = []

    def table(name, d):
        plain = {k: v for k, v in d.items() if not isinstance(v, dict)}
        subs = {k: v for k, v in d.items() if isinstance(v, dict)}
        if lines:
            lines.append("")
        if name in comments:
            for c in comments[name].strip().splitlines():
                lines.append("# " + c if c else "#")
        lines.append("[" + name + "]")
        for k, v in plain.items():
            lines.append("%s = %s" % (_key(k), _value(v)))
        for k, v in subs.items():
            table(name + "." + _key(k), v)

    top = {k: v for k, v in data.items() if not isinstance(v, dict)}
    for k, v in top.items():
        lines.append("%s = %s" % (_key(k), _value(v)))
    for k, v in data.items():
        if isinstance(v, dict):
            table(_key(k), v)
    return "\n".join(lines) + "\n"
