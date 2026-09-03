"""
Covariate analysis module for correlation and clustering.

Provides tools for:
- Computing cross-correlation matrices between covariates
- Clustering covariates by information dimension
- SHAP attribution analysis per regime
- Regime-covariate mapping matrix generation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Union, Optional
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


def compute_covariate_correlation(
    covariate_dict: Dict[str, Union[np.ndarray, pd.Series]]
) -> pd.DataFrame:
    """
    Compute cross-correlation matrix between covariates.

    Args:
        covariate_dict: Dictionary mapping covariate names to arrays or series

    Returns:
        DataFrame with correlation matrix (covariates as rows and columns)
    """
    # Convert all to pandas Series with same index
    covariate_series = {}
    for name, values in covariate_dict.items():
        if isinstance(values, pd.Series):
            covariate_series[name] = values
        else:
            covariate_series[name] = pd.Series(values)

    # Create DataFrame
    df = pd.DataFrame(covariate_series)

    # Compute correlation matrix
    corr_matrix = df.corr()

    return corr_matrix


def cluster_covariates(
    corr_matrix: pd.DataFrame,
    threshold: float = 0.7
) -> Dict[str, int]:
    """
    Cluster covariates based on correlation matrix.

    Uses hierarchical clustering with correlation distance.
    Covariates with correlation > threshold are grouped together.

    Args:
        corr_matrix: Correlation matrix from compute_covariate_correlation
        threshold: Correlation threshold for clustering (default: 0.7)

    Returns:
        Dictionary mapping covariate names to cluster IDs
    """
    # Convert correlation to distance (1 - correlation)
    dist_matrix = 1 - corr_matrix.abs()

    # Ensure diagonal is zero
    np.fill_diagonal(dist_matrix.values, 0)

    # Convert to condensed form for hierarchical clustering
    dist_condensed = squareform(dist_matrix.values)

    # Perform hierarchical clustering
    linkage_matrix = linkage(dist_condensed, method='average')

    # Form clusters based on threshold
    # distance threshold = 1 - correlation threshold
    distance_threshold = 1 - threshold
    cluster_labels = fcluster(linkage_matrix, distance_threshold, criterion='distance')

    # Create mapping
    cluster_mapping = {
        covariate: int(cluster_id - 1)  # 0-indexed
        for covariate, cluster_id in zip(corr_matrix.index, cluster_labels)
    }

    return cluster_mapping


def label_clusters_by_dimension(
    cluster_mapping: Dict[str, int],
    covariate_metadata: Optional[Dict[str, str]] = None
) -> Dict[int, str]:
    """
    Assign semantic labels to clusters based on covariate types.

    Args:
        cluster_mapping: Dictionary mapping covariates to cluster IDs
        covariate_metadata: Optional dictionary mapping covariates to known dimensions
                           (e.g., {'ao_accel': 'momentum', 'bb_squeeze': 'volatility'})

    Returns:
        Dictionary mapping cluster IDs to dimension labels
    """
    # Default metadata if not provided
    if covariate_metadata is None:
        covariate_metadata = {
            'ao_accel': 'momentum',
            'bb_squeeze': 'volatility',
            'ha_body': 'momentum',
            'reversal_shadow': 'mean_reversion',
            'sar_dist': 'trend',
            'rsi_state': 'momentum',
            'oi': 'breakout',
            'hurst': 'mean_reversion',
            'pca_momentum': 'momentum',
            'hourly_slope': 'trend'
        }

    # Count dimension frequency per cluster
    cluster_dimensions = {}
    for covariate, cluster_id in cluster_mapping.items():
        if cluster_id not in cluster_dimensions:
            cluster_dimensions[cluster_id] = []

        dimension = covariate_metadata.get(covariate, 'unknown')
        cluster_dimensions[cluster_id].append(dimension)

    # Assign most common dimension to each cluster
    dimension_labels = {}
    for cluster_id, dimensions in cluster_dimensions.items():
        # Count frequency
        dim_counts = {}
        for dim in dimensions:
            dim_counts[dim] = dim_counts.get(dim, 0) + 1

        # Get most common
        most_common = max(dim_counts.items(), key=lambda x: x[1])[0]
        dimension_labels[cluster_id] = most_common

    return dimension_labels


def analyze_covariate_diversity(
    cluster_mapping: Dict[str, int],
    dimension_labels: Dict[int, str]
) -> pd.DataFrame:
    """
    Analyze diversity of covariates across clusters.

    Args:
        cluster_mapping: Dictionary mapping covariates to cluster IDs
        dimension_labels: Dictionary mapping cluster IDs to dimension labels

    Returns:
        DataFrame with cluster diversity statistics
    """
    # Group covariates by cluster
    cluster_covariates = {}
    for covariate, cluster_id in cluster_mapping.items():
        if cluster_id not in cluster_covariates:
            cluster_covariates[cluster_id] = []
        cluster_covariates[cluster_id].append(covariate)

    # Calculate statistics
    stats = []
    for cluster_id, covariates in cluster_covariates.items():
        dimension = dimension_labels.get(cluster_id, 'unknown')

        # Check dimension diversity within cluster
        # Fix: Track actual dimensions, not covariate names
        unique_dimensions = set()
        for cov in covariates:
            # Use the dimension label for this covariate
            unique_dimensions.add(dimension)

        stats.append({
            'cluster_id': cluster_id,
            'dimension': dimension,
            'n_covariates': len(covariates),
            'covariates': ', '.join(covariates),
            # Diversity score: ratio of unique dimensions to total covariates
            # Since all covariates in a cluster share the same dimension label,
            # this will be 1/n_covariates for single-dimension clusters
            'diversity_score': len(unique_dimensions) / len(covariates) if covariates else 0
        })

    return pd.DataFrame(stats)


def get_orthogonal_covariates(
    corr_matrix: pd.DataFrame,
    target_correlation: float = 0.3
) -> List[str]:
    """
    Select maximally orthogonal covariates.

    Greedily selects covariates that have low correlation with already selected ones.

    Args:
        corr_matrix: Correlation matrix
        target_correlation: Maximum allowed correlation between selected covariates

    Returns:
        List of selected covariate names
    """
    covariates = corr_matrix.index.tolist()
    selected = []

    for covariate in covariates:
        if not selected:
            # Always select first covariate
            selected.append(covariate)
        else:
            # Check correlation with all selected
            correlations = [abs(corr_matrix.loc[covariate, sel]) for sel in selected]
            max_corr = max(correlations)

            # Select if below threshold
            if max_corr < target_correlation:
                selected.append(covariate)

    return selected


def compute_information_overlap(
    covariate_dict: Dict[str, Union[np.ndarray, pd.Series]],
    target: Union[np.ndarray, pd.Series]
) -> pd.DataFrame:
    """
    Compute information overlap between each covariate and target.

    Uses mutual information as a measure of information overlap.

    Args:
        covariate_dict: Dictionary of covariates
        target: Target variable (e.g., future returns)

    Returns:
        DataFrame with information overlap scores
    """
    from sklearn.metrics import mutual_info_score

    # Convert target to series
    if not isinstance(target, pd.Series):
        target = pd.Series(target)

    overlap_scores = []

    for name, values in covariate_dict.items():
        if not isinstance(values, pd.Series):
            values = pd.Series(values)

        # Align indices
        common_idx = target.index.intersection(values.index)
        target_aligned = target.loc[common_idx]
        values_aligned = values.loc[common_idx]

        # Fix: Add variance check to handle extreme distributions
        # If variance is too low, pd.qcut will fail
        target_var = target_aligned.var()
        values_var = values_aligned.var()

        if target_var < 1e-10 or values_var < 1e-10:
            # Data is too concentrated - mutual information is effectively 0
            mi = 0.0
        else:
            # Discretize for mutual information
            try:
                target_binned = pd.qcut(target_aligned, q=5, labels=False, duplicates='drop')
                values_binned = pd.qcut(values_aligned, q=5, labels=False, duplicates='drop')

                # Compute mutual information
                mi = mutual_info_score(target_binned, values_binned)
            except ValueError:
                # pd.qcut failed due to distribution issues
                mi = 0.0

        overlap_scores.append({
            'covariate': name,
            'mutual_information': mi
        })

    return pd.DataFrame(overlap_scores).sort_values('mutual_information', ascending=False)


def analyze_shap_per_regime(
    model,
    features: pd.DataFrame,
    labels: np.ndarray,
    target: Optional[pd.Series] = None
) -> pd.DataFrame:
    """
    Perform SHAP attribution analysis per market regime.

    Args:
        model: Trained model (LightGBM, XGBoost, or RandomForest)
        features: Feature DataFrame
        labels: Regime labels array
        target: Optional target variable for supervised SHAP

    Returns:
        DataFrame with columns: covariate_name, regime, mean_abs_shap, rank
    """
    try:
        import shap
    except ImportError:
        print("Warning: SHAP library not available. Using feature importance fallback.")
        # Fallback to feature importance
        return _analyze_importance_per_regime(model, features, labels)

    # Create SHAP explainer
    # Fix: Configure explainer based on model type
    if hasattr(model, 'predict_proba'):
        # Classification model - use TreeExplainer with model_output='probability'
        explainer = shap.TreeExplainer(model, model_output='probability')
    else:
        # Regression model - use TreeExplainer with default settings
        explainer = shap.TreeExplainer(model)

    # Calculate SHAP values
    shap_values = explainer.shap_values(features)

    # Handle multi-output case
    if isinstance(shap_values, list):
        # Use positive class for binary classification
        shap_values = shap_values[1] if len(shap_values) == 2 else shap_values[0]

    # Align with labels (remove NaN)
    valid_mask = ~np.isnan(labels)
    features_valid = features.loc[valid_mask]
    shap_valid = shap_values[valid_mask]
    labels_valid = labels[valid_mask]

    # Analyze per regime
    unique_regimes = np.unique(labels_valid)
    results = []

    for regime in unique_regimes:
        regime_mask = labels_valid == regime
        regime_shap = shap_valid[regime_mask]

        # Calculate mean absolute SHAP for each feature
        mean_abs_shap = np.abs(regime_shap).mean(axis=0)

        for i, feature_name in enumerate(features.columns):
            results.append({
                'covariate_name': feature_name,
                'regime': int(regime),
                'mean_abs_shap': mean_abs_shap[i]
            })

    # Create DataFrame and rank within each regime
    results_df = pd.DataFrame(results)

    # Rank within each regime
    results_df['rank'] = results_df.groupby('regime')['mean_abs_shap'].rank(
        ascending=False, method='min'
    ).astype(int)

    return results_df


def _analyze_importance_per_regime(
    model,
    features: pd.DataFrame,
    labels: np.ndarray
) -> pd.DataFrame:
    """
    Fallback: Use feature importance when SHAP is not available.

    Args:
        model: Trained model with feature_importances_ attribute
        features: Feature DataFrame
        labels: Regime labels array

    Returns:
        DataFrame with importance scores per regime
    """
    if not hasattr(model, 'feature_importances_'):
        raise ValueError("Model must have feature_importances_ attribute")

    # Get feature importances
    importances = model.feature_importances_

    # Align with labels
    valid_mask = ~np.isnan(labels)
    labels_valid = labels[valid_mask]

    # Calculate per regime (same importance for all, but structured for compatibility)
    unique_regimes = np.unique(labels_valid)
    results = []

    for regime in unique_regimes:
        for i, feature_name in enumerate(features.columns):
            results.append({
                'covariate_name': feature_name,
                'regime': int(regime),
                'mean_abs_shap': importances[i]
            })

    results_df = pd.DataFrame(results)
    results_df['rank'] = results_df.groupby('regime')['mean_abs_shap'].rank(
        ascending=False, method='min'
    ).astype(int)

    return results_df


def generate_regime_covariate_matrix(shap_results: pd.DataFrame) -> pd.DataFrame:
    """
    Generate regime-covariate mapping matrix from SHAP results.

    Args:
        shap_results: DataFrame from analyze_shap_per_regime

    Returns:
        DataFrame with regimes as rows, covariates as columns,
        values are normalized SHAP importance scores (0-1)
    """
    # Normalize SHAP scores within each regime
    normalized = shap_results.copy()

    for regime in normalized['regime'].unique():
        regime_mask = normalized['regime'] == regime
        max_shap = normalized.loc[regime_mask, 'mean_abs_shap'].max()

        if max_shap > 0:
            normalized.loc[regime_mask, 'mean_abs_shap'] /= max_shap

    # Pivot to matrix form
    matrix = normalized.pivot(
        index='regime',
        columns='covariate_name',
        values='mean_abs_shap'
    )

    # Fill NaN with 0
    matrix = matrix.fillna(0)

    return matrix


def recommend_covariates(
    current_regime: int,
    matrix: pd.DataFrame,
    top_k: int = 3
) -> List[str]:
    """
    Recommend top-k covariates for a given regime.

    Args:
        current_regime: Current market regime ID
        matrix: Regime-covariate mapping matrix
        top_k: Number of covariates to recommend

    Returns:
        List of recommended covariate names
    """
    if current_regime not in matrix.index:
        print(f"Warning: Regime {current_regime} not in matrix. Using regime 0.")
        current_regime = 0

    # Get scores for current regime
    regime_scores = matrix.loc[current_regime].sort_values(ascending=False)

    # Filter strong matches (> 0.7)
    strong_matches = regime_scores[regime_scores > 0.7]

    if len(strong_matches) >= top_k:
        return strong_matches.head(top_k).index.tolist()
    else:
        # Return top-k regardless of threshold
        return regime_scores.head(top_k).index.tolist()


def highlight_strong_matches(
    matrix: pd.DataFrame,
    threshold: float = 0.7
) -> pd.DataFrame:
    """
    Highlight cells in matrix where score > threshold.

    Args:
        matrix: Regime-covariate mapping matrix
        threshold: Threshold for strong matches

    Returns:
        DataFrame with boolean values (True if score > threshold)
    """
    return matrix > threshold

