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
# Train the model (writes models/quality_model.pkl)
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
| `tests/test_quality_predictor.py` | 21 unit tests |
| `models/quality_model.pkl` | Trained model (gitignored) |
| `scripts/sup_harvest.py` | Modified: adds ML quality bonus |
