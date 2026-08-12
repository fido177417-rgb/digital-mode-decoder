#!/usr/bin/env python3
"""
Digital Mode Decoder - Unified Application
Integrates CW/FT8/RTTY decoders, FFT spectrum, VirtualSDR, and audio I/O.
Works with Termux on Android for microphone recording and playback.
"""
import sys
import os
import math
import time
import struct
import wave
import threading
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from goertzel import GoertzelFilter, ToneDetector
from cw_decoder import CWDecoder, morse_to_audio
from rtty_decoder import RTTYDecoder, RTTYGenerator
from ft8_decoder import FT8Decoder, FT8Encoder
from fft_module import FFTAnalyzer, SpectrumAnalyzer, detect_pitch_fft, freq_to_musical
from virtual_sdr import VirtualSDR, IQToAudio
from audio_input import AudioFileReader


class AudioIO:
    """
    Audio Input/Output engine for Android (Termux).
    Uses termux-microphone-record for input and termux-media-player for output.
    """
    
    def __init__(self, sample_rate=8000):
        self.sample_rate = sample_rate
        self.recording_dir = Path.home() / '.digital-mode-decoder' / 'recordings'
        self.recording_dir.mkdir(parents=True, exist_ok=True)
        
        # Check Termux API availability
        self.has_termux_api = self._check_termux_api()
    
    def _check_termux_api(self):
        """Check if Termux API commands are available."""
        try:
            result = subprocess.run(['which', 'termux-microphone-record'], 
                                  capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def record(self, duration=5, filename=None):
        """
        Record audio from microphone.
        
        Args:
            duration: Recording duration in seconds
            filename: Output filename (auto-generated if None)
            
        Returns:
            Path to recorded WAV file
        """
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"rec_{timestamp}.wav"
        
        filepath = self.recording_dir / filename
        
        if self.has_termux_api:
            # Use Termux API
            cmd = ['termux-microphone-record', '-l', str(duration), '-f', str(filepath)]
            try:
                subprocess.run(cmd, timeout=duration + 5)
                return str(filepath) if filepath.exists() else None
            except Exception as e:
                print(f"Recording error: {e}")
                return None
        else:
            # Fallback: generate test signal
            print("Termux API not available, generating test signal...")
            return self._generate_test_recording(duration, str(filepath))
    
    def _generate_test_recording(self, duration, filepath):
        """Generate a test recording (for systems without mic access)."""
        samples = []
        n = int(self.sample_rate * duration)
        
        # Generate a tone with some variation
        for i in range(n):
            t = i / self.sample_rate
            # Mix of frequencies
            sample = 0.5 * math.sin(2 * math.pi * 700 * t)
            # Add some variation
            sample += 0.3 * math.sin(2 * math.pi * 880 * t * (1 + 0.1 * math.sin(0.5 * t)))
            samples.append(sample)
        
        self.save_wav(samples, filepath)
        return filepath
    
    def play(self, filepath):
        """
        Play audio file.
        
        Args:
            filepath: Path to audio file
            
        Returns:
            True if successful
        """
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return False
        
        if self.has_termux_api:
            # Use Termux media player
            cmd = ['termux-media-player', 'play', str(filepath)]
            try:
                subprocess.Popen(cmd)
                return True
            except Exception as e:
                print(f"Playback error: {e}")
                return False
        else:
            print(f"Would play: {filepath}")
            return True
    
    def stop_playback(self):
        """Stop current playback."""
        if self.has_termux_api:
            try:
                subprocess.run(['termux-media-player', 'stop'], timeout=5)
            except:
                pass
    
    def save_wav(self, samples, filepath):
        """
        Save audio samples to WAV file.
        
        Args:
            samples: List of float samples (-1.0 to 1.0)
            filepath: Output path
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with wave.open(str(filepath), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            
            # Convert to 16-bit integers
            int_samples = []
            for s in samples:
                s = max(-1.0, min(1.0, s))
                int_samples.append(int(s * 32767))
            
            raw_data = struct.pack(f'<{len(int_samples)}h', *int_samples)
            wf.writeframes(raw_data)
    
    def load_wav(self, filepath):
        """
        Load WAV file.
        
        Args:
            filepath: Path to WAV file
            
        Returns:
            Tuple of (samples, sample_rate)
        """
        with wave.open(str(filepath), 'rb') as wf:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            sample_width = wf.getsampwidth()
            
            raw_data = wf.readframes(n_frames)
        
        # Convert based on sample width
        if sample_width == 2:
            n_samples = len(raw_data) // 2
            int_samples = struct.unpack(f'<{n_samples}h', raw_data)
            samples = [s / 32768.0 for s in int_samples]
        elif sample_width == 1:
            samples = [((b - 128) / 128.0) for b in raw_data]
        else:
            raise ValueError(f"Unsupported sample width: {sample_width}")
        
        return samples, sample_rate
    
    def generate_tone(self, freq, duration, amplitude=0.8):
        """Generate a pure tone."""
        n = int(self.sample_rate * duration)
        samples = []
        for i in range(n):
            t = i / self.sample_rate
            samples.append(amplitude * math.sin(2 * math.pi * freq * t))
        return samples
    
    def generate_morse(self, text, wpm=15, freq=700):
        """Generate Morse code audio from text."""
        # Convert text to Morse code
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
        
        morse = ''
        for char in text.upper():
            if char in text_to_morse:
                morse += text_to_morse[char] + ' '
        
        return morse_to_audio(morse.strip(), wpm=wpm, freq=freq, sample_rate=self.sample_rate)
    
    def generate_noise(self, duration, amplitude=0.1):
        """Generate white noise."""
        import random
        n = int(self.sample_rate * duration)
        return [random.uniform(-amplitude, amplitude) for _ in range(n)]


class SpectrumDisplay:
    """ASCII spectrum display for terminal."""
    
    def __init__(self, width=60, height=10):
        self.width = width
        self.height = height
        self.bins = [0.0] * width
        self.min_db = -80
        self.max_db = 0
    
    def update(self, magnitudes):
        """Update with new dB values."""
        if not magnitudes:
            return
        step = len(magnitudes) / self.width
        for i in range(self.width):
            idx = int(i * step)
            if idx < len(magnitudes):
                self.bins[i] = magnitudes[idx]
        if self.bins:
            self.max_db = max(self.bins) if max(self.bins) > self.min_db else self.min_db + 10
    
    def render(self):
        """Render as ASCII bars."""
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


class DigitalModeApp:
    """Main application integrating all components."""
    
    def __init__(self):
        self.sample_rate = 8000
        self.mode = 'cw'
        
        # Audio I/O
        self.audio = AudioIO(self.sample_rate)
        
        # Decoders
        self.cw_decoder = CWDecoder(sample_rate=self.sample_rate, tone_freq=700)
        self.rtty_decoder = RTTYDecoder(sample_rate=self.sample_rate)
        self.ft8_decoder = FT8Decoder(sample_rate=self.sample_rate)
        
        # Spectrum analyzer
        self.spectrum_analyzer = SpectrumAnalyzer(fft_size=1024, sample_rate=self.sample_rate)
        self.spectrum_display = SpectrumDisplay(60, 10)
        
        # VirtualSDR
        self.sdr = VirtualSDR(sample_rate=48000)
        self.iq_converter = IQToAudio(sample_rate=48000, audio_rate=self.sample_rate)
        
        # State
        self.decoded_text = ''
        self.last_pitch = None
        self.last_spectrum = None
    
    def decode_file(self, filepath):
        """Decode audio from file."""
        samples, rate = self.audio.load_wav(filepath)
        self.sample_rate = rate
        return self._decode(samples)
    
    def decode_samples(self, samples):
        """Decode audio samples."""
        return self._decode(samples)
    
    def _decode(self, samples):
        """Internal decode with spectrum analysis."""
        # Spectrum analysis
        spectrum_data = self.spectrum_analyzer.process(samples)
        self.spectrum_display.update(spectrum_data['spectrum'])
        self.last_spectrum = spectrum_data
        
        # Pitch detection
        self.last_pitch = detect_pitch_fft(samples, self.sample_rate)
        
        # Decode based on mode
        if self.mode == 'cw':
            result = self.cw_decoder.decode_block(samples)
            self.decoded_text += result
            return result
        elif self.mode == 'rtty':
            result = self.rtty_decoder.process_samples(samples)
            self.decoded_text += result
            return result
        elif self.mode == 'ft8':
            messages = self.ft8_decoder.decode_audio_samples(samples)
            result = '\n'.join([str(m) for m in messages])
            self.decoded_text += result
            return result
        return ''
    
    def record_and_decode(self, duration=5):
        """Record from mic and decode."""
        filepath = self.audio.record(duration)
        if filepath:
            return self.decode_file(filepath)
        return ''
    
    def decode_sdr(self, duration=2.0, signal_type=None):
        """Decode from VirtualSDR."""
        num_samples = int(48000 * duration)
        
        if signal_type == 'cw' or (signal_type is None and self.mode == 'cw'):
            iq = self.sdr.read_samples_morse(num_samples, '... --- ...')
        elif signal_type == 'rtty' or (signal_type is None and self.mode == 'rtty'):
            iq = self.sdr.read_samples_rtty(num_samples, 'CQ')
        elif signal_type == 'ft8' or (signal_type is None and self.mode == 'ft8'):
            self.sdr.set_ft8_symbols(list(range(8)) * 6)
            iq = self.sdr.read_samples_ft8(num_samples)
        else:
            iq = self.sdr.read_samples(num_samples)
        
        audio = self.iq_converter.convert(iq)
        return self._decode(audio)
    
    def generate_and_play(self, text='SOS', freq=700):
        """Generate Morse and play it."""
        samples = self.audio.generate_morse(text, wpm=15, freq=freq)
        filepath = self.audio.recording_dir / 'playback.wav'
        self.audio.save_wav(samples, str(filepath))
        self.audio.play(str(filepath))
        return samples
    
    def generate_tone_and_play(self, freq=440, duration=1.0):
        """Generate tone and play it."""
        samples = self.audio.generate_tone(freq, duration)
        filepath = self.audio.recording_dir / 'tone.wav'
        self.audio.save_wav(samples, str(filepath))
        self.audio.play(str(filepath))
        return samples
    
    def set_mode(self, mode):
        """Set decoder mode."""
        if mode in ['cw', 'rtty', 'ft8', 'auto']:
            self.mode = mode
            self.cw_decoder = CWDecoder(sample_rate=self.sample_rate, tone_freq=700)
            return True
        return False
    
    def set_frequency(self, freq):
        """Set CW tone frequency."""
        self.cw_decoder.tone_freq = freq
    
    def set_wpm(self, wpm):
        """Set CW speed."""
        self.cw_decoder.unit_ms = 1200.0 / wpm
    
    def clear(self):
        """Clear decoded text."""
        self.decoded_text = ''
        self.cw_decoder.reset()
        self.rtty_decoder.reset()
    
    def get_pitch_str(self):
        """Get pitch as string."""
        if self.last_pitch:
            return freq_to_musical(self.last_pitch)
        return None


def print_banner():
    """Print app banner."""
    print('\033[2J\033[H')
    print('╔' + '═' * 58 + '╗')
    print('║' + ' DIGITAL MODE DECODER '.center(58) + '║')
    print('║' + ' CW • FT8 • RTTY with Audio I/O '.center(58) + '║')
    print('╚' + '═' * 58 + '╝')
    print()


def print_help():
    """Print help."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║ COMMANDS                                                     ║
╠══════════════════════════════════════════════════════════════╣
║ DECODE                                                       ║
║   file <path>        Decode audio file (WAV)                 ║
║   mic [seconds]      Record from mic and decode              ║
║   sdr [cw|rtty|ft8]  Decode from VirtualSDR                  ║
║                                                               ║
║ AUDIO OUTPUT                                                  ║
║   play <text>        Generate Morse and play                 ║
║   tone <freq> [sec]  Generate tone and play                  ║
║   stop               Stop playback                           ║
║                                                               ║
║ CONFIGURE                                                    ║
║   mode <cw|rtty|ft8> Set decoder mode                         ║
║   freq <hz>          Set CW frequency (default: 700)         ║
║   wpm <number>       Set CW speed (default: 15)              ║
║   noise <0-1>        Set SDR noise level                     ║
║                                                               ║
║ VIEW                                                         ║
║   spectrum           Show spectrum analysis                   ║
║   pitch              Show detected pitch                      ║
║   history            Show decode history                      ║
║   clear              Clear decoded text                       ║
║                                                               ║
║ SYSTEM                                                       ║
║   save <path>        Save decoded text to file                ║
║   demo               Run demo sequence                        ║
║   help               Show this help                           ║
║   quit               Exit                                     ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_spectrum(spectrum_display):
    """Print spectrum display."""
    lines = spectrum_display.render()
    print('\n╔══════════════════════════════════════════════════════════════╗')
    print('║ SPECTRUM                                                    ║')
    print('╠══════════════════════════════════════════════════════════════╣')
    for line in lines:
        print(f'║ {line:<56} ║')
    print('╠══════════════════════════════════════════════════════════════╣')
    print('║ 0Hz                                                  4kHz  ║')
    print('╚══════════════════════════════════════════════════════════════╝')


def run_demo(app):
    """Run demo sequence."""
    print('\n--- DEMO MODE ---\n')
    
    # 1. CW Demo
    print('1. CW (Morse) Demo')
    print('   Generating: ... --- ... (SOS)')
    samples = morse_to_audio('... --- ...', wpm=15, freq=700, sample_rate=8000)
    app.mode = 'cw'
    result = app.decode_samples(samples)
    print(f'   Decoded: {result}')
    print()
    
    # 2. Spectrum Demo
    print('2. Spectrum Analysis')
    print_spectrum(app.spectrum_display)
    print()
    
    # 3. Pitch Detection
    print('3. Pitch Detection')
    test_signal = [math.sin(2 * math.pi * 440 * i / 8000) for i in range(1024)]
    pitch = detect_pitch_fft(test_signal, 8000)
    if pitch:
        print(f'   Detected: {freq_to_musical(pitch)}')
    print()
    
    # 4. VirtualSDR Demo
    print('4. VirtualSDR Demo')
    result = app.decode_sdr(duration=1.0, signal_type='cw')
    print(f'   SDR Decode: {result}')
    print()
    
    # 5. Audio Output Demo
    print('5. Audio Output Demo')
    print('   Generating Morse tone...')
    samples = app.audio.generate_morse('SOS', wpm=15)
    filepath = app.audio.recording_dir / 'demo_sos.wav'
    app.audio.save_wav(samples, str(filepath))
    print(f'   Saved to: {filepath}')
    print()
    
    input('Press Enter to continue...')


def main():
    """Main entry point."""
    print_banner()
    
    app = DigitalModeApp()
    
    # Parse command line args
    if len(sys.argv) > 1:
        if sys.argv[1] == '--test':
            run_demo(app)
            return
        elif sys.argv[1] == '--file' and len(sys.argv) > 2:
            filepath = sys.argv[2]
            if os.path.exists(filepath):
                mode = sys.argv[3] if len(sys.argv) > 3 else 'cw'
                app.set_mode(mode)
                result = app.decode_file(filepath)
                print(f'Decoded ({mode}): {result}')
            else:
                print(f'File not found: {filepath}')
            return
        elif sys.argv[1] == '--help':
            print_help()
            return
    
    # Interactive mode
    print('Type "help" for commands, "quit" to exit.\n')
    print(f'Termux API: {"Available" if app.audio.has_termux_api else "Not available"}\n')
    
    while True:
        try:
            # Show status
            pitch_str = f' | Pitch: {app.get_pitch_str()}' if app.get_pitch_str() else ''
            cmd = input(f'[{app.mode.upper()}{pitch_str}] > ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nGoodbye!')
            break
        
        if not cmd:
            continue
        
        parts = cmd.split()
        action = parts[0].lower()
        
        # Quit
        if action in ['quit', 'exit', 'q']:
            print('Goodbye!')
            break
        
        # Help
        elif action == 'help':
            print_help()
        
        # Decode file
        elif action == 'file':
            if len(parts) < 2:
                print('Usage: file <path>')
                continue
            filepath = parts[1]
            if not os.path.exists(filepath):
                print(f'File not found: {filepath}')
                continue
            mode = parts[2] if len(parts) > 2 else app.mode
            app.set_mode(mode)
            result = app.decode_file(filepath)
            print(f'Decoded: {result}')
        
        # Record from mic
        elif action == 'mic':
            seconds = int(parts[1]) if len(parts) > 1 else 5
            print(f'Recording {seconds} seconds...')
            result = app.record_and_decode(seconds)
            print(f'Decoded: {result}')
        
        # VirtualSDR
        elif action == 'sdr':
            signal_type = parts[1] if len(parts) > 1 else app.mode
            print(f'Decoding from VirtualSDR ({signal_type})...')
            result = app.decode_sdr(duration=2.0, signal_type=signal_type)
            print(f'Decoded: {result}')
        
        # Play Morse
        elif action == 'play':
            text = ' '.join(parts[1:]) if len(parts) > 1 else 'SOS'
            print(f'Playing Morse: {text}')
            samples = app.generate_and_play(text)
            print(f'Generated {len(samples)} samples')
            # Decode it
            app.mode = 'cw'
            result = app.decode_samples(samples)
            print(f'Decoded: {result}')
        
        # Play tone
        elif action == 'tone':
            freq = int(parts[1]) if len(parts) > 1 else 440
            duration = float(parts[2]) if len(parts) > 2 else 1.0
            print(f'Playing {freq} Hz for {duration}s')
            app.generate_tone_and_play(freq, duration)
        
        # Stop playback
        elif action == 'stop':
            app.audio.stop_playback()
            print('Playback stopped')
        
        # Set mode
        elif action == 'mode':
            if len(parts) < 2:
                print(f'Current mode: {app.mode}')
                continue
            if app.set_mode(parts[1]):
                print(f'Mode set to: {parts[1]}')
            else:
                print('Invalid mode. Use: cw, rtty, ft8')
        
        # Set frequency
        elif action == 'freq':
            if len(parts) < 2:
                print(f'Current frequency: {app.cw_decoder.tone_freq} Hz')
                continue
            app.set_frequency(int(parts[1]))
            print(f'Frequency set to: {parts[1]} Hz')
        
        # Set WPM
        elif action == 'wpm':
            if len(parts) < 2:
                print(f'Current WPM: ~{int(1200 / app.cw_decoder.unit_ms)}')
                continue
            app.set_wpm(int(parts[1]))
            print(f'WPM set to: {parts[1]}')
        
        # Set noise
        elif action == 'noise':
            if len(parts) < 2:
                print(f'Current noise: {app.sdr.noise_level}')
                continue
            app.sdr.set_noise(float(parts[1]))
            print(f'Noise set to: {parts[1]}')
        
        # Show spectrum
        elif action == 'spectrum':
            print_spectrum(app.spectrum_display)
        
        # Show pitch
        elif action == 'pitch':
            pitch = app.get_pitch_str()
            if pitch:
                print(f'Detected pitch: {pitch}')
            else:
                print('No pitch detected')
        
        # Show history
        elif action == 'history':
            if app.decoded_text:
                print(f'\nDecode history:\n{app.decoded_text[-500:]}')
            else:
                print('No decode history')
        
        # Clear
        elif action == 'clear':
            app.clear()
            print('Cleared')
        
        # Save
        elif action == 'save':
            if len(parts) < 2:
                print('Usage: save <path>')
                continue
            with open(parts[1], 'w') as f:
                f.write(app.decoded_text)
            print(f'Saved to: {parts[1]}')
        
        # Demo
        elif action == 'demo':
            run_demo(app)
        
        else:
            print(f'Unknown command: {action}. Type "help" for commands.')


if __name__ == '__main__':
    main()
