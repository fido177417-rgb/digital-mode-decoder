"""
Enhanced Digital Mode Decoder - SDR-style features
Integrates spectrum analysis, waterfall, band plan, and multiple demod modes.
Inspired by MagicSDR and similar SDR applications.
"""
import sys
import os
import math
import time
import struct
import wave
from pathlib import Path
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from goertzel import GoertzelFilter, ToneDetector
from cw_decoder import CWDecoder, morse_to_audio
from rtty_decoder import RTTYDecoder, RTTYGenerator
from ft8_decoder import FT8Decoder, FT8Encoder
from fft_module import FFTAnalyzer, SpectrumAnalyzer, detect_pitch_fft, freq_to_musical
from virtual_sdr import VirtualSDR, IQToAudio


# Ham Radio Band Plan (MHz)
BAND_PLAN = {
    '160m': (1.8, 2.0, 'Amateur'),
    '80m': (3.5, 4.0, 'Amateur'),
    '60m': (5.3, 5.4, 'Amateur'),
    '40m': (7.0, 7.3, 'Amateur'),
    '30m': (10.1, 10.15, 'Amateur'),
    '20m': (14.0, 14.35, 'Amateur'),
    '17m': (18.068, 18.168, 'Amateur'),
    '15m': (21.0, 21.45, 'Amateur'),
    '12m': (24.89, 24.99, 'Amateur'),
    '10m': (28.0, 29.7, 'Amateur'),
    '6m': (50.0, 54.0, 'Amateur'),
    '2m': (144.0, 148.0, 'Amateur'),
    '70cm': (420.0, 450.0, 'Amateur'),
    'SW_L': (0.15, 0.53, 'Longwave'),
    'SW_M': (0.53, 1.7, 'Mediumwave'),
    'SW_80': (2.3, 2.5, 'Shortwave 80m'),
    'SW_60': (3.2, 3.4, 'Shortwave 60m'),
    'SW_49': (4.75, 5.1, 'Shortwave 49m'),
    'SW_31': (9.4, 9.9, 'Shortwave 31m'),
    'SW_25': (11.6, 12.1, 'Shortwave 25m'),
    'SW_22': (13.5, 13.9, 'Shortwave 22m'),
    'SW_19': (15.1, 15.8, 'Shortwave 19m'),
    'SW_16': (17.5, 18.0, 'Shortwave 16m'),
    'SW_13': (21.4, 21.9, 'Shortwave 13m'),
    'SW_11': (25.5, 26.1, 'Shortwave 11m'),
    'FM_BC': (88.0, 108.0, 'FM Broadcast'),
    'AIR': (108.0, 137.0, 'Airband'),
    'VHF': (137.0, 174.0, 'VHF'),
    'UHF': (400.0, 512.0, 'UHF'),
}

# Demodulation modes
DEMOD_MODES = {
    'AM': 'Amplitude Modulation',
    'FM': 'Frequency Modulation (NFM)',
    'WFM': 'Wide FM (Broadcast)',
    'CW': 'Continuous Wave (Morse)',
    'SSB_L': 'Single Sideband Lower',
    'SSB_U': 'Single Sideband Upper',
    'RTTY': 'Radio Teletype',
    'FT8': 'FT8 Digital Mode',
}


class AudioIO:
    """Audio I/O engine for Android (Termux)."""
    
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self.recording_dir = Path.home() / '.digital-mode-decoder' / 'recordings'
        self.recording_dir.mkdir(parents=True, exist_ok=True)
        self.has_termux_api = self._check_termux_api()
    
    def _check_termux_api(self):
        try:
            import subprocess
            result = subprocess.run(['which', 'termux-microphone-record'], 
                                  capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def record(self, duration=5, filename=None):
        """Record audio from microphone."""
        import subprocess
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"rec_{timestamp}.wav"
        filepath = self.recording_dir / filename
        
        if self.has_termux_api:
            cmd = ['termux-microphone-record', '-l', str(duration), '-f', str(filepath)]
            try:
                subprocess.run(cmd, timeout=duration + 5)
                return str(filepath) if filepath.exists() else None
            except:
                return None
        else:
            return self._generate_test_recording(duration, str(filepath))
    
    def _generate_test_recording(self, duration, filepath):
        """Generate test recording."""
        import random
        samples = []
        n = int(self.sample_rate * duration)
        for i in range(n):
            t = i / self.sample_rate
            sample = 0.3 * math.sin(2 * math.pi * 700 * t)
            sample += 0.1 * random.uniform(-1, 1)
            samples.append(sample)
        self.save_wav(samples, filepath)
        return filepath
    
    def play(self, filepath):
        """Play audio file."""
        import subprocess
        if self.has_termux_api and os.path.exists(filepath):
            subprocess.Popen(['termux-media-player', 'play', str(filepath)])
            return True
        return False
    
    def stop_playback(self):
        """Stop playback."""
        import subprocess
        if self.has_termux_api:
            try:
                subprocess.run(['termux-media-player', 'stop'], timeout=5)
            except:
                pass
    
    def save_wav(self, samples, filepath):
        """Save samples to WAV."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(filepath), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            int_samples = [int(max(-1, min(1, s)) * 32767) for s in samples]
            wf.writeframes(struct.pack(f'<{len(int_samples)}h', *int_samples))
    
    def load_wav(self, filepath):
        """Load WAV file."""
        with wave.open(str(filepath), 'rb') as wf:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)
        n_samples = len(raw_data) // 2
        int_samples = struct.unpack(f'<{n_samples}h', raw_data)
        return [s / 32768.0 for s in int_samples], sample_rate
    
    def generate_tone(self, freq, duration, amplitude=0.8):
        """Generate tone."""
        n = int(self.sample_rate * duration)
        return [amplitude * math.sin(2 * math.pi * freq * i / self.sample_rate) for i in range(n)]
    
    def generate_morse(self, text, wpm=15, freq=700):
        """Generate Morse code from text."""
        text_to_morse = {
            'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.',
            'F': '..-.', 'G': '--.', 'H': '....', 'I': '..', 'J': '.---',
            'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---',
            'P': '.--.', 'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-',
            'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-', 'Y': '-.--',
            'Z': '--..', '0': '-----', '1': '.----', '2': '..---',
            '3': '...--', '4': '....-', '5': '.....', '6': '-....',
            '7': '--...', '8': '---..', '9': '----.', ' ': ' '
        }
        morse = ' '.join(text_to_morse.get(c, '') for c in text.upper())
        return morse_to_audio(morse.strip(), wpm=wpm, freq=freq, sample_rate=self.sample_rate)


class SpectrumWaterfall:
    """Spectrum and waterfall display."""
    
    def __init__(self, width=80, height=15, waterfall_rows=20):
        self.width = width
        self.height = height
        self.waterfall_rows = waterfall_rows
        self.bins = [0.0] * width
        self.waterfall = deque(maxlen=waterfall_rows)
        self.min_db = -80
        self.max_db = 0
        self.min_freq = 0
        self.max_freq = 24000
    
    def update(self, magnitudes, min_freq=0, max_freq=24000):
        """Update with new spectrum data."""
        if not magnitudes:
            return
        self.min_freq = min_freq
        self.max_freq = max_freq
        
        step = len(magnitudes) / self.width
        for i in range(self.width):
            idx = int(i * step)
            if idx < len(magnitudes):
                self.bins[i] = magnitudes[idx]
        
        if self.bins:
            self.max_db = max(self.bins) if max(self.bins) > self.min_db else self.min_db + 10
        
        self.waterfall.append(self.bins.copy())
    
    def render_spectrum(self):
        """Render spectrum bars."""
        lines = []
        db_range = self.max_db - self.min_db
        if db_range <= 0:
            db_range = 1
        
        for row in range(self.height - 1, -1, -1):
            threshold = self.min_db + (row / self.height) * db_range
            line = ''
            for val in self.bins:
                if val >= threshold:
                    intensity = (val - self.min_db) / db_range
                    if intensity > 0.8:
                        line += '█'
                    elif intensity > 0.6:
                        line += '▓'
                    elif intensity > 0.4:
                        line += '▒'
                    elif intensity > 0.2:
                        line += '░'
                    else:
                        line += '·'
                else:
                    line += ' '
            lines.append(line)
        return lines
    
    def render_waterfall(self):
        """Render waterfall display."""
        lines = []
        db_range = self.max_db - self.min_db
        if db_range <= 0:
            db_range = 1
        
        for row in self.waterfall:
            line = ''
            for val in row:
                intensity = (val - self.min_db) / db_range
                if intensity > 0.9:
                    line += '@'
                elif intensity > 0.7:
                    line += '#'
                elif intensity > 0.5:
                    line += '*'
                elif intensity > 0.3:
                    line += '+'
                elif intensity > 0.1:
                    line += '.'
                else:
                    line += ' '
            lines.append(line)
        
        while len(lines) < self.waterfall_rows:
            lines.insert(0, ' ' * self.width)
        
        return lines


class Demodulator:
    """Multi-mode demodulator."""
    
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self.mode = 'CW'
        self.squelch = 0.0
        self.frequency = 700
    
    def demodulate(self, samples, mode=None):
        """Demodulate samples based on mode."""
        mode = mode or self.mode
        
        if mode == 'AM':
            return self._demod_am(samples)
        elif mode == 'FM':
            return self._demod_nfm(samples)
        elif mode == 'WFM':
            return self._demod_wfm(samples)
        elif mode == 'CW':
            return self._demod_cw(samples)
        elif mode == 'SSB_L':
            return self._demod_ssb(samples, upper=False)
        elif mode == 'SSB_U':
            return self._demod_ssb(samples, upper=True)
        else:
            return samples
    
    def _demod_am(self, samples):
        """AM demodulation (envelope detection)."""
        demod = []
        for i in range(len(samples)):
            # Envelope detection
            env = abs(samples[i])
            demod.append(env)
        return demod
    
    def _demod_nfm(self, samples):
        """NFM demodulation (frequency discrimination)."""
        demod = []
        for i in range(1, len(samples)):
            # Frequency discrimination
            if samples[i-1] != 0:
                phase_diff = math.atan2(samples[i], samples[i-1])
                demod.append(phase_diff / math.pi)
            else:
                demod.append(0)
        return demod
    
    def _demod_wfm(self, samples):
        """WFM demodulation (broadcast FM)."""
        # Similar to NFM but with de-emphasis
        demod = self._demod_nfm(samples)
        
        # Simple de-emphasis filter
        alpha = 0.0001  # Time constant
        filtered = [demod[0]]
        for i in range(1, len(demod)):
            filtered.append(filtered[-1] + alpha * (demod[i] - filtered[-1]))
        
        return filtered
    
    def _demod_cw(self, samples):
        """CW demodulation (tone detection)."""
        # Use Goertzel to detect tone
        detector = ToneDetector(self.frequency, self.sample_rate, threshold=0.1)
        block_size = 256
        demod = []
        
        for i in range(0, len(samples), block_size):
            block = samples[i:i+block_size]
            if len(block) < block_size:
                break
            detected = detector.detect(block)
            value = 1.0 if detected else 0.0
            demod.extend([value] * block_size)
        
        return demod[:len(samples)]
    
    def _demod_ssb(self, samples, upper=True):
        """SSB demodulation (phase shift method)."""
        # Simplified SSB demodulation
        demod = []
        hilbert = [0.0] * len(samples)
        
        # Simple Hilbert transform approximation
        for i in range(2, len(samples) - 2):
            hilbert[i] = (samples[i-2] - samples[i+2]) / 8 + \
                         (samples[i-1] - samples[i+1]) / 2
        
        for i in range(len(samples)):
            if upper:
                demod.append(samples[i] + hilbert[i])
            else:
                demod.append(samples[i] - hilbert[i])
        
        return demod
    
    def apply_squelch(self, samples, threshold=None):
        """Apply squelch to mute noise."""
        threshold = threshold or self.squelch
        if threshold <= 0:
            return samples
        
        # Calculate signal level
        output = []
        block_size = 256
        for i in range(0, len(samples), block_size):
            block = samples[i:i+block_size]
            if len(block) < block_size:
                break
            level = sum(abs(s) for s in block) / len(block)
            if level > threshold:
                output.extend(block)
            else:
                output.extend([0.0] * len(block))
        
        return output[:len(samples)]


class BandPlan:
    """Ham radio band plan display."""
    
    def __init__(self):
        self.bands = BAND_PLAN
    
    def get_band(self, freq_mhz):
        """Get band name for frequency."""
        for name, (low, high, desc) in self.bands.items():
            if low <= freq_mhz <= high:
                return f"{name} ({desc})"
        return "Unknown"
    
    def get_nearby_bands(self, freq_mhz, margin=0.5):
        """Get bands near frequency."""
        nearby = []
        for name, (low, high, desc) in self.bands.items():
            if abs(low - freq_mhz) < margin or abs(high - freq_mhz) < margin:
                nearby.append(f"{name}: {low}-{high} MHz")
        return nearby
    
    def render(self, center_freq=7.0, span=2.0):
        """Render band plan display."""
        lines = []
        min_freq = center_freq - span/2
        max_freq = center_freq + span/2
        
        for name, (low, high, desc) in sorted(self.bands.items(), key=lambda x: x[1][0]):
            if high >= min_freq and low <= max_freq:
                bar_start = max(0, int((low - min_freq) / span * 60))
                bar_end = min(60, int((high - min_freq) / span * 60))
                bar = ' ' * bar_start + '█' * (bar_end - bar_start) + ' ' * (60 - bar_end)
                lines.append(f"{name:8s} {bar} {desc}")
        
        return lines


class SDRApp:
    """Full-featured SDR-style application."""
    
    def __init__(self):
        self.sample_rate = 48000
        self.mode = 'CW'
        self.frequency = 700
        
        # Components
        self.audio = AudioIO(self.sample_rate)
        self.spectrum = SpectrumWaterfall(width=80, height=12, waterfall_rows=15)
        self.demod = Demodulator(self.sample_rate)
        self.band_plan = BandPlan()
        self.sdr = VirtualSDR(sample_rate=self.sample_rate)
        self.iq_converter = IQToAudio(sample_rate=self.sample_rate, audio_rate=8000)
        
        # Decoders
        self.cw_decoder = CWDecoder(sample_rate=8000, tone_freq=700)
        self.rtty_decoder = RTTYDecoder(sample_rate=8000)
        self.ft8_decoder = FT8Decoder(sample_rate=8000)
        
        # Spectrum analyzer
        self.spectrum_analyzer = SpectrumAnalyzer(fft_size=2048, sample_rate=self.sample_rate)
        
        # State
        self.decoded_text = ''
        self.last_pitch = None
        self.bookmarks = []
        self.recording = False
    
    def process_audio(self, samples):
        """Process audio through spectrum and demodulator."""
        # Spectrum analysis
        spectrum_data = self.spectrum_analyzer.process(samples)
        self.spectrum.update(spectrum_data['spectrum'])
        
        # Demodulate
        demodulated = self.demod.demodulate(samples)
        
        # Apply squelch
        if self.demod.squelch > 0:
            demodulated = self.demod.apply_squelch(demodulated)
        
        # Pitch detection
        self.last_pitch = detect_pitch_fft(demodulated[:1024] if len(demodulated) >= 1024 else demodulated, 8000)
        
        return demodulated
    
    def decode(self, samples):
        """Decode digital modes."""
        # Resample to 8000 Hz for decoders
        if self.sample_rate != 8000:
            ratio = self.sample_rate // 8000
            samples_8k = samples[::ratio]
        else:
            samples_8k = samples
        
        if self.mode == 'CW':
            result = self.cw_decoder.decode_block(samples_8k)
            self.decoded_text += result
            return result
        elif self.mode == 'RTTY':
            result = self.rtty_decoder.process_samples(samples_8k)
            self.decoded_text += result
            return result
        elif self.mode == 'FT8':
            messages = self.ft8_decoder.decode_audio_samples(samples_8k)
            result = '\n'.join([str(m) for m in messages])
            self.decoded_text += result
            return result
        return ''
    
    def generate_signal(self, text='SOS', freq=700, duration=2.0):
        """Generate test signal."""
        if self.mode == 'CW':
            return self.audio.generate_morse(text, wpm=15, freq=freq)
        else:
            return self.audio.generate_tone(freq, duration)
    
    def set_mode(self, mode):
        """Set demodulation mode."""
        if mode in DEMOD_MODES:
            self.mode = mode
            self.demod.mode = mode
            return True
        return False
    
    def set_frequency(self, freq):
        """Set center frequency."""
        self.frequency = freq
        self.demod.frequency = freq
        self.cw_decoder.tone_freq = freq
    
    def set_squelch(self, level):
        """Set squelch level."""
        self.demod.squelch = level
    
    def add_bookmark(self, freq, name=''):
        """Add frequency bookmark."""
        self.bookmarks.append({'freq': freq, 'name': name})
    
    def clear(self):
        """Clear decoded text."""
        self.decoded_text = ''
        self.cw_decoder.reset()
        self.rtty_decoder.reset()
        self.spectrum.waterfall.clear()


def print_banner():
    """Print app banner."""
    print('\033[2J\033[H')
    print('╔' + '═' * 68 + '╗')
    print('║' + ' SDR DIGITAL MODE DECODER '.center(68) + '║')
    print('║' + ' AM/FM/CW/SSB/RTTY/FT8 with Spectrum & Waterfall '.center(68) + '║')
    print('╚' + '═' * 68 + '╝')
    print()


def print_help():
    """Print help."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║ COMMANDS                                                         ║
╠══════════════════════════════════════════════════════════════════╣
║ DEMODULATION                                                     ║
║   mode <AM|FM|CW|SSB_L|SSB_U|RTTY|FT8>  Set demod mode         ║
║   freq <hz>           Set frequency (default: 700)              ║
║   squelch <0-1>       Set squelch level                         ║
║                                                                  ║
║ DECODE                                                           ║
║   file <path>         Decode audio file                         ║
║   mic [seconds]       Record and decode                         ║
║   sdr [mode]          Decode from VirtualSDR                    ║
║                                                                  ║
║ AUDIO                                                            ║
║   play <text>         Generate and play Morse                   ║
║   tone <freq> [sec]   Generate and play tone                    ║
║   stop                Stop playback                             ║
║   record [sec]        Record audio                              ║
║                                                                  ║
║ DISPLAY                                                          ║
║   spectrum            Show spectrum + waterfall                 ║
║   bands               Show band plan                            ║
║   pitch               Show detected pitch                       ║
║   bookmarks           Show frequency bookmarks                  ║
║   bm <freq> [name]    Add frequency bookmark                    ║
║                                                                  ║
║ VIEW                                                             ║
║   history             Show decode history                        ║
║   clear               Clear decoded text                        ║
║                                                                  ║
║ SYSTEM                                                           ║
║   save <path>         Save decoded text                         ║
║   demo                Run demo                                  ║
║   help                Show help                                 ║
║   quit                Exit                                      ║
╚══════════════════════════════════════════════════════════════════╝
""")


def print_spectrum_display(app):
    """Print spectrum and waterfall."""
    spectrum_lines = app.spectrum.render_spectrum()
    waterfall_lines = app.spectrum.render_waterfall()
    
    print('\n╔' + '═' * 70 + '╗')
    print('║' + ' SPECTRUM'.ljust(70) + '║')
    print('╠' + '═' * 70 + '╣')
    for line in spectrum_lines:
        print(f'║ {line:<68} ║')
    print('╠' + '═' * 70 + '╣')
    print('║' + ' WATERFALL'.ljust(70) + '║')
    print('╠' + '═' * 70 + '╣')
    for line in waterfall_lines[-15:]:
        print(f'║ {line:<68} ║')
    print('╠' + '═' * 70 + '╣')
    print(f'║ {app.spectrum.min_freq:.0f}Hz' + ' ' * 50 + f'{app.spectrum.max_freq:.0f}Hz ║')
    print('╚' + '═' * 70 + '╝')


def print_band_plan(app):
    """Print band plan."""
    lines = app.band_plan.render(center_freq=7.0, span=2.0)
    print('\n╔' + '═' * 70 + '╗')
    print('║' + ' BAND PLAN (7 MHz region)'.ljust(70) + '║')
    print('╠' + '═' * 70 + '╣')
    for line in lines:
        print(f'║ {line:<68} ║')
    print('╚' + '═' * 70 + '╝')


def run_demo(app):
    """Run demo."""
    print('\n--- SDR DEMO ---\n')
    
    # 1. Generate and decode CW
    print('[1] CW Demo')
    samples = app.generate_signal('SOS', freq=700)
    app.mode = 'CW'
    demodulated = app.process_audio(samples)
    result = app.decode(demodulated)
    print(f'    Decoded: {result}')
    
    # 2. Show spectrum
    print('\n[2] Spectrum')
    print_spectrum_display(app)
    
    # 3. Band plan
    print('\n[3] Band Plan')
    print_band_plan(app)
    
    # 4. Pitch
    print('\n[4] Pitch Detection')
    if app.last_pitch:
        print(f'    {freq_to_musical(app.last_pitch)}')
    
    input('\nPress Enter to continue...')


def main():
    """Main entry."""
    print_banner()
    app = SDRApp()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--test':
            run_demo(app)
            return
        elif sys.argv[1] == '--file' and len(sys.argv) > 2:
            filepath = sys.argv[2]
            if os.path.exists(filepath):
                samples, rate = app.audio.load_wav(filepath)
                app.sample_rate = rate
                demodulated = app.process_audio(samples)
                result = app.decode(demodulated)
                print(f'Decoded: {result}')
            return
    
    print('Type "help" for commands.\n')
    
    while True:
        try:
            pitch_str = f' | {freq_to_musical(app.last_pitch)}' if app.last_pitch else ''
            cmd = input(f'[{app.mode}|{app.frequency}Hz{pitch_str}] > ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nGoodbye!')
            break
        
        if not cmd:
            continue
        
        parts = cmd.split()
        action = parts[0].lower()
        
        if action in ['quit', 'exit', 'q']:
            break
        elif action == 'help':
            print_help()
        elif action == 'mode':
            if len(parts) < 2:
                print(f'Mode: {app.mode} - {DEMOD_MODES.get(app.mode, "")}')
            elif app.set_mode(parts[1].upper()):
                print(f'Mode: {parts[1].upper()}')
        elif action == 'freq':
            if len(parts) < 2:
                print(f'Frequency: {app.frequency} Hz')
            else:
                app.set_frequency(int(parts[1]))
                print(f'Frequency: {parts[1]} Hz')
        elif action == 'squelch':
            if len(parts) < 2:
                print(f'Squelch: {app.demod.squelch}')
            else:
                app.set_squelch(float(parts[1]))
                print(f'Squelch: {parts[1]}')
        elif action == 'file':
            if len(parts) > 1 and os.path.exists(parts[1]):
                samples, rate = app.audio.load_wav(parts[1])
                app.sample_rate = rate
                demodulated = app.process_audio(samples)
                result = app.decode(demodulated)
                print(f'Decoded: {result}')
        elif action == 'mic':
            sec = int(parts[1]) if len(parts) > 1 else 300
            print(f'Recording {sec}s...')
            filepath = app.audio.record(sec)
            if filepath:
                samples, rate = app.audio.load_wav(filepath)
                demodulated = app.process_audio(samples)
                result = app.decode(demodulated)
                print(f'Decoded: {result}')
        elif action == 'sdr':
            mode = parts[1] if len(parts) > 1 else app.mode
            app.mode = mode.upper()
            num_samples = int(app.sample_rate * 2)
            iq = app.sdr.read_samples(num_samples)
            audio = app.iq_converter.convert(iq)
            demodulated = app.process_audio(audio)
            result = app.decode(demodulated)
            print(f'SDR: {result}')
        elif action == 'play':
            text = ' '.join(parts[1:]) if len(parts) > 1 else 'SOS'
            samples = app.generate_signal(text)
            filepath = app.audio.recording_dir / 'playback.wav'
            app.audio.save_wav(samples, str(filepath))
            app.audio.play(str(filepath))
            print(f'Playing: {text}')
        elif action == 'tone':
            freq = int(parts[1]) if len(parts) > 1 else 440
            dur = float(parts[2]) if len(parts) > 2 else 1.0
            samples = app.audio.generate_tone(freq, dur)
            filepath = app.audio.recording_dir / 'tone.wav'
            app.audio.save_wav(samples, str(filepath))
            app.audio.play(str(filepath))
            print(f'Tone: {freq}Hz')
        elif action == 'stop':
            app.audio.stop_playback()
        elif action == 'record':
            sec = int(parts[1]) if len(parts) > 1 else 5
            filepath = app.audio.record(sec)
            print(f'Recorded: {filepath}')
        elif action == 'spectrum':
            print_spectrum_display(app)
        elif action == 'bands':
            print_band_plan(app)
        elif action == 'pitch':
            if app.last_pitch:
                print(freq_to_musical(app.last_pitch))
            else:
                print('No pitch')
        elif action == 'bm':
            if len(parts) > 1:
                freq = float(parts[1])
                name = parts[2] if len(parts) > 2 else ''
                app.add_bookmark(freq, name)
                print(f'Bookmark added: {freq}Hz')
        elif action == 'bookmarks':
            for bm in app.bookmarks:
                print(f"  {bm['freq']}Hz - {bm['name']}")
        elif action == 'history':
            print(app.decoded_text[-500:] if app.decoded_text else 'Empty')
        elif action == 'clear':
            app.clear()
            print('Cleared')
        elif action == 'save':
            if len(parts) > 1:
                with open(parts[1], 'w') as f:
                    f.write(app.decoded_text)
                print(f'Saved: {parts[1]}')
        elif action == 'demo':
            run_demo(app)
        else:
            print(f'Unknown: {action}')


if __name__ == '__main__':
    main()
