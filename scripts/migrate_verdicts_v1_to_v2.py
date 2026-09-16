#!/usr/bin/env python3
"""v1 -> v2 verdict 离线迁移脚本 (Task 14)。

把 v1 schema (fm.aligned_verdict.v1) 的 aligned verdict JSONL 逐行迁移为 v2
(fm.aligned_verdict.v2)，写到 {dst}.tmp，全部行处理完后 os.replace 原子替换到 dst。

迁移规则 (Task 14 规格):
- schema 固定 "fm.aligned_verdict.v2", batch_id 固定 "migrated_v1"
- path_corr / p_value 置 None (旧 checkpoint 无路径数据, 无法重算)
- n_eff: 优先用 v1 已有 n_eff; 缺失时 fallback_n_eff(n, HORIZON=24, STEP=24)
  —— STEP 显式传 24: 旧 verdict 均为 STEP=24 网格产出 (当前生产 STEP=2 不适用)
- v1 行有 checkpoint_path 且文件可读: 重算 endpoint_mape / endpoint_bias_pct /
  weighted_dir_acc, dir_acc 若 v1 缺也重算
- gate_pass 按新 gate() 重判 (min_dir_acc=0.52 默认, 无 baseline)
- fdr_pass / migrated_pass: v1 gate_pass AND 新 gate_pass (两者同时 True 才 True)
- cov_family 由 cascade.cov_family.resolve_cov_family() 解析
- checkpoint_path 字段缺失/None 或 checkpoint 缺失/不可读/无可用行 ->
  该行 status="migration_failed", warning 记到 stderr, 继续下一条;
  failed 行 fdr_pass/migrated_pass 强制 False (墓碑约定), gate_pass 保留新 gate 重判值
- 行数守恒: 输出行数 == 输入行数 (含 migration_failed 行)
- 输出行必须全部通过 registry_lib.validate_verdict (v2 校验)

运维 SOP (--help epilog 同款):
  1. 停 supervisor
  2. cp aligned_verdicts.jsonl aligned_verdicts.jsonl.bak_v1
  3. python scripts/migrate_verdicts_v1_to_v2.py --src <bak> --dst aligned_verdicts.jsonl
  4. 核对行数 (输入/输出一致; 统计 ok / migration_failed)
  5. 启 supervisor
"""
import argparse
import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
_SCRIPTS = os.path.join(REPO_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from config.backtest_config import HORIZON  # noqa: E402  (== 24)
from cascade.cov_family import load_covariate_pool, resolve_cov_family  # noqa: E402
from cascade.evaluation_metrics import fallback_n_eff  # noqa: E402
from registry_lib import validate_verdict  # noqa: E402

V2_SCHEMA = "fm.aligned_verdict.v2"
MIGRATION_BATCH_ID = "migrated_v1"
# 迁移语义: 旧 verdict 全部由 STEP=24 网格回测产出 (step >= horizon -> 不重叠)。
# 显式传 24, 不用当前生产 STEP (config.backtest_config.STEP == 2)。
MIGRATION_STEP = 24

_EPS = 1e-8


def _load_gate():
    """加载 task_FM/evaluations/fm_eval/evaluator.gate (task_FM 非包, 用 importlib)。"""
    path = os.path.join(REPO_ROOT, "task_FM", "evaluations", "fm_eval", "evaluator.py")
    spec = importlib.util.spec_from_file_location("fm_evaluator_migrate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.gate


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _checkpoint_metrics(path):
    """从 v1 checkpoint JSONL 重算 endpoint 指标。

    与存量实现对齐 (cascade/evaluation_metrics.calc_prediction_quality):
    - endpoint_mape     = mean(|pred_end - real_end| / max(base, 1.0)) * 100
    - endpoint_bias_pct = mean((delta_pred - delta_real) / max(base, 1.0)) * 100
    - weighted_dir_acc  = sum(|delta_real| * dir_ok) / sum(|delta_real|);
      分母 ~0 时取 0.5 (calc_prediction_quality 同款)
    dir_ok 按 checkpoint 的 scheme 加权 delta_pred/delta_real 判定 (符号一致),
    |delta_real| < eps 记 False (与 evaluator.endpoint_dir_ok 一致)。
    与 calc_prediction_quality 的差别: bias/dir 用 checkpoint 的 scheme 加权
    delta_pred/delta_real 字段 (而非 pred_end - base), 按迁移规格公式执行。

    无可用行时返回 None。
    """
    rows = 0
    mape_sum = 0.0
    bias_sum = 0.0
    w_num = 0.0
    w_den = 0.0
    dir_ok_count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or "error" in rec:
                continue
            base = rec.get("base")
            pred_end = rec.get("pred_end")
            real_end = rec.get("real_end")
            if not all(_is_num(x) for x in (base, pred_end, real_end)):
                continue
            delta_pred = rec.get("delta_pred")
            delta_real = rec.get("delta_real")
            if not _is_num(delta_real):
                delta_real = real_end - base
            if not _is_num(delta_pred):
                delta_pred = pred_end - base
            denom = max(base, 1.0)
            mape_sum += abs(pred_end - real_end) / denom
            bias_sum += (delta_pred - delta_real) / denom
            dr_abs = abs(delta_real)
            w_den += dr_abs
            if dr_abs >= _EPS and (delta_pred > 0) == (delta_real > 0):
                dir_ok_count += 1
                w_num += dr_abs
            rows += 1
    if rows == 0:
        return None
    return {
        "endpoint_mape": mape_sum / rows * 100.0,
        "endpoint_bias_pct": bias_sum / rows * 100.0,
        "weighted_dir_acc": (w_num / w_den) if w_den >= _EPS else 0.5,
        "dir_acc": dir_ok_count / rows,
    }


def _load_pool():
    """加载协变量池; 失败时退化空池 (跳过池匹配, 启发式兜底), 并向 stderr 打警告。"""
    try:
        return load_covariate_pool()
    except Exception as e:
        print(f"[migrate] WARN 协变量池加载失败, 降级为空池 (启发式兜底): {e}", file=sys.stderr)
        return {"covariates": []}


def migrate_row(rec, gate_fn, covariate_pool=None):
    """迁移单个 v1 verdict dict -> v2 dict (不做 IO)。"""
    failed = False
    err_msg = None

    cp = rec.get("checkpoint_path")
    metrics = None
    if not cp:
        # v1 行缺 checkpoint_path 字段 (键不存在或 None): 判 migration_failed
        failed = True
        err_msg = "checkpoint_path field missing"
    else:
        if os.path.exists(cp):
            try:
                metrics = _checkpoint_metrics(cp)
            except (OSError, UnicodeDecodeError):
                metrics = None
        if metrics is None:
            failed = True
            err_msg = ("checkpoint 文件不存在" if not os.path.exists(cp)
                       else "checkpoint 不可读/无可用行") + f": {cp}"

    n_raw = rec.get("n")
    n = int(n_raw) if _is_num(n_raw) and n_raw > 0 else 0

    n_eff_raw = rec.get("n_eff")
    if _is_num(n_eff_raw) and n_eff_raw > 0:
        n_eff = int(n_eff_raw) if float(n_eff_raw).is_integer() else float(n_eff_raw)
    elif n > 0:
        n_eff = fallback_n_eff(n, HORIZON, MIGRATION_STEP)
    else:
        n_eff = 0

    dir_acc_raw = rec.get("dir_acc")
    if _is_num(dir_acc_raw):
        dir_acc = float(dir_acc_raw)
    elif metrics is not None and _is_num(metrics.get("dir_acc")):
        dir_acc = float(metrics["dir_acc"])
    else:
        dir_acc = 0.0

    if metrics is not None:
        weighted_dir_acc = metrics["weighted_dir_acc"]
        endpoint_mape = metrics["endpoint_mape"]
        endpoint_bias_pct = metrics["endpoint_bias_pct"]
    elif failed:
        # make_error_tombstone 同款兜底: endpoint_mape=None, weighted_dir_acc=0.0
        weighted_dir_acc = 0.0
        endpoint_mape = None
        endpoint_bias_pct = None
    else:
        weighted_dir_acc = None
        endpoint_mape = None
        endpoint_bias_pct = None

    new_gate = bool(gate_fn({"n": n, "n_eff": n_eff, "dir_acc": dir_acc}))

    v1_gate = rec.get("gate_pass") is True
    both = v1_gate and new_gate
    if failed:
        # make_error_tombstone 墓碑约定: failed 行 fdr_pass/migrated_pass 强制 False
        # (gate_pass 保留新 gate 重判值, 不强制)
        both = False

    out = {
        "schema": V2_SCHEMA,
        "variant_id": rec.get("variant_id"),
        "symbol": rec.get("symbol"),
        "cov_override": rec.get("cov_override"),
        "cov_family": resolve_cov_family(rec, covariate_pool),
        "status": "migration_failed" if failed else "ok",
        "stage": rec.get("stage", "aligned"),
        "batch_id": MIGRATION_BATCH_ID,
        "n": n,
        "n_eff": n_eff,
        "dir_acc": dir_acc,
        "weighted_dir_acc": weighted_dir_acc,
        "gate_pass": new_gate,
        "p_value": None,
        "fdr_pass": both,
        "migrated_pass": both,
        "endpoint_mape": endpoint_mape,
        "endpoint_bias_pct": endpoint_bias_pct,
        "path_corr": None,
        "mae": rec.get("mae") if _is_num(rec.get("mae")) else None,
        "mape": rec.get("mape") if _is_num(rec.get("mape")) else None,
        "decay": rec.get("decay") if _is_num(rec.get("decay")) else None,
        "checkpoint_path": cp,
        "slow_loop_pid": rec.get("slow_loop_pid"),
        "git_rev": rec.get("git_rev"),
        "decided_at": rec.get("decided_at"),
        "metrics": {
            "batch_id": MIGRATION_BATCH_ID,
            "symbol": rec.get("symbol"),
            "n": n,
            "n_eff": n_eff,
            "dir_acc": dir_acc,
            "endpoint_mape": endpoint_mape,
            "endpoint_bias_pct": endpoint_bias_pct,
            "path_corr": None,
            "weighted_dir_acc": weighted_dir_acc,
            "status": "migration_failed" if failed else "ok",
            "gate_pass": new_gate,
            "fdr_pass": both,
            "migrated_pass": both,
            "mae": rec.get("mae") if _is_num(rec.get("mae")) else None,
            "mape": rec.get("mape") if _is_num(rec.get("mape")) else None,
            "decay": rec.get("decay") if _is_num(rec.get("decay")) else None,
        },
    }
    if failed:
        out["error_message"] = err_msg
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="v1 -> v2 verdict 离线迁移 (Task 14)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""运维 SOP:
  1. 停 supervisor
  2. cp aligned_verdicts.jsonl aligned_verdicts.jsonl.bak_v1
  3. python scripts/migrate_verdicts_v1_to_v2.py --src <bak> --dst aligned_verdicts.jsonl
  4. 核对行数 (输入/输出一致; ok / migration_failed 计数)
  5. 启 supervisor
""")
    parser.add_argument("--src", required=True, help="v1 verdict JSONL (迁移前先备份)")
    parser.add_argument("--dst", required=True, help="v2 verdict JSONL 输出路径")
    args = parser.parse_args(argv)

    src = os.path.abspath(args.src)
    dst = os.path.abspath(args.dst)
    if src == dst:
        parser.error("--dst 必须与 --src 不同 (拒绝原地覆盖; 先做 .bak_v1 备份)")
    if not os.path.exists(src):
        parser.error(f"--src 不存在: {src}")

    gate_fn = _load_gate()
    pool = _load_pool()

    rows_in = 0
    ok_count = 0
    fail_count = 0
    tmp = dst + ".tmp"
    try:
        with open(src, encoding="utf-8") as fsrc, open(tmp, "w", encoding="utf-8") as fdst:
            for lineno, line in enumerate(fsrc, 1):
                s = line.strip()
                if not s:
                    continue
                try:
                    rec = json.loads(s)
                except ValueError as e:
                    raise SystemExit(f"[migrate] line {lineno}: 无法解析的 JSON, 已中止 (dst 未被写入): {e}")
                if not isinstance(rec, dict):
                    raise SystemExit(f"[migrate] line {lineno}: 非 JSON 对象, 已中止 (dst 未被写入)")
                rows_in += 1
                out = migrate_row(rec, gate_fn, pool)
                errs = validate_verdict(out)
                if errs:
                    raise SystemExit(
                        f"[migrate] line {lineno}: 迁移行未通过 v2 校验 {errs}, 已中止 (dst 未被写入)")
                fdst.write(json.dumps(out, ensure_ascii=False) + "\n")
                if out["status"] == "migration_failed":
                    fail_count += 1
                    print(f"[migrate] WARN line {lineno} variant_id={out.get('variant_id')} "
                          f"{out.get('error_message')}", file=sys.stderr)
                else:
                    ok_count += 1
        os.replace(tmp, dst)
    except BaseException:
        # 中止路径: 清理 tmp 残留 (dst 未受影响), 校验失败/异常均不留垃圾文件
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print(f"[migrate] 完成: 输入 {rows_in} 行 -> 输出 {rows_in} 行 "
          f"(ok {ok_count} / migration_failed {fail_count}) -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
