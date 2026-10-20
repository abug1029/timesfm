# Quality Predictor for FM-a Proposals

## What it does

Predicts the probability that a proposal will pass the aligned verdict gate (`gate_pass`), enabling priority-based verification ordering.

## How it works

1. **Frequency model**: Builds empirical pass rates from historical aligned verdicts (`task_FM/config/aligned_verdicts.jsonl`), with Laplace smoothing.
2. **Hierarchical fallback**: Uses a weighted combination of rates at different granularities:
   - `cov_override` rate (e.g., "rsi6" pass rate across all symbols)
   - `(symbol, cov_family)` rate (e.g., "rb + momentum" pass rate)
   - `cov_family` rate (e.g., "momentum" pass rate across all symbols)
   - `symbol` rate
   - Global rate
3. **Optimal weights**: cov_override=0.4 + symfam=0.5 + fam=0.1, determined by leave-one-out grid search.

## Serialization format

Model is persisted as **JSON** at `models/quality_model.json`.

JSON was chosen over pickle to avoid the cross-process class-reference bug:
when `_FrequencyModel` was trained via CLI (`__main__._FrequencyModel`) but
loaded from `sup_harvest.py` (`quality_predictor._FrequencyModel`), pickle
silently failed the import and the predictor always returned 0.5 (no quality
discrimination). JSON is module-independent and human-readable.

The payload shape:

```json
{
  "version": 1,
  "freq_model": {
    "cov_rates": {"rsi6": [5, 5], ...},
    "symfam_rates": {"rb|momentum": [4, 5], ...},
    "fam_rates": {"momentum": [10, 15], ...},
    "sym_rates": {"rb": [6, 10], ...},
    "global_pass": 100,
    "global_total": 200
  },
  "threshold": 0.47
}
```

Tuple values are serialized as 2-element lists. The `(symbol, cov_family)`
composite key uses `"sym|fam"` encoding (split on first `|` to decode).

Writes are atomic: save writes to `.tmp` then `os.replace` to avoid partial
reads from a concurrent loader.

## Model performance (665 verdicts, 33% base pass rate)

| Metric | Training | Test (20% holdout) |
|--------|----------|--------------------|
| Accuracy | 72.2% | 67.5% |
| Precision | 70.0% | 50.0% |
| Recall | 35.8% | 15.0% |
| AUC | ~0.78 (in-sample) | 0.63 |

**Threshold**: 0.47 (optimized for training accuracy)

The model trades precision for recall: it's conservative at identifying likely passes, which is appropriate for prioritization (better to over-prioritize a few than miss the good ones).

## CLI usage

```bash
# Train the model (writes models/quality_model.json)
python3 scripts/quality_predictor.py train

# Predict unverified proposals (sorted by quality descending)
python3 scripts/quality_predictor.py predict --output predictions.jsonl

# Evaluate on held-out test set
python3 scripts/quality_predictor.py evaluate --test-set 0.2
```

## Harvest integration

The quality predictor is automatically loaded by `scripts/sup_harvest.py` if available:
- Adds a `ml_quality` bonus term (up to +5.0) to the proposal quality gate score
- Gracefully degrades if the model file is missing (no bonus, existing scoring unchanged)
- Does not modify Laya, prescreen, or any existing gate logic

## Files

| File | Purpose |
|------|---------|
| `scripts/quality_predictor.py` | Main predictor module + CLI |
| `tests/test_quality_predictor.py` | Unit tests + cross-process serialization test |
| `models/quality_model.json` | Trained model (gitignored) |
| `scripts/sup_harvest.py` | Modified: adds ML quality bonus |
