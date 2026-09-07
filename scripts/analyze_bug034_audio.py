"""Analyze BUG-034 recordings using the standard library; no gain normalization."""
import argparse
import array
import cmath
import json
import math
from pathlib import Path
import sys
import wave

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--directory', type=Path,
                default=Path(__file__).resolve().parents[1] / 'repro/bug034-audio-input')
out = ap.parse_args().directory


def samples(mode, scenario):
    with wave.open(str(out / f'{mode}-{scenario}.wav'), 'rb') as stream:
        assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
        rate = stream.getframerate()
        pcm = array.array('h', stream.readframes(stream.getnframes()))
    if sys.byteorder != 'little':
        pcm.byteswap()
    return rate, list(pcm)


def metrics(values):
    mean = sum(values) / len(values)
    rms = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    return {'samples': len(values), 'mean_pcm': mean, 'ac_rms_pcm': rms,
            'peak_to_peak_pcm': max(values) - min(values),
            'ac_dbfs': 20 * math.log10(rms / 32768) if rms else None}


quiet, tone = {}, {}
for mode in ('keyboard', 'joystick'):
    rate, values = samples(mode, 'quiet')
    quiet[mode] = metrics(values[int(.25 * rate):int(1.75 * rate)])
    rate, values = samples(mode, 'tone')
    values = values[int(.5 * rate):int(1.5 * rate)]
    assert len(values) == rate
    mean = sum(values) / len(values)
    window = [((value - mean) / 32768) * (.5 - .5 * math.cos(2 * math.pi * i / (len(values) - 1)))
              for i, value in enumerate(values)]

    def power(hz):
        step = cmath.exp(-2j * math.pi * hz / rate)
        phase, total = 1 + 0j, 0j
        for value in window:
            total += value * phase
            phase *= step
        return abs(total) ** 2

    def band(hz):
        return sum(power(i) for i in range(hz - 2, hz + 3))

    carrier = band(500)
    sidebands = band(440) + band(560)
    tone[mode] = {'carrier_498_502_power': carrier,
                  'sideband_438_442_and_558_562_power': sidebands,
                  'sideband_dbc': 10 * math.log10(sidebands / carrier),
                  'ac_rms_pcm': metrics(values)['ac_rms_pcm']}
    print(mode, 'quiet:', quiet[mode], 'tone:', tone[mode])

tone['sideband_reduction_db'] = tone['joystick']['sideband_dbc'] - tone['keyboard']['sideband_dbc']
tone['method'] = ('One second, 0.5–1.5s into each capture; Hann window; sum five one-Hz Fourier '
                  'bins around carrier500 and sidebands440/560; sideband power relative to carrier; single observations.')
quiet['method'] = '0.25–1.75s of each two-second muted-voice fixture; signed 16-bit PCM; null dBFS denotes exact zero.'
for name, data in [('quiet-analysis.json', quiet), ('tone-analysis.json', tone)]:
    (out / name).write_text(json.dumps(data, indent=2) + '\n')
print('sideband reduction:', tone['sideband_reduction_db'], 'dB')
