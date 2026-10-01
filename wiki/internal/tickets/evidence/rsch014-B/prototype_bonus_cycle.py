import json
from pathlib import Path

sequence = (('red', 30), ('yellow', 150), ('blue', 420))

def level_start():
    return {'colour': 'red', 'remaining': 30, 'index': 0}

def tick(state):
    state['remaining'] -= 1
    if state['remaining'] == 0:
        state['index'] = (state['index'] + 1) % len(sequence)
        state['colour'], state['remaining'] = sequence[state['index']]

trace = []
for level in (1, 2, 3):
    state = level_start()
    assert state == {'colour': 'red', 'remaining': 30, 'index': 0}
    trace.append({'level': level, 'event': 'start', **state})
    for _ in range(30):
        tick(state)
    assert state['colour'] == 'yellow' and state['remaining'] == 150
    trace.append({'level': level, 'event': 'tick_30', **state})

out = {'model': 'proposed red-start state and existing red/yellow/blue dwell sequence',
       'trace': trace,
       'assertions': 'three starts red/30; each 30th tick becomes yellow/150',
       'limitations': ['deterministic contract model only',
                       'does not execute or prove Ladybug source or rendering']}
Path(__file__).with_suffix('.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
