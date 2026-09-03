"""
Walk-forward optimization framework for covariate testing.

**NOT for SCHEMES solidification (CF-19 A).** Uses IS-IR selection, not PF/EV.
Solidify only via ``scripts/monthly_backtest.py`` + validation_criteria v2.

Provides IS/OOS (In-Sample/Out-of-Sample) validation for regime research only.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Callable, Tuple, Optional
from itertools import combinations


class WalkForwardOptimizer:
    """
    Walk-forward optimizer for testing covariate combinations.

    Implements:
    - IS/OOS period separation
    - Multiple fold cross-validation
    - Information Ratio evaluation
    - Maximum Drawdown tracking
    - OOS decay validation
    """

    def __init__(
        self,
        is_period: Tuple[str, str],
        oos_period: Tuple[str, str],
        n_splits: int = 5
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            is_period: (start_date, end_date) for in-sample period
            oos_period: (start_date, end_date) for out-of-sample period
            n_splits: Number of cross-validation folds
        """
        self.is_period = is_period
        self.oos_period = oos_period
        self.n_splits = n_splits

        # Evaluation thresholds
        self.min_ir_improvement = 0.3
        self.max_maxdd_deterioration = 0.10
        self.max_oos_decay = 0.30

    def create_folds(self, dates: pd.DatetimeIndex) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
        """
        Create cross-validation folds within IS period.

        Args:
            dates: DatetimeIndex of available dates

        Returns:
            List of (train_dates, val_dates) tuples
        """
        # Filter to IS period
        is_start = pd.Timestamp(self.is_period[0])
        is_end = pd.Timestamp(self.is_period[1])
        is_dates = dates[(dates >= is_start) & (dates <= is_end)]

        if len(is_dates) < self.n_splits * 2:
            raise ValueError(f"Insufficient IS dates: {len(is_dates)} < {self.n_splits * 2}")

        # Split into folds
        fold_size = len(is_dates) // self.n_splits
        folds = []

        for i in range(self.n_splits):
            val_start_idx = i * fold_size
            val_end_idx = (i + 1) * fold_size if i < self.n_splits - 1 else len(is_dates)

            val_dates = is_dates[val_start_idx:val_end_idx]
            train_dates = is_dates[~is_dates.isin(val_dates)]

            folds.append((train_dates, val_dates))

        return folds

    def evaluate_combination(
        self,
        returns: pd.Series,
        dates: pd.DatetimeIndex,
        covariate_weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Evaluate a covariate combination's performance.

        Args:
            returns: Return series (already weighted combination of covariate returns)
            dates: DatetimeIndex aligned with returns
            covariate_weights: Deprecated - kept for API compatibility, not used

        Returns:
            Dictionary with performance metrics

        Note:
            covariate_weights parameter is deprecated. Apply weights when constructing
            the `returns` series instead (see `optimize` method for example).
        """
        # Filter to valid dates
        valid_mask = ~returns.isna()
        valid_returns = returns[valid_mask]

        if len(valid_returns) == 0:
            return {
                'mean_return': 0,
                'std_return': 0,
                'information_ratio': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'win_rate': 0
            }

        # Calculate metrics
        mean_return = valid_returns.mean()
        std_return = valid_returns.std()

        # Information Ratio (mean / std)
        ir = mean_return / std_return if std_return > 0 else 0

        # Sharpe Ratio (assuming risk-free rate = 0)
        sharpe = ir

        # Maximum Drawdown
        cumulative = (1 + valid_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_dd = drawdown.min()

        # Win Rate
        win_rate = (valid_returns > 0).sum() / len(valid_returns)

        return {
            'mean_return': mean_return,
            'std_return': std_return,
            'information_ratio': ir,
            'max_drawdown': max_dd,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate
        }

    def optimize(
        self,
        covariate_returns: Dict[str, pd.Series],
        evaluation_fn: Optional[Callable] = None
    ) -> Dict[str, any]:
        """
        Optimize covariate combination using walk-forward validation.

        Args:
            covariate_returns: Dictionary mapping covariate names to return series
            evaluation_fn: Optional custom evaluation function

        Returns:
            Dictionary with optimization results
        """
        if evaluation_fn is None:
            evaluation_fn = self.evaluate_combination

        # Get all dates
        all_dates = None
        for cov_name, cov_returns in covariate_returns.items():
            if all_dates is None:
                all_dates = cov_returns.index
            else:
                all_dates = all_dates.union(cov_returns.index)

        # Create IS folds
        folds = self.create_folds(all_dates)

        # Test all covariate combinations (1-3 covariates)
        covariate_names = list(covariate_returns.keys())
        best_combination = None
        best_is_ir = -np.inf
        best_oos_metrics = None

        # Test combinations of size 1 to 3
        for combo_size in range(1, min(4, len(covariate_names) + 1)):
            for combo in combinations(covariate_names, combo_size):
                # Create weighted returns (equal weights)
                combo_returns = pd.Series(0, index=all_dates)
                for cov_name in combo:
                    combo_returns += covariate_returns[cov_name]
                combo_returns /= len(combo)

                # Cross-validation on IS
                is_irs = []
                is_maxdds = []

                for train_dates, val_dates in folds:
                    val_returns = combo_returns.loc[val_dates]
                    metrics = evaluation_fn(val_returns, val_dates)
                    is_irs.append(metrics['information_ratio'])
                    is_maxdds.append(metrics['max_drawdown'])

                # Average IS metrics
                avg_is_ir = np.mean(is_irs)
                avg_is_maxdd = np.mean(is_maxdds)

                # Fix: Skip combinations with non-positive IS performance
                # to avoid incorrect OOS decay calculation with negative IR
                if avg_is_ir <= 0:
                    continue

                # Evaluate on OOS
                oos_start = pd.Timestamp(self.oos_period[0])
                oos_end = pd.Timestamp(self.oos_period[1])
                oos_dates = all_dates[(all_dates >= oos_start) & (all_dates <= oos_end)]
                oos_returns = combo_returns.loc[oos_dates]
                oos_metrics = evaluation_fn(oos_returns, oos_dates)

                # Check acceptance criteria
                ir_improvement = avg_is_ir - 0  # Compare to baseline IR of 0
                maxdd_deterioration = abs(avg_is_maxdd)  # Absolute drawdown

                # OOS decay check
                if oos_metrics['information_ratio'] != 0 and avg_is_ir != 0:
                    oos_decay = 1 - (oos_metrics['information_ratio'] / avg_is_ir)
                else:
                    oos_decay = 1.0

                # Accept if meets criteria
                if (ir_improvement >= self.min_ir_improvement and
                    maxdd_deterioration <= self.max_maxdd_deterioration and
                    oos_decay <= self.max_oos_decay):

                    # Check if better than current best
                    if avg_is_ir > best_is_ir:
                        best_is_ir = avg_is_ir
                        best_combination = list(combo)
                        best_oos_metrics = oos_metrics

        if best_combination is None:
            return {
                'success': False,
                'message': 'No combination met acceptance criteria',
                'best_combination': None,
                'is_metrics': {},
                'oos_metrics': {}
            }

        return {
            'success': True,
            'best_combination': best_combination,
            'is_ir': best_is_ir,
            'oos_metrics': best_oos_metrics,
            'n_combinations_tested': sum(
                len(list(combinations(covariate_names, k)))
                for k in range(1, min(4, len(covariate_names) + 1))
            )
        }

    def validate_oos_stability(
        self,
        is_metrics: Dict[str, float],
        oos_metrics: Dict[str, float]
    ) -> Dict[str, any]:
        """
        Validate that OOS performance is stable relative to IS.

        Args:
            is_metrics: IS performance metrics
            oos_metrics: OOS performance metrics

        Returns:
            Dictionary with stability analysis
        """
        # Calculate decay ratios
        ir_decay = 1 - (oos_metrics['information_ratio'] / is_metrics['information_ratio'])
        sharpe_decay = 1 - (oos_metrics['sharpe_ratio'] / is_metrics['sharpe_ratio'])

        # MaxDD should not deteriorate significantly
        maxdd_ratio = oos_metrics['max_drawdown'] / is_metrics['max_drawdown']

        # Stability score (0-1, higher is better)
        stability_score = np.mean([
            1 - abs(ir_decay),
            1 - abs(sharpe_decay),
            1 - abs(maxdd_ratio - 1)
        ])

        return {
            'ir_decay': ir_decay,
            'sharpe_decay': sharpe_decay,
            'maxdd_ratio': maxdd_ratio,
            'stability_score': stability_score,
            'is_stable': stability_score > 0.7 and ir_decay < self.max_oos_decay
        }


def run_walk_forward_test(
    covariate_data: Dict[str, pd.Series],
    is_period: Tuple[str, str],
    oos_period: Tuple[str, str],
    n_splits: int = 5
) -> Dict[str, any]:
    """
    Convenience function to run walk-forward optimization.

    Args:
        covariate_data: Dictionary of covariate return series
        is_period: IS period (start, end)
        oos_period: OOS period (start, end)
        n_splits: Number of CV folds

    Returns:
        Optimization results dictionary
    """
    optimizer = WalkForwardOptimizer(is_period, oos_period, n_splits)
    return optimizer.optimize(covariate_data)
