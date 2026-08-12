#!/usr/bin/env python3
"""
Digital Mode Decoder Application
Decodes CW (Morse), FT8, and RTTY from audio input.

Usage:
    python decoder.py [options]

Modes:
    cw      - CW (Morse) decoder using Goertzel algorithm
    ft8     - FT8 decoder (requires wsjtx or ft8_lib)
    rtty    - RTTY decoder using zero-crossing detection
    auto    - Auto-detect mode

Examples:
    python decoder.py --mode cw --freq 700 --file audio.wav
    python decoder.py --mode rtty --file rtty_test.wav
    python decoder.py --mode ft8 --file ft8_recording.wav
    python decoder.py --test --mode cw
"""
import argparse
import sys
import os
import time
import threading
import signal

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from goertzel import GoertzelFilter, ToneDetector
from cw_decoder import CWDecoder, morse_to_audio
from rtty_decoder import RTTYDecoder, RTTYGenerator
from ft8_decoder import FT8Decoder, FT8Encoder
from audio_input import AudioFileReader, MicrophoneInput
from media_recorder import AndroidMediaRecorder, AudioRecorderWithDecoder
from virtual_sdr import VirtualSDR, SDRSource, IQToAudio
from fft_module import SpectrumAnalyzer, detect_pitch_fft, freq_to_musical


class DigitalModeDecoder:
    """
    Main decoder application combining all modes.
    """
    
    def __init__(self, mode='cw', sample_rate=8000):
        """
        Initialize decoder.
        
        Args:
            mode: Decoder mode ('cw', 'ft8', 'rtty', 'auto')
            sample_rate: Audio sample rate (Hz)
        """
        self.mode = mode
        self.sample_rate = sample_rate
        
        # Initialize decoders
        self.cw_decoder = CWDecoder(sample_rate=sample_rate, tone_freq=700)
        self.rtty_decoder = RTTYDecoder(sample_rate=sample_rate)
        self.ft8_decoder = FT8Decoder(sample_rate=sample_rate)
        
        # Audio reader
        self.audio_reader = AudioFileReader()
        
        # Virtual SDR for testing
        self.sdr = VirtualSDR(sample_rate=48000)
        self.iq_converter = IQToAudio(sample_rate=48000, audio_rate=sample_rate)
        
        # Spectrum analyzer
        self.spectrum = SpectrumAnalyzer(fft_size=1024, sample_rate=sample_rate)
        
        # State
        self.running = False
        self.decoded_text = ''
        self.callback = None
        self.spectrum_callback = None
    
    def set_callback(self, callback):
        """Set callback function for decoded output."""
        self.callback = callback
    
    def decode_file(self, filepath):
        """
        Decode audio from a file.
        
        Args:
            filepath: Path to audio file
            
        Returns:
            Decoded text
        """
        print(f"Decoding file: {filepath}")
        
        try:
            samples, sample_rate = self.audio_reader.read_wav(filepath)
            self.sample_rate = sample_rate
            
            # Update decoders with new sample rate
            self.cw_decoder = CWDecoder(sample_rate=sample_rate, tone_freq=700)
            self.rtty_decoder = RTTYDecoder(sample_rate=sample_rate)
            self.ft8_decoder = FT8Decoder(sample_rate=sample_rate)
            
            # Decode based on mode
            if self.mode == 'cw':
                return self._decode_cw(samples)
            elif self.mode == 'rtty':
                return self._decode_rtty(samples)
            elif self.mode == 'ft8':
                return self._decode_ft8_file(filepath)
            elif self.mode == 'auto':
                return self._auto_decode(samples, sample_rate)
            else:
                print(f"Unknown mode: {self.mode}")
                return ''
        
        except Exception as e:
            print(f"Error decoding file: {e}")
            return ''
    
    def decode_from_sdr(self, duration=2.0, morse_sequence=None, rtty_text=None):
        """
        Decode from VirtualSDR.
        
        Args:
            duration: Duration in seconds
            morse_sequence: Morse code to generate (CW mode)
            rtty_text: Text to generate (RTTY mode)
            
        Returns:
            Decoded text
        """
        num_samples = int(48000 * duration)
        
        # Generate IQ samples based on mode
        if self.mode == 'cw' and morse_sequence:
            iq_samples = self.sdr.read_samples_morse(num_samples, morse_sequence)
        elif self.mode == 'rtty' and rtty_text:
            iq_samples = self.sdr.read_samples_rtty(num_samples, rtty_text)
        elif self.mode == 'ft8':
            # Generate FT8 test pattern
            symbols = list(range(8)) * 6  # 48 symbols
            self.sdr.set_ft8_symbols(symbols)
            iq_samples = self.sdr.read_samples_ft8(num_samples)
        else:
            iq_samples = self.sdr.read_samples(num_samples)
        
        # Convert to audio
        audio_samples = self.iq_converter.convert(iq_samples)
        
        # Decode
        if self.mode == 'cw':
            return self._decode_cw(audio_samples)
        elif self.mode == 'rtty':
            return self._decode_rtty(audio_samples)
        elif self.mode == 'ft8':
            return self._decode_ft8_samples(audio_samples)
        else:
            return self._auto_decode(audio_samples, self.sample_rate)
    
    def _decode_cw(self, samples):
        """Decode CW from samples."""
        print("Decoding CW (Morse)...")
        
        # Process in chunks
        chunk_size = 1024
        decoded = []
        
        for i in range(0, len(samples), chunk_size):
            chunk = samples[i:i + chunk_size]
            result = self.cw_decoder.process_samples(chunk)
            decoded.extend(result)
            
            # Check for character/word gaps
            char = self.cw_decoder.check_character_gap()
            if char:
                decoded.append(char)
        
        self.decoded_text = ''.join(decoded)
        return self.decoded_text
    
    def _decode_rtty(self, samples):
        """Decode RTTY from samples."""
        print("Decoding RTTY...")
        
        self.decoded_text = self.rtty_decoder.process_samples(samples)
        return self.decoded_text
    
    def _decode_ft8_file(self, filepath):
        """Decode FT8 from file."""
        print("Decoding FT8...")
        
        messages = self.ft8_decoder.decode_audio_file(filepath)
        
        decoded = []
        for msg in messages:
            decoded.append(msg.get('message', str(msg)))
        
        self.decoded_text = '\n'.join(decoded)
        return self.decoded_text
    
    def _decode_ft8_samples(self, samples):
        """Decode FT8 from audio samples."""
        print("Decoding FT8...")
        
        messages = self.ft8_decoder.decode_audio_samples(samples)
        
        decoded = []
        for msg in messages:
            if isinstance(msg, dict):
                decoded.append(msg.get('message', str(msg)))
            else:
                decoded.append(str(msg))
        
        self.decoded_text = '\n'.join(decoded) if decoded else ''
        return self.decoded_text
    
    def process_audio_with_spectrum(self, samples):
        """
        Process audio samples with spectrum analysis.
        
        Args:
            samples: Audio samples
            
        Returns:
            Dict with 'decoded', 'spectrum', and 'pitch'
        """
        # Get spectrum data
        spectrum_data = self.spectrum.process(samples)
        
        # Detect pitch
        pitch = detect_pitch_fft(samples, self.sample_rate)
        
        # Decode based on mode
        if self.mode == 'cw':
            decoded = self._decode_cw(samples)
        elif self.mode == 'rtty':
            decoded = self._decode_rtty(samples)
        elif self.mode == 'ft8':
            decoded = self._decode_ft8_samples(samples)
        else:
            decoded = ''
        
        # Callback for spectrum update
        if self.spectrum_callback:
            self.spectrum_callback(spectrum_data['spectrum'])
        
        return {
            'decoded': decoded,
            'spectrum': spectrum_data,
            'pitch': pitch
        }
    
    def _auto_decode(self, samples, sample_rate):
        """Attempt to auto-detect and decode signal."""
        print("Auto-detecting signal type...")
        
        # Analyze signal characteristics
        signal_type = self._analyze_signal(samples, sample_rate)
        print(f"Detected signal type: {signal_type}")
        
        if signal_type == 'cw':
            return self._decode_cw(samples)
        elif signal_type == 'rtty':
            return self._decode_rtty(samples)
        elif signal_type == 'ft8':
            return self._decode_ft8_samples(samples)
        else:
            print("Could not determine signal type")
            return ''
    
    def _analyze_signal(self, samples, sample_rate):
        """
        Analyze signal to determine type.
        
        Returns:
            'cw', 'rtty', 'ft8', or 'unknown'
        """
        # Simple analysis based on frequency content
        
        # Check for single tone (CW)
        tone_detector = ToneDetector(700, sample_rate)
        tone_present = False
        
        for i in range(0, min(len(samples), sample_rate), 1024):
            chunk = samples[i:i+1024]
            if len(chunk) < 1024:
                break
            if tone_detector.detect(chunk):
                tone_present = True
                break
        
        if tone_present:
            # Check if it's on/off keyed
            transitions = 0
            prev_sample = 0
            for s in samples[:min(len(samples), sample_rate)]:
                if (prev_sample >= 0.3 and s < 0.3) or (prev_sample < 0.3 and s >= 0.3):
                    transitions += 1
                prev_sample = s
            
            if transitions > 5:
                return 'cw'
        
        # Check for FSK (RTTY)
        # Look for two distinct frequencies
        freq_bins = {}
        block_size = 2048
        
        for i in range(0, len(samples) - block_size, block_size // 2):
            block = samples[i:i + block_size]
            
            # Simple frequency estimation
            crossings = 0
            for j in range(1, len(block)):
                if (block[j-1] >= 0 and block[j] < 0) or \
                   (block[j-1] < 0 and block[j] >= 0):
                    crossings += 1
            
            freq = crossings * sample_rate / (2 * block_size)
            freq_bins[int(freq / 50) * 50] = freq_bins.get(int(freq / 50) * 50, 0) + 1
        
        if len(freq_bins) >= 2:
            sorted_bins = sorted(freq_bins.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_bins) >= 2:
                f1 = sorted_bins[0][0]
                f2 = sorted_bins[1][0]
                shift = abs(f1 - f2)
                
                if 100 < shift < 500:
                    return 'rtty'
        
        return 'unknown'
    
    def _decode_ft8_samples(self, samples):
        """Decode FT8 from samples."""
        return self.ft8_decoder.decode_audio_samples(samples)
    
    def live_decode(self, use_microphone=False, device_index=None):
        """
        Run live decoding from microphone or test signal.
        
        Args:
            use_microphone: Use microphone input
            device_index: Microphone device index
        """
        self.running = True
        
        if use_microphone:
            self._live_decode_mic(device_index)
        else:
            self._live_decode_test()
    
    def _live_decode_mic(self, device_index):
        """Live decode from microphone."""
        try:
            mic = MicrophoneInput(sample_rate=self.sample_rate)
            mic.open(device_index)
            
            print("Live decoding from microphone... Press Ctrl+C to stop")
            
            while self.running:
                chunk = mic.read_chunk()
                
                if self.mode == 'cw':
                    result = self.cw_decoder.process_samples(chunk)
                    if result:
                        for char in result:
                            self._output_char(char)
                    
                    char = self.cw_decoder.check_character_gap()
                    if char:
                        self._output_char(char)
                
                elif self.mode == 'rtty':
                    text = self.rtty_decoder.process_samples(chunk)
                    if text:
                        self._output_text(text)
                
                time.sleep(0.01)
            
            mic.close()
        
        except Exception as e:
            print(f"Microphone error: {e}")
    
    def _live_decode_test(self):
        """Live decode with test signals."""
        print("Running test decode...")
        
        # Generate SOS
        print("\nGenerating SOS signal...")
        sos_samples = morse_to_audio('... --- ...', wpm=15)
        
        print("Decoding...")
        result = self._decode_cw(sos_samples)
        
        print(f"\nResult: {result}")
    
    def _output_char(self, char):
        """Output a decoded character."""
        self.decoded_text += char
        print(char, end='', flush=True)
        
        if self.callback:
            self.callback(char)
    
    def _output_text(self, text):
        """Output decoded text."""
        self.decoded_text += text
        print(text, end='', flush=True)
        
        if self.callback:
            self.callback(text)
    
    def stop(self):
        """Stop live decoding."""
        self.running = False
    
    def get_decoded_text(self):
        """Get accumulated decoded text."""
        return self.decoded_text
    
    def clear(self):
        """Clear decoded text."""
        self.decoded_text = ''
        self.cw_decoder.reset()
        self.rtty_decoder.reset()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Digital Mode Decoder - CW/FT8/RTTY',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --mode cw --file audio.wav
  %(prog)s --mode rtty --file rtty.wav
  %(prog)s --mode ft8 --file ft8.wav
  %(prog)s --test --mode cw
  %(prog)s --live --mode cw
        """
    )
    
    parser.add_argument('--mode', choices=['cw', 'ft8', 'rtty', 'auto'],
                        default='cw', help='Decoder mode (default: cw)')
    parser.add_argument('--file', '-f', help='Input audio file (WAV)')
    parser.add_argument('--test', action='store_true', help='Run test decode')
    parser.add_argument('--live', action='store_true', help='Live decode from microphone')
    parser.add_argument('--device', type=int, help='Microphone device index')
    parser.add_argument('--freq', type=int, default=700, help='Tone frequency for CW (Hz)')
    parser.add_argument('--rate', type=int, default=8000, help='Sample rate (Hz)')
    parser.add_argument('--wpm', type=int, default=15, help='CW speed (WPM)')
    parser.add_argument('--output', '-o', help='Output file for decoded text')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Create decoder
    decoder = DigitalModeDecoder(mode=args.mode, sample_rate=args.rate)
    
    # Set CW parameters
    if args.mode == 'cw':
        decoder.cw_decoder = CWDecoder(
            sample_rate=args.rate,
            tone_freq=args.freq,
            wpm=args.wpm
        )
    
    print(f"Digital Mode Decoder - {args.mode.upper()} mode")
    print("=" * 50)
    
    if args.test:
        # Run test
        decoder.live_decode(use_microphone=False)
    
    elif args.file:
        # Decode file
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        
        result = decoder.decode_file(args.file)
        
        print("\n" + "=" * 50)
        print("Decoded output:")
        print(result)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(result)
            print(f"\nSaved to: {args.output}")
    
    elif args.live:
        # Live decode
        try:
            decoder.live_decode(
                use_microphone=True,
                device_index=args.device
            )
        except KeyboardInterrupt:
            print("\n\nStopped.")
    
    else:
        # Interactive mode
        run_interactive(decoder)


def run_interactive(decoder):
    """Run interactive decoder session."""
    # Initialize Android recorder
    recorder = AndroidMediaRecorder()
    audio_decoder = AudioRecorderWithDecoder(decoder)
    
    print("\nInteractive mode")
    print("Commands:")
    print("  file <path>      - Decode audio file")
    print("  test             - Run test decode")
    print("  mode <mode>      - Change mode (cw/ft8/rtty/auto)")
    print("  freq <hz>        - Set CW frequency")
    print("  wpm <wpm>        - Set CW speed")
    print("  sdr [morse|rtty] - Decode from VirtualSDR")
    print("  sdr noise <0-1>  - Set SDR noise level")
    print("  record <sec>     - Record from Android mic and decode")
    print("  live             - Live monitoring mode")
    print("  list             - List recordings")
    print("  micinfo          - Show microphone info")
    print("  clear            - Clear decoded text")
    print("  help             - Show this help")
    print("  quit             - Exit")
    print(f"\n  Android Mic API: {'Available' if recorder.available else 'Not available'}")
    print()
    
    while True:
        try:
            cmd = input("decoder> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if not cmd:
            continue
        
        parts = cmd.split()
        action = parts[0].lower()
        
        if action == 'quit' or action == 'exit':
            break
        
        elif action == 'help':
            print("Commands:")
            print("  file <path>      - Decode audio file")
            print("  test             - Run test decode")
            print("  mode <mode>      - Change mode (cw/ft8/rtty/auto)")
            print("  freq <hz>        - Set CW frequency")
            print("  wpm <wpm>        - Set CW speed")
            print("  sdr [morse|rtty] - Decode from VirtualSDR")
            print("  sdr noise <0-1>  - Set SDR noise level")
            print("  record <sec>     - Record from Android mic and decode")
            print("  live             - Live monitoring mode")
            print("  list             - List recordings")
            print("  micinfo          - Show microphone info")
            print("  clear            - Clear decoded text")
            print("  quit             - Exit")
        
        elif action == 'file':
            if len(parts) < 2:
                print("Usage: file <path>")
                continue
            
            filepath = parts[1]
            if not os.path.exists(filepath):
                print(f"File not found: {filepath}")
                continue
            
            result = decoder.decode_file(filepath)
            print(f"\nDecoded: {result}\n")
        
        elif action == 'test':
            decoder.live_decode(use_microphone=False)
        
        elif action == 'mode':
            if len(parts) < 2:
                print(f"Current mode: {decoder.mode}")
                continue
            
            new_mode = parts[1].lower()
            if new_mode in ['cw', 'ft8', 'rtty', 'auto']:
                decoder.mode = new_mode
                print(f"Mode changed to: {new_mode}")
            else:
                print(f"Invalid mode: {new_mode}")
        
        elif action == 'freq':
            if len(parts) < 2:
                print("Usage: freq <hz>")
                continue
            
            try:
                freq = int(parts[1])
                decoder.cw_decoder.tone_freq = freq
                decoder.cw_decoder.detector.freq = freq
                print(f"Frequency set to: {freq} Hz")
            except ValueError:
                print("Invalid frequency")
        
        elif action == 'wpm':
            if len(parts) < 2:
                print("Usage: wpm <wpm>")
                continue
            
            try:
                wpm = int(parts[1])
                decoder.cw_decoder.unit_ms = 1200.0 / wpm
                print(f"WPM set to: {wpm}")
            except ValueError:
                print("Invalid WPM")
        
        elif action == 'sdr':
            if len(parts) < 2:
                # Show SDR status
                print(f"VirtualSDR: sample_rate={decoder.sdr.sample_rate}, "
                      f"freq={decoder.sdr.signal频率}Hz, noise={decoder.sdr.noise_level}")
                print("Usage: sdr morse [sequence] | sdr rtty [text] | sdr ft8 | sdr noise <0-1>")
                continue
            
            sdr_cmd = parts[1].lower()
            
            if sdr_cmd == 'morse':
                sequence = ' '.join(parts[2:]) if len(parts) > 2 else '... --- ...'
                print(f"Decoding CW from VirtualSDR: {sequence}")
                result = decoder.decode_from_sdr(duration=3.0, morse_sequence=sequence)
                print(f"Decoded: {result}")
            
            elif sdr_cmd == 'rtty':
                text = ' '.join(parts[2:]) if len(parts) > 2 else 'CQ'
                print(f"Decoding RTTY from VirtualSDR: {text}")
                decoder.mode = 'rtty'
                result = decoder.decode_from_sdr(duration=2.0, rtty_text=text)
                print(f"Decoded: {result}")
            
            elif sdr_cmd == 'ft8':
                print("Decoding FT8 from VirtualSDR...")
                decoder.mode = 'ft8'
                result = decoder.decode_from_sdr(duration=2.0)
                print(f"Decoded: {result}")
            
            elif sdr_cmd == 'noise':
                if len(parts) > 2:
                    try:
                        noise = float(parts[2])
                        decoder.sdr.set_noise(noise)
                        print(f"SDR noise set to: {noise}")
                    except ValueError:
                        print("Invalid noise level (0.0-1.0)")
                else:
                    print(f"Current noise: {decoder.sdr.noise_level}")
            
            else:
                print(f"Unknown SDR command: {sdr_cmd}")
                print("Usage: sdr morse | sdr rtty | sdr ft8 | sdr noise")
        
        elif action == 'clear':
            decoder.clear()
            print("Cleared.")
        
        else:
            print(f"Unknown command: {action}")


if __name__ == '__main__':
    main()
