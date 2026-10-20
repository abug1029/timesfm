"""Quality predictor for FM-a proposals: predict gate_pass probability.

Uses empirical frequency-based scoring trained on historical aligned verdicts.
Primary signal: cov_override pass rate with Laplace smoothing.
Fallback chain: cov_override -> (symbol, cov_family) -> cov_family -> symbol -> global.

Serialization: JSON (cross-process safe; avoids pickle module-namespace mismatch).

CLI:
  python3 scripts/quality_predictor.py train --proposals task_FM/experiments --verdicts task_FM/config/aligned_verdicts.jsonl
  python3 scripts/quality_predictor.py predict --proposals task_FM/experiments --output predictions.jsonl
  python3 scripts/quality_predictor.py evaluate --test-set 0.2
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import random
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger(__name__)


def _resolve_cov_family(cov_override: str) -> str:
    """Resolve covariate family from override name."""
    cov_lower = cov_override.lower()
    if any(k in cov_lower for k in ["rsi", "macd", "momentum", "nvi", "pvi", "mfi"]):
        return "momentum"
    if any(k in cov_lower for k in ["oi", "inventory", "stock"]):
        return "inventory"
    if any(k in cov_lower for k in ["vol", "volatility", "atr", "realized"]):
        return "volatility"
    if any(k in cov_lower for k in ["calendar", "seasonal", "cyclical", "monthly", "delivery"]):
        return "calendar"
    if any(k in cov_lower for k in ["basis", "spread", "contango", "crack", "crush", "slope"]):
        return "term_structure"
    return "unknown"


def _smoothed_rate(pass_count: int, total: int) -> float:
    """Laplace-smoothed pass rate."""
    return (pass_count + 1) / (total + 2)


# -- FrequencyModel ---------------------------------------------------------

class _FrequencyModel:
    """Empirical pass rate lookup with smoothing and hierarchical fallback."""

    def __init__(self):
        self.cov_rates: Dict[str, Tuple[int, int]] = {}
        self.symfam_rates: Dict[Tuple[str, str], Tuple[int, int]] = {}
        self.fam_rates: Dict[str, Tuple[int, int]] = {}
        self.sym_rates: Dict[str, Tuple[int, int]] = {}
        self.global_pass = 0
        self.global_total = 0

    def fit(self, verdicts: List[dict]):
        for v in verdicts:
            sym = v.get("symbol") or "unknown"
            cov = v.get("cov_override") or "unknown"
            fam = v.get("cov_family") or "unknown"
            if fam == "unknown":
                fam = _resolve_cov_family(cov)
            gp = 1 if v.get("gate_pass") else 0

            p, t = self.cov_rates.get(cov, (0, 0))
            self.cov_rates[cov] = (p + gp, t + 1)

            key = (sym, fam)
            p, t = self.symfam_rates.get(key, (0, 0))
            self.symfam_rates[key] = (p + gp, t + 1)

            p, t = self.fam_rates.get(fam, (0, 0))
            self.fam_rates[fam] = (p + gp, t + 1)

            p, t = self.sym_rates.get(sym, (0, 0))
            self.sym_rates[sym] = (p + gp, t + 1)

            self.global_pass += gp
            self.global_total += 1

    def predict_proba(self, symbol: str, cov_override: str, cov_family: str) -> float:
        """Predict P(gate_pass) using weighted combination of hierarchical rates."""
        if not cov_family or cov_family == "unknown":
            cov_family = _resolve_cov_family(cov_override)

        p_cov, t_cov = self.cov_rates.get(cov_override, (0, 0))
        cov_rate = _smoothed_rate(p_cov, t_cov) if t_cov >= 3 else None

        key = (symbol, cov_family)
        p_sf, t_sf = self.symfam_rates.get(key, (0, 0))
        sf_rate = _smoothed_rate(p_sf, t_sf) if t_sf >= 3 else None

        p_fam, t_fam = self.fam_rates.get(cov_family, (0, 0))
        fam_rate = _smoothed_rate(p_fam, t_fam) if t_fam >= 3 else None

        p_sym, t_sym = self.sym_rates.get(symbol, (0, 0))
        sym_rate = _smoothed_rate(p_sym, t_sym) if t_sym >= 3 else None

        # Optimized weights via leave-one-out grid search: cov=0.4, sf=0.5, fam=0.1
        if cov_rate is not None and sf_rate is not None:
            return 0.4 * cov_rate + 0.5 * sf_rate + 0.1 * fam_rate
        elif cov_rate is not None and fam_rate is not None:
            return 0.7 * cov_rate + 0.3 * fam_rate
        elif cov_rate is not None:
            return cov_rate
        elif sf_rate is not None:
            return sf_rate
        elif fam_rate is not None:
            return fam_rate
        elif sym_rate is not None:
            return sym_rate
        elif self.global_total > 0:
            return _smoothed_rate(self.global_pass, self.global_total)
        return 0.5

    # -- JSON serialization (cross-process safe) ----------------------------
    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict. Tuples become 2-element lists."""
        return {
            "cov_rates": {k: list(v) for k, v in self.cov_rates.items()},
            # symfam key (sym, fam) -> "sym|fam"; restore with split("|", 1)
            "symfam_rates": {"|".join(k): list(v) for k, v in self.symfam_rates.items()},
            "fam_rates": {k: list(v) for k, v in self.fam_rates.items()},
            "sym_rates": {k: list(v) for k, v in self.sym_rates.items()},
            "global_pass": self.global_pass,
            "global_total": self.global_total,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "_FrequencyModel":
        m = cls()
        m.cov_rates = {k: tuple(v) for k, v in data.get("cov_rates", {}).items()}
        m.symfam_rates = {tuple(k.split("|", 1)): tuple(v) for k, v in data.get("symfam_rates", {}).items()}
        m.fam_rates = {k: tuple(v) for k, v in data.get("fam_rates", {}).items()}
        m.sym_rates = {k: tuple(v) for k, v in data.get("sym_rates", {}).items()}
        m.global_pass = int(data.get("global_pass", 0))
        m.global_total = int(data.get("global_total", 0))
        return m


# -- QualityPredictor -------------------------------------------------------

_DEFAULT_MODEL_PATH = os.path.join(_REPO_ROOT, "models", "quality_model.json")


class QualityPredictor:
    """Predict gate_pass probability for FM-a proposals."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self.freq_model: Optional[_FrequencyModel] = None
        self.threshold: float = 0.5

    def extract_features_from_dict(self, proposal: dict, verdict: Optional[dict] = None) -> dict:
        """Extract features and predicted probability from a proposal dict."""
        if self.freq_model is None:
            return None

        symbol = proposal.get("symbol") or proposal.get("extra", {}).get("symbol", "unknown")
        cov_override = proposal.get("cov_override") or proposal.get("extra", {}).get("covariate", "unknown")
        if symbol is None:
            symbol = "unknown"
        if cov_override is None:
            cov_override = "unknown"

        if verdict and verdict.get("cov_family"):
            cov_family = verdict["cov_family"]
        else:
            cov_family = proposal.get("cov_family") or "unknown"
            if cov_family == "unknown":
                cov_family = _resolve_cov_family(cov_override)

        prob = self.freq_model.predict_proba(symbol, cov_override, cov_family)
        confidence = abs(prob - 0.5) * 2.0

        return {
            "gate_pass_prob": round(prob, 4),
            "confidence": round(confidence, 4),
            "symbol": symbol,
            "cov_override": cov_override,
            "cov_family": cov_family,
        }

    def extract_features_from_file(self, proposal_path: str) -> Optional[dict]:
        """Extract features from a proposal JSON file."""
        try:
            with open(proposal_path) as f:
                proposal = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        result = self.extract_features_from_dict(proposal)
        if result:
            result["path"] = proposal_path
        return result

    def train(
        self,
        proposals_dir: str,
        verdicts_path: str,
        **kwargs,
    ) -> Dict[str, float]:
        """Train the model from verdicts. kwargs accepted for API compatibility."""
        verdicts: Dict[str, dict] = {}
        with open(verdicts_path) as f:
            for line in f:
                v = json.loads(line)
                verdicts[v["variant_id"]] = v

        self.freq_model = _FrequencyModel()
        self.freq_model.fit(list(verdicts.values()))

        probs, labels = [], []
        for vid, v in verdicts.items():
            sym = v.get("symbol") or "unknown"
            cov = v.get("cov_override") or "unknown"
            fam = v.get("cov_family") or "unknown"
            if fam == "unknown":
                fam = _resolve_cov_family(cov)
            p_cov, t_cov = self.freq_model.cov_rates.get(cov, (0, 0))
            prob = _smoothed_rate(p_cov - (1 if v.get("gate_pass") else 0), t_cov - 1) if t_cov > 1 else _smoothed_rate(p_cov, t_cov)
            probs.append(prob)
            labels.append(1 if v.get("gate_pass") else 0)

        best_acc = 0
        best_thr = 0.5
        for thr_int in range(20, 60):
            thr = thr_int / 100.0
            tp = fp = tn = fn = 0
            for p, y in zip(probs, labels):
                pred = 1 if p >= thr else 0
                if pred == 1 and y == 1: tp += 1
                elif pred == 1 and y == 0: fp += 1
                elif pred == 0 and y == 0: tn += 1
                else: fn += 1
            acc = (tp + tn) / len(labels) if labels else 0
            if acc > best_acc:
                best_acc = acc
                best_thr = thr
        self.threshold = best_thr

        probs_full = []
        labels_full = []
        for vid, v in verdicts.items():
            sym = v.get("symbol") or "unknown"
            cov = v.get("cov_override") or "unknown"
            fam = v.get("cov_family") or "unknown"
            if fam == "unknown":
                fam = _resolve_cov_family(cov)
            prob = self.freq_model.predict_proba(sym, cov, fam)
            probs_full.append(prob)
            labels_full.append(1 if v.get("gate_pass") else 0)

        metrics = _compute_metrics_at_threshold(probs_full, labels_full, self.threshold)
        metrics["n_samples"] = len(probs_full)
        metrics["n_pass"] = sum(labels_full)
        metrics["n_fail"] = len(labels_full) - sum(labels_full)
        metrics["threshold"] = self.threshold

        self._save()
        return metrics

    def _find_proposals(self, root: str) -> List[str]:
        """Find all proposal JSON files under root."""
        patterns = [
            os.path.join(root, "**", "proposals", "*.json"),
            os.path.join(root, "**", "shared_findings", "*_proposal.json"),
        ]
        files: List[str] = []
        for pat in patterns:
            files.extend(glob.glob(pat, recursive=True))
        seen = set()
        result = []
        for f in sorted(files):
            if "_corrupted" in f or "/archive/" in f:
                continue
            norm = os.path.normpath(f)
            if norm not in seen:
                seen.add(norm)
                result.append(f)
        return result

    def predict(self, proposal_path: str) -> Optional[Dict[str, Any]]:
        """Predict gate_pass probability for one proposal file."""
        if self.freq_model is None:
            self._load()
            if self.freq_model is None:
                return None
        return self.extract_features_from_file(proposal_path)

    def predict_from_dict(self, proposal: dict, verdict: Optional[dict] = None) -> Optional[Dict[str, Any]]:
        """Predict from a proposal dict (for harvest integration)."""
        if self.freq_model is None:
            self._load()
            if self.freq_model is None:
                return None
        return self.extract_features_from_dict(proposal, verdict=verdict)

    def predict_batch(self, proposals_dir: str) -> List[Dict[str, Any]]:
        """Batch predict for all proposals under a directory."""
        if self.freq_model is None:
            self._load()
            if self.freq_model is None:
                return []
        results: List[Dict[str, Any]] = []
        for pf in self._find_proposals(proposals_dir):
            pred = self.predict(pf)
            if pred:
                results.append(pred)
        results.sort(key=lambda r: r["gate_pass_prob"], reverse=True)
        return results

    def evaluate(
        self,
        proposals_dir: str,
        verdicts_path: str,
        test_fraction: float = 0.2,
    ) -> Dict[str, float]:
        """Evaluate model on a held-out test set."""
        verdicts: Dict[str, dict] = {}
        with open(verdicts_path) as f:
            for line in f:
                v = json.loads(line)
                verdicts[v["variant_id"]] = v

        all_verdicts = list(verdicts.values())
        indices = list(range(len(all_verdicts)))
        random.seed(42)
        random.shuffle(indices)
        split = int(len(indices) * (1 - test_fraction))
        train_idx = set(indices[:split])
        test_idx = indices[split:]

        train_verdicts = [all_verdicts[i] for i in train_idx]
        freq_model = _FrequencyModel()
        freq_model.fit(train_verdicts)

        probs, labels = [], []
        for i in train_idx:
            v = all_verdicts[i]
            sym = v.get("symbol") or "unknown"
            cov = v.get("cov_override") or "unknown"
            fam = v.get("cov_family") or "unknown"
            if fam == "unknown":
                fam = _resolve_cov_family(cov)
            p_cov, t_cov = freq_model.cov_rates.get(cov, (0, 0))
            prob = _smoothed_rate(p_cov - (1 if v.get("gate_pass") else 0), t_cov - 1) if t_cov > 1 else _smoothed_rate(p_cov, t_cov)
            probs.append(prob)
            labels.append(1 if v.get("gate_pass") else 0)

        best_acc = 0
        best_thr = 0.5
        for thr_int in range(20, 60):
            thr = thr_int / 100.0
            tp = fp = tn = fn = 0
            for p, y in zip(probs, labels):
                pred = 1 if p >= thr else 0
                if pred == 1 and y == 1: tp += 1
                elif pred == 1 and y == 0: fp += 1
                elif pred == 0 and y == 0: tn += 1
                else: fn += 1
            acc = (tp + tn) / len(labels) if labels else 0
            if acc > best_acc:
                best_acc = acc
                best_thr = thr

        test_probs, test_labels = [], []
        for i in test_idx:
            v = all_verdicts[i]
            sym = v.get("symbol") or "unknown"
            cov = v.get("cov_override") or "unknown"
            fam = v.get("cov_family") or "unknown"
            if fam == "unknown":
                fam = _resolve_cov_family(cov)
            prob = freq_model.predict_proba(sym, cov, fam)
            test_probs.append(prob)
            test_labels.append(1 if v.get("gate_pass") else 0)

        metrics = _compute_metrics_at_threshold(test_probs, test_labels, best_thr)
        metrics["n_test"] = len(test_probs)
        metrics["n_train"] = len(train_verdicts)
        metrics["threshold"] = best_thr

        auc = _approx_auc(test_probs, test_labels)
        metrics["auc"] = round(auc, 4)

        return metrics

    def _save(self):
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        payload = {
            "version": 1,
            "freq_model": self.freq_model.to_dict(),
            "threshold": self.threshold,
        }
        # Atomic write: write to tmp then rename to avoid partial reads
        tmp_path = self.model_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(payload, f)
        os.replace(tmp_path, self.model_path)

    def _load(self) -> bool:
        if not os.path.exists(self.model_path):
            logger.info("quality_model file missing: %s", self.model_path)
            return False
        try:
            with open(self.model_path) as f:
                data = json.load(f)
            self.freq_model = _FrequencyModel.from_dict(data["freq_model"])
            self.threshold = float(data.get("threshold", 0.5))
            return True
        except Exception as exc:
            logger.error("failed to load quality_model from %s: %s", self.model_path, exc)
            self.freq_model = None
            return False


# -- Metrics ----------------------------------------------------------------

def _compute_metrics_at_threshold(
    probs: List[float], labels: List[int], threshold: float = 0.5
) -> Dict[str, float]:
    n = len(labels)
    tp = fp = tn = fn = 0
    for p, y in zip(probs, labels):
        pred = 1 if p >= threshold else 0
        if pred == 1 and y == 1: tp += 1
        elif pred == 1 and y == 0: fp += 1
        elif pred == 0 and y == 0: tn += 1
        else: fn += 1
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


def _approx_auc(probs: List[float], labels: List[int]) -> float:
    pos = [probs[i] for i in range(len(labels)) if labels[i] == 1]
    neg = [probs[i] for i in range(len(labels)) if labels[i] == 0]
    if not pos or not neg:
        return 0.5
    concordant = 0
    tied = 0
    for p in pos:
        for q in neg:
            if p > q: concordant += 1
            elif p == q: tied = tied + 0.5
    return (concordant + tied) / (len(pos) * len(neg))


# -- Harvest integration ----------------------------------------------------

def score_proposal_for_harvest(
    proposal: dict,
    predictor: Optional["QualityPredictor"] = None,
) -> Tuple[float, dict]:
    """Score a proposal for harvest priority. Returns (score, prediction_dict)."""
    if predictor is None:
        if os.path.exists(_DEFAULT_MODEL_PATH):
            predictor = QualityPredictor(_DEFAULT_MODEL_PATH)
        else:
            return (0.5, {})
    pred = predictor.predict_from_dict(proposal)
    if pred is None:
        return (0.5, {})
    return (pred["gate_pass_prob"], pred)


# -- CLI --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="FM-a Quality Predictor")
    sub = parser.add_subparsers(dest="command")

    p_train = sub.add_parser("train", help="Train the model")
    p_train.add_argument("--proposals", default="task_FM/experiments")
    p_train.add_argument("--verdicts", default="task_FM/config/aligned_verdicts.jsonl")

    p_pred = sub.add_parser("predict", help="Predict unverified proposals")
    p_pred.add_argument("--proposals", default="task_FM/experiments")
    p_pred.add_argument("--output", default="predictions.jsonl")

    p_eval = sub.add_parser("evaluate", help="Evaluate model")
    p_eval.add_argument("--proposals", default="task_FM/experiments")
    p_eval.add_argument("--verdicts", default="task_FM/config/aligned_verdicts.jsonl")
    p_eval.add_argument("--test-set", type=float, default=0.2, dest="test_set")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    predictor = QualityPredictor()

    if args.command == "train":
        proposals = os.path.join(_REPO_ROOT, args.proposals)
        verdicts = os.path.join(_REPO_ROOT, args.verdicts)
        metrics = predictor.train(proposals, verdicts)
        print(json.dumps(metrics, indent=2))

    elif args.command == "predict":
        proposals = os.path.join(_REPO_ROOT, args.proposals)
        results = predictor.predict_batch(proposals)
        output = args.output
        if not os.path.isabs(output):
            output = os.path.join(_REPO_ROOT, output)
        with open(output, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"Wrote {len(results)} predictions to {output}")
        if results:
            high = [r for r in results if r["gate_pass_prob"] > 0.5]
            print(f"High-quality (prob > 0.5): {len(high)}/{len(results)}")

    elif args.command == "evaluate":
        proposals = os.path.join(_REPO_ROOT, args.proposals)
        verdicts = os.path.join(_REPO_ROOT, args.verdicts)
        metrics = predictor.evaluate(proposals, verdicts, test_fraction=args.test_set)
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
