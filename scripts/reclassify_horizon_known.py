#!/usr/bin/env python3
"""按 features.py 的**实际 horizon 构造**重定 horizon_known 标签。

判定依据（spec §4.5 W5.1 的定义，非举例）：
  - self_referential : horizon 由**模型自身输出**（predicted_*）算出
  - persistence      : horizon 是 **context 末值**的确定性函数（常数/衰减）
  - unknowable       : horizon **全零**（无任何近似）

做法：静态解析 `cascade/features.py` 中每个 `covariate_type == "xxx"` 分支，
提取其 `covariate_full = ...` 赋值表达式，按表达式形态分类。
**不**采信任何外部清单。

用法:
    .venv/bin/python scripts/reclassify_horizon_known.py --check   # 只报告
    .venv/bin/python scripts/reclassify_horizon_known.py --write   # 落盘

⚠️ 已知局限（**不要**据此直接落盘全量改判）
    纯正则解析 `covariate_full = ...` 的赋值表达式，覆盖不全：
      - 走 helper 的分支（`_build_rsi_state_from_daily` 等）无法从表达式
        看出 horizon 来源 → 落入「无法判定」，需人工读 helper
      - 表达式用中间变量时（`np.concatenate([ctx_vor, horizon_vor])`）
        同样无法判定
    实测 31 项中 14 项可自动判定、11 项需人工、6 项已一致。
    `--write` 在存在「无法判定」项时**拒绝落盘**（fail-loud），
    避免用半成品替换现有标签。

    要真正完成重标，需要**逐协变量的实证探针**（扰动 predicted_* 看
    horizon 是否变化 / 检查 horizon 是否全零 / 是否等于 context 末值），
    而不是静态表达式匹配。本脚本是诊断起点，不是权威。
"""
import argparse
import json
import re
import sys
from pathlib import Path

FEATURES = Path("cascade/features.py")
POOL = Path("task_FM/config/covariate_pool.json")

# 表达式形态 → 类别。顺序即优先级。
_PATTERNS = (
    # horizon 段直接来自模型预测输出
    ("self_referential", re.compile(r"pred(icted)?[_a-z]*", re.I)),
    # horizon 段全零
    ("unknowable", re.compile(r"np\.zeros\(\s*horizon")),
    # horizon 段取 context 末值（常数或衰减）
    ("persistence", re.compile(r"np\.full\(\s*horizon|_decay_fill|_generate_rsi_state_horizon")),
)


def classify_expr(expr: str) -> str:
    """按 horizon 段的构造表达式分类。"""
    # 只看 horizon 部分：表达式里 horizon 相关的那一项
    for label, pat in _PATTERNS:
        if pat.search(expr):
            return label
    return "UNKNOWN"


def extract_branches(src: str) -> dict:
    """提取 {covariate_type: horizon 构造表达式}。

    抓取形如
        elif covariate_type == "xxx":
            ...
            covariate_full = <expr>
    的赋值表达式。多协变量分支（如 ("rsi_state","rsi6",...)）逐个登记。
    """
    out = {}
    lines = src.splitlines()
    cur_names = []
    for i, line in enumerate(lines):
        m = re.match(r'\s*(?:el)?if\s+covariate_type\s*(?:==|in)\s*(.+):\s*$', line)
        if m:
            names = re.findall(r'"([a-z0-9_]+)"', m.group(1))
            cur_names = names
            continue
        if cur_names and re.match(r"\s*covariate_full\s*=", line):
            # 取该赋值的完整表达式（可能跨行）
            expr = line.split("=", 1)[1].strip()
            j = i + 1
            depth = expr.count("(") + expr.count("[") - expr.count(")") - expr.count("]")
            while depth > 0 and j < len(lines):
                expr += " " + lines[j].strip()
                depth += lines[j].count("(") + lines[j].count("[") \
                    - lines[j].count(")") - lines[j].count("]")
                j += 1
            for n in cur_names:
                out.setdefault(n, expr)
            cur_names = []
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="落盘（默认只报告）")
    args = ap.parse_args()

    branches = extract_branches(FEATURES.read_text(encoding="utf-8"))
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    covs = pool["covariates"]

    changes, unknown, unchanged = [], [], 0
    for name, cfg in sorted(covs.items()):
        cur = cfg.get("horizon_known")
        expr = branches.get(name)
        if expr is None:
            unknown.append((name, cur, "features.py 无该分支"))
            continue
        new = classify_expr(expr)
        if new == "UNKNOWN":
            unknown.append((name, cur, expr[:70]))
            continue
        if new != cur:
            changes.append((name, cur, new, expr[:70]))
        else:
            unchanged += 1

    print("=== 需改判 (%d) ===" % len(changes))
    for name, cur, new, expr in changes:
        print("  %-28s %-16s -> %-16s   %s" % (name, cur, new, expr))

    print("\n=== 无法自动判定 (%d) ===" % len(unknown))
    for name, cur, why in unknown:
        print("  %-28s cur=%-16s %s" % (name, cur, why))

    print("\n=== 已一致 (%d) ===" % unchanged)

    if args.write:
        if unknown:
            print("\n[REFUSE] 有 %d 项无法自动判定，拒绝落盘"
                  "（fail-loud，不静默留半成品）" % len(unknown), file=sys.stderr)
            return 2
        for name, cur, new, _ in changes:
            covs[name]["horizon_known"] = new
        POOL.write_text(json.dumps(pool, indent=1, ensure_ascii=False),
                        encoding="utf-8")
        print("\n已写入 %s（%d 项改判）" % (POOL, len(changes)))
    else:
        print("\n（未落盘；加 --write 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
