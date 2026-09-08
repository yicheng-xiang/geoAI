"""Opt-in live WFS integration check; does not modify local data files."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import init_map_state
from csdi_tools import csdi_map, csdi_nearby

state = init_map_state()
result = csdi_map(state, 'csdi_fitness_rooms')
assert result['ok'], result
print(result['message'], flush=True)
store = state['temporary_datasets']
origin = store['csdi_fitness_rooms']['dataframe'].iloc[0].NAME
print('Origin:', origin, flush=True)
for mode in ['buffer', 'driving']:
    result = csdi_nearby(state, origin, mode=mode)
    assert result['ok'], result
    print(mode, result['message'], flush=True)
    print('Sources:', [(d['id'], d['row_count']) for d in store.values()], flush=True)
    print('Statistics:', result['data']['statistics'], flush=True)
assert len(store) == 2
