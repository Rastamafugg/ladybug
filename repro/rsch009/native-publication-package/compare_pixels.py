"""Local-file-only comparator primitives; no target, emulator, process, or network imports."""
import hashlib, json

FRAME_BYTES = 30720
SAVED_BYTES = 128
MAX_SAMPLES = 64

def sha256_bytes(data): return hashlib.sha256(data).hexdigest()

def compare_bytes(expected, actual):
    if len(expected) != len(actual): return {'passed': False, 'reason': 'length-mismatch', 'expected_bytes': len(expected), 'actual_bytes': len(actual)}
    samples = []; mismatches = 0
    for i, (x, y) in enumerate(zip(expected, actual)):
        if x != y:
            mismatches += 1
            if len(samples) < MAX_SAMPLES: samples.append({'offset': i, 'expected': x, 'actual': y})
    return {'passed': mismatches == 0, 'mismatches': mismatches, 'samples': samples, 'sha256': sha256_bytes(actual)}

def decode_sprite(stream, origin, limit=FRAME_BYTES):
    """Decode bounded descriptors; ordinary zero is valid, and FF 0000 terminates."""
    pos = 0; destination = origin; pixels = []
    while pos < len(stream):
        delta = stream[pos]; pos += 1
        if delta == 0xff:
            if pos + 2 > len(stream): raise ValueError('truncated extended delta')
            extended = int.from_bytes(stream[pos:pos+2], 'big'); pos += 2
            if extended == 0: return pixels
            destination += extended
            if pos >= len(stream): raise ValueError('truncated stage delta')
            pos += 1
        else: destination += delta
        if pos >= len(stream): raise ValueError('truncated run')
        command = stream[pos]; pos += 1; masked = bool(command & 0x80); run = command & 0x7f
        if run == 0: raise ValueError('zero-length run')
        width = run * (2 if masked else 1)
        if pos + width > len(stream): raise ValueError('truncated masked/unmasked run')
        for i in range(run):
            if masked:
                value, mask = stream[pos + 2*i], stream[pos + 2*i + 1]
                pixels.append((destination + i, value, mask))
            else: pixels.append((destination + i, stream[pos + i], None))
        pos += width
        if pos > len(stream): raise ValueError('truncated sprite payload')
    raise ValueError('unterminated sprite stream')

def compare_file(expected_path, actual_path):
    return compare_bytes(expected_path.read_bytes(), actual_path.read_bytes())
