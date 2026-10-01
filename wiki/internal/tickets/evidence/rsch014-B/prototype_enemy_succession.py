import json
from pathlib import Path

order = [1, 2, 3, 4]
cursor = 0
pending = None
deadline = None
trace = []

def preview():
    return pending if pending is not None else order[cursor]

def release(tick):
    global cursor, pending, deadline
    kind = preview()
    if pending is not None:
        assert deadline is not None and tick >= deadline
        pending, deadline = None, None
    else:
        assert kind == order[cursor]
        cursor = (cursor + 1) % len(order)
    trace.append({'tick': tick, 'event': 'release', 'type': kind,
                  'next_preview': preview(), 'normal_cursor': order[cursor]})

def skull_death(tick, kind, release_at):
    global pending, deadline
    if pending is None:
        pending, deadline = kind, release_at
    else:
        assert release_at == deadline
        pending = kind
    trace.append({'tick': tick, 'event': 'skull_death', 'type': kind,
                  'next_preview': preview(), 'release_at': deadline,
                  'normal_cursor': order[cursor]})

for tick in (0, 10, 20, 30):
    release(tick)
assert preview() == 1 and cursor == 0
skull_death(40, 3, 53)
assert preview() == 3 and deadline == 53
skull_death(49, 4, 53)
assert preview() == 4 and deadline == 53 and cursor == 0
release(53)
assert trace[-1] == {'tick': 53, 'event': 'release', 'type': 4,
                      'next_preview': 1, 'normal_cursor': 1}

result = {
    'model': 'one ordered four-type group with one latest-death override',
    'trace': trace,
    'assertions': 'normal group order; preview; latest of two pending deaths wins; original deadline and normal cursor persist; cursor resumes after replacement',
    'limitations': ['tick values are illustrative, not arcade measurements',
                    'does not execute or prove Ladybug source, ROM behavior, or memory fit',
                    'later-part group policy awaits clarification']
}
Path(__file__).with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
