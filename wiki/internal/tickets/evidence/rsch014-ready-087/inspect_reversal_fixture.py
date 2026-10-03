"""Source-qualified legal predecessor audit; no runtime or movement acceptance."""
from pathlib import Path
import hashlib,itertools,json,sys
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_bug002_enemy_gate_collision as oracle
initial=[int(g['initial_orientation']=='vertical') for g in oracle.GATES]
def runtime_legal(x,y,d,states):
    if y<11:return oracle.expected(x,y,d,states)
    if not (oracle.NAV[y][x]&oracle.EXIT_MASKS[d]):return False
    tx,ty=oracle.target(x,y,d)
    if not (0<=tx<24 and 0<=ty<24):return False
    return oracle.expected(x,y,d,states) if oracle.OWNER[ty][tx] else True
source=(ROOT/'src/enemy_runtime.s').read_text()
assert 'cmpa    #11\n        blo     edl_slow' in source
assert 'bne     edl_slow         ; target gate state must be authoritative' in source
assert 'bcc     ecd_blocked' in source
cases=0;model_blocked=[];source_blocked=[]
for y in range(24):
    for x in range(24):
        # Nonzero exit masks define authored traversable floor. Empty cells,
        # border $40 and pivot $10 have no legal actor-entry predecessor.
        if not (oracle.NAV[y][x]&15):continue
        neighbors=[oracle.target(x,y,d) for d in range(4)]
        ids=sorted({oracle.OWNER[ty][tx]-1 for tx,ty in [(x,y)]+neighbors
                    if 0<=tx<24 and 0<=ty<24 and oracle.OWNER[ty][tx]})
        for bits in itertools.product((0,1),repeat=len(ids)):
            states=initial[:]
            for gate,value in zip(ids,bits):states[gate]=value
            cases+=1
            if not any(oracle.fixed_enemy(x,y,d,states) for d in range(4)):
                model_blocked.append([x,y,bits])
            if not any(runtime_legal(x,y,d,states) for d in range(4)):
                source_blocked.append([x,y,bits])
assert not model_blocked and not source_blocked
assert runtime_legal(6,4,3,initial) and runtime_legal(5,4,3,initial)
assert [d for d in range(4) if runtime_legal(4,4,d,initial)]==[1]
flipped=initial[:];flipped[0]=1
assert [d for d in range(4) if runtime_legal(4,4,d,flipped)]==[0]
receipt={
 'ticket':'BUG-087','kind':'offline source/predecessor preparation only',
 'source_sha256':hashlib.sha256((ROOT/'src/enemy_runtime.s').read_bytes()).hexdigest(),
 'maze_sha256':hashlib.sha256((ROOT/'assets/arcade/maze.json').read_bytes()).hexdigest(),
 'oracle_sha256':hashlib.sha256((ROOT/'scripts/verify_bug002_enemy_gate_collision.py').read_bytes()).hexdigest(),
 'floor_definition':'maze_nav low nibble nonzero; empty/border/pivot records excluded as non-enterable actor cells',
 'local_orientation_cases':cases,'source_model_all_exits_closed':0,'existing_oracle_all_exits_closed':0,
 'reversal_predecessor':{'gate_states':initial,'legal_arrival_cells':[[6,4],[5,4],[4,4]],
   'incoming_direction':3,'incoming_name':'west','only_exit_at_boundary':1,'exit_name':'east',
   'runtime_branch':'ecd_choose after scanning all nonreverse directions; ENEMY_CANDIDATE equals ENEMY_REVERSE'},
 'rejected_agent_description':'Gate0 pivot(5,3) flip0->1 at actor(4,4) leaves north, not east. Reversal fixture uses unchanged initial gate0=0; no rotation is required.',
 'remaining':'Bind a real enemy callback with this legal predecessor and another moving actor; observe FRONT displacement and selector. No direct-helper shortcut, forced DIR_NONE, position-hold assertion or CPU acceptance follows from this source model.',
 'runtime_launched':False,'status':'pass-offline-only'}
print(json.dumps(receipt,indent=2))
