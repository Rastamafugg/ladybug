"""Local-file-only publication oracle. Constructed statically; never run in Phase A."""
import hashlib
import time
from pathlib import Path

FRAME_BYTES = 30720
STATIC_SHA = 'd994c4575891f72441836057a7a737f1b72fcc5b3d385ed878527dc60ab47b17'

class Budget:
    def __init__(self, deadline, clock=time.monotonic):
        self.deadline, self.clock, self.operations = deadline, clock, 0
        self.check()
    def check(self):
        if self.clock() >= self.deadline:
            raise TimeoutError('offline deadline; comparison incomplete')
    def tick(self, count=1):
        self.operations += count
        if self.operations >= 256:
            self.check()
            self.operations %= 256

def require(condition, message):
    if not condition:
        raise ValueError(message)

def bounded_read(path, expected_bytes, budget):
    budget.check()
    path = Path(path)
    require(path.stat().st_size == expected_bytes, 'wrong input size: ' + str(path))
    data = bytearray()
    with path.open('rb') as handle:
        while len(data) < expected_bytes:
            budget.check()
            part = handle.read(min(65536, expected_bytes - len(data)))
            budget.check()
            require(bool(part), 'truncated input')
            data.extend(part)
        require(handle.read(1) == b'', 'input grew during read')
    budget.check()
    return bytes(data)

def digest(data, budget):
    value = hashlib.sha256()
    for offset in range(0, len(data), 65536):
        budget.check()
        value.update(data[offset:offset + 65536])
        budget.check()
    return value.hexdigest()

def packed_tile(cold, runtime, glyph, colour, budget):
    budget.check()
    if colour == 0:
        offset = glyph * 32
        require(0 <= offset and offset + 32 <= len(cold), 'graphic bounds')
        return cold[offset:offset + 32]
    require(0 <= glyph < 41 and 1 <= colour <= 15, 'text descriptor bounds')
    offset = 0x35c8 + glyph * 8
    require(offset + 8 <= len(runtime), 'font bounds')
    result = bytearray()
    for row in runtime[offset:offset + 8]:
        for shift in (6, 4, 2, 0):
            budget.tick()
            high = colour if row & (2 << shift) else 0
            low = colour if row & (1 << shift) else 0
            result.append((high << 4) | low)
    return bytes(result)

def draw_tile(frame, tile, destination, budget):
    require(len(frame) == FRAME_BYTES and len(tile) == 32, 'tile/frame length')
    offset = destination - 0x2000
    require(0 <= offset and offset % 160 <= 156 and offset + 7 * 160 + 4 <= FRAME_BYTES, 'tile destination bounds')
    for row in range(8):
        for column in range(4):
            budget.tick()
            frame[offset + row * 160 + column] = tile[row * 4 + column]

def compose_static(cold, runtime, budget):
    budget.check()
    require(len(cold) == 13817 and len(runtime) == 16384, 'pinned payload lengths')
    stream = cold[0x1e26:0x21d5]
    pos = cell = 0
    frame = bytearray(FRAME_BYTES)
    while cell < 960:
        budget.tick()
        require(pos + 2 <= len(stream), 'truncated RLE token')
        count, value = stream[pos:pos + 2]
        pos += 2
        require(count > 0 and cell + count <= 960, 'RLE count bounds')
        if value < 174:
            tile = packed_tile(cold, runtime, value, 0, budget)
        else:
            require(pos < len(stream), 'missing text colour')
            colour = stream[pos]
            pos += 1
            glyph = value - 174
            require(0 <= glyph < 41 and 0 <= colour <= 15, 'static text bounds')
            tile = bytes(32) if colour == 0 else packed_tile(cold, runtime, glyph, colour, budget)
        for _ in range(count):
            row, column = divmod(cell, 40)
            draw_tile(frame, tile, 0x2000 + row * 1280 + column * 4, budget)
            cell += 1
    require(pos == len(stream), 'trailing RLE data')
    require(digest(frame, budget) == STATIC_SHA, 'static golden hash mismatch')
    budget.check()
    return bytes(frame)

def dynamic_tile(cold, runtime, ident, budget):
    require(0 <= ident < 219, 'dynamic tile ID')
    offset = 0x39a2 + ident * 2
    glyph, colour = runtime[offset:offset + 2]
    return packed_tile(cold, runtime, glyph, colour, budget)

def sprite_operations(stream, origin, budget, limit=FRAME_BYTES):
    pos, destination = 0, origin
    budget.check()
    while pos < len(stream):
        budget.tick()
        delta = stream[pos]
        pos += 1
        if delta == 255:
            require(pos + 2 <= len(stream), 'truncated extended delta')
            delta = int.from_bytes(stream[pos:pos + 2], 'big')
            pos += 2
            if delta == 0:
                budget.check()
                return
            require(pos < len(stream), 'missing stage delta')
            pos += 1
        destination += delta
        require(pos < len(stream), 'missing sprite run')
        command = stream[pos]
        pos += 1
        count, masked = command & 127, bool(command & 128)
        require(count > 0 and 0 <= destination and destination + count <= limit, 'sprite destination bounds')
        require(pos + count * (2 if masked else 1) <= len(stream), 'truncated sprite run')
        for _ in range(count):
            budget.tick()
            if masked:
                mask, value = stream[pos:pos + 2]
                pos += 2
            else:
                mask, value = 0, stream[pos]
                pos += 1
            yield destination, mask, value
            destination += 1
    raise ValueError('unterminated sprite stream')

def expected_images(cold, runtime, highscore, player, budget):
    require(len(highscore) == 821 and len(player) == 2294, 'module lengths')
    background = bytearray(compose_static(cold, runtime, budget))
    for start in (0x7f04, 0x3984):
        for index in range(7):
            draw_tile(background, dynamic_tile(cold, runtime, 178, budget), start + 4 * index, budget)
    glyphs = highscore[0x324:0x32e]
    require(len(glyphs) == 10, 'digit table bounds')
    for start in (0x2a84, 0x6104, 0x3e84):
        for index, digit in enumerate((0, 9, 5, 0, 0, 0)):
            draw_tile(background, dynamic_tile(cold, runtime, glyphs[digit], budget), start + 4 * index, budget)
    saved = bytearray()
    for row in range(16):
        for column in range(8):
            budget.tick()
            saved.append(background[0x694c + row * 160 + column])
    require(player[0] == 0x39, 'sprite descriptor page')
    offset = int.from_bytes(player[1:3], 'big') - 0xa000
    require(0 <= offset < len(player), 'sprite descriptor pointer')
    expected = bytearray(background)
    for destination, mask, value in sprite_operations(player[offset:], 0x694c, budget):
        expected[destination] = (expected[destination] & mask) | value
    budget.check()
    return {'background': bytes(background), 'frame': bytes(expected), 'saved': bytes(saved)}

def compare_bytes(expected, actual, budget):
    budget.check()
    require(len(expected) == len(actual), 'comparison length mismatch')
    count, samples = 0, []
    for index, (left, right) in enumerate(zip(expected, actual)):
        budget.tick()
        if left != right:
            count += 1
            if len(samples) < 64:
                samples.append({'offset': index, 'expected': left, 'actual': right})
    budget.check()
    return {'passed': count == 0, 'mismatches': count, 'samples': samples, 'sha256': digest(actual, budget)}

def compare_publications(expected, frames, saves, budget, player_stream=None):
    require(len(frames) == 2 and len(saves) == 4, 'capture cardinality')
    require(len(expected['frame']) == FRAME_BYTES and len(expected['saved']) == 128, 'expected image sizes')
    comparisons = []
    for actual in frames:
        comparisons.append(compare_bytes(expected['frame'], actual, budget))
    for actual in saves:
        comparisons.append(compare_bytes(expected['saved'], actual, budget))
    budget.check()
    result={'passed': all(row['passed'] for row in comparisons), 'objects': comparisons,
            'classification': 'exact-stationary-pair' if all(row['passed'] for row in comparisons) else 'unexplained-residual'}
    if player_stream is not None and not result['passed']:
        result['location_fits']=[classify_pair(expected,x,player_stream,budget) for x in frames]
        fits=[x['classification'] for x in result['location_fits']]
        result['classification']='duplicate-confirmed' if all(x=='unique-location-fit' for x in fits) else ('alternating-location' if len(set(fits))>1 else 'unexplained-residual')
    return result

def fit_locations(background, actual, player_stream, budget, origins=range(FRAME_BYTES)):
    """Bounded complete overlay fits. Four origin scans, 245760 origins, 256 pixels each."""
    require(len(background) == FRAME_BYTES and len(actual) == FRAME_BYTES, 'fit frame length')
    matches=[]; scanned=0; candidates=0
    for scan in range(4):
        for origin in origins:
            budget.tick(); scanned += 1
            if scanned > 245760: raise TimeoutError('location scan limit')
            try: ops=list(sprite_operations(player_stream, origin, budget))
            except ValueError: continue
            if len(ops)>256: continue
            mismatch=False; distinguishing=False
            for offset,mask,value in ops:
                predicted=(background[offset]&mask)|value
                if predicted!=actual[offset]: mismatch=True; break
                if predicted!=background[offset]: distinguishing=True
            candidates += 1
            if not mismatch and distinguishing: matches.append({'origin':origin,'scan':scan,'pixels':len(ops)})
    unique=sorted({x['origin'] for x in matches})
    return {'matches':matches,'origins':unique,'scanned_origins':scanned,'candidate_overlays':candidates,
            'classification':'unique-location-fit' if len(unique)==1 else ('ambiguous-location-fit' if len(unique)>1 else 'unexplained-residual')}

def classify_pair(expected, actual, player_stream, budget):
    base=compare_bytes(expected['frame'],actual,budget)
    if base['passed']: return {'comparison':base,'classification':'exact-stationary-pair'}
    fit=fit_locations(expected['background'],actual,player_stream,budget)
    return {'comparison':base,'fit':fit,'classification':fit['classification']}
