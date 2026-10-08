import sys, os
from pathlib import Path

# 仓库根由本文件位置推导（不硬编码绝对路径：换机器/换用户仍可用）
FM_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FM_ROOT))
sys.path.insert(0, str(FM_ROOT / "scripts"))
os.chdir(FM_ROOT)

from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
import scripts.monthly_backtest as mb

dm = DailyModel()
hm = HourlyModel(shared_model=dm.model)
r = mb.run_symbol_backtest(symbol='RB', daily_model=dm, hourly_model=hm,
                           cov_override='none', max_points=6)
ci = getattr(hm, 'last_covariate_input', None)
print('last_covariate_input keys =', None if ci is None else ci[1])
if ci is not None:
    print('n_channels =', ci[0].shape if hasattr(ci[0], 'shape') else 'n/a')
    assert ci[1] == ['daily_slope'], f'expected slope_only, got {ci[1]}'
    print('PASS: slope_only confirmed')
else:
    print('last_covariate_input is None (xreg fallback path)')
