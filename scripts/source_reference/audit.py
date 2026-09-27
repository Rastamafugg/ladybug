"""Source-adjacent ownership declarations joined to extracted build facts.

This is a conservative lexical audit, not a dataflow or runtime safety proof.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import html
import json
import re

from .links import module_page, source_line_id

ANNOTATION = re.compile(r'^\s*[;#]\s*@audit(?:-(producer|use))?\s+(\{.*\})\s*$')
TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
WORD = {'ldd', 'ldx', 'ldy', 'ldu', 'lds', 'std', 'stx', 'sty', 'stu', 'sts', 'addd', 'subd', 'cmpd', 'cmpx', 'cmpy', 'cmpu', 'cmps'}
BYTE = {'lda', 'ldb', 'sta', 'stb', 'adda', 'addb', 'suba', 'subb', 'cmpa', 'cmpb', 'anda', 'andb', 'ora', 'orb', 'eora', 'eorb', 'bita', 'bitb', 'tst', 'clr', 'inc', 'dec', 'asl', 'lsr', 'asr', 'rol', 'ror', 'neg', 'com', 'adca', 'adcb', 'sbca', 'sbcb'}
MODIFY = {'clr', 'inc', 'dec', 'asl', 'lsr', 'asr', 'rol', 'ror', 'neg', 'com'}


def instruction(text):
    code = text.split(';', 1)[0].rstrip()
    parts = code.split(None, 2)
    if not parts:
        return '', ''
    if not code[0].isspace():
        parts = parts[1:]
    return (parts[0].lower(), ' '.join(parts[1:])) if parts else ('', '')


def access(text, symbol):
    """Return access, width, offset. Unknown expressions remain explicitly unknown."""
    op, operand = instruction(text)
    if symbol not in TOKEN.findall(operand):
        return None
    if op in {'equ', 'rmb', 'fcb', 'fdb', 'fqb', 'include', 'org', 'ifne', 'ifeq'}:
        return {'access': 'expression', 'width': None, 'offset': None}
    if operand.startswith('#') or op.startswith('lea'):
        return {'access': 'address-or-value', 'width': 0, 'offset': None}
    width = 2 if op in WORD else 1 if op in BYTE else None
    kind = 'write' if op.startswith('st') and op in WORD | BYTE else 'read-write' if op in MODIFY else 'read' if width else 'unresolved'
    match = re.fullmatch(r'[<>]?' + re.escape(symbol) + r'(?:\+([0-9]+)|\+\$([0-9A-Fa-f]+))?', operand.strip())
    offset = (int(match[1]) if match[1] else int(match[2], 16) if match[2] else 0) if match else None
    if '[' in operand or ',' in operand or offset is None:
        kind = 'unresolved-indirect'
    return {'access': kind, 'width': width, 'offset': offset}


def overlap_errors(records):
    errors = []
    for left, right in combinations(records, 2):
        if left['mapping'] != right['mapping'] or not set(left['phases']) & set(right['phases']):
            continue
        if left['address'] < right['address'] + right['width'] and right['address'] < left['address'] + left['width']:
            alias = left.get('alias_group')
            if alias and alias == right.get('alias_group') and left.get('alias_reason') and right.get('alias_reason'):
                continue
            errors.append(f"overlapping storage: {left['id']} / {right['id']}")
    return errors


def build_audit(project, root, policy, receipt):
    errors, records, uses, producers = [], [], [], []
    modules = {m.id: m for m in project.modules}
    symbols = {m.id: {s.name: s for s in m.symbols} for m in project.modules}
    definitions = {m.id: {} for m in project.modules}
    references = {}
    for m in project.modules:
        for line in m.source_lines:
            code = line.text.split(';', 1)[0]
            if code and not code[0].isspace() and TOKEN.match(code):
                definitions[m.id][TOKEN.match(code)[0]] = line
            op, operand = instruction(line.text)
            for token in set(TOKEN.findall(operand)) & symbols[m.id].keys():
                references.setdefault((m.id, token), []).append((line, access(line.text, token)))
            match = ANNOTATION.match(line.text)
            if match:
                try:
                    declaration = json.loads(match[2])
                except ValueError as exc:
                    errors.append(f'invalid annotation {line.file}:{line.number}: {exc}')
                    continue
                declaration = dict(declaration, module=m.id, file=line.file, line=line.number)
                if declaration.get('modules') and m.id not in declaration['modules']:
                    continue
                (uses if match[1] == 'use' else producers if match[1] == 'producer' else records).append(declaration)
    for path in sorted((root / 'scripts').glob('*')):
        if path.suffix not in ('.py', '.sh'):
            continue
        for number, text in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            match = ANNOTATION.match(text)
            if match and match[1] == 'producer':
                producers.append(dict(json.loads(match[2]), file=path.relative_to(root).as_posix(), line=number))

    def resolve(module, name):
        m_id, sep, target = name.partition(':')
        m_id, target = (m_id, target) if sep else (module, name)
        s = symbols.get(m_id, {}).get(target)
        line = definitions.get(m_id, {}).get(target)
        if not s or not line:
            errors.append(f'dangling lifecycle/symbol: {m_id}:{target}')
            return None
        return {'module': m_id, 'symbol': target, 'address': s.assembled_address,
                'file': line.file, 'line': line.number,
                'href': module_page(m_id) + '#' + source_line_id(line.file, line.number)}

    ids = Counter(r['id'] for r in records)
    for name in policy['required']:
        if ids[name] != 1:
            errors.append(f'required ownership record missing or duplicated: {name}')
    for name, count in ids.items():
        if count != 1:
            errors.append(f'duplicate audit identity: {name}')
    for record in records:
        if record['kind'] == 'index' and not any(u['id'] == record['id'] for u in uses):
            errors.append(f"missing declared index consumer: {record['id']}")
    documented = set()
    storage = []
    for record in records:
        module, name = record['module'], record['symbol']
        record['evidence'] = 'authored declaration'
        location = resolve(module, name)
        record['definition'] = location
        record['references'] = []
        if not location:
            continue
        documented.add((module, name))
        record['address'] = location['address']
        for line, ref in references.get((module, name), []):
            record['references'].append(dict(ref, file=line.file, line=line.number,
                evidence='extracted fact', href=module_page(module)+'#'+source_line_id(line.file, line.number)))
        kind = record['kind']
        required = {'scratch': ('width', 'mapping', 'phases', 'owner', 'initialization', 'lifetime', 'clobbers'),
                    'background': ('owner', 'extent', 'clean_source', 'capture', 'restore', 'draw', 'validity', 'invalidation', 'publication', 'order', 'overlap', 'verifier'),
                    'index': ('producer', 'domain', 'encoding', 'bounds')}[kind]
        for field in required:
            if not record.get(field):
                errors.append(f"missing {kind} contract: {record['id']}:{field}")
        if kind == 'scratch' and all(record.get(k) for k in ('width','mapping','phases')):
            if not isinstance(record['width'], int) or record['width'] <= 0:
                errors.append(f"invalid storage width: {record['id']}")
                continue
            record['interval'] = [record['address'], record['address'] + record['width'] - 1]
            line = definitions[module][name]
            allocation = next((l for l in modules[module].source_lines if l.file == line.file and l.number >= line.number and instruction(l.text)[0]), None)
            if allocation:
                opcode, operand = instruction(allocation.text)
                if opcode == 'rmb':
                    allocated = int(operand) if operand.isdigit() else symbols[module][operand].assembled_address if operand in symbols[module] else None
                    record['extracted_allocation_width'] = allocated
                    if allocated is not None and allocated != record['width']:
                        errors.append(f"declared width differs from allocation: {record['id']}")
            record['minimum_direct_access_extent'] = max((r['offset']+r['width'] for r in record['references']
                if r['access'] in ('read','write','read-write') and r['offset'] is not None and r['width']), default=0)
            for ref in record['references']:
                if ref['access'] == 'address-or-value':
                    ref['access'] = 'address-taking'
            storage.append(record)
            for ref in record['references']:
                if ref['access'] in ('read','write','read-write') and ref['offset'] is not None and ref['width'] and ref['offset'] + ref['width'] > record['width']:
                    errors.append(f"access exceeds extent: {record['id']}:{ref['line']}")
        if kind == 'background':
            record['lifecycle'] = {field: [resolve(module, s) for s in record.get(field, [])]
                                   for field in ('capture','restore','draw','validity','invalidation','publication')}
            for verifier in record.get('verifier', []):
                if not (root / verifier).is_file():
                    errors.append(f'missing verifier: {verifier}')
        if kind == 'index':
            found = [p for p in producers if p['id'] == record.get('producer')]
            record['producers'] = found
            if not found:
                errors.append(f"missing index producer: {record['id']}")
            for p in found:
                source = (root / p['file']).read_text(encoding='utf-8')
                if p.get('function') and not re.search(r'^\s*def '+re.escape(p['function'])+r'\(', source, re.M):
                    errors.append(f"missing producer function: {p['id']}")
                if name not in p.get('symbols', []):
                    errors.append(f"producer does not declare symbol: {p['id']}:{name}")
                p['href'] = 'producers.html#' + source_line_id(p['file'], p['line'])
            if record.get('index_bytes'):
                extent = resolve(module, record['index_bytes'])
                page = resolve(module, record['index_page'])
                stride = record['stride']
                if extent and page:
                    if extent['address'] % stride:
                        errors.append(f"index extent is not a multiple of stride: {record['id']}")
                    record['extracted_bounds'] = {'minimum': 0, 'exclusive_maximum': extent['address']//stride,
                        'index_bytes': extent, 'page': page, 'stride': stride, 'evidence': 'extracted fact'}
            bounds = record.get('bounds')
            if isinstance(bounds, list) and len(bounds) == 2 and not bounds[0] <= record['address'] <= bounds[1]:
                errors.append(f"index out of bounds: {record['id']}")
    for use in uses:
        lines = modules[use['module']].source_lines
        following = next((l for l in lines if l.file == use['file'] and l.number > use['line'] and l.text.split(';',1)[0].strip()), None)
        if use['id'] not in ids or not following or use['symbol'] not in TOKEN.findall(instruction(following.text)[1]):
            errors.append(f"obsolete or missing index operand: {use['module']}:{use['file']}:{use['line']}")
        else:
            use['operand_line'] = following.number
            use['href'] = module_page(use['module'])+'#'+source_line_id(following.file, following.number)
    errors.extend(overlap_errors(storage))
    candidates = []
    for module in project.modules:
        emitted = {(s.file, s.line) for s in module.emitted_spans}
        generated_files = {line.file for line in module.source_lines
                           if line.number <= 5 and 'generated by' in line.text.lower()}
        for name, line in definitions[module.id].items():
            op, operand = instruction(line.text)
            address = symbols[module.id].get(name)
            following = next((l for l in module.source_lines if l.file == line.file and l.number > line.number and l.text.split(';',1)[0].strip()), None) if not op else None
            allocation = op == 'rmb' or (following is not None and instruction(following.text)[0] == 'rmb')
            category = ('generated-index' if line.file.startswith('build/') or line.file in generated_files else
                        'storage' if allocation or (op == 'equ' and address and address.assembled_address < 0x100 and re.search(r'\$[0-9a-fA-F]{4}\b', operand)) else
                        'retained-background' if re.search(r'(background|underlay|_bg(?:_|$)|ring_|cache)', name, re.I) else None)
            if not category:
                continue
            state = 'documented' if (module.id, name) in documented else 'unresolved'
            reason = 'Semantic ownership needs review; discovery does not prove allocation or lifetime.'
            if category == 'generated-index' and not re.search(r'(INDEX|GRAPHIC|FRAME|ADDR|PAGE|ENTRY|COUNT|OFFSET|DESCRIPTOR)', name, re.I):
                state, reason = 'excluded', 'Generated data/constant outside index-name discovery policy; retained in inventory.'
            candidates.append({'module': module.id, 'symbol': name, 'category': category, 'state': state,
                'reason': reason, 'evidence': 'extracted fact', 'file': line.file, 'line': line.number,
                'profile_presence': 'assembled-symbol' if address else 'source-only/inactive',
                'emits_at_definition': (line.file,line.number) in emitted,
                'href': module_page(module.id)+'#'+source_line_id(line.file,line.number)})
    return {'schema': 1, 'revision': project.revision, 'build': receipt, 'records': records,
            'producer_sources': {p['file']: (root / p['file']).read_text(encoding='utf-8').splitlines()
                                 for p in producers},
            'index_uses': uses, 'candidates': candidates, 'errors': sorted(set(errors)),
            'counts': dict(Counter(c['state'] for c in candidates)),
            'limits': 'Lexical discovery. Unresolved candidates and indirect references are not safety passes. Authored lifecycle ordering is not runtime proof.'}


def render_audit(audit, root, output):
    from .render import _page
    chunks = ['<h1>Index, scratch and retained-background audit</h1>',
              '<p>Extracted fact = parsed source/build value. Authored declaration = reviewed intent. Verified result requires linked test evidence. Unresolved = not established.</p>',
              '<p>'+html.escape(audit['limits'])+'</p>',
              '<label>Filter records and candidates <input id="filter" type="search"></label>']
    chunks.append('<p>Revision <code>'+html.escape(audit['revision'])+'</code>. Required contract validation: '+
                  ('FAIL' if audit['errors'] else 'PASS')+'. Discovery counts: '+html.escape(str(audit['counts']))+'.</p>')
    if audit['errors']:
        chunks.append('<pre>'+html.escape('\n'.join(audit['errors']))+'</pre>')
    for r in audit['records']:
        links = []
        for loc in [r.get('definition'), *r.get('references', [])]:
            if loc:
                links.append(f'<a href="{loc["href"]}">{html.escape(loc["file"])}:{loc["line"]}</a>')
        for values in r.get('lifecycle', {}).values():
            for loc in values:
                if loc:
                    links.append(f'<a href="{loc["href"]}">{html.escape(loc["symbol"])}</a>')
        for p in r.get('producers', []):
            links.append(f'<a href="{p["href"]}">{html.escape(p["file"])}:{p["line"]}</a>')
        chunks.append(f'<section class="record" id="{html.escape(r["id"])}"><h2>{html.escape(r["id"])}</h2><p>{" | ".join(links)}</p><pre>{html.escape(json.dumps(r,indent=2))}</pre></section>')
    chunks.append('<h2>Discovery inventory</h2><p>Includes inactive/source-only candidates. Unresolved entries are coverage debt, not demonstrated defects.</p>')
    for c in audit['candidates']:
        chunks.append(f'<p class="record"><a href="{c["href"]}">{html.escape(c["module"]+":"+c["symbol"])}</a> — {c["state"]}; {c["category"]}; {c["profile_presence"]}. {c["reason"]}</p>')
    chunks.append('<script>document.getElementById("filter").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll(".record").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script>')
    (output/'ownership.html').write_text(_page('Ownership audit',''.join(chunks)),encoding='utf-8')
    (output/'ownership.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    producer_files = sorted({p['file'] for r in audit['records'] for p in r.get('producers', [])})
    if audit.get('producer_sources'):
        producer_body = []
        for filename in producer_files:
            producer_body.append('<h2>'+html.escape(filename)+'</h2>')
            for number, line in enumerate(audit['producer_sources'][filename], 1):
                producer_body.append(f'<pre id="{source_line_id(filename,number)}">{number}: {html.escape(line)}</pre>')
        (output/'producers.html').write_text(_page('Index producers',''.join(producer_body)),encoding='utf-8')
