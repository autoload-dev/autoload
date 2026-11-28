"""Print a wasm module's custom sections, imports and exports summary."""

import sys


def leb(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            return r, i


def name(b, i):
    n, i = leb(b, i)
    return b[i : i + n].decode(), i + n


def main(path):
    b = open(path, "rb").read()
    assert b[:4] == b"\0asm", "not wasm"
    i = 8
    imports = []
    exports = []
    customs = []
    while i < len(b):
        sid = b[i]
        i += 1
        size, i = leb(b, i)
        end = i + size
        if sid == 0:
            n, _ = name(b, i)
            customs.append(n)
        elif sid == 2:
            cnt, j = leb(b, i)
            for _ in range(cnt):
                m, j = name(b, j)
                f, j = name(b, j)
                kind = b[j]
                j += 1
                imports.append((m, f, kind))
                if kind == 0:
                    _, j = leb(b, j)
                elif kind == 1:
                    j += 1
                    fl, j = leb(b, j)
                    _, j = leb(b, j)
                    if fl & 1:
                        _, j = leb(b, j)
                elif kind == 2:
                    fl, j = leb(b, j)
                    _, j = leb(b, j)
                    if fl & 1:
                        _, j = leb(b, j)
                elif kind == 3:
                    j += 2
                elif kind == 4:
                    j += 1
                    _, j = leb(b, j)
        elif sid == 7:
            cnt, j = leb(b, i)
            for _ in range(cnt):
                f, j = name(b, j)
                kind = b[j]
                j += 1
                _, j = leb(b, j)
                exports.append(f)
        i = end
    print("custom sections:", customs)
    print("imports: %d" % len(imports))
    for m, f, k in imports:
        if len(sys.argv) > 2 or not f.startswith("_ZN5godot"):
            print("  import", m, f, "kind", k)
    print(
        "exports: %d; init symbol exported: %s"
        % (len(exports), [e for e in exports if "init" in e][:5])
    )


main(sys.argv[1])
