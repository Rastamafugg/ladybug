"""Verify natural first-rank entry, pending TOP ownership, and END commit."""
from collections import deque
from pathlib import Path
import json
import time


root = Path(__file__).resolve().parents[1]
source = (root / "repro/bug044-top-authority-20260926.py").read_text()
prefix = source.split('\ntry:\n    go("attract_tick_ready")', 1)[0]
exec(compile(prefix, str(root / "repro/bug044-top-authority-20260926.py"), "exec"))
presentation = runtime.symbols(build / "ladybug-presentation-runtime.map")
name_module = runtime.symbols(build / "ladybug-highscore-runtime.map")
helper = runtime.symbols(build / "ladybug-highscore-helper.map")
name_runtime = (build / "ladybug-highscore-runtime.bin").read_bytes()
scenario=sys.argv[1] if len(sys.argv)>1 else "rank1"
assert scenario in ("rank1","rank2","nonqualifying")
score_seed="089990" if scenario=="rank1" else ("084990" if scenario=="rank2" else "000000")
score_final="090010" if scenario=="rank1" else ("085010" if scenario=="rank2" else "000020")
insert_rank=0 if scenario=="rank1" else 1
manifest = json.loads((build / "ladybug-presentation.json").read_text())
contract = manifest["high_score_name_entry"]
edges = contract["full_edge_masks"]
table_addr = 0xAF84
pending_addr = 0xAFDE
table_physical = 0x34 * 8192 + table_addr - 0xA000
pending_physical = 0x34 * 8192 + pending_addr - 0xA000
helper_bytes = (build / "ladybug-highscore-helper.bin").read_bytes()
glyphs = {
    int(index): int(tile_id)
    for index, tile_id in re.findall(
        r"^PRESENTATION_GLYPH_(\d+) equ (\d+)$",
        (build / "ladybug_presentation.inc").read_text(encoding="ascii"),
        re.MULTILINE,
    )
    if int(index) < 10
}
evidence = {
    "schema": "bug044-ranking-end-v1",
    "rom_sha256": evidence["rom_sha256"],
    "phase_deadline_seconds": 40,
    "success_marker": "natural qualified entry keeps committed TOP before END and commits score/name once after END",
    "timeout_meaning": "the named runtime marker was not reached before its bounded phase deadline",
    "natural_route": {},
    "pending": {},
    "commit": {},
}


def go(symbol, symbols=presentation, deadline=40):
    address = symbols[symbol]
    ids = monitor.setup(client, [address])
    try:
        client.call("run")
        hit = client.call("wait_for_stop",{"timeout_ms":int(deadline*1000)},timeout=deadline+2)
        assert hit.get("pc") == address, (symbol, hit, hex(address))
    finally:
        monitor.clear(client, ids)
    return hit


def key(code, pressed):
    client.call("inject_key", {"key": code, "action": "press" if pressed else "release"})


def physical_record():
    return physical(table_physical, 10)


def expected_tile(tile_id):
    if tile_id in (0, manifest["black_tile"]):
        return bytes(32)
    code, pen = resident[descriptor_offset + 2 * tile_id:descriptor_offset + 2 * tile_id + 2]
    assert pen != 0, ("TOP text ID is not a typed glyph", tile_id, code, pen)
    return glyph(code, pen)


def top_pixels(record, phase):
    name_expected = [expected_tile(native or manifest["black_tile"])
                     for native in record[3:10]]
    digits = [digit for value in record[:3] for digit in (value >> 4, value & 15)]
    score_expected = [expected_tile(glyphs[digit]) for digit in digits]
    mismatches = []
    for owner in (0, 1):
        frame = runtime.read_owner(client, owner)

        def tile(address):
            offset = address - 0x2000
            return b"".join(frame[offset + row * 160:offset + row * 160 + 4]
                            for row in range(8))

        for key, expected in (("top_name_destinations", name_expected),
                              ("top_right_destinations", score_expected),
                              ("top_destinations", score_expected)):
            for index, (address, exp) in enumerate(zip(contract[key], expected)):
                actual = runtime.frame_tile(frame, address)
                if actual != exp:
                    mismatches.append((owner, key, index, actual.hex(), exp.hex()))
    assert not mismatches, (phase, mismatches[:5])


def route_between(start, target):
    dirs = ((0, -1, 1), (1, 0, 2), (0, 1, 4), (-1, 0, 8))
    queue = deque([start])
    previous = {start: None}
    previous_dir = {}
    while queue:
        x, y = queue.popleft()
        if (x, y) == target:
            break
        mask = edges[y * 24 + (x - 8)]
        for direction, (dx, dy, bit) in enumerate(dirs):
            nxt = (x + dx, y + dy)
            if 8 <= nxt[0] <= 31 and 0 <= nxt[1] < 24 and mask & bit and nxt not in previous:
                previous[nxt] = (x, y)
                previous_dir[nxt] = direction
                queue.append(nxt)
    assert target in previous, ("unreachable name action", start, target)
    path = []
    while target != start:
        path.append(previous_dir[target])
        target = previous[target]
    return path[::-1]


def move_cell(direction):
    delta = (-320, 1, 320, -1)[direction]
    for pixel in range(4):
        start = low(0x000B, 2)
        start_ptr = int.from_bytes(start, "big")
        for attempt in range(4):
            runtime.write_byte(client, 0x0005, direction)
            runtime.write_byte(client, 0x000F, direction)
            client.call("run")
            hit = client.call("wait_for_stop", {"timeout_ms": 5000}, timeout=7)
            if hit.get("pc")==name_module["name_action_cl"]:
                before=low(0xCB)[0];assert before>0
                go("name_action_done",name_module)
                assert low(0xCB)[0]==before-1
                assert physical_record()==default_record
                evidence["CL"]={"before":before,"after":low(0xCB)[0],"committed_TOP_unchanged":True}
                client.call("run");hit=client.call("wait_for_stop",{"timeout_ms":5000},timeout=7)
            assert hit.get("pc") == name_module["name_joy_ready"], ("name movement", hit)
            now = int.from_bytes(low(0x000B, 2), "big")
            if now != start_ptr:
                assert now == ((start_ptr + delta) & 0xFFFF), (direction, pixel, hex(now), hex(start_ptr))
                break
        else:
            raise AssertionError(("name pixel step timeout", direction, pixel))
    runtime.write_byte(client, 0x0005, 0xFF)
    runtime.write_byte(client, 0x000F, 0xFF)


def route_to(target):
    pos = (low(0x0009)[0], low(0x000A)[0])
    for direction in route_between(pos, tuple(target)):
        move_cell(direction)
    assert (low(0x0009)[0], low(0x000A)[0]) == tuple(target), (pos, target)


def route_to_end(target):
    global name_bp
    end_address = helper["highscore_after_highscore_start"]
    action_address = name_module["name_action_end"]
    directions = route_between((low(0x0009)[0], low(0x000A)[0]), tuple(target))
    for direction in directions[:-1]:
        move_cell(direction)
    direction = directions[-1]
    delta = (-320, 1, 320, -1)[direction]
    monitor.clear(client, name_bp)
    name_bp = monitor.setup(client, [name_marker, action_address, end_address])
    for pixel in range(4):
        start_ptr = int.from_bytes(low(0x000B, 2), "big")
        for attempt in range(4):
            runtime.write_byte(client, 0x0005, direction)
            runtime.write_byte(client, 0x000F, direction)
            client.call("run")
            hit = client.call("wait_for_stop", {"timeout_ms": 5000}, timeout=7)
            assert hit.get("reason") == "breakpoint", hit
            if hit.get("pc") == end_address:
                assert pixel == 3, ("early-END-transition", pixel, hit)
                return hit
            if hit.get("pc") == action_address:
                assert pixel == 3, ("early-END-action", pixel, hit)
                assert (low(0x0009)[0], low(0x000A)[0]) == tuple(target)
                assert physical_record() == default_record
                evidence["commit"]["record0_at_END_action_before_commit"] = physical_record().hex()
                evidence["commit"]["pending_at_END"] = physical(pending_physical,7).hex()
                runtime.write_byte(client, 0x0005, 0xFF)
                runtime.write_byte(client, 0x000F, 0xFF)
                monitor.clear(client, name_bp)
                name_bp = monitor.setup(client, [end_address])
                client.call("run")
                boundary = client.call("wait_for_stop", {"timeout_ms": 10000}, timeout=12)
                assert boundary.get("reason") == "breakpoint" and boundary.get("pc") == end_address, boundary
                return boundary
            assert hit.get("pc") == name_marker, hit
            now = int.from_bytes(low(0x000B, 2), "big")
            if now != start_ptr:
                assert now == ((start_ptr + delta) & 0xFFFF), (direction, pixel, hex(now), hex(start_ptr))
                break
        else:
            raise AssertionError(("END approach pixel timeout", direction, pixel))
    runtime.write_byte(client, 0x0005, 0xFF)
    runtime.write_byte(client, 0x000F, 0xFF)
    # END sets the commit flag in name_cell_arrival. The helper commits on the
    # next page-$23 phase tick, before it can call name_joy_ready again.
    monitor.clear(client, name_bp)
    name_bp = monitor.setup(client, [end_address])
    client.call("run")
    hit = client.call("wait_for_stop", {"timeout_ms": 10000}, timeout=12)
    assert hit.get("reason") == "breakpoint" and hit.get("pc") == end_address, hit
    return hit


try:
    go("attract_tick_ready")
    actual_module = runtime.read_bytes(client, 0x1900,
        len((build / "ladybug-presentation-runtime.bin").read_bytes()))
    assert actual_module == (build / "ladybug-presentation-runtime.bin").read_bytes()
    key(5, True); go("credit_tick"); key(5, False)
    assert low(0xA8) == b"\x01"
    key(1, True); go("start_screen_done"); key(1, False)
    assert low(0xA8) == b"\x00"
    key(0x2B, True)
    go("add_dot_score", main_symbols)
    assert_live_resident("add_dot_score", 48)
    assert physical_record() == default_record
    client.call("write_memory", {
        "space": "physical", "addr": 0x38 * 8192 + 0x1D, "data": score_seed,
    })
    go("add_dot_score", main_symbols)
    go("mainloop", main_symbols)
    assert low(0x1D, 3) == bytes.fromhex(score_final)
    key(0x2B, False)
    evidence["natural_route"] = {
        "score_after_natural_dot_awards": low(0x1D, 3).hex(),
        "record0_before_death": physical_record().hex(),
        "death_probe_deadline_seconds": 40,
        "success_marker": "name_joy_ready after normal gameplay death and qualified game-over dispatch",
    }

    # The complete high-score runtime is the live input/renderer module at $0300.
    if scenario=="nonqualifying":
        table_before=physical(table_physical,90)
        go("credit_tick")
        assert low(0xA5)[0]==5 and low(0xA6)[0]==3
        assert low(0xC9)[0]==255
        assert physical(table_physical,90)==table_before
        evidence["nonqualifying"]={"insert":255,"table_unchanged":True,"name_entry_bypassed":True}
        evidence["result"]="pass"
        raise SystemExit(0)
    name_marker = name_module["name_joy_ready"]
    name_bp = monitor.setup(client, [name_marker])
    deadline = time.monotonic() + 40
    while True:
        client.call("run")
        remaining = max(1, int((deadline - time.monotonic()) * 1000))
        hit = client.call("wait_for_stop", {"timeout_ms": remaining}, timeout=max(2, remaining / 1000 + 2))
        assert hit.get("reason") == "breakpoint" and hit.get("pc") == name_marker, hit
        if low(0xA5)[0] == 8 and low(0xA6)[0] == 5:
            break
        assert time.monotonic() < deadline, ("natural-death-to-name-screen", low(0xA5)[0], low(0xA6)[0])
    assert runtime.read_bytes(client, 0x0300, len(name_runtime)) == name_runtime
    assert low(0xC9)[0] == insert_rank
    assert low(0xBF, 3) == bytes.fromhex(score_final)
    assert physical_record() == default_record
    top_pixels(default_record, "pending-rank1")
    evidence["natural_route"].update({"name_mode": low(0xA5)[0], "name_screen": low(0xA6)[0],
        "insert_rank": low(0xC9)[0], "live_name_runtime_exact": True})

    # Sample complete active name-entry calls with actual keyboard input.
    monitor.clear(client,name_bp)
    main=main_symbols["mainloop"];ret=main+resident[main-0xC000:main-0xC000+32].index(bytes.fromhex("bd1900"))+3
    key(0x2D,True);samples=[];deadline=time.monotonic()+40
    for i in range(40):
        assert time.monotonic()<deadline
        go("presentation_flow_tick");t=client.call("read_cycles")["cpu_cycles"]
        go("return",{"return":ret});samples.append(client.call("read_cycles")["cpu_cycles"]-t)
        assert low(0xA5)[0]==8
    key(0x2D,False)
    evidence["active_name_control_timing"]={"samples":len(samples),"maximum_cycles":max(samples),"target_cycles":27000}
    assert max(samples)<=27000,evidence["active_name_control_timing"]
    go("name_joy_ready",name_module)
    name_bp=monitor.setup(client,[name_marker])

    # Move to A, verify it remains pending, then move to END.
    route_to(next((x, y) for x, y, tile_id in contract["action_records"] if tile_id == 36))
    assert low(0xCB)[0] == 1
    assert physical(pending_physical, 7) == bytes([36]) + bytes([manifest["black_tile"]]) * 6
    assert physical_record() == default_record
    top_pixels(default_record, "letter-pending-before-END")
    evidence["pending"] = {"name_length": low(0xCB)[0], "name_hex": physical(pending_physical, 7).hex(),
        "record0_unchanged": True, "TOP_exact_both_owners": True}

    if scenario=="rank1":
        clear_bp=monitor.setup(client,[name_module["name_action_cl"]])
        route_to(contract["cl_cells"][0]);monitor.clear(client,clear_bp)
        assert "CL" in evidence
        top_pixels(default_record,"after-CL")
    table_before_commit = physical(table_physical, 90)
    end_hit = route_to_end(contract["end_cells"][0])
    end_address = helper["highscore_after_highscore_start"]
    helper_offset = end_address - helper["highscore_phase_tick"]
    expected_live = helper_bytes[helper_offset:helper_offset + 16]
    actual_live = runtime.read_bytes(client, end_address, len(expected_live))
    assert actual_live == expected_live, ("helper live-byte identity", actual_live.hex(), expected_live.hex())
    assert (physical_record() != default_record) == (insert_rank==0)
    evidence["commit"].update({"END_requested": True, "record0_after_commit": physical_record().hex(),
        "deadline_seconds": 10, "success_marker": "highscore_after_highscore_start after END commit", "pc": end_hit.get("pc")}
    )
    expected_record = bytes.fromhex(score_final) + bytes.fromhex(evidence["commit"]["pending_at_END"])
    committed = physical(table_physical+insert_rank*10,10)
    assert committed == expected_record, (committed.hex(), expected_record.hex())
    expected_table = table_before_commit[:insert_rank*10]+committed+table_before_commit[insert_rank*10:80]
    assert physical(table_physical, 90) == expected_table
    evidence["commit"].update({"record0_after_END": committed.hex(), "record1_after_END": physical(table_physical + 10, 10).hex(), "table_shift_exact": True})
    monitor.clear(client,name_bp)
    go("credit_tick")
    for _ in range(3):go("pft_ready")
    committed=physical_record() # TOP is always row zero, even after a rank-two insertion.
    published=set()
    for publication in range(2):
        owner=low(0x8F)[0];published.add(owner)
        frame=runtime.read_owner(client,owner)
        for i,native in enumerate(committed[3:]):
            assert runtime.frame_tile(frame,manifest["high_score_table"]["name_destinations"][0]+i*4)==expected_tile(native),("rank-name",owner,i)
        for i,digit in enumerate([d for v in committed[:3] for d in (v>>4,v&15)]):
            assert runtime.frame_tile(frame,manifest["high_score_table"]["score_destinations"][0]+i*4)==expected_tile(glyphs[digit]),("rank-score",owner,i)
        if publication==0:
            key(5,True);go("start_screen_done");key(5,False);go("credit_tick")
            for _ in range(3):go("pft_ready")
    assert published=={0,1},published
    evidence["post_commit_highscore_published_owners"]=sorted(published)
    evidence["result"] = "pass"
except Exception as exc:
    evidence["result"] = "fail"
    evidence["failure"] = f"{type(exc).__name__}: {exc}"
    try:
        client.call("pause")
        evidence["failure_state"] = {"registers": client.call("read_registers"), "mode": low(0xA5)[0],
            "screen": low(0xA6)[0], "score": low(0x1D, 3).hex(), "record0": physical_record().hex()}
    except Exception:
        pass
finally:
    client.close()
    monitor.stop(process)
    (build / f"bug044-ranking-{scenario}-20260926.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(json.dumps(evidence, indent=2))
if evidence["result"] != "pass":
    raise SystemExit(1)
