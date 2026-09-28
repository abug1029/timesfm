# T5-PR-C2 Changelog: family 定义 + 封账 + 未完成检验 p=1 + T_max 兜底 + 跨品种范围声明

**Status:** 文档化完成，待实施
**Date:** 2026-09-28
**Spec:** §4.3 W3.6

## 问题描述

PR-C2 实现多重比较校正的完整框架，包括：

1. **family 定义**：确定哪些假设属于同一检验家族
2. **封账逻辑**：何时运行 BH-FDR 校正
3. **未完成检验的 p=1**：如何处理 timeout/abandoned 假设
4. **T_max 兜底**：确保 family 最终能封账
5. **跨品种范围声明**：明确结论仅限于品种内

## 实施方案

### W3.6 ① 检验家族（family）的定义

**一个 family = 同一研究问题 + 同一预注册系列内全部确认检验**

**family_key 定义**：
```python
family_key = (symbol, research_question)
research_question = (预测目标, 预测任务/期限, research_target_hash)
```

**research_target_hash**：
```python
research_target_hash = hash(
    symbol, 
    target_var, 
    price_series_def, 
    adjust_roll_rule_version
)
```

**关键规则**：
- 默认：一个品种 = 一个研究问题 = 一个 family
- **批次、运行、代际都不重置校正**
- 只有确认检验进 family，探索期结果不进
- 每个假设在 family 中**恰好一个** p 值

**跨品种错误率范围**：
- 本 spec **默认不跨品种合并校正**
- 每个品种是独立研究问题，各自控制 FDR
- 结论范围仅限品种内
- 报告**不得**产出跨品种聚合声称

### W3.6 ② 封账、注册截止、未完成检验的 p 值

**family 封账条件**：
- 全部成员到达终态时封账
- 终态四种：`confirmed` / `refuted` / `abandoned` / `timeout`

**注册截止（二者并用，先到者为准）**：
- **时间截止** `family_close_at`：默认 family 首个成员注册后 90 天
- **成员上限** `family_max_members`：默认 20

**T_max 兜底**：
- 从成员注册时间（`registered_at`）起算，默认 180 天
- 已注册但从未获得确认数据的成员：在 `family_close_at` 封账时若仍未达终态，立即落 `timeout` + `p=1`

**封账上界**：
- family 最晚于 `family_close_at + T_max` 封账
- 注册截止（使集合固定）+ 成员 T_max（给每个成员一个终止点）二者缺一不可

**p=1 的适用范围**：
- 仅当该假设已进入确认 family、且在截止前未完成确认时
- 探索中止、尚未注册确认的假设不得计入确认 family

**abandoned 与 timeout 仍计入 K**：
- 防止"结果不好就悄悄丢掉"= 缩小 K = p-hacking

## 实施步骤

### 1. 实现 family 管理逻辑

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import hashlib


@dataclass
class ResearchTarget:
    """研究目标的稳定标识"""
    symbol: str
    target_var: str
    price_series_def: str
    adjust_roll_rule_version: str
    
    @property
    def hash(self) -> str:
        """计算 research_target_hash"""
        parts = [
            "research_target_v1",
            self.symbol,
            self.target_var,
            self.price_series_def,
            self.adjust_roll_rule_version
        ]
        input_str = "|".join(parts)
        return hashlib.sha256(input_str.encode()).hexdigest()[:16]


@dataclass
class ResearchQuestion:
    """研究问题定义"""
    target: ResearchTarget
    prediction_target: str  # 预测目标
    prediction_task: str    # 预测任务/期限
    
    @property
    def key(self) -> tuple:
        return (
            self.target.symbol,
            self.prediction_target,
            self.prediction_task,
            self.target.hash
        )


@dataclass
class PreregisteredHypothesis:
    """预注册假设"""
    prereg_id: str
    symbol: str
    cov_fingerprint_keys: str
    mechanism: str
    predicted_direction: str
    registered_at: datetime
    confirm_from_ts: datetime
    n_planned: int
    
    # 终态相关
    status: str = "pending"  # pending / confirmed / refuted / abandoned / timeout
    p_value: Optional[float] = None
    closed_at: Optional[datetime] = None


@dataclass
class Family:
    """检验家族"""
    research_question: ResearchQuestion
    members: List[PreregisteredHypothesis] = field(default_factory=list)
    
    # 封账参数
    family_close_at: Optional[datetime] = None
    family_max_members: int = 20
    t_max_days: int = 180
    
    # 封账结果
    is_closed: bool = False
    K: int = 0
    bh_results: Optional[Dict] = None
    
    def add_member(self, hypothesis: PreregisteredHypothesis):
        """添加成员"""
        if self.is_closed:
            raise ValueError("Family is closed, cannot add members")
        
        if len(self.members) >= self.family_max_members:
            raise ValueError(f"Family reached max members ({self.family_max_members})")
        
        if self.family_close_at and hypothesis.registered_at > self.family_close_at:
            raise ValueError("Hypothesis registered after family close time")
        
        self.members.append(hypothesis)
        
        # 首个成员注册后 90 天封账
        if len(self.members) == 1:
            self.family_close_at = (
                hypothesis.registered_at + timedelta(days=90)
            )
    
    def close_family(self, current_time: datetime):
        """封账 family（spec W3.6②）。

        ⚠️ 审计 D3 修正 —— 原稿有两处**违反 spec**:

        (1) 原稿仅在 `days_since_registration >= t_max_days` 时才赋 timeout。
            spec W3.6② 明定: 「已注册但从未获得确认数据的成员：在
            `family_close_at` 封账时若仍未达终态，**立即**落 `timeout` + `p=1`，
            **不等待**」。故封账时**所有** pending 成员一律立即 timeout+p=1。

        (2) 原稿 BH 输入过滤为 `status in ["confirmed","refuted"]`，
            **排除了 timeout/abandoned 的 p=1** —— 这恰好复刻 spec 明令防止的
            「结果不好就悄悄丢掉 = 缩小 K = p-hacking」路径。
            spec: 「`abandoned` 与 `timeout` **仍计入 K**」，
            其 p=1 必须**进入 BH 输入**（p=1 不会被判显著，但计入校正基数）。
        """
        if self.is_closed:
            return

        # (1) 封账时所有未达终态成员立即 timeout + p=1（spec W3.6②）
        for member in self.members:
            if member.status not in ("confirmed", "refuted",
                                     "abandoned", "timeout"):
                member.status = "timeout"
                member.p_value = 1.0
                member.closed_at = current_time

        # K = 全部成员（含 abandoned / timeout）—— 禁止缩小 K
        self.K = len(self.members)

        # (2) BH 输入 = **全部 K 个** p 值（含 timeout/abandoned 的 p=1）
        #     p=1 不会显著，但必须计入校正基数；排除它们等于 p-hacking。
        p_values = []
        for m in self.members:
            if m.p_value is None:
                # 终态成员必须有 p 值；缺失即 fail-loud（不得静默补 1）
                raise ValueError(
                    f"成员 {m.prereg_id} 处于 {m.status} 但 p_value 为 None；"
                    "终态成员必须携带 p 值（timeout/abandoned 应为 1.0）"
                )
            p_values.append(m.p_value)

        assert len(p_values) == self.K, "BH 输入数必须等于 K（禁止排除任何成员）"

        # 运行 BH-FDR（K>=1 即运行，单成员时退化为其自身 p 值）
        if p_values:
            from statsmodels.stats.multitest import multipletests
            reject, pvals_corrected, _, _ = multipletests(
                p_values, alpha=0.05, method="fdr_bh"
            )
            self.bh_results = {
                "K": self.K,
                "p_values": p_values,
                "pvals_corrected": pvals_corrected.tolist(),
                "reject": reject.tolist(),
                "n_rejected": int(sum(reject)),
            }

        self.is_closed = True


class FamilyManager:
    """family 管理器"""
    
    def __init__(self):
        self.families: Dict[tuple, Family] = {}
    
    def get_or_create_family(self, research_question: ResearchQuestion) -> Family:
        """获取或创建 family"""
        key = research_question.key
        if key not in self.families:
            self.families[key] = Family(research_question=research_question)
        return self.families[key]
    
    def register_hypothesis(self, hypothesis: PreregisteredHypothesis):
        """注册假设"""
        # 构建 research_question
        target = ResearchTarget(
            symbol=hypothesis.symbol,
            target_var="price_direction",  # 假设预测目标是价格方向
            price_series_def="1H_close",
            adjust_roll_rule_version="v1"
        )
        research_question = ResearchQuestion(
            target=target,
            prediction_target="price_direction",
            prediction_task="24h"
        )
        
        family = self.get_or_create_family(research_question)
        family.add_member(hypothesis)
    
    def close_all_families(self, current_time: datetime):
        """封账所有 family"""
        for family in self.families.values():
            if not family.is_closed:
                family.close_family(current_time)
```

### 2. 创建测试 `tests/test_family_management.py`

```python
"""family 管理测试"""

import pytest
from datetime import datetime, timedelta
from scripts.family_management import (
    ResearchTarget,
    ResearchQuestion,
    PreregisteredHypothesis,
    Family,
    FamilyManager
)


def test_research_target_hash_stable():
    """测试 research_target_hash 稳定"""
    target1 = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    target2 = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    assert target1.hash == target2.hash


def test_research_target_hash_changes_with_definition():
    """测试 research_target_hash 随定义变化"""
    target1 = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    target2 = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v2"  # 版本变化
    )
    assert target1.hash != target2.hash


def test_family_key_same_for_same_research_question():
    """测试同一研究问题的 family_key 相同"""
    target = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    rq1 = ResearchQuestion(
        target=target,
        prediction_target="price_direction",
        prediction_task="24h"
    )
    rq2 = ResearchQuestion(
        target=target,
        prediction_target="price_direction",
        prediction_task="24h"
    )
    assert rq1.key == rq2.key


def test_family_close_at_set_on_first_member():
    """测试首个成员注册后设置 family_close_at"""
    target = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    research_question = ResearchQuestion(
        target=target,
        prediction_target="price_direction",
        prediction_task="24h"
    )
    family = Family(research_question=research_question)
    
    hypothesis = PreregisteredHypothesis(
        prereg_id="test_001",
        symbol="ss",
        cov_fingerprint_keys="rsi_state",
        mechanism="RSI momentum",
        predicted_direction="up",
        registered_at=datetime(2026, 1, 1),
        confirm_from_ts=datetime(2026, 1, 1),
        n_planned=100
    )
    
    family.add_member(hypothesis)
    
    # family_close_at 应该是注册后 90 天
    expected_close_at = datetime(2026, 1, 1) + timedelta(days=90)
    assert family.family_close_at == expected_close_at


def test_family_timeout_assignment():
    """测试 timeout 分配 p=1"""
    target = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    research_question = ResearchQuestion(
        target=target,
        prediction_target="price_direction",
        prediction_task="24h"
    )
    family = Family(research_question=research_question, t_max_days=180)
    
    hypothesis = PreregisteredHypothesis(
        prereg_id="test_001",
        symbol="ss",
        cov_fingerprint_keys="rsi_state",
        mechanism="RSI momentum",
        predicted_direction="up",
        registered_at=datetime(2026, 1, 1),
        confirm_from_ts=datetime(2026, 1, 1),
        n_planned=100
    )
    
    family.add_member(hypothesis)
    
    # 180 天后封账
    close_time = datetime(2026, 1, 1) + timedelta(days=180)
    family.close_family(close_time)
    
    # 假设应该被标记为 timeout + p=1
    assert family.members[0].status == "timeout"
    assert family.members[0].p_value == 1.0
    assert family.K == 1


def test_abandoned_and_timeout_counted_in_K():
    """spec W3.6②: abandoned 与 timeout 计入 K，且其 p=1 进入 BH 输入。

    审计 D3 修正: 原测试只断言 `K == 3` 且手动置 is_closed 绕过 BH，
    抓不到「BH 输入排除 timeout/abandoned」这一违规。本版**实际调用
    close_family** 并断言 BH 输入数 == K。
    """
    target = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    research_question = ResearchQuestion(
        target=target,
        prediction_target="price_direction",
        prediction_task="24h"
    )
    family = Family(research_question=research_question)

    for i in range(3):
        family.add_member(PreregisteredHypothesis(
            prereg_id=f"test_{i:03d}",
            symbol="ss",
            cov_fingerprint_keys="rsi_state",
            mechanism="RSI momentum",
            predicted_direction="up",
            registered_at=datetime(2026, 1, 1),
            confirm_from_ts=datetime(2026, 1, 1),
            n_planned=100
        ))

    # 两个成员已达终态；第三个保持 pending
    family.members[0].status = "confirmed"
    family.members[0].p_value = 0.03
    family.members[1].status = "abandoned"
    family.members[1].p_value = 1.0          # abandoned 也须带 p=1
    # members[2] 保持 pending

    # 封账（实际运行 BH，不绕过）
    family.close_family(datetime(2026, 1, 1) + timedelta(days=90))

    # K 含全部成员（含 timeout/abandoned）
    assert family.K == 3
    # pending 成员被立即赋 timeout + p=1（不等待 T_max）
    assert family.members[2].status == "timeout"
    assert family.members[2].p_value == 1.0
    # BH 输入数必须 == K（禁止排除任何成员）
    assert family.bh_results is not None
    assert len(family.bh_results["p_values"]) == family.K == 3
    assert family.bh_results["K"] == 3
    # p=1 不会被判显著
    assert family.bh_results["n_rejected"] == 0


def test_bh_input_excludes_nobody():
    """spec W3.6② 反向断言: 若排除 timeout 的 p=1，BH 基数会被缩小。

    构造 4 成员：1 个 confirmed(p=0.04) + 3 个 timeout(p=1)。
    正确行为: BH 在 K=4 上校正；错误行为（排除 timeout）会在 K=1 上校正。
    """
    target = ResearchTarget(
        symbol="ss", target_var="price_direction",
        price_series_def="1H_close", adjust_roll_rule_version="v1"
    )
    rq = ResearchQuestion(target=target, prediction_target="price_direction",
                          prediction_task="24h")
    family = Family(research_question=rq)

    for i in range(4):
        family.add_member(PreregisteredHypothesis(
            prereg_id=f"h_{i}", symbol="ss", cov_fingerprint_keys="rsi_state",
            mechanism="m", predicted_direction="up",
            registered_at=datetime(2026, 1, 1),
            confirm_from_ts=datetime(2026, 1, 1), n_planned=100
        ))

    family.members[0].status = "confirmed"
    family.members[0].p_value = 0.04
    # 其余 3 个保持 pending → 封账时全部 timeout + p=1

    family.close_family(datetime(2026, 1, 1) + timedelta(days=90))

    assert family.K == 4
    assert len(family.bh_results["p_values"]) == 4, (
        "BH 输入必须含全部 4 个成员（含 3 个 p=1）—— 排除它们即 p-hacking"
    )
    # K=4 上校正 0.04 → 0.16 > 0.05，不显著；若错误地在 K=1 上校正则会显著
    assert family.bh_results["n_rejected"] == 0


def test_pending_member_gets_timeout_immediately():
    """spec W3.6②: 封账时 pending 成员**立即** timeout，不等待 T_max。"""
    target = ResearchTarget(
        symbol="ss", target_var="price_direction",
        price_series_def="1H_close", adjust_roll_rule_version="v1"
    )
    rq = ResearchQuestion(target=target, prediction_target="price_direction",
                          prediction_task="24h")
    family = Family(research_question=rq, t_max_days=180)
    family.add_member(PreregisteredHypothesis(
        prereg_id="h_0", symbol="ss", cov_fingerprint_keys="rsi_state",
        mechanism="m", predicted_direction="up",
        registered_at=datetime(2026, 1, 1),
        confirm_from_ts=datetime(2026, 1, 1), n_planned=100
    ))

    # 仅过 90 天（< T_max=180），但已到 family_close_at
    family.close_family(datetime(2026, 1, 1) + timedelta(days=90))

    assert family.members[0].status == "timeout", (
        "封账时 pending 成员必须立即 timeout，不得等待 T_max"
    )
    assert family.members[0].p_value == 1.0


def test_terminal_member_without_p_fails_loud():
    """终态成员缺 p 值 → fail-loud（不得静默补 1）。"""
    target = ResearchTarget(
        symbol="ss", target_var="price_direction",
        price_series_def="1H_close", adjust_roll_rule_version="v1"
    )
    rq = ResearchQuestion(target=target, prediction_target="price_direction",
                          prediction_task="24h")
    family = Family(research_question=rq)
    family.add_member(PreregisteredHypothesis(
        prereg_id="h_0", symbol="ss", cov_fingerprint_keys="rsi_state",
        mechanism="m", predicted_direction="up",
        registered_at=datetime(2026, 1, 1),
        confirm_from_ts=datetime(2026, 1, 1), n_planned=100
    ))
    family.members[0].status = "confirmed"
    family.members[0].p_value = None      # 违规：终态无 p

    with pytest.raises(ValueError, match="p_value 为 None"):
        family.close_family(datetime(2026, 1, 1) + timedelta(days=90))



def test_cross_symbol_no_aggregation():
    """测试跨品种不聚合"""
    # 这个测试确保不同品种的 family 是独立的
    manager = FamilyManager()
    
    # 注册 ss 品种的假设
    target_ss = ResearchTarget(
        symbol="ss",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    rq_ss = ResearchQuestion(
        target=target_ss,
        prediction_target="price_direction",
        prediction_task="24h"
    )
    
    hypothesis_ss = PreregisteredHypothesis(
        prereg_id="ss_001",
        symbol="ss",
        cov_fingerprint_keys="rsi_state",
        mechanism="RSI momentum",
        predicted_direction="up",
        registered_at=datetime(2026, 1, 1),
        confirm_from_ts=datetime(2026, 1, 1),
        n_planned=100
    )
    
    manager.register_hypothesis(hypothesis_ss)
    
    # 注册 sr 品种的假设
    target_sr = ResearchTarget(
        symbol="sr",
        target_var="price_direction",
        price_series_def="1H_close",
        adjust_roll_rule_version="v1"
    )
    rq_sr = ResearchQuestion(
        target=target_sr,
        prediction_target="price_direction",
        prediction_task="24h"
    )
    
    hypothesis_sr = PreregisteredHypothesis(
        prereg_id="sr_001",
        symbol="sr",
        cov_fingerprint_keys="rsi_state",
        mechanism="RSI momentum",
        predicted_direction="up",
        registered_at=datetime(2026, 1, 1),
        confirm_from_ts=datetime(2026, 1, 1),
        n_planned=100
    )
    
    manager.register_hypothesis(hypothesis_sr)
    
    # 应该有两个独立的 family
    assert len(manager.families) == 2
    assert rq_ss.key != rq_sr.key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## 预计工作量

- family 管理逻辑实现: 1.5 天
- 测试: 1 天
- **总计: 2.5 天**

## 依赖

- 不依赖 T1a（可并行实施）
- 需要理解当前预注册逻辑

## 风险

1. **统计正确性风险**：BH-FDR 校正必须正确实现，否则会导致错误的统计推断
2. **性能风险**：无，family 管理是轻量级操作
3. **前视风险**：无，这是事后统计检验

## 验收标准

1. family_key 正确计算（基于 research_target_hash）
2. research_target_hash 稳定（不随数据变化）
3. family_close_at 正确设置（首个成员注册后 90 天）
4. timeout 正确分配 p=1
5. abandoned 和 timeout 计入 K
6. 跨品种 family 独立
7. 所有 L1 测试 37-46 通过

## 审核结论

**T5-PR-C2 文档化完成**。实施推迟，需 2.5 天工作量。
