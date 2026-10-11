"""Retarget setattr and alias assigns of supervisor symbols onto their home module."""
import argparse
import ast
from pathlib import Path

from s1_symbol_home import HOME

_SUPERVISOR_MODULES = {"praxist_supervisor", "scripts.praxist_supervisor"}


def _alias_imports(tree):
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            if alias.name in _SUPERVISOR_MODULES and alias.asname:
                found.append((alias.asname, node))
                break
    return found


def _is_setattr_call(func):
    if isinstance(func, ast.Name) and func.id == "setattr":
        return True
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "setattr"
        and isinstance(func.value, ast.Name)
        and func.value.id == "monkeypatch"
    )


def _store_attrs(target):
    if isinstance(target, ast.Attribute):
        yield target
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _store_attrs(elt)
    elif isinstance(target, ast.Starred):
        yield from _store_attrs(target.value)


def _imported_modules(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def retarget_source(src: str, names: set[str]) -> str:
    names = set(names)
    if not names:
        return src
    tree = ast.parse(src)
    alias_imports = _alias_imports(tree)
    aliases = {name for name, _node in alias_imports}
    if not aliases:
        return src

    replacements = []

    def consider(name_node, attr):
        if not isinstance(name_node, ast.Name) or name_node.id not in aliases:
            return None
        if attr not in names:
            return None
        try:
            home = HOME[attr]
        except KeyError as exc:
            raise KeyError(f"{attr} is not in s1_symbol_home.HOME") from exc
        replacements.append(
            (
                name_node.lineno,
                name_node.col_offset,
                name_node.end_lineno,
                name_node.end_col_offset,
                home,
            )
        )
        return home

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_setattr_call(node.func):
            if len(node.args) < 2:
                continue
            obj, attr_node = node.args[0], node.args[1]
            if not isinstance(obj, ast.Name):
                continue
            if not isinstance(attr_node, ast.Constant) or not isinstance(attr_node.value, str):
                continue
            consider(obj, attr_node.value)
            continue
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            for attr in _store_attrs(target):
                consider(attr.value, attr.attr)

    if not replacements:
        return src

    replacements.sort()
    homes = []
    for item in replacements:
        home = item[-1]
        if home not in homes:
            homes.append(home)

    raw = src.encode("utf-8")
    line_starts = [0]
    for index, byte in enumerate(raw):
        if byte == 10:
            line_starts.append(index + 1)

    def pos(lineno, col):
        return line_starts[lineno - 1] + col

    edits = []
    for lineno, col, end_lineno, end_col, home in replacements:
        start = pos(lineno, col)
        end = pos(end_lineno, end_col)
        edits.append((start, end, home.encode("utf-8")))

    edits.sort()
    for prev, nxt in zip(edits, edits[1:]):
        if nxt[0] < prev[1]:
            raise RuntimeError("overlapping retarget replacements")

    imported = _imported_modules(tree)
    missing = [home for home in homes if home not in imported]
    if missing:
        anchor = min(alias_imports, key=lambda item: (item[1].lineno, item[1].col_offset))[1]
        raw_line = raw[line_starts[anchor.lineno - 1]:].split(b"\n", 1)[0]
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        block = b"".join(
            indent + b"import " + home.encode("utf-8") + b"\n" for home in missing
        )
        edits.append((line_starts[anchor.lineno - 1], line_starts[anchor.lineno - 1], block))

    out = raw
    for start, end, text in sorted(edits, reverse=True):
        out = out[:start] + text + out[end:]
    return out.decode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", required=True)
    args = parser.parse_args(argv)
    names = {part.strip() for part in args.names.split(",") if part.strip()}
    root = Path(__file__).resolve().parents[1]
    changed = []
    for path in sorted((root / "tests").rglob("*.py")):
        if "archive" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        out = retarget_source(src, names)
        if out != src:
            path.write_text(out, encoding="utf-8")
            path.chmod(0o644)
            changed.append(path.relative_to(root).as_posix())
    for item in changed:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
