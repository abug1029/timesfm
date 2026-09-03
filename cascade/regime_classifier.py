"""
Market regime classification using clustering methods.

Classifies market states into distinct regimes based on rolling features:
- Regime 0: High volatility trend (strong directional movement)
- Regime 1: Low volatility narrow range (consolidation)
- Regime 2: Wide oscillation (range-bound with high volatility)
- Regime 3: Transition (mixed signals between regimes)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


class RegimeClassifier:
    """
    Classify market states into distinct regimes using K-Means clustering.

    Regimes are characterized by:
    - Regime 0: High volatility trend (high ADX, extreme VOR skew)
    - Regime 1: Low volatility narrow range (low ADX, low volatility)
    - Regime 2: Wide oscillation (moderate ADX, high volatility cone position)
    - Regime 3: Transition (mixed signals, moderate features)
    """

    def __init__(self, n_states: int = 4, random_state: int = 42):
        """
        Initialize regime classifier.

        Args:
            n_states: Number of regime states (default: 4)
            random_state: Random seed for reproducibility
        """
        self.n_states = n_states
        self.random_state = random_state
        self.model = None
        self.scaler = StandardScaler()
        self.regime_labels = {
            0: 'high_vol_trend',
            1: 'low_vol_narrow',
            2: 'wide_oscillation',
            3: 'transition'
        }

    def fit_predict(self, features_df: pd.DataFrame, n_states: int = None) -> np.ndarray:
        """
        Fit classifier and predict regime labels.

        **IMPORTANT**: After clustering, regime IDs are reordered based on feature means
        to ensure consistent interpretation:
        - Regime 0: high_vol_trend (highest ADX)
        - Regime 1: low_vol_narrow (lowest volatility)
        - Regime 2: wide_oscillation (high volatility cone position)
        - Regime 3: transition (remaining)

        Args:
            features_df: DataFrame with rolling features from regime_features module
            n_states: Override number of states (optional)

        Returns:
            Array of regime labels (0-3), sorted by economic meaning
        """
        if n_states is not None:
            self.n_states = n_states

        # Drop rows with NaN values
        features_clean = features_df.dropna()

        if len(features_clean) < self.n_states * 10:
            raise ValueError(f"Insufficient data: need at least {self.n_states * 10} rows, got {len(features_clean)}")

        # Standardize features
        features_scaled = self.scaler.fit_transform(features_clean)

        # Fit K-Means
        self.model = KMeans(
            n_clusters=self.n_states,
            random_state=self.random_state,
            n_init=10,
            max_iter=300
        )
        raw_labels = self.model.fit_predict(features_scaled)

        # **CRITICAL FIX**: Reorder labels based on feature means to ensure consistency
        features_with_labels = features_clean.copy()
        features_with_labels['cluster'] = raw_labels

        # Calculate mean of key features for each cluster
        # Dynamically detect column names based on actual windows used
        adx_col = next((c for c in features_with_labels.columns if c.startswith('rolling_adx_')), None)
        vol_cone_col = next((c for c in features_with_labels.columns if c.startswith('vol_cone_position_')), None)
        hurst_col = next((c for c in features_with_labels.columns if c.startswith('rolling_hurst_')), None)

        # Validate required columns exist
        missing = []
        if adx_col is None:
            missing.append('rolling_adx_*')
        if vol_cone_col is None:
            missing.append('vol_cone_position_*')
        if hurst_col is None:
            missing.append('rolling_hurst_*')
        if missing:
            raise ValueError(f"Missing required feature columns: {missing}. "
                           f"Available columns: {list(features_with_labels.columns)}")

        agg_dict = {
            adx_col: 'mean',           # ADX for trend strength
            vol_cone_col: 'mean',      # Volatility cone position
            hurst_col: 'mean'          # Hurst exponent
        }
        cluster_stats = features_with_labels.groupby('cluster').agg(agg_dict).reset_index()

        # Sort clusters by economic meaning:
        # 1. Highest ADX -> high_vol_trend (label 0)
        # 2. Lowest vol cone position -> low_vol_narrow (label 1)
        # 3. High vol cone position (excluding label 0) -> wide_oscillation (label 2)
        # 4. Remaining -> transition (label 3)

        sorted_by_adx = cluster_stats.sort_values(adx_col, ascending=False)
        regime_0_cluster = sorted_by_adx.iloc[0]['cluster']  # Highest ADX

        # Exclude regime 0 cluster for next sorting
        remaining_clusters = cluster_stats[cluster_stats['cluster'] != regime_0_cluster]

        # Sort remaining by vol_cone_position ascending (lowest first)
        sorted_by_vol = remaining_clusters.sort_values(vol_cone_col, ascending=True)
        regime_1_cluster = sorted_by_vol.iloc[0]['cluster']  # Lowest volatility

        # Sort remaining by vol_cone_position descending (highest first)
        remaining_clusters = remaining_clusters[remaining_clusters['cluster'] != regime_1_cluster]
        sorted_by_vol_desc = remaining_clusters.sort_values(vol_cone_col, ascending=False)
        regime_2_cluster = sorted_by_vol_desc.iloc[0]['cluster']  # High volatility

        # Remaining cluster is transition
        regime_3_cluster = remaining_clusters[remaining_clusters['cluster'] != regime_2_cluster].iloc[0]['cluster']

        # Create mapping from raw cluster IDs to economic regime labels
        cluster_to_regime = {
            int(regime_0_cluster): 0,  # high_vol_trend
            int(regime_1_cluster): 1,  # low_vol_narrow
            int(regime_2_cluster): 2,  # wide_oscillation
            int(regime_3_cluster): 3   # transition
        }

        # Apply mapping
        reordered_labels = np.array([cluster_to_regime[label] for label in raw_labels])

        # Store mapping for predict() method
        self.cluster_to_regime_ = cluster_to_regime

        # Map back to original index using integer positions
        labels = pd.Series(np.nan, index=features_df.index)
        labels.loc[features_clean.index] = reordered_labels

        return labels.values

    def predict(self, features_df: pd.DataFrame) -> np.ndarray:
        """
        Predict regime labels using fitted model.

        Uses the same cluster-to-regime mapping established during fit_predict
        to ensure consistent regime interpretation.

        Args:
            features_df: DataFrame with rolling features

        Returns:
            Array of regime labels (0-3), sorted by economic meaning
        """
        if self.model is None:
            raise ValueError("Model not fitted. Call fit_predict first.")

        if not hasattr(self, 'cluster_to_regime_'):
            raise ValueError("Cluster mapping not found. Re-fit the model.")

        features_clean = features_df.dropna()
        features_scaled = self.scaler.transform(features_clean)
        raw_labels = self.model.predict(features_scaled)

        # Apply the same mapping from fit_predict
        reordered_labels = np.array([self.cluster_to_regime_[label] for label in raw_labels])

        # Map back to original index using integer positions
        labels = pd.Series(np.nan, index=features_df.index)
        labels.loc[features_clean.index] = reordered_labels

        return labels.values

    def summarize_regimes(self, features_df: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
        """
        Generate summary statistics for each regime.

        Args:
            features_df: DataFrame with rolling features
            labels: Array of regime labels

        Returns:
            DataFrame with regime characteristics
        """
        # Combine features and labels
        df_analysis = features_df.copy()
        df_analysis['regime'] = labels

        # Calculate statistics per regime
        summary_rows = []

        for regime_id in range(self.n_states):
            regime_data = df_analysis[df_analysis['regime'] == regime_id]

            if len(regime_data) == 0:
                continue

            row = {
                'regime': regime_id,
                'label': self.regime_labels.get(regime_id, f'regime_{regime_id}'),
                'count': len(regime_data),
                'percentage': len(regime_data) / len(df_analysis) * 100
            }

            # Add mean values for key features
            for col in features_df.columns:
                row[f'{col}_mean'] = regime_data[col].mean()
                row[f'{col}_std'] = regime_data[col].std()

            summary_rows.append(row)

        summary_df = pd.DataFrame(summary_rows)

        # Sort by frequency
        summary_df = summary_df.sort_values('count', ascending=False)

        return summary_df

    def get_regime_transitions(self, labels: np.ndarray) -> pd.DataFrame:
        """
        Analyze regime transition patterns.

        Args:
            labels: Array of regime labels

        Returns:
            DataFrame with transition matrix
        """
        # Remove NaN values
        labels_clean = labels[~np.isnan(labels)]

        if len(labels_clean) < 2:
            return pd.DataFrame()

        # Count transitions
        transitions = {}
        for i in range(len(labels_clean) - 1):
            from_regime = int(labels_clean[i])
            to_regime = int(labels_clean[i + 1])

            key = (from_regime, to_regime)
            transitions[key] = transitions.get(key, 0) + 1

        # Create transition matrix
        matrix_data = []
        for from_regime in range(self.n_states):
            row = []
            for to_regime in range(self.n_states):
                count = transitions.get((from_regime, to_regime), 0)
                row.append(count)
            matrix_data.append(row)

        transition_matrix = pd.DataFrame(
            matrix_data,
            index=[f'from_{i}' for i in range(self.n_states)],
            columns=[f'to_{i}' for i in range(self.n_states)]
        )

        # Normalize to probabilities
        row_sums = transition_matrix.sum(axis=1)
        transition_probs = transition_matrix.div(row_sums, axis=0)

        return transition_probs

    def identify_regime_changes(self, labels: np.ndarray) -> pd.DataFrame:
        """
        Identify points where regime changes occur.

        Args:
            labels: Array of regime labels

        Returns:
            DataFrame with regime change events
        """
        changes = []

        for i in range(1, len(labels)):
            if not np.isnan(labels[i]) and not np.isnan(labels[i-1]):
                if labels[i] != labels[i-1]:
                    changes.append({
                        'index': i,
                        'from_regime': int(labels[i-1]),
                        'to_regime': int(labels[i]),
                        'from_label': self.regime_labels.get(int(labels[i-1]), 'unknown'),
                        'to_label': self.regime_labels.get(int(labels[i]), 'unknown')
                    })

        return pd.DataFrame(changes)


def classify_market_regime(features_df: pd.DataFrame, n_states: int = 4) -> Tuple[np.ndarray, pd.DataFrame]:
    """
    Convenience function to classify market regimes.

    Args:
        features_df: DataFrame with rolling features
        n_states: Number of regime states

    Returns:
        Tuple of (regime_labels, regime_summary)
    """
    classifier = RegimeClassifier(n_states=n_states)
    labels = classifier.fit_predict(features_df, n_states)
    summary = classifier.summarize_regimes(features_df, labels)

    return labels, summary
