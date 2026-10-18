import os

HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(HERE)
QUEUE = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.jsonl")
INPROGRESS = os.path.join(FM_ROOT, "data", "cache", "aligned_pending.inprogress.jsonl")
REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "aligned_verdicts.jsonl")
SEARCH_COMMITMENTS_PATH = os.path.join(FM_ROOT, "task_FM", "config", "search_commitments.jsonl")
STATE_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_state.json")
LOCK_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor.lock")
VERDICTS_INC = os.path.join(FM_ROOT, "task_FM", "known_verdicts.inc.md")
POOL_PATH = os.path.join(FM_ROOT, "task_FM", "config", "covariate_pool.json")
BACKLOG_PATH = os.path.join(FM_ROOT, "task_FM", "config", "covariate_backlog.jsonl")
SYMBOL_STATUS_PATH = os.path.join(FM_ROOT, "task_FM", "config", "symbol_status.json")
MENU_INC = os.path.join(FM_ROOT, "task_FM", "covariate_menu.inc.md")
REPORT_DIR = os.path.join(FM_ROOT, "docs", "superpowers", "reports")
STATE_MD = os.path.join(FM_ROOT, "STATE.md")
EVENTS_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_events.jsonl")
HEARTBEAT_PATH = os.path.join(FM_ROOT, "data", "cache", "supervisor_heartbeat")
STOP_REPORT_JSON = os.path.join(FM_ROOT, "data", "cache", "stop_report.json")
POLL_S = 300
PHASES = ("fast", "slow", "wait_quota")
RETEST_GATE_N = 350
FAMILY_REGISTRY = os.path.join(FM_ROOT, "task_FM", "config", "family_registry.jsonl")
PREREGISTRY_PATH = os.path.join(FM_ROOT, "task_FM", "config", "preregistry.jsonl")

# 障碍 1：拒收摘要文件路径（供 aggregate_rejection_stats.py 使用）
REJECTIONS_INC = os.path.join(FM_ROOT, 'task_FM', 'known_rejections.inc.md')

# Proposal lifecycle paths
PROPOSAL_STATUS_PATH = os.path.join(FM_ROOT, 'data', 'cache', 'proposal_status.jsonl')
REJECTED_PROPOSALS_PATH = os.path.join(FM_ROOT, 'data', 'cache', 'rejected_proposals.jsonl')
