#!/usr/bin/env python3
import json, os

state_file = 'data/cache/supervisor_state.json'
if os.path.exists(state_file):
    with open(state_file) as f:
        state = json.load(f)
    state['user_paused'] = False
    state.pop('user_paused_at', None)
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)
    print('  ✓ 已清除 user_paused 标志')
else:
    print('  ✓ 无需清除')
