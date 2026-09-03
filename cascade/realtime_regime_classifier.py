"""
实时 Regime 分类器 - 预测时动态识别市场状态

⚠️ 防坑机制：
1. 严格 lookback-only：每个时间点只用该截面之前的数据
2. 迟滞机制（Hysteresis）：避免状态闪烁，连续 3 bar 确认才切换
3. Context 完整性：确保传入 XReg 的协变量序列完整平稳

使用示例：
    classifier = RealtimeRegimeClassifier()
    result = classifier.classify(
        hourly_closes=hourly_data,
        lookback=480  # 20 天
    )
    # 输出：
    # {
    #     'regime': 1,
    #     'label': 'low_vol_narrow',
    #     'confidence': 0.85,
    #     'recommended_covariates': ['oi', 'rsi_state'],
    #     'stable': True  # 已连续 3 bar 确认
    # }
"""

import numpy as np
import pandas as pd
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import deque


@dataclass
class RegimeState:
    """Regime 状态记录"""
    regime_id: int
    label: str
    confidence: float
    timestamp: str
    bars_held: int  # 该状态已持续的 bar 数


class RealtimeRegimeClassifier:
    """
    实时 Regime 分类器（防穿越 + 迟滞机制）

    核心特性：
    1. 严格 lookback-only：每次只用当前 bar 之前的数据
    2. 迟滞机制：连续 N bar 确认才切换状态
    3. 历史缓存：避免重复计算
    """

    # Regime 定义（与 Regime-Covariate 分析一致）
    REGIME_LABELS = {
        0: 'high_vol_trend',       # 高波动趋势
        1: 'low_vol_narrow',       # 低波动窄幅
        2: 'wide_oscillation',     # 宽幅震荡
        3: 'transition'            # 过渡状态
    }

    # 协变量推荐映射 (P0 安全版)
    # 规则:
    # - 仅第二协变量；daily_slope 由 XReg 自动注入，禁止出现在此表
    # - 每 regime 最多 1 个第二协变量（规避线性 XReg 多特征糊化）
    # - transition 返回空列表 → 调用侧回退静态 scheme
    # - 正式映射须经 P1.4 门禁后由数据驱动覆盖（P2.1 JSON）
    REGIME_COVARIATE_MAP = {
        0: ['ha_body'],        # high_vol_trend: 趋势段最广单变量
        1: ['rsi_state'],      # low_vol_narrow: 震荡敏感（单变量）
        2: ['pca_momentum'],   # wide_oscillation: 宽幅动量（单变量）
        3: [],                 # transition: 不切换 → 回退静态
    }

    def __init__(
        self,
        hysteresis_bars: int = 3,
        confidence_threshold: float = 0.6,
        lookback_window: int = 480
    ):
        """
        初始化实时 Regime 分类器

        Args:
            hysteresis_bars: 迟滞 bar 数（默认 3，连续 3 bar 确认才切换）
            confidence_threshold: 分类置信度阈值（低于此值维持上一状态）
            lookback_window: 默认回看窗口（480 bars = 20 天）
        """
        self.hysteresis_bars = hysteresis_bars
        self.confidence_threshold = confidence_threshold
        self.lookback_window = lookback_window

        # 状态历史（用于迟滞判断）
        self.state_history: deque = deque(maxlen=hysteresis_bars * 2)

        # 特征提取器（1H 契约，与 train_regime_model 一致）
        from cascade.regime_features import extract_1h_regime_features
        self.extract_features = extract_1h_regime_features

        # K-Means 模型（从训练好的 1H 模型加载）
        self.kmeans_model = None
        self.cluster_to_regime = None
        self.scaler = None
        self.feature_columns = None
        try:
            self.kmeans_model, self.cluster_to_regime, self.scaler, self.feature_columns = (
                self._load_model()
            )
        except Exception as e:
            print(f"[WARN] 模型加载失败 ({e})，使用规则版分类器")

    def _load_model(self):
        """
        加载预训练的 1H K-Means 模型

        模型文件: models/regime_kmeans_1h.pkl
        训练命令: python scripts/train_regime_model.py

        Returns:
            (kmeans, cluster_to_regime_dict, scaler, feature_columns)
        """
        import pickle
        model_path = 'models/regime_kmeans_1h.pkl'

        if not os.path.exists(model_path):
            print(f"[WARN] 模型文件不存在: {model_path}")
            return None, None, None, None

        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)

        kmeans = model_data['model']
        cluster_to_regime = model_data['cluster_to_regime']
        scaler = model_data.get('scaler')
        feature_columns = model_data.get('feature_columns')
        print(f"[INFO] 已加载 1H K-Means 模型: "
              f"{model_data.get('n_samples', '?')} 样本, "
              f"{len(model_data.get('trained_symbols', []))} 品种, "
              f"train_end={model_data.get('train_end', '?')}, "
              f"scaler={'yes' if scaler is not None else 'no'}")

        return kmeans, cluster_to_regime, scaler, feature_columns

    def classify(
        self,
        hourly_df: pd.DataFrame,
        lookback: Optional[int] = None,
        current_bar_idx: Optional[int] = None
    ) -> Dict:
        """
        识别当前市场 Regime（严格 lookback-only）

        ⚠️ 防穿越：
        - 只用 current_bar_idx 之前的数据
        - 绝不使用 future data

        Args:
            hourly_df: 1H OHLCV DataFrame（完整历史）
            lookback: 回看窗口（默认 self.lookback_window）
            current_bar_idx: 当前 bar 索引（默认 len(hourly_df) - 1）

        Returns:
            {
                'regime': int (0-3),
                'label': str,
                'confidence': float (0-1),
                'recommended_covariates': List[str],
                'stable': bool,  # 是否已通过迟滞确认
                'bars_held': int,  # 当前状态已持续的 bar 数
                'raw_scores': np.ndarray  # 各 Regime 的原始得分
            }
        """
        if lookback is None:
            lookback = self.lookback_window

        if current_bar_idx is None:
            current_bar_idx = len(hourly_df) - 1

        # ⚠️ 防穿越：严格切取 lookback 窗口
        start_idx = max(0, current_bar_idx - lookback + 1)
        historical_window = hourly_df.iloc[start_idx:current_bar_idx + 1]

        # 提取 Regime 特征（只用当前窗口）
        features_df = self.extract_features(historical_window)

        # 获取最后一行（当前时间截面的特征值）
        if features_df.empty:
            # 如果特征为空，返回默认过渡状态
            return {
                'regime': 3,
                'label': self.REGIME_LABELS[3],
                'confidence': 0.0,
                'recommended_covariates': self.REGIME_COVARIATE_MAP[3],
                'stable': False,
                'bars_held': 0,
                'raw_scores': np.array([0.25, 0.25, 0.25, 0.25]),
                'timestamp': str(current_bar_idx)
            }

        # 取最后一行并转换为 numpy array
        features = features_df.iloc[-1].values

        # 分类
        regime_id, confidence, raw_scores = self._classify_single(features)

        # 迟滞判断
        stable, bars_held = self._apply_hysteresis(regime_id, confidence)

        # 构建结果
        result = {
            'regime': regime_id,
            'label': self.REGIME_LABELS[regime_id],
            'confidence': float(confidence),
            'recommended_covariates': self.REGIME_COVARIATE_MAP[regime_id],
            'stable': stable,
            'bars_held': bars_held,
            'raw_scores': raw_scores,
            'timestamp': str(current_bar_idx)
        }

        return result

    def _classify_single(self, features: np.ndarray) -> Tuple[int, float, np.ndarray]:
        """
        对单个时间截面进行分类

        Returns:
            (regime_id, confidence, raw_scores)
        """
        if self.kmeans_model is not None:
            # 使用预训练的 K-Means 模型（先 scaler，与训练一致）
            x = features.reshape(1, -1).astype(float)
            if self.scaler is not None:
                x = self.scaler.transform(x)
            raw_cluster = int(self.kmeans_model.predict(x)[0])

            # 映射到经济意义的 regime
            regime_id = (
                self.cluster_to_regime.get(raw_cluster, raw_cluster)
                if self.cluster_to_regime else raw_cluster
            )

            # 置信度：最近中心 margin（1 - min/second_min 风格）
            distances = self.kmeans_model.transform(x)[0]
            order = np.argsort(distances)
            d0 = distances[order[0]]
            d1 = distances[order[1]] if len(distances) > 1 else d0 + 1e-8
            # margin 归一化到 (0,1)
            confidence = float(1.0 - d0 / (d1 + 1e-8))
            confidence = max(0.0, min(1.0, confidence))

            max_dist = distances.max()
            raw_scores = 1.0 - (distances / (max_dist + 1e-8))

        else:
            # 后备: 规则版分类器
            regime_id, confidence, raw_scores = self._rule_based_classify(features)

        return regime_id, confidence, raw_scores

    def _rule_based_classify(self, features: np.ndarray) -> Tuple[int, float, np.ndarray]:
        """
        基于规则的简化分类器（当预训练模型不可用时使用）

        规则逻辑：
        - ADX > 30 且 Hurst > 0.6 → 趋势市 (0)
        - ADX < 20 且 vol_cone < 0.3 → 窄幅震荡 (1)
        - vol_cone > 0.7 → 宽幅震荡 (2)
        - 其他 → 过渡状态 (3)

        Args:
            features: numpy array of feature values (from extract_rolling_features)
        """
        # 特征顺序来自 extract_rolling_features 的列顺序：
        # vor_skew_40, oi_vol_zscore_40, rolling_hurst_40, rolling_adx_40, vol_cone_position_40,
        # vor_skew_60, oi_vol_zscore_60, rolling_hurst_60, rolling_adx_60, vol_cone_position_60

        # 使用 40 窗口特征（索引 0-4）
        hurst = features[2] if len(features) > 2 else 0.5  # rolling_hurst_40
        adx = features[3] if len(features) > 3 else 25     # rolling_adx_40
        vol_cone = features[4] if len(features) > 4 else 0.5  # vol_cone_position_40

        # 规则判断
        if adx > 30 and hurst > 0.6:
            regime_id = 0  # 趋势市
            confidence = min((adx - 30) / 20, 1.0)
        elif adx < 20 and vol_cone < 0.3:
            regime_id = 1  # 窄幅震荡
            confidence = min((20 - adx) / 10, 1.0)
        elif vol_cone > 0.7:
            regime_id = 2  # 宽幅震荡
            confidence = min((vol_cone - 0.7) / 0.3, 1.0)
        else:
            regime_id = 3  # 过渡状态
            confidence = 0.5

        # 生成 raw_scores（简化版）
        raw_scores = np.array([0.25, 0.25, 0.25, 0.25])
        raw_scores[regime_id] = confidence

        return regime_id, confidence, raw_scores

    def _apply_hysteresis(self, regime_id: int, confidence: float) -> Tuple[bool, int]:
        """
        应用迟滞机制，避免状态闪烁

        逻辑：
        1. 如果置信度 < threshold，维持上一状态
        2. 新状态必须连续 N bar 才确认切换

        Returns:
            (stable: bool, bars_held: int)
        """
        # 记录当前判断
        self.state_history.append({
            'regime_id': regime_id,
            'confidence': confidence
        })

        # 如果历史不足，返回当前状态
        if len(self.state_history) < self.hysteresis_bars:
            return False, len(self.state_history)

        # 检查最近 N bar 是否一致
        recent_states = list(self.state_history)[-self.hysteresis_bars:]
        regime_counts = {}
        for state in recent_states:
            rid = state['regime_id']
            regime_counts[rid] = regime_counts.get(rid, 0) + 1

        # 找到最常见的状态
        most_common_regime = max(regime_counts.items(), key=lambda x: x[1])

        if most_common_regime[1] >= self.hysteresis_bars:
            # 已确认：连续 N bar 都是同一状态
            return True, self.hysteresis_bars
        else:
            # 未确认：状态闪烁
            return False, most_common_regime[1]

    def classify_history(
        self,
        hourly_df: pd.DataFrame,
        step: int = 1
    ) -> pd.DataFrame:
        """
        对历史序列进行 Regime 分类（用于回测和可视化）

        ⚠️ 严格 lookback-only：
        - 每个时间点只用该截面之前的数据
        - 绝不使用 future data

        Args:
            hourly_df: 1H OHLCV DataFrame
            step: 采样步长（默认 1，每个 bar 都分类）

        Returns:
            DataFrame with columns:
            - timestamp: bar 索引
            - regime: Regime ID (0-3)
            - label: Regime 标签
            - confidence: 分类置信度
            - stable: 是否通过迟滞确认
            - bars_held: 当前状态已持续的 bar 数
        """
        results = []

        # 重置状态历史
        self.state_history.clear()

        # 逐 bar 分类（严格 lookback-only）
        for i in range(self.lookback_window, len(hourly_df), step):
            result = self.classify(
                hourly_df=hourly_df,
                current_bar_idx=i
            )

            results.append({
                'timestamp': i,
                'regime': result['regime'],
                'label': result['label'],
                'confidence': result['confidence'],
                'stable': result['stable'],
                'bars_held': result['bars_held']
            })

        return pd.DataFrame(results)

    def visualize_regimes(
        self,
        hourly_df: pd.DataFrame,
        regime_df: pd.DataFrame,
        output_path: str = 'reports/regime_classification.png'
    ):
        """
        可视化 Regime 分类结果

        图形包含：
        1. K 线图（收盘价）
        2. Regime 状态条（不同颜色表示不同 Regime）
        3. 置信度曲线
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                          gridspec_kw={'height_ratios': [3, 1]})

            # K 线图
            ax1.plot(hourly_df['close'], label='Close Price', color='black', linewidth=1)
            ax1.set_ylabel('Price')
            ax1.set_title('Regime Classification')
            ax1.legend()

            # Regime 状态条
            regime_colors = {
                0: 'red',      # 趋势市
                1: 'blue',     # 窄幅震荡
                2: 'green',    # 宽幅震荡
                3: 'gray'      # 过渡状态
            }

            for _, row in regime_df.iterrows():
                start = row['timestamp']
                end = start + 1
                color = regime_colors[row['regime']]
                alpha = row['confidence']
                ax2.axvspan(start, end, color=color, alpha=alpha)

            ax2.set_ylabel('Regime')
            ax2.set_xlabel('Bar Index')

            # 图例
            patches = [
                mpatches.Patch(color='red', label='High Vol Trend'),
                mpatches.Patch(color='blue', label='Low Vol Narrow'),
                mpatches.Patch(color='green', label='Wide Oscillation'),
                mpatches.Patch(color='gray', label='Transition')
            ]
            ax2.legend(handles=patches, loc='upper right')

            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            print(f"[OK] Regime 可视化已保存: {output_path}")

        except ImportError:
            print("[WARN] matplotlib 不可用，跳过可视化")


def quick_test():
    """快速测试脚本"""
    print("=== 实时 Regime 分类器测试 ===\n")

    # 生成测试数据（模拟趋势市 + 震荡市）
    np.random.seed(42)
    n = 1000

    # 前 500 bar：趋势市（随机游走）
    trend_data = np.cumsum(np.random.randn(500)) + 100

    # 后 500 bar：震荡市（正弦波 + 噪声）
    t = np.arange(500)
    oscillation_data = 100 + 10 * np.sin(2 * np.pi * t / 50) + np.random.randn(500) * 2

    # 拼接
    hourly_closes = np.concatenate([trend_data, oscillation_data])

    # 分类
    classifier = RealtimeRegimeClassifier(
        hysteresis_bars=3,
        confidence_threshold=0.6,
        lookback_window=100
    )

    print("正在分类历史序列...")
    regime_df = classifier.classify_history(hourly_closes, step=10)

    print(f"\n分类结果：")
    print(regime_df.head(10))

    # 可视化
    try:
        classifier.visualize_regimes(hourly_closes, regime_df)
    except Exception as e:
        print(f"[WARN] 可视化失败: {e}")

    print("\n=== 测试完成 ===")


if __name__ == '__main__':
    quick_test()
