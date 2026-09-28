"""Bounded CPU bookkeeping experiment using the existing verifier harness.
No complete adaptive ROM is installed. Callback stubs do not draw or play sound.
"""
from pathlib import Path
import hashlib,json,sys,time
reference=Path(sys.argv[1]);fit=Path(sys.argv[2]);output=Path(sys.argv[3])
sys.path.insert(0,str(reference/"scripts"))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=reference/"build";f=fit/"build/adaptive-fit"
ms=r.symbols(f/"mapped.map");bs=r.symbols(f/"banked.map");ps=r.symbols(b/"ladybug-presentation-runtime.map")
rom=b/"ladybug.rom";mapped=(f/"mapped.bin").read_bytes();banked=(f/"banked.bin").read_bytes();callbacks=(f/"callbacks.bin").read_bytes()
assert len(mapped)<=220 and len(banked)<=698
S=0xBD24;A=0xBC04;B=0xBC94;RET=0x18FC
results={"phase":"isolated bookkeeping with synthetic no-draw callbacks","deadline_seconds":45,"success_marker":"all component calls return to $18FC with expected journals and intents","timeout_meaning":"component boundary absent, not proof of game slowdown","rom_sha256":hashlib.sha256(rom.read_bytes()).hexdigest(),"mapped_sha256":hashlib.sha256(mapped).hexdigest(),"banked_sha256":hashlib.sha256(banked).hexdigest(),"cycles_unit":"verified fast CPU cycles = event_ticks / 8","cases":[],"scope":"No gameplay, collision, pixel restoration, audio or complete worklist acceptance"}
p,c=r.launch_fast(m,Path("/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar"),rom)
def read(addr,n=1):return r.read_bytes(c,addr,n)
def write(addr,v):c.call("write_memory",{"addr":addr,"data":bytes(v).hex()})
def word(addr,v):write(addr,v.to_bytes(2,"big"))
def call(name,owner=0,trace=False):
    address=ms.get(name,bs.get(name));assert address is not None
    write(0x1EFC,[RET>>8,RET&255]);c.call("write_registers",{"pc":address,"s":0x1EFC,"dp":0,"cc":0x50,"a":owner})
    starts=c.call("read_cycles")["event_ticks"]
    events=[];stops=[RET]+([0x1803,0x1806] if trace else [])
    ids=m.setup(c,stops)
    deadline=time.monotonic()+45
    try:
        while True:
            assert time.monotonic()<deadline,"45-second component marker deadline"
            c.call("run");h=c.call("wait_for_stop",{"timeout_ms":10000},timeout=12)
            if h.get("pc")==RET:break
            assert h.get("pc") in stops,h
            regs=c.call("read_registers");events.append({"kind":"global" if h["pc"]==0x1803 else "key","class":regs["a"],"record":(read(0x7F,16)+read(9,2)).hex()})
            # Existing harness resumes from a breakpoint with run; it does not
            # provide a monitor step method.
    finally:m.clear(c,ids)
    ticks=c.call("read_cycles")["event_ticks"]-starts
    assert ticks%8==0,ticks
    return ticks//8,events,c.call("read_registers")
def reset():
    word(2,1000);write(0x91,[0]);word(0x92,0);call("adaptive_reset")
def rec(cell,box=None,letter=None,gates=(),reset=False):
    v=bytearray(18);v[0]=0x20;v[16:18]=bytes(cell)
    if box:v[0]|=0x10;v[2:4]=bytes(box)
    if letter:v[1]|=4;v[4:7]=bytes(letter)
    for j,(gate,mode) in enumerate(gates):v[9+j*2]=gate;v[10+j*2]=mode;v[14+j]=1
    if reset:v[1]|=0x1A
    return bytes(v)
def expected(records):
    if any(v[0]&0x40 for v in records):return [("global",3,None)]
    event=[("global",k,None) for k in range(3)]
    last_reset=max([i+1 for i,v in enumerate(records) if v[1]&8] or [0])
    def present(v,k):return bool(v[0]&0x20) if k==0 else bool(v[0]&0x10) if k==1 else bool(v[1]&4) if k==2 else bool(v[9 if k==3 else 11])
    def key(v,k):return v[16:18] if k==0 else v[2:3] if k==1 else v[4:6] if k==2 else v[9 if k==3 else 11:10 if k==3 else 12]
    for k in range(5):
        for i,v in enumerate(records):
            if not present(v,k) or (k==1 and i<last_reset):continue
            newer=any((key(v,k) in (w[9:10],w[11:12])) if k>=3 else (present(w,k) and key(v,k)==key(w,k)) for w in records[i+1:])
            if not newer:event.append(("key",k,v.hex()))
    return event
try:
    ids=m.setup(c,[ps["pft_ready"]]);c.call("run");h=c.call("wait_for_stop",{"timeout_ms":45000},timeout=47);m.clear(c,ids)
    assert h.get("pc")==ps["pft_ready"],h
    assert read(0x800,4091)==(b/"ladybug-enemy-runtime.rom").read_bytes(),"loaded enemy identity"
    assert read(0x1900,1273)==(b/"ladybug-presentation-runtime.bin").read_bytes(),"loaded presentation identity"
    assert read(0xC000,15872)==(b/"ladybug-runtime.rom").read_bytes()[:15872],"loaded resident/assets identity"
    write(0xFFA5,[0x34]);write(0x9FD,mapped);write(0xBD44,banked);write(0x1800,callbacks);write(RET,[0x20,0xFE])
    assert read(0x9FD,len(mapped))==mapped and read(0xBD44,len(banked))==banked and read(0x1800,len(callbacks))==callbacks,"staged/destination payload identity"
    results["identity_verified"]={"loaded_enemy_bytes":4091,"loaded_presentation_bytes":1273,"loaded_resident_assets_bytes":15872,"mapped_payload_bytes":len(mapped),"banked_payload_bytes":len(banked),"callback_payload_bytes":len(callbacks)}
    for steps in (1,2,4):
        reset();word(2,1000+steps);cycles,events,regs=call("adaptive_batch")
        assert read(S+20,2)==bytes([steps,steps]);assert int.from_bytes(read(S+2,2),"big")==steps
        assert read(A,steps*18)==read(B,steps*18);assert int.from_bytes(read(S+4,2),"big")==0
        assert regs["cc"]&1
        results["cases"].append({"name":"batch","steps":steps,"cycles":cycles,"history_records_each":steps,"synthetic_tick_only":True})
    records=[rec((2,4),(5,6),(3,4,3),[(1,0)]),rec((4,4),(5,5),(3,4,1),[(2,0)]),rec((2,4),(6,6),(4,4,1),[(0,0),(1,1)]),rec((4,4),reset=True),rec((6,4),(5,5),(3,4,3),[(2,1)]),bytes(18),rec((8,4),(7,6),(5,4,5),[(3,0),(4,0)]),rec((6,4),(7,5),(5,4,3),[(4,1),(3,1)])]
    for count in (0,1,2,4):
        reset();write(A,b"".join(records[:count]));write(S+20,[count])
        cycles,events,_=call("adaptive_reduce",0,True)
        observed=[(e["kind"],e["class"],e["record"] if e["kind"]=="key" else None) for e in events]
        assert observed==expected(records[:count])
        results["cases"].append({"name":"bounded journal reduction","records":count,"cycles":cycles,"pixels_not_drawn":True})
    # Required rare coverage: a staged rebuild supersedes all earlier keys.
    reset();stage_records=list(records[:4]);v=bytearray(stage_records[1]);v[0]|=0x40;stage_records[1]=bytes(v)
    write(A,b"".join(stage_records));write(S+20,[4]);before=read(0x7F,16)+read(9,2)
    cycles,events,_=call("adaptive_reduce",0,True)
    assert [(e["kind"],e["class"]) for e in events]==[("global",3)]
    assert read(0x7F,16)+read(9,2)==before and read(S+20)==b"\x04"
    results["cases"].append({"name":"stage dominance preserves caller and pending journal","records":4,"cycles":cycles,"only_stage_callback":True,"pixels_not_drawn":True})
    for owner in (0,1):
        reset();target=A if owner==0 else B
        write(target,b"".join(records));write(S+20+owner,[8]);live=bytes(range(16));write(0x7F,live);write(9,[10,12]);before=read(0x7F,16)+read(9,2)
        cycles,events,regs=call("adaptive_reduce",owner,True)
        observed=[(e["kind"],e["class"],e["record"] if e["kind"]=="key" else None) for e in events]
        assert observed==expected(records),(observed,expected(records))
        assert read(S+20+owner)==bytes([8]),"reducer must not clear before completion"
        assert read(0x7F,16)+read(9,2)==before,"caller intents restored"
        write(S+21-owner,[3]);word(S+8,999);cycles_complete,_,_=call("adaptive_complete",owner)
        assert read(S+20+owner)==bytes([0]) and read(S+21-owner)==bytes([3]),"completed owner only"
        results["cases"].append({"name":"eight-record reduction","owner_secondary":owner,"cycles":cycles,"key_callbacks":sum(e["kind"]=="key" for e in events),"global_callbacks":sum(e["kind"]=="global" for e in events),"complete_cycles":cycles_complete,"pixels_not_drawn":True})
    # Alternating completed targets must retain the other target's accumulated
    # history. This replays transaction ordering with synthetic callbacks only.
    for first_owner in (0,1):
        reset();raw=1000;transactions=[]
        for transaction,steps in enumerate((2,2,4,4)):
            raw+=steps;word(2,raw);call("adaptive_batch")
            owner=(first_owner+transaction)%2;target=A if owner==0 else B
            count=read(S+20+owner)[0];other_before=read(S+21-owner)[0]
            data=read(target,count*18);items=[data[i:i+18] for i in range(0,len(data),18)]
            live=read(0x7F,16)+read(9,2)
            _,events,_=call("adaptive_reduce",owner,True)
            observed=[(e["kind"],e["class"],e["record"] if e["kind"]=="key" else None) for e in events]
            assert observed==expected(items) and read(0x7F,16)+read(9,2)==live
            assert read(S+20+owner)[0]==count and count<=8
            call("adaptive_complete",owner)
            assert read(S+20+owner)==b"\0" and read(S+21-owner)[0]==other_before
            transactions.append({"steps":steps,"records_consumed":count,"other_records_retained":other_before,"target_secondary":owner})
        results["cases"].append({"name":"alternating transaction histories","first_target_secondary":first_owner,"transactions":transactions,"synthetic_callbacks_only":True})
    reset();word(2,1002);write(0x91,[1]);before=read(A,320);cycles,_,regs=call("adaptive_batch")
    assert read(A,320)==before and not regs["cc"]&1
    write(0x91,[0]);call("adaptive_batch");assert read(S+20,2)==b"\x02\x02"
    results["cases"].append({"name":"pending publication blocks mutation then resumes two ticks","blocked_cycles":cycles})
    reset();write(S+20,[8,8]);before=read(A,288);cycles,_,regs=call("adaptive_append")
    assert regs["cc"]&1 and read(A,288)==before and read(S+20,2)==b"\x08\x08"
    results["cases"].append({"name":"ninth record refused","cycles":cycles})
    reset();word(S,0xFFFF);word(S+12,0xFFFF);word(2,1);cycles,_,_=call("adaptive_batch");assert int.from_bytes(read(S+2,2),"big")==2
    results["cases"].append({"name":"raw counter wrap two ticks","cycles":cycles})
    reset();word(S+4,0xFFFE);word(2,1005);cycles,_,regs=call("adaptive_batch");assert read(S+22)[0]&1 and read(S+20,2)==b"\0\0"
    _,_,_=call("adaptive_batch");assert read(S+20,2)==b"\0\0"
    results["cases"].append({"name":"debt saturation stops later mutation","cycles":cycles})
    reset();modified=callbacks[:-2]+bytes([0x86,1,0x39]);write(0x1800,modified)
    assert read(0x1800,len(modified))==modified
    word(2,1004);cycles,_,_=call("adaptive_batch")
    assert read(S+20,2)==b"\x01\x01" and int.from_bytes(read(S+4,2),"big")==3
    held,_,_=call("adaptive_batch");assert read(S+20,2)==b"\x01\x01"
    word(0x92,1);word(2,1005);released,_,_=call("adaptive_batch");assert read(S+20,2)==b"\x02\x02"
    results["cases"].append({"name":"publication barrier blocks until commit changes","first_cycles":cycles,"held_cycles":held,"resumed_cycles":released,"synthetic_barrier_callback_sha256":hashlib.sha256(modified).hexdigest()})
    write(0x1800,callbacks);assert read(0x1800,len(callbacks))==callbacks
    reset();word(S+8,1000);word(2,1001);call("adaptive_complete")
    assert read(S+16)==b"\x02"
    for i in range(8):
        word(S+8,1001);call("adaptive_complete")
        assert read(S+16)==bytes([1 if i==7 else 2])
    results["cases"].append({"name":"cadence lowers on miss and raises after eight quick transactions","controller_only":True})
    results["result"]="PASS: isolated bookkeeping assertions only; no complete adaptive ROM acceptance"
except Exception as error:
    results["result"]="FAIL";results["error"]=repr(error);raise
finally:
    output.write_text(json.dumps(results,indent=2)+"\n")
    c.close();p.terminate()
    try:p.wait(timeout=3)
    except Exception:p.kill()
print(json.dumps(results,indent=2))
