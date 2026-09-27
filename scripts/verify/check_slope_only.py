import sys, os
sys.path.insert(0, '/home/abug/timesfm')
os.chdir('/home/abug/timesfm')

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
