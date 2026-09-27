"""Build receipts: inputs are captured BEFORE assembly, never reconstructed later."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs(root):
    # Include untracked inputs too; do not use git's index as a content snapshot.
    result = {}
    for directory in ('src', 'scripts', 'assets', 'tiled'):
        for path in sorted((root / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                result[path.relative_to(root).as_posix()] = digest(path)
    return result


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)


def revision(root):
    git_file = root / '.git'
    command = ['git', '-C', str(root)]
    if os.name != 'nt' and git_file.is_file():
        target = git_file.read_text().strip().split('gitdir: ', 1)[-1]
        if re.match(r'^[A-Za-z]:/', target):
            target = '/mnt/' + target[0].lower() + target[2:]
            command += ['--git-dir=' + target]
    return subprocess.check_output(command + ['rev-parse', 'HEAD'], text=True).strip()


def validate(root, artifacts, config):
    path = artifacts / 'source-build-receipt.json'
    if not path.exists():
        raise ValueError('missing build provenance; run scripts/build.sh build')
    receipt = json.loads(path.read_text())
    if receipt.get('state') != 'complete' or receipt.get('profile') != 'complete':
        raise ValueError('incomplete or unsupported build provenance')
    if receipt['inputs'] != inputs(root):
        raise ValueError('stale build inputs; a fresh hash cannot certify old artifacts')
    for name, sha in receipt['artifacts'].items():
        if not (artifacts / name).is_file() or digest(artifacts / name) != sha:
            raise ValueError(f'stale build artifact: {name}')
    configured = {m.get('assembly_output', m['binary']): m for m in config['modules'] if m.get('binary')}
    required_artifacts = {m[key] for m in configured.values() for key in ('binary', 'listing', 'map')}
    if not required_artifacts <= receipt['artifacts'].keys():
        raise ValueError('missing required artifact provenance: ' + ', '.join(sorted(required_artifacts - receipt['artifacts'].keys())))
    emitted = {m['output']: m for m in receipt['invocations']}
    if set(configured) != set(emitted):
        raise ValueError(f'module inventory mismatch: unregistered={set(emitted)-set(configured)}, absent={set(configured)-set(emitted)}')
    for output, invocation in emitted.items():
        module = configured[output]
        definitions = dict(argument[2:].split('=', 1) for argument in invocation.get('arguments', [])
                           if argument.startswith('-D') and '=' in argument)
        for name, expected in module.get('defines', {}).items():
            if definitions.get(name) != str(expected):
                raise ValueError(f'module profile mismatch: {output}:{name}')
        for key in ('source', 'listing', 'map'):
            if module.get('assembly_' + key, module[key]) != invocation[key]:
                raise ValueError(f'module identity mismatch: {output}:{key}')
    return receipt


def main():
    action, root_text, artifact_text, *args = sys.argv[1:]
    root, artifacts = Path(root_text).resolve(), Path(artifact_text).resolve()
    path = artifacts / 'source-build-receipt.json'
    if action == 'begin':
        assembler = Path(shutil.which('lwasm')).resolve()
        receipt = {'schema': 1, 'state': 'building', 'profile': args[0],
                   'revision': revision(root),
                   'inputs': inputs(root), 'invocations': [],
                   'assembler': {'path': str(assembler), 'sha256': digest(assembler),
                                 'version': subprocess.check_output([str(assembler), '--version'], text=True).strip()}}
    else:
        receipt = json.loads(path.read_text())
        if action == 'assemble':
            def option(name):
                return next(a.split('=', 1)[1] for a in args if a.startswith(name + '='))
            receipt['invocations'].append({
                'source': Path(args[-1]).resolve().relative_to(root).as_posix(),
                'output': Path(option('--output')).resolve().relative_to(artifacts).as_posix(),
                'listing': Path(option('--list')).resolve().relative_to(artifacts).as_posix(),
                'map': Path(option('--map')).resolve().relative_to(artifacts).as_posix(),
                'assembled_sha256': digest(option('--output')),
                'arguments': [a.replace(str(root), '${ROOT}').replace(str(artifacts), '${BUILD}') for a in args]})
        elif action == 'finish':
            if receipt['inputs'] != inputs(root):
                raise ValueError('source changed while build was running')
            receipt['artifacts'] = {p.relative_to(artifacts).as_posix(): digest(p)
                                    for p in sorted(artifacts.rglob('*'))
                                    if p.is_file() and p.suffix in ('.inc', '.map', '.lst', '.bin', '.rom')
                                    and 'source-reference' not in p.parts}
            receipt['state'] = 'complete'
        else:
            raise ValueError(action)
    save(path, receipt)


if __name__ == '__main__':
    main()
