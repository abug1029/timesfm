import re
from pathlib import Path

_SPEC = (
    Path(__file__).resolve().parents[1]
    / "docs/superpowers/specs/2026-10-09-s1-supervisor-split-spec.md"
)
_MOD = re.compile(r"sup_[a-z]+")

OVERRIDES = {
    "CROSS_MATRIX_MAX_ROWS": "sup_evidence",
    "OLD_PRIORS_MAX_ROWS": "sup_evidence",
    "_CONFIRMATORY_DM": "sup_evidence",
    "_CONFIRM_DATA_CACHE": "sup_state",
    "_CONFIRM_DATA_TTL_S": "sup_state",
    "_ev_mod_for_goal": "sup_evidence",
}


def _section(text, start, end):
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


def _rows(section):
    rows = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or cells[0].startswith("-") or cells[0] in {"函数名", "符号"}:
            continue
        rows.append(cells)
    return rows


def _mod(cell):
    match = _MOD.search(cell)
    if match is None:
        raise ValueError(f"no sup_* module in {cell!r}")
    return match.group(0)


def _load():
    text = _SPEC.read_text(encoding="utf-8")
    funcs = {row[0]: _mod(row[2]) for row in _rows(_section(text, "### A.1", "### A.2"))}
    nested = {row[0]: row[2] for row in _rows(_section(text, "### A.2", "### A.3"))}
    assigns = {row[0]: _mod(row[2]) for row in _rows(_section(text, "### A.3", "### A.4"))}
    return funcs, assigns, nested


FUNCS, ASSIGNS, NESTED = _load()
HOME = {**FUNCS, **ASSIGNS, **OVERRIDES}
