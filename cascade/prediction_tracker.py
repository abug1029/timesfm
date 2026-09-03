"""
历史预测追踪模块

功能：
1. 记录每次预测的关键数据
2. 对比历史预测与实际值
3. 计算预测准确率
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class PredictionRecord:
    """单条预测记录"""
    timestamp: str              # 预测时间 YYYY-MM-DD HH:MM
    symbol: str                 # 品种代码
    current_price: float        # 当前价格
    pred_t1: float              # T+1 预测价
    pred_t24: float             # T+24 预测价
    weighted_pred: float        # 加权预测价
    direction: str              # 方向判断 ↑/↓/→
    dir_acc: float              # 方向准确率
    mape: float                 # MAPE
    ev_ratio: float             # EV_ratio
    pf: float                   # PF
    covariate: str              # 协变量类型

    # 后续验证字段
    actual_t1: Optional[float] = None      # T+1 实际价
    actual_t24: Optional[float] = None     # T+24 实际价
    t1_error: Optional[float] = None       # T+1 误差%
    t24_error: Optional[float] = None      # T+24 误差%
    t1_direction_correct: Optional[bool] = None  # T+1 方向正确
    t24_direction_correct: Optional[bool] = None # T+24 方向正确


class PredictionTracker:
    """预测追踪器"""

    def __init__(self, history_dir: str = "reports/history"):
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _get_record_file(self, symbol: str) -> Path:
        """获取品种的预测记录文件路径"""
        return self.history_dir / symbol / "predictions.json"

    def load_records(self, symbol: str) -> List[PredictionRecord]:
        """加载品种的预测记录"""
        record_file = self._get_record_file(symbol)
        if not record_file.exists():
            return []

        with open(record_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return [PredictionRecord(**r) for r in data]

    def save_records(self, symbol: str, records: List[PredictionRecord]):
        """保存品种的预测记录"""
        record_file = self._get_record_file(symbol)
        record_file.parent.mkdir(parents=True, exist_ok=True)

        with open(record_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(r) for r in records], f, ensure_ascii=False, indent=2)

    def add_prediction(self, record: PredictionRecord):
        """添加新的预测记录"""
        records = self.load_records(record.symbol)
        records.append(record)
        self.save_records(record.symbol, records)

    def get_recent_predictions(self, symbol: str, n: int = 5) -> List[PredictionRecord]:
        """获取最近的N条预测记录"""
        records = self.load_records(symbol)
        return records[-n:] if len(records) >= n else records

    def get_prediction_accuracy(self, symbol: str, days: int = 30) -> Dict:
        """计算指定天数内的预测准确率"""
        records = self.load_records(symbol)

        # 筛选已验证的记录
        verified = [r for r in records if r.t1_error is not None]

        if not verified:
            return {
                'total_predictions': len(records),
                'verified_predictions': 0,
                't1_mae': None,
                't24_mae': None,
                't1_dir_acc': None,
                't24_dir_acc': None,
            }

        # 计算MAE
        t1_errors = [abs(r.t1_error) for r in verified if r.t1_error is not None]
        t24_errors = [abs(r.t24_error) for r in verified if r.t24_error is not None]

        # 计算方向准确率
        t1_dir_correct = sum(1 for r in verified if r.t1_direction_correct)
        t24_dir_correct = sum(1 for r in verified if r.t24_direction_correct)

        return {
            'total_predictions': len(records),
            'verified_predictions': len(verified),
            't1_mae': sum(t1_errors) / len(t1_errors) if t1_errors else None,
            't24_mae': sum(t24_errors) / len(t24_errors) if t24_errors else None,
            't1_dir_acc': t1_dir_correct / len(verified) if verified else None,
            't24_dir_acc': t24_direction_correct / len(verified) if verified else None,
        }

    def compare_with_last_prediction(self, symbol: str, current_price: float) -> Optional[Dict]:
        """与上次预测对比"""
        records = self.load_records(symbol)
        if not records:
            return None

        last = records[-1]

        # 计算上次预测的误差（如果已经有实际值）
        result = {
            'last_timestamp': last.timestamp,
            'last_pred_t1': last.pred_t1,
            'last_pred_t24': last.pred_t24,
            'current_price': current_price,
        }

        # 如果上次预测的T+1时间已过，计算误差
        last_time = datetime.strptime(last.timestamp, '%Y-%m-%d %H:%M')
        now = datetime.now()
        hours_passed = (now - last_time).total_seconds() / 3600

        if hours_passed >= 1 and last.actual_t1 is None:
            # 需要更新上次记录的actual_t1
            result['hours_passed'] = hours_passed
            result['needs_update'] = True

        return result

    def update_actual_values(self, symbol: str, timestamp: str,
                             actual_t1: float = None, actual_t24: float = None):
        """更新预测记录的实际值"""
        records = self.load_records(symbol)

        for record in records:
            if record.timestamp == timestamp:
                if actual_t1 is not None:
                    record.actual_t1 = actual_t1
                    record.t1_error = (actual_t1 - record.pred_t1) / record.pred_t1 * 100
                    # 判断方向是否正确
                    pred_dir = 1 if record.pred_t1 > record.current_price else -1
                    actual_dir = 1 if actual_t1 > record.current_price else -1
                    record.t1_direction_correct = (pred_dir == actual_dir)

                if actual_t24 is not None:
                    record.actual_t24 = actual_t24
                    record.t24_error = (actual_t24 - record.pred_t24) / record.pred_t24 * 100
                    # 判断方向是否正确
                    pred_dir = 1 if record.pred_t24 > record.current_price else -1
                    actual_dir = 1 if actual_t24 > record.current_price else -1
                    record.t24_direction_correct = (pred_dir == actual_dir)

                break

        self.save_records(symbol, records)

    def generate_accuracy_report(self, symbol: str) -> str:
        """生成准确率报告（Markdown格式）"""
        records = self.load_records(symbol)
        accuracy = self.get_prediction_accuracy(symbol)

        lines = [
            f"# {symbol.upper()} 预测准确率报告",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## 统计概览",
            "",
            f"- 总预测次数: {accuracy['total_predictions']}",
            f"- 已验证次数: {accuracy['verified_predictions']}",
        ]

        if accuracy['verified_predictions'] > 0:
            lines.extend([
                "",
                "## 预测误差",
                "",
                f"- T+1 MAE: {accuracy['t1_mae']:.2f}%" if accuracy['t1_mae'] else "- T+1 MAE: N/A",
                f"- T+24 MAE: {accuracy['t24_mae']:.2f}%" if accuracy['t24_mae'] else "- T+24 MAE: N/A",
                "",
                "## 方向准确率",
                "",
                f"- T+1 方向准确率: {accuracy['t1_dir_acc']:.1%}" if accuracy['t1_dir_acc'] else "- T+1 方向准确率: N/A",
                f"- T+24 方向准确率: {accuracy['t24_dir_acc']:.1%}" if accuracy['t24_dir_acc'] else "- T+24 方向准确率: N/A",
            ])

        # 最近5条预测
        recent = self.get_recent_predictions(symbol, 5)
        if recent:
            lines.extend([
                "",
                "## 最近预测记录",
                "",
                "| 时间 | 当前价 | T+1预测 | T+24预测 | 方向 | T+1误差 | T+24误差 |",
                "|------|--------|---------|----------|------|---------|----------|",
            ])
            for r in reversed(recent):
                t1_err = f"{r.t1_error:+.2f}%" if r.t1_error is not None else "-"
                t24_err = f"{r.t24_error:+.2f}%" if r.t24_error is not None else "-"
                lines.append(
                    f"| {r.timestamp} | {r.current_price:.0f} | {r.pred_t1:.0f} | "
                    f"{r.pred_t24:.0f} | {r.direction} | {t1_err} | {t24_err} |"
                )

        return '\n'.join(lines)


# 全局实例
_tracker = PredictionTracker()


def track_prediction(symbol: str, current_price: float, pred_t1: float, pred_t24: float,
                     weighted_pred: float, direction: str, dir_acc: float, mape: float,
                     covariate: str, ev_ratio: float = 0.0, pf: float = 0.0,
                     *,
                     write_ledger: bool = True,
                     asof_ts: str | None = None,
                     trajectory: list | None = None,
                     source: str = "cascade"):
    """记录一次预测

    单一写入入口：
      1) 兼容 JSON history（reports/history/<sym>/predictions.json）
      2) 可选写入 SQLite live_ledger（Phase L 真相源，跨品种可查询）

    Args:
        ev_ratio: 回测 EV 收益比 (可选，无回测元数据时留 0)
        pf: 回测盈亏比 (可选，无回测元数据时留 0)
        write_ledger: 是否写入 db/live_ledger.db
    """
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    record = PredictionRecord(
        timestamp=ts,
        symbol=symbol,
        current_price=current_price,
        pred_t1=pred_t1,
        pred_t24=pred_t24,
        weighted_pred=weighted_pred,
        direction=direction,
        dir_acc=dir_acc,
        mape=mape,
        ev_ratio=ev_ratio,
        pf=pf,
        covariate=covariate,
    )
    _tracker.add_prediction(record)

    if write_ledger:
        try:
            from cascade.live_ledger import LiveLedger, PredictionRun

            traj = list(trajectory) if trajectory else [pred_t1, pred_t24]
            # pad minimal trajectory for t24 index if only two points
            if len(traj) < 24 and pred_t24 is not None:
                while len(traj) < 24:
                    traj.append(float(pred_t24))
            LiveLedger().insert_run(
                PredictionRun(
                    symbol=symbol,
                    asof_ts=asof_ts or ts,
                    base_price=float(current_price),
                    cov_used=str(covariate or ""),
                    pred_trajectory=traj,
                    source=source,
                    direction=direction,
                    horizon=len(traj),
                )
            )
        except Exception:
            # ledger 失败不阻断预测主路径
            pass
    return record


def get_recent_predictions(symbol: str, n: int = 5) -> List[PredictionRecord]:
    """获取最近的预测记录"""
    return _tracker.get_recent_predictions(symbol, n)


def get_prediction_accuracy(symbol: str) -> Dict:
    """获取预测准确率统计"""
    return _tracker.get_prediction_accuracy(symbol)


def generate_accuracy_report(symbol: str) -> str:
    """生成准确率报告"""
    return _tracker.generate_accuracy_report(symbol)
