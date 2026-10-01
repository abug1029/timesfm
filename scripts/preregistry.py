"""预注册纯逻辑：冻结字段、入队、确认集、no-peek、个体标签。

不写文件，不读时钟。样本量只调用 cascade.statistical_tests.n_required。
途径 B：传入的 var_lr 已是 HAC 长程方差，调用时 vif 固定为 1，禁止再乘规划 VIF。
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cascade.statistical_tests import n_required

# 写入后不可改。改任一字段必须新开一条预注册。
FROZEN_FIELDS = (
    "symbol",
    "cov_fingerprint",
    "model_fingerprint",
    "predict_params",
    "horizon",
    "metric_version",
    "n_confirm_required",
    "registered_at",
    "confirm_from_ts",
    "delta_star",
    "power",
    "alpha",
    "var_lr",
)

# confirm_from_ts / registered_at 只走 new_preregistration 的关键字参数。
_CHANGEABLE_FIELDS = (
    "symbol",
    "cov_fingerprint",
    "model_fingerprint",
    "predict_params",
    "horizon",
    "metric_version",
    "n_confirm_required",
    "delta_star",
    "power",
    "alpha",
    "var_lr",
)

_REQUIRED_INPUT = (
    "symbol",
    "cov_fingerprint",
    "model_fingerprint",
    "predict_params",
    "horizon",
    "metric_version",
    "registered_at",
    "confirm_from_ts",
    "delta_star",
    "power",
    "alpha",
    "var_lr",
    "kill_condition",
    "promote_condition",
    "mechanism",
    "predicted_direction",
)
_OPTIONAL_INPUT = ("jev", "n_confirm_required", "n_planned")

TERMINAL_STATES = frozenset({
    "confirmed",
    "refuted",
    "underpowered",
    "abandoned",
    "timeout",
    "refuted_by_contamination",
})

_DM_STATUS_OK = frozenset({"ok", "set_mismatch_ok"})

# 表外品种用 jd 的保守 Var_LR。名字未规范化，调用方传入规范拼写。
_SYMBOL_VAR_LR = {
    "jd": 1.240,
    "m": 1.056,
    "rb": 1.223,
    "sr": 1.020,
    "ss": 1.154,
}
_DEFAULT_VAR_LR = 1.240

_REFUTED_NOTE = "未在预定样本量上检出优于基线的效应；不得表述为小效应无效"


@dataclass(frozen=True)
class Prereg:
    prereg_id: str
    symbol: str
    cov_fingerprint: object
    model_fingerprint: object
    predict_params: object
    horizon: object
    metric_version: str
    n_confirm_required: int
    registered_at: str
    confirm_from_ts: str
    delta_star: object
    power: object
    alpha: object
    var_lr: object
    kill_condition: dict
    promote_condition: dict
    mechanism: str
    predicted_direction: str
    n_planned: int | None = None
    jev: dict | None = None
    terminal_state: str | None = None


@dataclass(frozen=True)
class QueueDecision:
    accepted: bool
    reason: str | None
    run_label: str | None
    prereg_id: str | None


@dataclass(frozen=True)
class PeekDecision:
    allowed: bool
    audit: dict | None


@dataclass(frozen=True)
class Seal:
    terminal_state: str
    n_confirm_actual: object
    n_confirm_required: object


def n_confirm_required(var_lr: float) -> int:
    # var_lr 已是长程方差，vif 固定为 1，禁止再乘。
    return n_required(var_d=var_lr, vif=1.0, delta=0.08)


def n_confirm_required_for_symbol(symbol: str) -> int:
    return n_confirm_required(_SYMBOL_VAR_LR.get(symbol, _DEFAULT_VAR_LR))


def _snapshot(value):
    return copy.deepcopy(value)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty str")
    return value


def _condition(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(
            f"{name} must be a dict with string field and numeric threshold, not free text"
        )
    if "field" not in value or "threshold" not in value:
        raise ValueError(f"{name} must contain field and threshold")
    if not isinstance(value["field"], str) or value["field"] == "":
        raise ValueError(f"{name} field must be a non-empty str")
    if not _is_number(value["threshold"]):
        raise ValueError(f"{name} threshold must be a number")
    return _snapshot(value)


def _get(row: Prereg | Mapping, key: str, default=None):
    if isinstance(row, Prereg):
        return getattr(row, key)
    if isinstance(row, Mapping):
        return row.get(key, default)
    raise TypeError(f"record must be Prereg or mapping, got {type(row).__name__}")


def _prereg_id(row: Prereg | Mapping) -> str | None:
    value = _get(row, "prereg_id")
    if isinstance(value, str) and value != "":
        return value
    return None


def _mint_id(reserved: set[str]) -> str:
    prereg_id = uuid.uuid4().hex
    while prereg_id in reserved:
        prereg_id = uuid.uuid4().hex
    return prereg_id


def _require_locked_effect(delta_star: object, power: object, alpha: object) -> None:
    # (a′) 只接受这三个字面量。0.80 == 0.8，用 == 即可。
    if delta_star != 0.08:
        raise ValueError(f"delta_star must be 0.08, got {delta_star!r}")
    if power != 0.80:
        raise ValueError(f"power must be 0.80, got {power!r}")
    if alpha != 0.05:
        raise ValueError(f"alpha must be 0.05, got {alpha!r}")


def _optional_n_planned(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"n_planned must be a non-negative int, got {value!r}")
    return value


def _locked_n(var_lr: object, supplied: object) -> int:
    computed = n_confirm_required(var_lr)
    if supplied is not None and supplied != computed:
        raise ValueError(
            f"n_confirm_required {supplied!r} does not match n_required(var_lr)={computed}"
        )
    return computed


def register(fields: Mapping, existing: Sequence) -> Prereg:
    """分配新 prereg_id。不修改 existing。"""
    if not isinstance(fields, Mapping):
        raise TypeError("fields must be a mapping")
    unknown = set(fields) - set(_REQUIRED_INPUT) - set(_OPTIONAL_INPUT)
    if unknown:
        raise ValueError(f"unknown fields: {sorted(unknown)}")
    missing = [key for key in _REQUIRED_INPUT if key not in fields]
    if missing:
        raise ValueError(f"missing fields: {missing}")

    symbol = _require_text(fields["symbol"], "symbol")
    metric_version = _require_text(fields["metric_version"], "metric_version")
    registered_at = _require_text(fields["registered_at"], "registered_at")
    confirm_from_ts = _require_text(fields["confirm_from_ts"], "confirm_from_ts")
    mechanism = _require_text(fields["mechanism"], "mechanism")
    predicted_direction = _require_text(fields["predicted_direction"], "predicted_direction")
    _require_locked_effect(fields["delta_star"], fields["power"], fields["alpha"])
    n_value = _locked_n(fields["var_lr"], fields.get("n_confirm_required"))
    n_planned = _optional_n_planned(fields.get("n_planned"))
    jev = fields.get("jev")
    if jev is not None and not isinstance(jev, dict):
        raise ValueError("jev must be a dict when present")

    reserved = {pid for row in existing if (pid := _prereg_id(row)) is not None}
    return Prereg(
        prereg_id=_mint_id(reserved),
        symbol=symbol,
        cov_fingerprint=_snapshot(fields["cov_fingerprint"]),
        model_fingerprint=_snapshot(fields["model_fingerprint"]),
        predict_params=_snapshot(fields["predict_params"]),
        horizon=fields["horizon"],
        metric_version=metric_version,
        n_confirm_required=n_value,
        registered_at=registered_at,
        confirm_from_ts=confirm_from_ts,
        delta_star=fields["delta_star"],
        power=fields["power"],
        alpha=fields["alpha"],
        var_lr=fields["var_lr"],
        kill_condition=_condition(fields["kill_condition"], "kill_condition"),
        promote_condition=_condition(fields["promote_condition"], "promote_condition"),
        mechanism=mechanism,
        predicted_direction=predicted_direction,
        n_planned=n_planned,
        jev=None if jev is None else _snapshot(jev),
        terminal_state=None,
    )


def new_preregistration(
    old: Prereg,
    changes: Mapping,
    *,
    confirm_from_ts: str,
    registered_at: str,
) -> Prereg:
    """新 id。确认起点必须字典序严格大于旧值，且不继承旧确认结果。"""
    if not isinstance(old, Prereg):
        raise TypeError("old must be a Prereg")
    if not isinstance(changes, Mapping):
        raise TypeError("changes must be a mapping")
    unknown = set(changes) - set(_CHANGEABLE_FIELDS)
    if unknown:
        raise ValueError(
            f"changes may only set frozen fields {list(_CHANGEABLE_FIELDS)}, got {sorted(unknown)}"
        )
    confirm_from_ts = _require_text(confirm_from_ts, "confirm_from_ts")
    registered_at = _require_text(registered_at, "registered_at")
    # 字典序：调用方给出的规范字符串原样比较，不解析、不改写。
    if not (confirm_from_ts > old.confirm_from_ts):
        raise ValueError(
            "confirm_from_ts must differ from the locked value and be lexicographically greater"
        )

    values = {field: _snapshot(getattr(old, field)) for field in _CHANGEABLE_FIELDS}
    for key, value in changes.items():
        values[key] = _snapshot(value)
    # 没改 var_lr / n 时沿用旧的冻结样本量；改了就必须跟 n_required 一致。
    if "var_lr" in changes or "n_confirm_required" in changes:
        values["n_confirm_required"] = _locked_n(
            values["var_lr"],
            changes["n_confirm_required"] if "n_confirm_required" in changes else None,
        )
    # (a′) 效应量在新预注册上也不许改。其他冻结字段仍可换新 id。
    _require_locked_effect(values["delta_star"], values["power"], values["alpha"])

    return Prereg(
        prereg_id=_mint_id({old.prereg_id}),
        symbol=values["symbol"],
        cov_fingerprint=values["cov_fingerprint"],
        model_fingerprint=values["model_fingerprint"],
        predict_params=values["predict_params"],
        horizon=values["horizon"],
        metric_version=_require_text(values["metric_version"], "metric_version"),
        n_confirm_required=values["n_confirm_required"],
        registered_at=registered_at,
        confirm_from_ts=confirm_from_ts,
        delta_star=values["delta_star"],
        power=values["power"],
        alpha=values["alpha"],
        var_lr=values["var_lr"],
        kill_condition=_snapshot(old.kill_condition),
        promote_condition=_snapshot(old.promote_condition),
        mechanism=old.mechanism,
        predicted_direction=old.predicted_direction,
        n_planned=old.n_planned,
        jev=_snapshot(old.jev),
        terminal_state=None,
    )


def validate_reuse(old: Prereg | Mapping, claimed: Prereg | Mapping) -> None:
    """旧 id 配上不同冻结字段即拒绝。消息含 prereg_immutable。"""
    old_id = _prereg_id(old)
    claimed_id = _prereg_id(claimed)
    if old_id is None or claimed_id is None or old_id != claimed_id:
        raise ValueError(
            f"prereg_immutable: reuse requires the same prereg_id, got {old_id!r} vs {claimed_id!r}"
        )
    for field in FROZEN_FIELDS:
        if _get(old, field) != _get(claimed, field):
            raise ValueError(f"prereg_immutable: {field}")


def validate_registry(records: Sequence, *, require_terminal: bool) -> None:
    seen: set[str] = set()
    for row in records:
        prereg_id = _prereg_id(row)
        if prereg_id is None:
            raise ValueError("prereg_id is required")
        if prereg_id in seen:
            raise ValueError(f"duplicate prereg_id: {prereg_id}")
        seen.add(prereg_id)
        terminal = _get(row, "terminal_state")
        if terminal is None:
            if require_terminal:
                raise ValueError(f"missing terminal_state: {prereg_id}")
            continue
        if terminal not in TERMINAL_STATES:
            raise ValueError(f"invalid terminal_state: {terminal!r}")


def queue_decision(proposal: Mapping, registry: Sequence, *, run_mode: str) -> QueueDecision:
    if run_mode not in {"exploration", "confirmation"}:
        raise ValueError(
            f"run_mode must be 'exploration' or 'confirmation', got {run_mode!r}"
        )
    if not isinstance(proposal, Mapping):
        raise TypeError("proposal must be a mapping")
    # skip_suggested 只是建议，不参与拒绝。
    prereg_id = proposal.get("prereg_id")
    stored_id = prereg_id if isinstance(prereg_id, str) and prereg_id != "" else None
    if run_mode == "exploration":
        return QueueDecision(
            accepted=True,
            reason=None,
            run_label="exploratory_unconfirmed",
            prereg_id=stored_id,
        )

    matched = None
    if stored_id is not None:
        for row in registry:
            if _prereg_id(row) == stored_id:
                matched = row
                break
    registered_at = None if matched is None else _get(matched, "registered_at")
    if matched is None or not isinstance(registered_at, str) or registered_at == "":
        return QueueDecision(
            accepted=False,
            reason="no_prereg_id",
            run_label=None,
            prereg_id=stored_id,
        )
    return QueueDecision(
        accepted=True,
        reason=None,
        run_label=None,
        prereg_id=stored_id,
    )


def confirmation_cutoffs(planned: Sequence, confirm_from_ts: str) -> list:
    """留下 planned 中字典序 >= confirm_from_ts 的点，保持原顺序。"""
    return [cutoff for cutoff in planned if cutoff >= confirm_from_ts]


def pair_cutoffs(variant_cutoffs: Sequence, baseline_cutoffs: Sequence) -> list:
    """按 variant 的顺序取交集。"""
    baseline = set(baseline_cutoffs)
    return [cutoff for cutoff in variant_cutoffs if cutoff in baseline]


def pair_set_hash(cutoffs: Sequence | None) -> str | None:
    if not cutoffs:
        return None
    payload = json.dumps(list(cutoffs), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def peek_gate(n_actual: object, n_required: object) -> PeekDecision:
    """未达样本量则拒绝。只返回审计字典，不写文件。"""
    if n_actual < n_required:
        return PeekDecision(
            allowed=False,
            audit={
                "event": "no_peek_rejected",
                "n_actual": n_actual,
                "n_required": n_required,
            },
        )
    return PeekDecision(allowed=True, audit=None)


def early_seal(n_actual: object, n_required: object) -> Seal:
    if n_actual >= n_required:
        raise ValueError(
            "early_seal requires n_actual < n_required; a full sample is not an early seal"
        )
    return Seal(
        terminal_state="underpowered",
        n_confirm_actual=n_actual,
        n_confirm_required=n_required,
    )


def _test_invalid(row: Mapping) -> bool:
    return (
        row.get("pairing_valid") is not True
        or row.get("missingness_admissible") is not True
        or row.get("protocol_compatible") is not True
        or row.get("dm_status") not in _DM_STATUS_OK
    )


def _passes_confirmation(row: Mapping) -> bool:
    return (
        row.get("gate_pass") is True
        and row.get("p_value") is not None
        and row.get("covariates_used") is True
        and row.get("pairing_valid") is True
        and row.get("missingness_admissible") is True
        and row.get("protocol_compatible") is True
        and row.get("dm_significant") is True
        and row.get("dm_status") in _DM_STATUS_OK
    )


def classify_confirmation(row: Mapping) -> str:
    """个体标签。fdr_pass 不参与。只接受 run_mode='confirmation'。"""
    if not isinstance(row, Mapping):
        raise TypeError("row must be a mapping")
    if row.get("run_mode") != "confirmation":
        raise ValueError("classify_confirmation requires run_mode='confirmation'")
    # 顺序固定：污染 > 样本/信息不足 > 检验无效或未通过 > 个体通过。
    if row.get("contaminated") is True:
        return "refuted_by_contamination"
    if (
        row.get("early_sealed") is True
        or row.get("common_insufficient") is True
        or row.get("meets_min_info") is not True
    ):
        return "underpowered"
    if "n_confirm_actual" not in row or "n_confirm_required" not in row:
        raise ValueError(
            "classify_confirmation requires n_confirm_actual and n_confirm_required"
        )
    if row["n_confirm_actual"] < row["n_confirm_required"]:
        return "underpowered"
    if _passes_confirmation(row):
        return "confirmed"
    if _test_invalid(row):
        return "underpowered"
    return "refuted"


def counts_as_success(row: Mapping) -> bool:
    if classify_confirmation(row) != "confirmed":
        return False
    return row.get("fdr_pass") is True


def judgment_note(run_label: str) -> str:
    if run_label != "refuted":
        raise ValueError(f"no judgment note for run_label={run_label!r}")
    return _REFUTED_NOTE


def checkpoint_filename(variant_id, prereg_id):
    """确认与探索分文件。有 prereg_id 时带其前 8 位，否则沿用 {variant_id}.jsonl。"""
    if prereg_id:
        return f"{variant_id}__prereg_{prereg_id[:8]}.jsonl"
    return f"{variant_id}.jsonl"
