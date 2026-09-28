"""Static BUG-058 design accounting; does not assemble or change runtime code."""
import argparse, hashlib, json, re, subprocess
from pathlib import Path

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def symbol(path, name):
    match = re.search(r"Symbol: " + re.escape(name) + r" .*? = ([0-9A-Fa-f]+)", path.read_text())
    if not match:
        raise ValueError(name)
    return int(match.group(1), 16)

def histories(start):
    # Abstract record retention, not renderer or collision verification.
    pending = [[], []]
    observed = [[], []]
    ticks = 0
    maximum = 0
    for image, steps in enumerate([4, 4, 1, 2, 4, 1, 3, 2] * 8):
        owner = (start + image) % 2
        for _ in range(steps):
            ticks += 1
            for queue in pending:
                if len(queue) >= 8:
                    raise AssertionError("journal must stop before accepting another tick")
                queue.append(ticks)
                maximum = max(maximum, len(queue))
        observed[owner].extend(pending[owner])
        pending[owner].clear()  # Only this successfully rendered owner clears.
    for owner in range(2):
        observed[owner].extend(pending[owner])
        assert observed[owner] == list(range(1, ticks + 1))
    return {"starting_owner": start, "ticks": ticks, "maximum_records": maximum,
            "both_histories_retain_every_tick": True}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.candidate
    layout_path = root / "build/ladybug-sparse-layout.json"
    layout = json.loads(layout_path.read_text())
    resident = symbol(root / "build/ladybug.map", "resident_end") - 0xC000
    enemy = (root / "build/ladybug-enemy-runtime.rom").stat().st_size
    projection = symbol(root / "build/ladybug-enemy-runtime.map", "framebuffer_queue_damage") - symbol(root / "build/ladybug-enemy-runtime.map", "framebuffer_project_damage")
    queue = symbol(root / "build/ladybug-enemy-runtime.map", "roam_mark_underlay") - symbol(root / "build/ladybug-enemy-runtime.map", "framebuffer_queue_damage")
    gmc = layout["gmc"]
    assert not any("cadence" in s["target"] for s in gmc["segments"]), "wrong prototype manifest"
    regions = [("history_a", 0xBC04, 0xBC94), ("history_b", 0xBC94, 0xBD24),
               ("scheduler_state", 0xBD24, 0xBD44), ("helper_envelope", 0xBD44, 0xBFFE)]
    assert all(a[2] == b[1] for a, b in zip(regions, regions[1:]))
    assert regions[-1][2] <= 0xBFFE  # Entropy seed never allocated.
    state_names = {"last_vblank": 2, "sim_sequence": 2, "debt": 2,
                   "audio_sequence": 2, "work_begin": 2, "work_end": 2,
                   "presentation_due": 2, "barrier_commit": 2,
                   "cadence": 1, "quick_streak": 1, "batch_left": 1,
                   "barrier": 1, "history_counts": 2, "fault_flags": 1,
                   "current_index": 1, "journal_pointer": 2,
                   "saved_pointer": 2, "saved_mode": 1, "reserved": 3}
    assert sum(state_names.values()) == 32
    overflow_queue = list(range(8))
    overflow_rejected = len(overflow_queue) >= 8
    assert overflow_rejected and len(overflow_queue) == 8
    examples = []
    for steps in (1, 2):
        seq = 0
        movement = [0, 0]
        for _ in range(120 // steps):
            for _ in range(steps):
                seq += 1
                for actor in range(2):
                    if seq & 1 == actor:
                        movement[actor] += 2
        assert movement == [120, 120]
        examples.append({"logic_ticks": seq, "ticks_per_image": steps,
                         "images": 120 // steps, "actor_pixels": movement})
    # New direct-copy descriptor costs 8 loader-table bytes, not payload bytes.
    table_after = gmc["sparse_copy_table_bytes"] + 8
    assert table_after <= 120
    helper_envelope = 0xBFFE - 0xBD44
    source_margin = gmc["spare_bytes"]
    result = {
        "schema": 1, "date": "2026-09-28", "kind": "static-design-accounting",
        "candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "rom_sha256": digest(root / "build/ladybug.rom"),
        "layout_sha256": digest(layout_path),
        "source_sha256": {name: digest(root / name) for name in
                          ["src/main.s", "src/enemy_runtime.s", "src/audio_runtime.s", "scripts/build_sparse_sprites.py"]},
        "baseline": {"resident_used": resident, "resident_limit": 8192,
                     "resident_free": 8192-resident, "enemy_used": enemy,
                     "enemy_limit": 4096, "enemy_free": 4096-enemy,
                     "cartridge_source_free": source_margin,
                     "copy_table_used": gmc["sparse_copy_table_bytes"],
                     "projection_bytes": projection, "queue_bytes": queue},
        "proposed": {"max_steps_per_image": 4, "records_per_history": 8,
                     "record_bytes": 18, "history_bytes": 288,
                     "scheduler_bytes": 32, "additional_state_bytes": 320,
                     "fields": state_names, "regions_exclusive_end": regions,
                     "helper_destination_envelope": helper_envelope,
                     "copy_table_after_one_unsplit_segment": table_after},
        "abstract_checks": {"history_models": [histories(0), histories(1)],
                            "shared_movement_clock": examples,
                            "ninth_record_guard_required": overflow_rejected},
        "capacity_verdict": {"documented_ram_interval_arithmetic": "PASS",
                             "journal_bound_under_stated_scheduler": "PASS",
                             "copy_table_one_segment_arithmetic": "PASS",
                             "helper_assembled_fit": "UNPROVEN",
                             "complete_cartridge_packing": "UNPROVEN",
                             "gross_raw_helper_envelope_minus_source_margin": helper_envelope-source_margin,
                             "net_delta_includes_removed_code_compression": "not measured",
                             "runtime_cycles_pixels_mapping_audio": "NOT TESTED"},
        "limits": ["Free RAM comes from the documented allocation; indirect lifetime safety requires the updated ownership audit.",
                   "A region envelope is not an assembled helper size.",
                   "Projection and queue sizes describe existing routines; they are not automatically reusable bytes or cartridge savings.",
                   "Copy-table arithmetic does not prove loader ordering, fragmented source placement, or bootstrap size.",
                   "Models establish retention and clock arithmetic only; they do not execute 6809 code."]}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"baseline":result["baseline"], "verdict":result["capacity_verdict"]}, indent=2))

if __name__ == "__main__":
    main()
