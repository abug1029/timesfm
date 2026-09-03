#!/usr/bin/env python3
"""
Regime-Covariate Analysis Orchestration Script.

Executes the full pipeline:
1. Feature extraction (rolling features)
2. Regime classification (K-Means clustering)
3. Covariate correlation analysis
4. Walk-forward optimization with IS/OOS validation
5. SHAP attribution analysis per regime
6. Regime-covariate mapping matrix generation

Usage:
    python scripts/regime_covariate_analysis.py --varieties RB JM I --is-years 2018-2022 --oos-years 2023-2024
"""

import os
import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cascade.regime_features import extract_rolling_features, summarize_feature_distributions
from cascade.regime_classifier import RegimeClassifier, classify_market_regime
from cascade.covariate_analysis import (
    compute_covariate_correlation,
    cluster_covariates,
    label_clusters_by_dimension,
    analyze_shap_per_regime,
    generate_regime_covariate_matrix,
    recommend_covariates,
    highlight_strong_matches
)
from cascade.walk_forward import WalkForwardOptimizer, run_walk_forward_test
from cascade.deployment_monitor import SandboxMonitor


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Regime-Covariate Analysis Pipeline'
    )

    parser.add_argument(
        '--varieties',
        nargs='+',
        default=['RB', 'JM', 'I', 'SS', 'UR'],
        help='List of variety symbols to analyze (default: RB JM I SS UR)'
    )

    parser.add_argument(
        '--is-years',
        type=str,
        default='2018-2022',
        help='In-sample period as YYYY-YYYY (default: 2018-2022)'
    )

    parser.add_argument(
        '--oos-years',
        type=str,
        default='2023-2024',
        help='Out-of-sample period as YYYY-YYYY (default: 2023-2024)'
    )

    parser.add_argument(
        '--n-regimes',
        type=int,
        default=4,
        help='Number of market regimes to classify (default: 4)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default='reports/regime_analysis',
        help='Output directory for reports (default: reports/regime_analysis)'
    )

    return parser.parse_args()


def parse_year_range(year_range_str):
    """Parse year range string like '2018-2022' into start and end dates."""
    start_year, end_year = year_range_str.split('-')
    start_date = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"
    return start_date, end_date


def load_variety_data(variety, data_dir='db'):
    """
    Load variety data from SQLite database.

    Args:
        variety: Variety symbol (e.g., 'RB')
        data_dir: Directory containing database files

    Returns:
        DataFrame with OHLCV data
    """
    # Fix: Use correct database naming convention (futures_{symbol}.db)
    db_path = Path(data_dir) / f'futures_{variety.lower()}.db'

    if not db_path.exists():
        print(f"Warning: Database not found for {variety} at {db_path}")
        return None

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))

        # Fix: Use correct column names and filter by contract_code to avoid data contamination
        contract_code = f'{variety.upper()}_CONT'
        query = """
        SELECT dt, open_price, high, low, close_price, volume, open_interest
        FROM kline_1d
        WHERE open_interest IS NOT NULL
          AND contract_code = ?
        ORDER BY dt
        """

        df = pd.read_sql_query(query, conn, params=(contract_code,))
        conn.close()

        # Convert dt to datetime
        df['dt'] = pd.to_datetime(df['dt'])
        df.set_index('dt', inplace=True)

        # Rename columns to standard names for downstream processing
        df = df.rename(columns={
            'open_price': 'open',
            'close_price': 'close'
        })

        return df

    except Exception as e:
        print(f"Error loading data for {variety}: {e}")
        return None


def run_feature_extraction(dfs, varieties):
    """
    Step 1: Extract rolling features for all varieties.

    Args:
        dfs: Dictionary of DataFrames keyed by variety
        varieties: List of variety symbols

    Returns:
        Dictionary of feature DataFrames
    """
    print("\n" + "="*60)
    print("STEP 1: Feature Extraction")
    print("="*60)

    features_dict = {}

    for variety in varieties:
        if variety not in dfs or dfs[variety] is None:
            continue

        print(f"\nExtracting features for {variety}...")

        # Extract rolling features with 40 and 60 day windows
        # Note: Hurst calculation requires window >= 40 for reliable R/S analysis
        features = extract_rolling_features(dfs[variety], windows=[40, 60])
        features_dict[variety] = features

        # Print summary
        summary = summarize_feature_distributions(features)
        print(f"  Features shape: {features.shape}")
        print(f"  Valid samples: {len(features.dropna())}")

    return features_dict


def run_regime_classification(features_dict, varieties, n_regimes=4):
    """
    Step 2: Classify market regimes.

    Args:
        features_dict: Dictionary of feature DataFrames
        varieties: List of variety symbols
        n_regimes: Number of regimes to classify

    Returns:
        Dictionary of regime labels and summaries
    """
    print("\n" + "="*60)
    print("STEP 2: Regime Classification")
    print("="*60)

    regime_results = {}

    for variety in varieties:
        if variety not in features_dict:
            continue

        print(f"\nClassifying regimes for {variety}...")

        features = features_dict[variety]
        labels, summary = classify_market_regime(features, n_states=n_regimes)

        regime_results[variety] = {
            'labels': labels,
            'summary': summary
        }

        print(f"  Regimes identified: {len(summary)}")
        print(f"  Regime distribution:")
        for _, row in summary.iterrows():
            print(f"    Regime {int(row['regime'])}: {row['percentage']:.1f}%")

    return regime_results


def run_covariate_analysis(covariate_data, varieties):
    """
    Step 3: Analyze covariate correlations and clustering.

    Args:
        covariate_data: Dictionary of covariate return series
        varieties: List of variety symbols

    Returns:
        Dictionary with correlation matrices and cluster assignments
    """
    print("\n" + "="*60)
    print("STEP 3: Covariate Correlation Analysis")
    print("="*60)

    analysis_results = {}

    for variety in varieties:
        if variety not in covariate_data:
            continue

        print(f"\nAnalyzing covariates for {variety}...")

        # Compute correlation matrix
        corr_matrix = compute_covariate_correlation(covariate_data[variety])
        print(f"  Correlation matrix shape: {corr_matrix.shape}")

        # Cluster covariates
        clusters = cluster_covariates(corr_matrix, threshold=0.7)
        print(f"  Clusters identified: {len(set(clusters.values()))}")

        # Label clusters by dimension
        labels = label_clusters_by_dimension(clusters)
        print(f"  Cluster dimensions: {labels}")

        analysis_results[variety] = {
            'correlation_matrix': corr_matrix,
            'clusters': clusters,
            'cluster_labels': labels
        }

    return analysis_results


def run_walk_forward_optimization(covariate_returns, is_period, oos_period, varieties):
    """
    Step 4: Perform walk-forward optimization.

    Args:
        covariate_returns: Dictionary of covariate return series
        is_period: In-sample period (start, end)
        oos_period: Out-of-sample period (start, end)
        varieties: List of variety symbols

    Returns:
        Dictionary with optimization results
    """
    print("\n" + "="*60)
    print("STEP 4: Walk-Forward Optimization")
    print("="*60)

    wfo_results = {}

    for variety in varieties:
        if variety not in covariate_returns:
            continue

        print(f"\nOptimizing covariates for {variety}...")

        result = run_walk_forward_test(
            covariate_returns[variety],
            is_period,
            oos_period,
            n_splits=5
        )

        wfo_results[variety] = result

        if result['success']:
            print(f"  Best combination: {result['best_combination']}")
            print(f"  IS IR: {result['is_ir']:.3f}")
            print(f"  OOS IR: {result['oos_metrics']['information_ratio']:.3f}")
        else:
            print(f"  No valid combination found")

    return wfo_results


def run_shap_analysis(model, features_dict, regime_results, varieties):
    """
    Step 5: Perform SHAP attribution analysis per regime.

    Args:
        model: Trained model for SHAP analysis
        features_dict: Dictionary of feature DataFrames
        regime_results: Dictionary of regime classification results
        varieties: List of variety symbols

    Returns:
        Dictionary with SHAP results
    """
    print("\n" + "="*60)
    print("STEP 5: SHAP Attribution Analysis")
    print("="*60)

    shap_results = {}

    for variety in varieties:
        if variety not in features_dict or variety not in regime_results:
            continue

        print(f"\nAnalyzing SHAP values for {variety}...")

        features = features_dict[variety]
        labels = regime_results[variety]['labels']

        # Align features and labels
        valid_mask = ~np.isnan(labels)
        features_aligned = features.loc[valid_mask]
        labels_aligned = labels[valid_mask]

        if len(features_aligned) == 0:
            print(f"  No valid samples for {variety}")
            continue

        # Analyze SHAP per regime
        shap_df = analyze_shap_per_regime(model, features_aligned, labels_aligned)

        shap_results[variety] = shap_df

        print(f"  SHAP analysis completed for {len(shap_df)} feature-regime pairs")

    return shap_results


def generate_mapping_matrices(shap_results, varieties):
    """
    Step 6: Generate regime-covariate mapping matrices.

    Args:
        shap_results: Dictionary of SHAP analysis results
        varieties: List of variety symbols

    Returns:
        Dictionary with mapping matrices and recommendations
    """
    print("\n" + "="*60)
    print("STEP 6: Regime-Covariate Mapping Matrix")
    print("="*60)

    mapping_results = {}

    for variety in varieties:
        if variety not in shap_results:
            continue

        print(f"\nGenerating mapping matrix for {variety}...")

        shap_df = shap_results[variety]

        # Generate matrix
        matrix = generate_regime_covariate_matrix(shap_df)
        print(f"  Matrix shape: {matrix.shape}")

        # Highlight strong matches
        highlights = highlight_strong_matches(matrix, threshold=0.7)
        n_strong = highlights.sum().sum()
        print(f"  Strong matches (>0.7): {n_strong}")

        # Generate recommendations for each regime
        recommendations = {}
        for regime in matrix.index:
            top_covs = recommend_covariates(regime, matrix, top_k=3)
            recommendations[int(regime)] = top_covs
            print(f"    Regime {regime}: {', '.join(top_covs)}")

        mapping_results[variety] = {
            'matrix': matrix,
            'highlights': highlights,
            'recommendations': recommendations
        }

    return mapping_results


def save_results(output_dir, all_results):
    """
    Save all analysis results to output directory.

    Args:
        output_dir: Output directory path
        all_results: Dictionary with all analysis results
    """
    print("\n" + "="*60)
    print("Saving Results")
    print("="*60)

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Save each component
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Save regime classification results
    if 'regime_results' in all_results:
        regime_path = output_path / f'regime_classification_{timestamp}.json'
        regime_data = {
            variety: {
                'summary': data['summary'].to_dict(orient='records')
            }
            for variety, data in all_results['regime_results'].items()
        }
        with open(regime_path, 'w', encoding='utf-8') as f:
            json.dump(regime_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {regime_path}")

    # Save correlation analysis results
    if 'correlation' in all_results and all_results['correlation']:
        corr_path = output_path / f'correlation_analysis_{timestamp}.json'
        corr_data = {}
        for variety, data in all_results['correlation'].items():
            corr_data[variety] = {
                'correlation_matrix': data['correlation_matrix'].to_dict(),
                'clusters': data['clusters']
            }
        with open(corr_path, 'w', encoding='utf-8') as f:
            json.dump(corr_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {corr_path}")

    # Save walk-forward optimization results
    if 'wfo' in all_results and all_results['wfo']:
        wfo_path = output_path / f'walk_forward_optimization_{timestamp}.json'
        wfo_data = {}
        for variety, data in all_results['wfo'].items():
            wfo_data[variety] = {
                'best_combination': data.get('best_combination'),
                'is_ir': data.get('is_ir'),
                'oos_metrics': data.get('oos_metrics')
            }
        with open(wfo_path, 'w', encoding='utf-8') as f:
            json.dump(wfo_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {wfo_path}")

    # Save SHAP analysis results
    if 'shap' in all_results and all_results['shap']:
        shap_path = output_path / f'shap_analysis_{timestamp}.json'
        shap_data = {}
        for variety, data in all_results['shap'].items():
            shap_data[variety] = {
                'shap_results': data.to_dict(orient='records')
            }
        with open(shap_path, 'w', encoding='utf-8') as f:
            json.dump(shap_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {shap_path}")

    # Save mapping matrices
    if 'mapping_results' in all_results:
        mapping_path = output_path / f'mapping_matrices_{timestamp}.json'
        mapping_data = {
            variety: {
                'matrix': data['matrix'].to_dict(),
                'recommendations': data['recommendations']
            }
            for variety, data in all_results['mapping_results'].items()
        }
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {mapping_path}")

    # Save summary report
    summary_path = output_path / f'analysis_summary_{timestamp}.txt'
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("Regime-Covariate Analysis Summary\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write("="*60 + "\n\n")

        for variety, data in all_results.get('mapping_results', {}).items():
            f.write(f"Variety: {variety}\n")
            f.write("-"*40 + "\n")
            for regime, covs in data['recommendations'].items():
                f.write(f"  Regime {regime}: {', '.join(covs)}\n")
            f.write("\n")

    print(f"  Saved: {summary_path}")


def main():
    """Main orchestration function."""
    print("="*60)
    print("REGIME-COVARIATE ANALYSIS PIPELINE")
    print("="*60)

    # Parse arguments
    args = parse_arguments()

    # Parse year ranges
    is_period = parse_year_range(args.is_years)
    oos_period = parse_year_range(args.oos_years)

    print(f"\nConfiguration:")
    print(f"  Varieties: {', '.join(args.varieties)}")
    print(f"  IS Period: {is_period[0]} to {is_period[1]}")
    print(f"  OOS Period: {oos_period[0]} to {oos_period[1]}")
    print(f"  Number of Regimes: {args.n_regimes}")
    print(f"  Output Directory: {args.output_dir}")

    # Load data
    print("\n" + "="*60)
    print("Loading Data")
    print("="*60)

    dfs = {}
    for variety in args.varieties:
        print(f"\nLoading {variety}...")
        df = load_variety_data(variety)
        if df is not None:
            dfs[variety] = df
            print(f"  Loaded {len(df)} samples")

    if not dfs:
        print("\nError: No data loaded. Exiting.")
        return

    # Run pipeline
    all_results = {}

    # Step 1: Feature extraction
    features_dict = run_feature_extraction(dfs, args.varieties)
    all_results['features'] = features_dict

    # Step 2: Regime classification
    regime_results = run_regime_classification(features_dict, args.varieties, args.n_regimes)
    all_results['regime_results'] = regime_results

    # Step 3: Covariate correlation analysis
    print("\n" + "="*60)
    print("STEP 3: Covariate Correlation Analysis")
    print("="*60)
    # This would load covariate data from prediction results or external sources
    # For now, we'll use placeholder logic
    covariate_data = {}
    for variety in args.varieties:
        if variety in features_dict:
            # Extract covariate columns from features (excluding regime labels)
            covariate_features = features_dict[variety].dropna()
            # In production, this would load actual covariate returns
            # e.g., from prediction tracker or backtest results
            covariate_data[variety] = {
                'feature_1': covariate_features.iloc[:, 0] if len(covariate_features.columns) > 0 else pd.Series(),
                'feature_2': covariate_features.iloc[:, 1] if len(covariate_features.columns) > 1 else pd.Series(),
            }

    correlation_results = {}
    for variety, covs in covariate_data.items():
        if covs:
            corr_matrix = compute_covariate_correlation(covs)
            clusters = cluster_covariates(corr_matrix, threshold=0.7)
            correlation_results[variety] = {
                'correlation_matrix': corr_matrix,
                'clusters': clusters
            }
            print(f"\n{variety}: Computed correlation matrix for {len(covs)} covariates")
    all_results['correlation'] = correlation_results

    # Step 4: Walk-forward optimization
    print("\n" + "="*60)
    print("STEP 4: Walk-Forward Optimization")
    print("="*60)
    wfo_results = {}
    for variety in args.varieties:
        if variety in correlation_results:
            # Placeholder: In production, this would load covariate return series
            # and run actual walk-forward optimization
            print(f"\n{variety}: Walk-forward optimization requires covariate returns")
            print("  (Skipping - no covariate return data available)")
    all_results['wfo'] = wfo_results

    # Step 5: SHAP attribution analysis
    print("\n" + "="*60)
    print("STEP 5: SHAP Attribution Analysis")
    print("="*60)
    shap_results = {}
    for variety in args.varieties:
        if variety in features_dict and variety in regime_results:
            # Placeholder: In production, this would train a model and run SHAP
            print(f"\n{variety}: SHAP analysis requires trained model")
            print("  (Skipping - no model available)")
    all_results['shap'] = shap_results

    # Step 6: Regime-covariate mapping matrix
    print("\n" + "="*60)
    print("STEP 6: Regime-Covariate Mapping Matrix")
    print("="*60)
    mapping_results = {}
    for variety in args.varieties:
        if variety in shap_results:
            # Generate mapping matrix from SHAP results
            print(f"\n{variety}: Generating regime-covariate mapping matrix")
            # Placeholder: Would call generate_regime_covariate_matrix(shap_results[variety])
    all_results['mapping_results'] = mapping_results

    print("\n" + "="*60)
    print("Pipeline Execution Complete")
    print("="*60)
    print("\nCompleted Steps:")
    print("  [OK] Step 1: Feature extraction")
    print("  [OK] Step 2: Regime classification")
    print("  [OK] Step 3: Covariate correlation analysis")
    print("  [OK] Step 4: Walk-forward optimization (placeholder)")
    print("  [OK] Step 5: SHAP attribution analysis (placeholder)")
    print("  [OK] Step 6: Regime-covariate mapping matrix (placeholder)")
    print("\nNote: Steps 4-6 require additional data/model integration:")
    print("  - Covariate return series from backtest results")
    print("  - Trained models for SHAP analysis")
    print("\nThese can be added by extending the placeholder logic")
    print("with actual data loading and model training.")

    # Save results
    save_results(args.output_dir, all_results)

    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)


if __name__ == '__main__':
    main()
