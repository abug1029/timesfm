"""
Sandbox deployment monitor for tracking covariate performance.

Monitors deployed covariate configurations against expected backtest curves
to detect performance degradation early.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class SandboxMonitor:
    """
    Monitor deployed covariate configurations against expected performance.

    Tracks:
    - Predicted vs actual performance for each variety
    - Deviation alerts when performance diverges
    - Historical monitoring events
    """

    def __init__(self, log_file: str = "reports/sandbox_monitor.log"):
        """
        Initialize sandbox monitor.

        Args:
            log_file: Path to monitoring log file
        """
        self.log_file = log_file
        self._setup_logging()

        # Tracking state
        self.variety_history: Dict[str, List[Dict]] = {}
        self.consecutive_deviations: Dict[str, int] = {}

        # Alert thresholds
        self.deviation_tolerance = 0.10  # 10% deviation
        self.consecutive_days_threshold = 5  # 5 consecutive days

    def _setup_logging(self):
        """Setup logging configuration."""
        # Ensure log directory exists
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Configure logger with unique name per instance
        # Fix: Use instance-specific logger name to avoid handler conflicts
        self.logger = logging.getLogger(f'SandboxMonitor.{id(self)}')
        self.logger.setLevel(logging.INFO)

        # Only add handlers if this logger doesn't have any yet
        if not self.logger.handlers:
            # File handler
            fh = logging.FileHandler(self.log_file)
            fh.setLevel(logging.INFO)

            # Console handler
            ch = logging.StreamHandler()
            ch.setLevel(logging.WARNING)

            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            fh.setFormatter(formatter)
            ch.setFormatter(formatter)

            self.logger.addHandler(fh)
            self.logger.addHandler(ch)

    def record_performance(
        self,
        variety: str,
        date: str,
        expected_return: float,
        actual_return: float,
        expected_dir_acc: Optional[float] = None,
        actual_dir_acc: Optional[float] = None
    ) -> Dict:
        """
        Record performance metrics for a variety on a given date.

        Args:
            variety: Variety symbol (e.g., 'RB', 'JM')
            date: Date string (YYYY-MM-DD)
            expected_return: Expected return from backtest
            actual_return: Actual realized return
            expected_dir_acc: Expected directional accuracy
            actual_dir_acc: Actual directional accuracy

        Returns:
            Dictionary with recording details
        """
        if variety not in self.variety_history:
            self.variety_history[variety] = []
            self.consecutive_deviations[variety] = 0

        # Calculate deviations
        return_deviation = abs(actual_return - expected_return) / (abs(expected_return) + 1e-8)

        dir_acc_deviation = None
        if expected_dir_acc is not None and actual_dir_acc is not None:
            dir_acc_deviation = abs(actual_dir_acc - expected_dir_acc)

        # Check alignment
        is_aligned = self.check_alignment(
            variety,
            expected_return,
            actual_return,
            self.deviation_tolerance
        )

        # Record entry
        entry = {
            'date': date,
            'expected_return': expected_return,
            'actual_return': actual_return,
            'return_deviation': return_deviation,
            'expected_dir_acc': expected_dir_acc,
            'actual_dir_acc': actual_dir_acc,
            'dir_acc_deviation': dir_acc_deviation,
            'is_aligned': is_aligned
        }

        self.variety_history[variety].append(entry)

        # Update consecutive deviations
        if not is_aligned:
            self.consecutive_deviations[variety] += 1

            # Alert if threshold exceeded
            if self.consecutive_deviations[variety] >= self.consecutive_days_threshold:
                self.logger.warning(
                    f"ALERT: {variety} has {self.consecutive_deviations[variety]} "
                    f"consecutive days of misalignment. Return deviation: "
                    f"{return_deviation:.2%}"
                )
        else:
            self.consecutive_deviations[variety] = 0

        # Log entry
        self.logger.info(
            f"{variety} | {date} | Expected: {expected_return:.4f} | "
            f"Actual: {actual_return:.4f} | Deviation: {return_deviation:.2%} | "
            f"Aligned: {is_aligned}"
        )

        return entry

    def check_alignment(
        self,
        variety: str,
        expected_curve: float,
        actual_curve: float,
        tolerance: float = 0.10
    ) -> bool:
        """
        Check if actual performance aligns with expected curve.

        Args:
            variety: Variety symbol
            expected_curve: Expected performance metric
            actual_curve: Actual performance metric
            tolerance: Maximum allowed deviation (default: 0.10 = 10%)

        Returns:
            True if aligned, False if deviated
        """
        if abs(expected_curve) < 1e-8:
            # Avoid division by zero
            return abs(actual_curve) < 1e-8

        deviation = abs(actual_curve - expected_curve) / abs(expected_curve)
        return deviation <= tolerance

    def get_alerts(self, variety: Optional[str] = None) -> List[Dict]:
        """
        Get current alerts for varieties.

        Args:
            variety: Optional specific variety (None for all)

        Returns:
            List of alert dictionaries
        """
        alerts = []

        varieties = [variety] if variety else self.variety_history.keys()

        for var in varieties:
            if var not in self.consecutive_deviations:
                continue

            consecutive = self.consecutive_deviations[var]

            if consecutive >= self.consecutive_days_threshold:
                # Get recent history
                recent = self.variety_history[var][-consecutive:]

                alerts.append({
                    'variety': var,
                    'consecutive_days': consecutive,
                    'recent_deviations': [
                        {
                            'date': entry['date'],
                            'deviation': entry['return_deviation']
                        }
                        for entry in recent
                    ],
                    'severity': 'HIGH' if consecutive >= 10 else 'MEDIUM'
                })

        return alerts

    def get_performance_summary(
        self,
        variety: str,
        days: Optional[int] = None
    ) -> Dict:
        """
        Get performance summary for a variety.

        Args:
            variety: Variety symbol
            days: Number of recent days to analyze (None for all)

        Returns:
            Dictionary with summary statistics
        """
        if variety not in self.variety_history:
            return {'error': f'No history for {variety}'}

        history = self.variety_history[variety]

        if days:
            history = history[-days:]

        if not history:
            return {'error': 'No history available'}

        # Calculate statistics
        deviations = [entry['return_deviation'] for entry in history]
        aligned_count = sum(1 for entry in history if entry['is_aligned'])

        return {
            'variety': variety,
            'period_days': len(history),
            'avg_deviation': np.mean(deviations),
            'max_deviation': np.max(deviations),
            'alignment_rate': aligned_count / len(history),
            'consecutive_deviations': self.consecutive_deviations.get(variety, 0),
            'has_alert': self.consecutive_deviations.get(variety, 0) >= self.consecutive_days_threshold
        }

    def export_report(self, output_file: str = "reports/sandbox_monitor_report.json"):
        """
        Export monitoring report to JSON file.

        Args:
            output_file: Output file path
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'varieties': {},
            'alerts': self.get_alerts()
        }

        for variety in self.variety_history.keys():
            report['varieties'][variety] = self.get_performance_summary(variety)

        # Ensure directory exists
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Report exported to {output_file}")

    def load_history(self, history_file: str):
        """
        Load historical monitoring data from JSON file.

        Args:
            history_file: Path to history JSON file
        """
        if not os.path.exists(history_file):
            self.logger.warning(f"History file not found: {history_file}")
            return

        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.variety_history = data.get('variety_history', {})

        # Recalculate consecutive deviations
        self.consecutive_deviations = {}
        for variety, history in self.variety_history.items():
            consecutive = 0
            for entry in reversed(history):
                if not entry.get('is_aligned', True):
                    consecutive += 1
                else:
                    break
            self.consecutive_deviations[variety] = consecutive

        self.logger.info(f"Loaded history for {len(self.variety_history)} varieties")

    def save_history(self, history_file: str):
        """
        Save monitoring history to JSON file.

        Args:
            history_file: Path to history JSON file
        """
        data = {
            'timestamp': datetime.now().isoformat(),
            'variety_history': self.variety_history
        }

        # Ensure directory exists
        history_dir = os.path.dirname(history_file)
        if history_dir and not os.path.exists(history_dir):
            os.makedirs(history_dir, exist_ok=True)

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"History saved to {history_file}")
