#!/usr/bin/env python3
"""FEAT-005 cold menu sequence and bounded edge/lifecycle checks.

Each runtime phase has a 40-second deadline. A timeout fails its marker;
it does not diagnose execution speed. Reuses the existing private monitor.
"""
import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import verify_bug011_runtime as r
import verify_shared_text as shared
from gmc_lzss import decompress

ROOT = r.ROOT
BUILD = ROOT / 'build'


def run_current_menu(output: Path) -> int:
    output = output.resolve()
    adapter = ROOT / 'wiki/internal/tickets/evidence/rsch014-ready-menu/gdb_menu_probe.py'
    rom_path = BUILD / 'ladybug.rom'
    if not adapter.is_file():
        raise FileNotFoundError(f'parent shared menu GDB adapter is missing: {adapter}')
    if not rom_path.is_file():
        raise FileNotFoundError(f'current complete build ROM is missing: {rom_path}')

    rom_sha256 = r.digest(rom_path.read_bytes())
    invocations = (
        ('--bindings', 'bindings'),
        ('--entry-edges-only', 'entry-edges'),
        ('--name-only', 'name-only'),
    )
    outputs = [output.with_name(f'{output.stem}-{suffix}{output.suffix}')
               for _, suffix in invocations]
    collisions = [path for path in [output, *outputs] if path.exists()]
    if collisions:
        raise FileExistsError('refusing to overwrite current-menu evidence: ' +
                              ', '.join(str(path) for path in collisions))

    report = {
        'schema': 'feat005-current-menu-dispatch-v1',
        'status': 'FAIL',
        'root': str(ROOT),
        'build_dir': str(BUILD),
        'rom_path': str(rom_path),
        'rom_sha256': rom_sha256,
        'shared_adapter': str(adapter.relative_to(ROOT)),
        'scope': 'Three separate bounded GDB invocations against this complete current ROM; no monitor protocol extension.',
        'invocations': [],
    }
    failed = False
    for (mode, _), result_path in zip(invocations, outputs):
        command = [sys.executable, str(adapter), '--worktree', str(ROOT),
                   '--rom-sha256', rom_sha256, '--output', str(result_path), mode]
        try:
            completed = subprocess.run(command, cwd=ROOT, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.is_file() else {}
            passed = completed.returncode == 0 and result.get('status') == 'PASS'
            failed = failed or not passed
            phases = [{
                'name': phase.get('name'),
                'deadline_seconds': phase.get('deadline_seconds'),
                'elapsed_seconds': phase.get('elapsed_seconds'),
                'check_count': len(phase.get('checks', [])),
            } for phase in result.get('phases', [])]
            report['invocations'].append({
                'mode': mode,
                'command': command,
                'output': str(result_path),
                'returncode': completed.returncode,
                'status': result.get('status', 'NO_RECEIPT'),
                'phases': phases,
                'adapter_stdout': completed.stdout,
            })
        except OSError as exc:
            failed = True
            report['invocations'].append({
                'mode': mode, 'command': command, 'output': str(result_path),
                'status': 'LAUNCH_FAILURE', 'failure': repr(exc),
            })

    report['status'] = 'FAIL' if failed else 'PASS'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'rom_sha256': rom_sha256,
                      'invocations': len(report['invocations']), 'output': str(output)}, indent=2))
    return 2 if failed else 0


def run_current_lives(output: Path, adapter: Path) -> int:
    output = output.resolve()
    adapter = adapter.resolve()
    rom_path = BUILD / 'ladybug.rom'
    if output.exists() or not adapter.is_file() or not rom_path.is_file():
        raise FileNotFoundError('fresh output, current shared adapter, and complete ROM are required')
    rom_sha256 = r.digest(rom_path.read_bytes())
    scenarios = [(f'natural-prefill-{total}', '--initial-lives', total)
                 for total in (1, 3, 4, 6, 7, 9, 10, 12)]
    scenarios.append(('controlled-both-owner-depletion-12-to-0', '--hud-lives', None))
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        'schema': 'bug062-current-life-grid-observer-v1',
        'status': 'RUNNING',
        'root': str(ROOT),
        'rom_path': str(rom_path),
        'rom_sha256': rom_sha256,
        'adapter_path': str(adapter),
        'adapter_sha256': r.digest(adapter.read_bytes()),
        'input_joystick_flag': r.symbols(BUILD / 'ladybug.map').get('INPUT_JOYSTICK'),
        'gameplay_map_sha256': r.digest((ROOT / 'tiled/coco-screen.tmx').read_bytes()),
        'phase_contract': 'Each adapter phase has a 40-second deadline. Timeout means the named publication or handoff boundary was not observed; it is not target-speed evidence.',
        'runtime_profile': 'The measured current complete joystick-input ROM uses fixed menu coin 5 and Enter. No remapped gameplay-key behavior is inferred.',
        'scenarios': [],
    }
    failed = False
    for name, selector, value in scenarios:
        target = output.with_name(output.stem + '-' + name + '.json')
        scratch = output.parent / (output.stem + '-' + name + '-scratch')
        if target.exists() or scratch.exists():
            raise FileExistsError(f'refusing to overwrite retained life evidence: {target} or {scratch}')
        command = [sys.executable, str(adapter), '--worktree', str(ROOT),
                   '--rom-sha256', rom_sha256, '--output', str(target),
                   '--scratch-dir', str(scratch), selector]
        if value is not None:
            command.append(str(value))
        print('BUG-062 ' + name, flush=True)
        try:
            completed = subprocess.run(command, cwd=ROOT, text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        timeout=600)
            proof = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else {}
            status = proof.get('status', 'NO_RECEIPT')
            passed = completed.returncode == 0 and status == 'PASS'
            failed = failed or not passed
            receipt['scenarios'].append({
                'name': name,
                'status': status,
                'accepted': passed,
                'returncode': completed.returncode,
                'command': command,
                'receipt_sha256': r.digest(target.read_bytes()) if target.is_file() else None,
                'phases': [{'name': phase.get('name'),
                            'deadline_seconds': phase.get('deadline_seconds'),
                            'elapsed_seconds': phase.get('elapsed_seconds'),
                            'checks': len(phase.get('checks', []))}
                           for phase in proof.get('phases', [])],
                'adapter_output': completed.stdout,
            })
        except (OSError, subprocess.TimeoutExpired) as error:
            failed = True
            receipt['scenarios'].append({'name': name, 'status': 'LAUNCH_OR_TIMEOUT_FAILURE',
                                         'accepted': False, 'failure': repr(error),
                                         'command': command})
        if sum(not row.get('accepted', False) for row in receipt['scenarios']) >= 2:
            receipt['aborted_after_two_rejected_cases'] = True
            break
    receipt['planned_scenarios'] = [row[0] for row in scenarios]
    receipt['missing_scenarios'] = receipt['planned_scenarios'][len(receipt['scenarios']):]
    failed = failed or bool(receipt['missing_scenarios'])
    receipt['status'] = 'FAIL' if failed else 'PASS'
    if not output.parent.exists():
        output.parent.mkdir(parents=True)
    output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': receipt['status'], 'rom_sha256': rom_sha256,
                      'scenarios': len(receipt['scenarios']), 'output': str(output)}, indent=2))
    return 2 if failed else 0


def _bug110_player_score_red_cells(scratch_dir: Path, score: str):
    """Compare the delivered left-HUD score pixels with the authoritative BCD score."""
    dp = (scratch_dir / 'gap-name-dp.bin').read_bytes()
    actual_score = ''.join(f'{value:02x}' for value in dp[0xBF:0xC2])
    if actual_score != score:
        raise AssertionError(f'pending score bytes {actual_score} do not match {score}')

    font = shared.values((BUILD / 'ladybug_shared_text.inc').read_text(), 'font', 'colour_lut')
    descriptors = shared.values((BUILD / 'ladybug_shared_text.inc').read_text(), 'dynamic_descriptors', 'no_end')
    glyphs = r.symbols(BUILD / 'ladybug-highscore-helper.map')

    def numeric_tile(digit: str) -> bytes:
        index = glyphs[f'PRESENTATION_GLYPH_{digit}']
        glyph = descriptors[index * 2]
        mask = font[glyph * 8:glyph * 8 + 8]
        return bytes(
            (1 if mask[row] & (128 >> (column * 2)) else 0) * 16
            + (1 if mask[row] & (64 >> (column * 2)) else 0)
            for row in range(8) for column in range(4)
        )

    expected = [numeric_tile(digit) for digit in score]
    results = {}
    for owner in (0, 1):
        frame = (scratch_dir / f'gap-name-replay-owner-{owner}.bin').read_bytes()
        actual = [
            b''.join(frame[(20 * 8 + row) * 160 + (1 + column) * 4:
                           (20 * 8 + row) * 160 + (2 + column) * 4]
                     for row in range(8))
            for column in range(6)
        ]
        results[f'owner{owner}'] = actual == expected
    return results


def run_name_case(output: Path, ticket: str) -> int:
    """Run every approved placement rank with the current complete-ROM adapter.

    Each invocation begins with a natural credit and game start, then uses the
    adapter's legal score/death fixture to reach the requested insertion rank.
    Rank 1 and 9 also exercise last parts 1 and 100; rank 2 checks stale-cell
    clearing, rank 1 checks the natural score table, and rank 9 checks timer
    scratch preservation. The adapter captures both naturally published owners.
    """
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f'refusing to overwrite BUG-108 evidence: {output}')
    rom_path = BUILD / 'ladybug.rom'
    bug110 = ticket == 'bug110'
    adapter = ROOT / 'wiki/internal/tickets/evidence/rsch014-ready-109' / (
        'gdb_name_hud_adapter.py' if bug110 else 'gdb_name_ordinal_prefix_adapter.py')
    if not rom_path.is_file() or not adapter.is_file():
        raise FileNotFoundError('current complete keyboard ROM and approved-prefix adapter are required')

    rom_sha256 = r.digest(rom_path.read_bytes())
    build_symbols = r.symbols(BUILD / 'ladybug.map')
    if build_symbols.get('INPUT_JOYSTICK') != 0:
        raise RuntimeError('BUG-108 natural host-key sequence requires the complete keyboard build')

    scores = {rank: f'{10 - rank:02d}5000' for rank in range(1, 10)}
    ordinals = {
        1: [29, 24, 25], 2: [2, 23, 13], 3: [3, 27, 13],
        4: [4, 29, 17], 5: [5, 29, 17], 6: [6, 29, 17],
        7: [7, 29, 17], 8: [8, 29, 17], 9: [9, 29, 17],
    }
    evidence_dir = output.parent / (output.stem + '-cases')
    evidence_dir.mkdir(parents=True, exist_ok=True)
    scratch_dir = ROOT / 'repro/ready-menu-gdb'
    scratch_dir.mkdir(parents=True, exist_ok=True)
    tmx_paths = (
        'tiled/coco-attract-screen.tmx', 'tiled/coco-credits-screen.tmx',
        'tiled/coco-enter-high-score-screen.tmx', 'tiled/coco-game-over-screen.tmx',
        'tiled/coco-high-score-screen.tmx', 'tiled/coco-instructions-screen.tmx',
        'tiled/coco-keybind-options-screen.tmx', 'tiled/coco-level-start-screen.tmx',
        'tiled/coco-screen.tmx',
    )
    tmx_before = {path: r.digest((ROOT / path).read_bytes()) for path in tmx_paths}
    summary = {
        'schema': f'{ticket}-current-prefix-nine-rank-v1',
        'status': 'RUNNING',
        'root': str(ROOT),
        'build_dir': str(BUILD),
        'rom_sha256': rom_sha256,
        'input_profile': 'complete keyboard',
        'adapter': str(adapter.relative_to(ROOT)),
        'adapter_sha256': r.digest(adapter.read_bytes()),
        'production_sources': {
            'src/shared_text_stage.inc': r.digest((ROOT / 'src/shared_text_stage.inc').read_bytes()),
            'scripts/source_reference.json': r.digest((ROOT / 'scripts/source_reference.json').read_bytes()),
            **({'src/shared_text_ranking.inc': r.digest((ROOT / 'src/shared_text_ranking.inc').read_bytes())}
               if bug110 else {}),
        },
        'case_contract': 'Each adapter phase has a 40-second deadline; success is the named natural publication or field check. Timeout means the boundary was not observed, not that target code is slow.',
        'natural_sequence': 'Each rank case admits a natural credit, starts from the menu with Enter, waits for ordinary credited gameplay, then applies only legal six-digit score, death state, and requested part fixtures before natural qualification and publication.',
        'cases': [],
        'rejected_experiments': [],
    }
    earlier_attempt = ROOT / 'repro/bug108/current-nine-rank.json'
    if earlier_attempt.is_file():
        earlier = json.loads(earlier_attempt.read_text(encoding='utf-8'))
        if earlier.get('status') == 'FAIL' and earlier.get('cases'):
            first = earlier['cases'][0]
            if first.get('status') == 'PASS-SEPARATE-108-PLACEMENT-OWNER-FIELDS' and not first.get('accepted'):
                summary['rejected_experiments'].append({
                    'artifact': str(earlier_attempt.relative_to(ROOT)),
                    'sha256': r.digest(earlier_attempt.read_bytes()),
                    'finding': 'The adapter passed rank 1 and every named phase was within 40 seconds. The first selector revision looked for check names at the report root while the reused adapter stores them inside each phase; the false negative is verifier parsing, not a product failure. Per-phase check aggregation is corrected for this run.',
                    'rank1_adapter_receipt': first.get('receipt_path'),
                    'rank1_adapter_receipt_sha256': first.get('receipt_sha256'),
                })

    expected_markers = (
        'full delivered low name owner equals current artifact',
        'full delivered mapped name owner equals current artifact',
    )
    failed = False
    for rank in range(1, 10):
        last_part = 100 if rank == 9 else rank
        case_name = f'rank-{rank}-part-{last_part}'
        case_output = evidence_dir / f'{case_name}.json'
        if case_output.exists():
            raise FileExistsError(f'refusing to overwrite BUG-108 case evidence: {case_output}')
        before_scratch = {
            path.name: r.digest(path.read_bytes())
            for path in scratch_dir.iterdir() if path.is_file()
        }
        command = [
            sys.executable, str(adapter), '--worktree', str(ROOT),
            '--build-dir', str(BUILD), '--rom-sha256', rom_sha256,
            '--output', str(case_output), '--credit-admission-only',
            '--qualifying-score', scores[rank], '--last-part', str(last_part),
            '--gap-expect', 'blank',
        ]
        if rank == 1:
            command.append('--ranking-regression')
        if rank == 2:
            command.append('--short-name-regression')
        if rank == 9:
            command.append('--timer-scratch')

        print(f'{ticket.upper()} rank {rank}, part {last_part}', flush=True)
        try:
            completed = subprocess.run(
                command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=600,
            )
            case = json.loads(case_output.read_text(encoding='utf-8')) if case_output.is_file() else {}
            checks = [
                item for phase in case.get('phases', [])
                for item in phase.get('checks', [])
            ]
            fields = case.get('joint_hud', {})
            expected_fields = (
                case.get('status') == ('PASS-CURRENT-JOINT-LAST-PART-VEGETABLE-VALUE-RANK-OWNERS'
                                       if bug110 else 'PASS-SEPARATE-108-PLACEMENT-OWNER-FIELDS')
                and fields.get('rank_zero_based') == rank - 1
                and fields.get('last_part') == last_part
                and fields.get('owners') == [0, 1]
                and (not bug110 or fields.get('ordinal_rows') in (None, [12, 18]))
                and (bug110 or fields.get('ordinal_rows') == [12])
                and fields.get('ordinal_raw_codes') == ordinals[rank]
                and fields.get('pending_name') == ('red1' if bug110 else 'unchanged white6')
            )
            owner_checks = all(
                f'ordinal row12 owner{owner}' in checks
                and (not bug110 or f'ordinal row18 owner{owner}' in checks)
                and f'three-position last part owner{owner}' in checks
                and f'matching vegetable four-digit green value owner{owner}' in checks
                and f'dark-green equals owner{owner}' in checks
                and f'authored final-part native vegetable owner{owner}' in checks
                and f'gap-name-replay player score unchanged on owner{owner}' in checks
                and f'gap-name-replay top-right score unchanged on owner{owner}' in checks
                and f'gap-name-replay gap cells match blank on owner{owner}' in checks
                for owner in (0, 1)
            ) and checks.count('gap-name-replay pending-name ' + ('red' if bug110 else 'white')
                               + ' cells match authoritative data') >= 2 \
                and checks.count('gap-name-replay TOP-name stage103 cells match authoritative data') >= 2
            score_pixels = ({'owner0': True, 'owner1': True} if not bug110 else
                            _bug110_player_score_red_cells(scratch_dir, scores[rank]))
            score_pixels_pass = all(score_pixels.values())
            identity_checks = all(marker in checks for marker in expected_markers)
            rank_authority = 'actual ranking and pending score match fixture' in checks
            timer_continues = 'natural timer boxes advance without field-repaint reset' in checks
            natural_ranking = rank != 1 or (
                case.get('ranking_regression', {}).get('rows') == 9
                and case.get('ranking_regression', {}).get('owners') == [0, 1]
            )
            short_name = rank != 2 or (
                'actual pending name contains four glyphs and three blank cells' in checks
                and checks.count('gap-name-short pending-name ' + ('red' if bug110 else 'white')
                                 + ' cells match authoritative data') >= 2
                and checks.count('gap-name-short TOP-name stage103 cells match authoritative data') >= 2
                and all(
                    f'gap-name-short player score unchanged on owner{owner}' in checks
                    and f'gap-name-short top-right score unchanged on owner{owner}' in checks
                    for owner in (0, 1)
                )
            )
            timer_scratch = rank != 9 or all(
                any(marker in item for item in checks)
                for marker in (
                    'name writer natural return preserves legal timer phase1',
                    'score writer natural return preserves legal timer phase0',
                )
            )
            phase_names = [phase.get('name') for phase in case.get('phases', [])]
            natural_sequence = all(name in phase_names for name in (
                'credited-menu-before-gap-reproduction',
                'credited-gameplay-before-qualifying-death',
                'qualifying-gameover-to-name-gap',
                'natural-name-owner-replay',
            ))
            owner_publication = 'natural replay publishes both FRONT owners' in checks
            phase_deadlines_pass = bool(case.get('phases')) and all(
                phase.get('deadline_seconds', 41) <= 40
                and phase.get('elapsed_seconds') is not None
                and phase['elapsed_seconds'] <= phase['deadline_seconds']
                for phase in case['phases']
            )
            passed = (completed.returncode == 0 and expected_fields and owner_checks
                      and score_pixels_pass
                      and identity_checks and natural_ranking and short_name
                      and timer_scratch and natural_sequence and owner_publication
                      and rank_authority and timer_continues and phase_deadlines_pass)
            changed_artifacts = {}
            for path in scratch_dir.iterdir():
                if path.is_file():
                    digest = r.digest(path.read_bytes())
                    if before_scratch.get(path.name) != digest:
                        changed_artifacts[path.name] = {'sha256': digest, 'bytes': path.stat().st_size}
            case_summary = {
                'rank': rank,
                'last_part': last_part,
                'qualifying_score': scores[rank],
                'status': case.get('status', 'NO_RECEIPT'),
                'accepted': passed,
                'returncode': completed.returncode,
                'receipt_path': str(case_output.relative_to(ROOT)),
                'receipt_sha256': r.digest(case_output.read_bytes()) if case_output.is_file() else None,
                'fields': fields,
                'phase_markers': [
                    {'name': phase.get('name'), 'deadline_seconds': phase.get('deadline_seconds'),
                     'elapsed_seconds': phase.get('elapsed_seconds'),
                     'check_count': len(phase.get('checks', [])),
                     'timeout_meaning': phase.get('timeout_meaning')}
                    for phase in case.get('phases', [])
                ],
                'required_identity_checks': {marker: marker in checks for marker in expected_markers},
                'player_score_red_pixels': score_pixels,
                'actual_rank_authority_check': rank_authority,
                'timer_continues_without_redraw_reset': timer_continues,
                'phase_deadlines_pass': phase_deadlines_pass,
                'artifact_hashes': changed_artifacts,
            }
            if rank == 2:
                case_summary['short_name_clearing_check'] = any(
                    'four glyphs and three blank cells' in item for item in checks
                )
            if rank == 9:
                case_summary['timer_scratch_checks'] = {
                    'name_return': 'name writer natural return preserves legal timer phase1' in checks,
                    'score_return': 'score writer natural return preserves legal timer phase0' in checks,
                }
            if rank == 1:
                case_summary['natural_ranking_regression'] = case.get('ranking_regression', {})
            summary['cases'].append(case_summary)
            if not passed:
                failed = True
                failure_copy = evidence_dir / f'{case_name}-failed-probe'
                if failure_copy.exists():
                    raise FileExistsError(f'refusing to overwrite failed BUG-108 probe artifacts: {failure_copy}')
                import shutil
                shutil.copytree(scratch_dir, failure_copy)
                case_summary['failure_probe_copy'] = str(failure_copy.relative_to(ROOT))
                case_summary['adapter_output_tail'] = completed.stdout[-8000:]
                summary['missing_ranks'] = list(range(rank + 1, 10))
                break
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            failed = True
            summary['cases'].append({
                'rank': rank, 'last_part': last_part, 'qualifying_score': scores[rank],
                'status': 'LAUNCH_OR_TIMEOUT_FAILURE', 'accepted': False,
                'failure': repr(error), 'command': command,
            })
            failure_copy = evidence_dir / f'{case_name}-failed-probe'
            if scratch_dir.exists() and not failure_copy.exists():
                import shutil
                shutil.copytree(scratch_dir, failure_copy)
            summary['missing_ranks'] = list(range(rank + 1, 10))
            break

    tmx_after = {path: r.digest((ROOT / path).read_bytes()) for path in tmx_paths}
    summary['tmx_sha256'] = tmx_after
    summary['tmx_unchanged'] = tmx_after == tmx_before
    if not summary['tmx_unchanged']:
        failed = True
        summary['tmx_changed'] = [path for path in tmx_paths if tmx_after[path] != tmx_before[path]]
    summary['status'] = 'PASS' if not failed and len(summary['cases']) == 9 else 'FAIL'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': summary['status'], 'rom_sha256': rom_sha256,
                      'cases': len(summary['cases']), 'output': str(output)}, indent=2))
    return 2 if failed or len(summary['cases']) != 9 else 0


def run_name_case_bug108(output: Path) -> int:
    return run_name_case(output, 'bug108')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-menu', action='store_true',
                        help='dispatch current bindings, entry-edge, and name-control GDB phases')
    parser.add_argument('--current-lives', action='store_true',
                        help='run natural credited prefill rows and controlled reverse 12-to-0 grid audit')
    parser.add_argument('--name-case', choices=('bug108', 'bug110'),
                        help='run the approved BUG-108 or post-BUG-108 BUG-110 nine-rank current-ROM case')
    parser.add_argument('--adapter', type=Path,
                        help='current parent shared GDB adapter or bounded candidate copy')
    parser.add_argument('--output', type=Path,
                        help='report path; required by --current-menu, --name-case, or --current-lives')
    args = parser.parse_args()
    if args.name_case == 'bug108':
        if args.output is None:
            parser.error('--name-case bug108 requires --output')
        raise SystemExit(run_name_case_bug108(args.output))
    if args.name_case == 'bug110':
        if args.output is None:
            parser.error('--name-case bug110 requires --output')
        raise SystemExit(run_name_case(args.output, 'bug110'))
    if args.current_lives:
        if args.output is None or args.adapter is None:
            parser.error('--current-lives requires --output and --adapter')
        raise SystemExit(run_current_lives(args.output, args.adapter))
    if args.current_menu:
        if args.output is None:
            parser.error('--current-menu requires --output')
        raise SystemExit(run_current_menu(args.output))
    if args.output is None:
        args.output = ROOT/'repro/feat005-runtime-20260930.json'
    report = {'status': 'FAIL', 'rom_sha256': r.digest((BUILD/'ladybug.rom').read_bytes()), 'checks': []}
    monitor = r.load_monitor()
    process, client = r.launch_fast(monitor, ROOT/'docs/reference/xroar/src/xroar', BUILD/'ladybug.rom')
    read = lambda a: r.read_byte(client, a)
    write = lambda a,v: r.write_byte(client, a, v)
    syms = r.symbols(BUILD/'ladybug.map')
    helper = r.symbols(BUILD/'ladybug-highscore-helper.map')
    ids = monitor.setup(client, [0x1900])
    chars = shared.s.load_chars(ROOT/'assets/arcade/chars.json')
    manifest = json.loads((BUILD/'ladybug-presentation.json').read_text())
    font = shared.values((BUILD/'ladybug_shared_text.inc').read_text(),'font','colour_lut')
    # Raw masks use the same authored glyph identity as the compiler, checked
    # against its retained coverage rather than hard-coded glyph indices.
    stage = (BUILD/'ladybug_stage_glyphs.inc').read_text()
    trans = shared.values(stage,'stage_source_glyphs','no_end')
    masks = {i:font[g*8:g*8+8] for i,g in enumerate(trans)}

    def check(name, detail=True):
        report['checks'].append({'name':name,'result':detail})
        print(name, flush=True)

    def tick():
        hit = client.run_to_breakpoint(timeout=10)
        assert hit['pc']==0x1900, hit

    def wait(name, predicate):
        deadline = time.monotonic()+40
        while not predicate():
            assert time.monotonic()<deadline, ('phase timeout',name,read(0xA5),read(0xA6),read(0xD4))
            tick()

    def ready(screen):
        wait('screen '+str(screen)+' fully published', lambda:read(0xA6)==screen and read(0xA5)==5 and read(0xD4)==0 and read(0x91)==0)

    def key(scan, screen=None):
        client.call('inject_key', {'key':scan,'action':'press'})
        for _ in range(4): tick()
        client.call('inject_key', {'key':scan,'action':'release'})
        for _ in range(4): tick()
        if screen is not None: ready(screen)

    def paint(frame, dst, code, colour):
        for y,bits in enumerate(masks[code]):
            at=dst-0x2000+y*160
            frame[at:at+4]=bytes((colour if bits&(128>>(j*2)) else 0)*16+(colour if bits&(64>>(j*2)) else 0) for j in range(4))

    def options_pixels(selection):
        # Decode the compiler stream independently, then override only authored
        # option rows and pairs. Full frames on both publications must match.
        cold=(BUILD/'ladybug-presentation-cold.bin').read_bytes()
        ptr=manifest['map_stream_offsets'][6];frame=bytearray(30720);cell=0
        while cell<960:
            count,glyph=cold[ptr:ptr+2];ptr+=2
            if glyph>=174:
                colour=cold[ptr];ptr+=1
                mask=font[(glyph-174)*8:(glyph-174+1)*8]
                tile=bytes((colour if mask[y]&(128>>(j*2)) else 0)*16+(colour if mask[y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4))
            else: tile=cold[glyph*32:glyph*32+32]
            for _ in range(count):
                at=(cell//40)*1280+(cell%40)*4
                for y in range(8):frame[at+y*160:at+y*160+4]=tile[y*4:y*4+4]
                cell+=1
        root=ET.parse(ROOT/'tiled/coco-options-screen.tmx').getroot()
        path=ROOT/'tiled/coco-options-screen.tmx'
        _,flat,_=shared.p.flatten_map(path)
        labels=[shared.p.raw_char_code(root,path,gid) for gid in flat]
        for i,(row,lo,hi) in enumerate(manifest['menus']['option_rows']):
            for col in range(lo,hi+1):paint(frame,0x2000+row*1280+col*4,labels[row*40+col] if labels[row*40+col] is not None and labels[row*40+col]<=35 else 36,10 if i==selection else 7)
        anchors=[shared.p.raw_char_code(root,path,int(v)) for v in root.find("layer[@name='Selected Option']/data").text.strip().split(',')]
        pairs=[]
        for row in range(24):
            cells=[col for col in range(40) if anchors[row*40+col] in (43,44)]
            if cells:pairs.append((row,*cells))
        for i,(row,left,right) in enumerate(pairs):
            value=read(0xEA+i);colour=10 if i==selection else 7
            for col in (left,right):paint(frame,0x2000+row*1280+col*4,36,7)
            paint(frame,0x2000+row*1280+(left+1)*4,value//10,colour)
            paint(frame,0x2000+row*1280+(left+2)*4,value%10,colour)
            if i==selection:
                paint(frame,0x2000+row*1280+left*4,43,10)
                paint(frame,0x2000+row*1280+right*4,44,10)
        owners=[r.read_owner(client,i) for i in (0,1)]
        assert all(bytes(frame)==owner for owner in owners), ('options pixels',selection,[(i,sum(a!=b for a,b in zip(frame,o))) for i,o in enumerate(owners)])
        check('both options publications selection '+str(selection), r.digest(frame))

    def high_pixels(selection):
        path=ROOT/'tiled/coco-high-score-screen.tmx';root=ET.parse(path).getroot()
        cells=[shared.p.raw_char_code(root,path,int(v)) for v in root.find("layer[@name='Selected Option']/data").text.strip().split(',')]
        pairs=[[(i%40,i//40,code) for i,code in enumerate(cells) if code in (43,44) and i//40==row] for row in range(24)]
        pairs=[pair[i:i+2] for pair in pairs for i in range(0,len(pair),2)]
        for owner in (0,1):
            frame=r.read_owner(client,owner)
            for index,pair in enumerate(pairs):
                for col,row,code in pair:
                    expected=bytearray(30720);dst=0x2000+row*1280+col*4
                    paint(expected,dst,code if index==selection else 36,10)
                    assert r.frame_tile(frame,dst)==r.frame_tile(expected,dst),(owner,selection,index)
        check('both high-score bracket publications selection '+str(selection))

    def call(label, values=None, bank=None):
        regs=client.call('read_registers');saved=read(0xFFA5)
        for a,v in (values or {}).items():write(a,v)
        if bank is not None:write(0xFFA5,bank)
        sp=regs['s']-2;r.write_word(client,sp,0x0700)
        client.call('write_registers',{'pc':label,'s':sp,'dp':0,'cc':regs['cc']|0x50})
        step_to({0x0700},40)
        write(0xFFA5,saved)
        client.call('write_registers',{'s':regs['s'],'pc':0x1900,'cc':regs['cc']})

    def step_to(markers, seconds):
        deadline=time.monotonic()+seconds
        while True:
            assert time.monotonic()<deadline,('step phase timeout',markers)
            client.call('step_instruction',{'n':1})
            hit=client.call('wait_for_stop',{'timeout_ms':2000})
            if hit['pc'] in markers:return hit

    try:
        tick()
        # Identity precedes symbol interpretation or forced calls.
        runtime=(BUILD/'ladybug-runtime.rom').read_bytes()
        assert r.read_bytes(client,0xC000,0x2000)==runtime[:0x2000]
        pres=(BUILD/'ladybug-presentation-runtime.bin').read_bytes()
        assert r.read_bytes(client,0x1900,len(pres))==pres
        saved=read(0xFFA5);write(0xFFA5,0x23)
        h=(BUILD/'ladybug-highscore-helper.bin').read_bytes()
        assert r.read_bytes(client,0xAC40,len(h))==h
        title=(BUILD/'ladybug-attract-actor-underlays.bin').read_bytes()+(BUILD/'ladybug-attract-actor-records.bin').read_bytes()
        assert r.read_bytes(client,0xB880,len(title))==title
        layout=json.loads((BUILD/'ladybug-sparse-layout.json').read_text())
        cartridge=(BUILD/'ladybug.rom').read_bytes()
        stream_checks=[]
        for stream in layout['compression']['streams']:
            start=stream['bank']*16384+stream['source_offset']
            packed=cartridge[start:start+stream['compressed_bytes']]
            expanded=decompress(packed,stream['raw_bytes'])
            assert r.digest(expanded)==stream['raw_sha256']
            write(0xFFA5,stream['destination_page'])
            assert r.read_bytes(client,stream['destination_address'],len(expanded))==expanded,stream['name']
            stream_checks.append({'name':stream['name'],'live_sha256':r.digest(expanded)})
        write(0xFFA5,saved)
        check('cold resident/presentation/helper/title and seven staged/live stream identities',stream_checks)
        assert (read(0xEA),read(0xEB))==(3,1)
        wait('cold attract fully published',lambda:read(0xA6)==0 and read(0xA5)==2 and read(0xD4)==0 and read(0x91)==0)
        key(5,3)  # physical CoCo scan 5 naturally enters high scores
        assert read(0xE0)==0
        high_pixels(0)
        key(0x30,6);options_pixels(0)
        key(0x2E,6);assert read(0xEA)==4;options_pixels(0)
        client.call('inject_key',{'key':0x2E,'action':'press'})
        for _ in range(20):tick()
        ready(6);assert read(0xEA)==5
        for _ in range(20):tick()
        assert read(0xEA)==5
        client.call('inject_key',{'key':0x2E,'action':'release'});tick()
        key(0x2C,6);assert read(0xE0)==1;options_pixels(1)
        key(0x2E,6);assert read(0xEB)==2;options_pixels(1)
        key(0x2C,6);assert read(0xE0)==2;options_pixels(2)
        key(0x30,3);assert read(0xE0)==0
        key(0x2C,3);high_pixels(1);key(0x30,7);key(0x32,3)
        key(0x30,6);assert (read(0xEA),read(0xEB))==(5,2)
        # Rare formatting values seed settings but use normal input and load.
        write(0xEA,9);key(0x2E,6);assert read(0xEA)==10;options_pixels(0)
        key(0x2D,6);assert read(0xEA)==9;options_pixels(0)
        for _ in range(3):key(0x2E)
        ready(6);assert read(0xEA)==12
        options_pixels(0)
        key(0x2C,6);write(0xEB,98);key(0x2E,6);assert read(0xEB)==99;options_pixels(1)
        key(0x2E,6);assert read(0xEB)==99
        write(0xEA,5);write(0xEB,2)
        # Opposing held arrows cancel through the actual keyboard scanner.
        client.call('inject_key',{'key':0x2D,'action':'press'})
        client.call('inject_key',{'key':0x2E,'action':'press'})
        for _ in range(8):tick()
        assert read(0xEB)==2
        for scan in (0x2D,0x2E):client.call('inject_key',{'key':scan,'action':'release'})
        tick()
        key(0x32,3)
        check('natural options/BACK/credits/Escape and retained settings')
        key(1)
        wait('natural live game',lambda:read(0xA5)==0 and read(0xA0)==0)
        assert (read(0x23),read(0x24))==(4,2),('live init',read(0x23),read(0x24))
        check('natural configured live game first entrant',{'reserves':4,'level':2})
        ids.extend(monitor.setup(client,[0x0700]))
        # Isolated arithmetic runs the assembled routine for every legal value.
        saved=read(0xFFA5);write(0xFFA5,0x23)
        assert r.read_bytes(client,0xAC40,len(h))==h
        write(0xFFA5,saved)
        arithmetic_ids=monitor.setup(client,[helper['menu_redraw'],helper['menu_hold']])
        arithmetic_regs=client.call('read_registers')
        for row,maximum in ((0,12),(1,99)):
            for value in range(1,maximum+1):
                for event,expected in ((4,max(1,value-1)),(8,min(maximum,value+1))):
                    for address,v in {0xA5:5,0xA6:6,0xE0:row,0xEA+row:value,0xDF:event,0xD0:event}.items():write(address,v)
                    write(0xFFA5,0x23)
                    client.call('write_registers',{'pc':helper['menu_tick'],'s':arithmetic_regs['s'],'cc':0x50,'dp':0})
                    hit=step_to({helper['menu_redraw'],helper['menu_hold']},5)
                    assert hit['pc']==helper['menu_redraw' if expected!=value else 'menu_hold'],hit
                    assert read(0xEA+row)==expected,(row,value,event,read(0xEA+row))
        monitor.clear(client,arithmetic_ids)
        write(0xFFA5,saved)
        client.call('write_registers',{'pc':0x1900,'s':arithmetic_regs['s'],'cc':arithmetic_regs['cc']})
        check('all 222 clamped arithmetic transitions')
        for total,level in ((1,1),(3,2),(12,99)):
            call(syms['init_game_state'],{0xA7:1,0xEA:total,0xEB:level})
            assert (read(0x23),read(0x24))==(total,level)
            assert read(0x4A)==(9 if level==1 else 6 if level<5 else 3)
            call(syms['init_entities'])
            assert read(0x49)==(8 if level==1 else 9 if level==2 else 12)
            # First-entry transfer is tested from its final stage-ready boundary.
            call(syms['initial_entry_tick'],{0xA0:1,0x7F:0,0x99:0})
            assert (read(0x23),read(0x24))==(total-1,level)
            before=r.read_bytes(client,0x2000,30720)
            call(syms['draw_lives'])
            after=r.read_bytes(client,0x2000,30720)
            allowed={row*160+col for row in range(168,184) for col in range(132,156)}
            assert all(a==b or index in allowed for index,(a,b) in enumerate(zip(before,after))),('life HUD overwrite',total)
            if total==12:
                expected=bytearray(30720)
                for col,code in ((33,1),(34,1)):paint(expected,0x2000+21*1280+col*4,code,8)
                for col in (33,34):assert r.frame_tile(after,0x2000+21*1280+col*4)==r.frame_tile(expected,0x2000+21*1280+col*4)
            check('configured initialization '+str(total)+'/'+str(level),{'lives':read(0x23),'level':read(0x24)})
            call(syms['death_tick'],{0x4D:3,0x3A:0})
            assert read(0x24)==level and read(0x23)==max(0,total-2)
            assert read(0x4D)==(4 if total==1 else 0)
        call(syms['apply_letter_pickup'],{0x39:2,0x26:0,0x23:0,0x3D:15,0x2F:2})
        assert read(0x23)==1 and read(0x3D)==0 and read(0x26)==1
        check('EXTRA adds a reserve without resetting configured lives')
        call(syms['next_stage'],{0x24:99})
        assert read(0x24)==100 and read(0x49)==12
        call(syms['draw_hud'])
        frame=r.read_bytes(client,0x2000,30720)
        expected=bytearray(30720)
        colour=json.loads((ROOT/'assets/arcade/text-colours.json').read_text())['fields']['part']
        for col in (37,38):paint(expected,0x2000+11*1280+col*4,0,colour)
        for col in (37,38):assert r.frame_tile(frame,0x2000+11*1280+col*4)==r.frame_tile(expected,0x2000+11*1280+col*4)
        check('death retains stage; final life terminates; level clear advances 99 to 100')
        call(syms['init_game_state'],{0xA7:0,0xEA:12,0xEB:99})
        assert (read(0x23),read(0x24))==(3,1)
        check('demo default initialization excludes live settings')
        # A fresh process proves reset and the natural unattended demo path.
        client.close();monitor.stop(process)
        process,client=r.launch_fast(monitor,ROOT/'docs/reference/xroar/src/xroar',BUILD/'ladybug.rom')
        demo_ids=monitor.setup(client,[0x1900]);tick()
        assert (read(0xEA),read(0xEB))==(3,1)
        write(0xEA,12);write(0xEB,99)
        monitor.clear(client,demo_ids)
        pres_syms=r.symbols(BUILD/'ladybug-presentation-runtime.map')
        demo_ids=monitor.setup(client,[pres_syms['demo_tick']])
        hit=client.run_to_breakpoint(timeout=40)
        assert hit['pc']==pres_syms['demo_tick'] and read(0xA5)==4
        assert (read(0x23),read(0x24))==(3,1)
        check('cold reset and natural demo exclude retained live settings')
        report['status']='pass'
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        client.close();monitor.stop(process)


if __name__=='__main__':main()
