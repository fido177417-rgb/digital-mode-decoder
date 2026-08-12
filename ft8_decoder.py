"""
FT8 Decoder Module
FT8 is a digital mode designed for weak-signal communications.
This module provides:
1. Wrapper for external FT8 decoders (wsjt-x, wsjtx, etc.)
2. Simplified FT8 encoder for testing
3. Basic spectral analysis for FT8 signal detection

FT8 specifications:
- 15-second transmit/receive periods
- 8-FSK modulation (8 tones)
- 50 symbols per period (6.25s message)
- Tone spacing: 6.25 Hz
- Total bandwidth: ~50 Hz
- LDPC error correction (rate 1/2)
"""
import math
import struct
import subprocess
import os
from pathlib import Path
from collections import deque


# FT8 Constants
FT8_PROTOCOL_VERSION = 10
FT8_TONE_SPACING = 6.25  # Hz
FT8_SYMBOL_DURATION = 0.625  # seconds (1/1.6)
FT8_NN = 79  # Number of symbols
FT8_KK = 32  # Message length (77 bits / 2 = 38.5, rounded)
FT8_NN = 50  # Actually 50 symbols per message

# 8-FSK tones (relative to base frequency)
FT8_TONES = [0, 1, 2, 3, 4, 5, 6, 7]

# Standard FT8 frequencies (MHz)
FT8_FREQUENCIES = {
    '160m': 1.840,
    '80m': 3.573,
    '60m': 5.357,
    '40m': 7.074,
    '30m': 10.136,
    '20m': 14.074,
    '17m': 18.100,
    '15m': 21.074,
    '12m': 24.915,
    '10m': 28.074,
    '6m': 50.313,
    '4m': 70.100,
    '2m': 144.170,
    '222': 222.000,
    '432': 432.000,
    '1296': 1296.100,
}


class FT8Decoder:
    """
    FT8 decoder using external tools or simplified processing.
    """
    
    def __init__(self, sample_rate=12000):
        """
        Initialize FT8 decoder.
        
        Args:
            sample_rate: Audio sample rate (Hz), FT8 uses 12000 Hz typically
        """
        self.sample_rate = sample_rate
        
        # External decoder paths
        self.wsjtx_path = self._find_wsjtx()
        self.ft8_lib_path = self._find_ft8_lib()
        
        # Buffer for 15-second periods
        self.period_samples = []
        self.period_duration = 15.0  # seconds
        self.samples_per_period = int(sample_rate * self.period_duration)
        
        # Decoded messages
        self.decoded_messages = []
        self.message_history = deque(maxlen=100)
        
        # Signal parameters
        self.base_freq = 1500  # Hz, audio base frequency for FT8
        self.tone_spacing = FT8_TONE_SPACING
    
    def _find_wsjtx(self):
        """Find wsjtx executable."""
        possible_paths = [
            '/usr/bin/wsjtx',
            '/usr/local/bin/wsjtx',
            os.path.expanduser('~/wsjtx/bin/wsjtx'),
            'wsjtx',  # Try PATH
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _find_ft8_lib(self):
        """Find ft8_lib shared library."""
        possible_paths = [
            '/usr/lib/libft8.so',
            '/usr/local/lib/libft8.so',
            os.path.expanduser('~/ft8_lib/libft8.so'),
            'libft8.so',
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def decode_audio_file(self, filepath):
        """
        Decode FT8 from an audio file.
        
        Args:
            filepath: Path to WAV audio file
            
        Returns:
            List of decoded messages
        """
        # Try external decoder first
        if self.wsjtx_path:
            return self._decode_with_wsjtx(filepath)
        elif self.ft8_lib_path:
            return self._decode_with_ft8lib(filepath)
        else:
            return self._decode_simplified(filepath)
    
    def _decode_with_wsjtx(self, filepath):
        """Decode using wsjtx command line tool."""
        try:
            cmd = [self.wsjtx_path, '--decode', filepath]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return self._parse_wsjtx_output(result.stdout)
            else:
                print(f"wsjtx error: {result.stderr}")
                return []
        except Exception as e:
            print(f"wsjtx decode error: {e}")
            return []
    
    def _decode_with_ft8lib(self, filepath):
        """Decode using ft8_lib C library."""
        # This would require ctypes bindings to libft8
        # For now, return empty
        print("ft8_lib integration not yet implemented")
        return []
    
    def _decode_simplified(self, filepath):
        """
        Simplified FT8 decoder for basic message detection.
        This is a demonstration - real FT8 decoding requires LDPC.
        """
        try:
            import wave
            with wave.open(filepath, 'rb') as wf:
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                audio_data = wf.readframes(n_frames)
                
                # Convert to samples
                samples = struct.unpack(f'<{n_frames}h', audio_data)
                
                return self.decode_audio_samples(list(samples), sample_rate)
        except Exception as e:
            print(f"Simplified decode error: {e}")
            return []
    
    def decode_audio_samples(self, samples, sample_rate=None):
        """
        Decode FT8 from audio samples.
        
        Args:
            samples: Audio samples (16-bit signed integers)
            sample_rate: Sample rate (uses default if None)
            
        Returns:
            List of decoded messages
        """
        if sample_rate is None:
            sample_rate = self.sample_rate
        
        # Ensure we have enough samples for one period
        if len(samples) < self.samples_per_period:
            return []
        
        # Process the 15-second period
        messages = []
        
        # Detect FT8 signals using spectral analysis
        signals = self._detect_ft8_signals(samples, sample_rate)
        
        # Try to decode each detected signal
        for signal in signals:
            msg = self._decode_signal(signal, samples, sample_rate)
            if msg:
                messages.append(msg)
                self.message_history.append(msg)
        
        self.decoded_messages.extend(messages)
        return messages
    
    def _detect_ft8_signals(self, samples, sample_rate):
        """
        Detect FT8 signals using sliding FFT.
        
        Returns:
            List of detected signals (time, freq, strength)
        """
        signals = []
        
        # FT8 symbols are 0.625 seconds
        symbol_samples = int(sample_rate * FT8_SYMBOL_DURATION)
        
        # Check each possible start time
        for start in range(0, len(samples) - symbol_samples * 50, symbol_samples):
            window = samples[start:start + symbol_samples * 50]
            
            # Simple energy detection in FT8 band (1000-2000 Hz)
            energy = self._calculate_band_energy(window, sample_rate, 1000, 2000)
            
            if energy > 10000:  # Threshold
                # Estimate center frequency
                freq = self._estimate_ft8_frequency(window, sample_rate)
                signals.append({
                    'start': start,
                    'frequency': freq,
                    'energy': energy
                })
        
        return signals
    
    def _calculate_band_energy(self, samples, sample_rate, low_freq, high_freq):
        """Calculate energy in a frequency band using Goertzel."""
        energy = 0
        block_size = 1024
        
        for i in range(0, len(samples) - block_size, block_size // 2):
            block = samples[i:i + block_size]
            
            # Simple DFT in the band
            for freq in range(low_freq, high_freq, 25):
                energy += self._goertzel_magnitude(block, freq, sample_rate) ** 2
        
        return energy / (len(samples) // block_size)
    
    def _goertzel_magnitude(self, samples, target_freq, sample_rate):
        """Goertzel algorithm for single frequency."""
        n = len(samples)
        k = int(0.5 + n * target_freq / sample_rate)
        omega = 2.0 * math.pi * k / n
        
        s1 = 0.0
        s2 = 0.0
        
        coeff = 2.0 * math.cos(omega)
        
        for sample in samples:
            s1 = sample + coeff * s1 - s2
            s2 = s1 * coeff - s2 + sample
        
        real = s1 - s2 * math.cos(omega)
        imag = s2 * math.sin(omega)
        
        return math.sqrt(real * real + imag * imag)
    
    def _estimate_ft8_frequency(self, samples, sample_rate):
        """Estimate the center frequency of an FT8 signal."""
        # Find frequency with maximum energy
        max_energy = 0
        max_freq = 1500
        
        block_size = 2048
        for freq in range(1000, 2000, 10):
            energy = 0
            for i in range(0, len(samples) - block_size, block_size):
                block = samples[i:i + block_size]
                mag = self._goertzel_magnitude(block, freq, sample_rate)
                energy += mag
            
            if energy > max_energy:
                max_energy = energy
                max_freq = freq
        
        return max_freq
    
    def _decode_signal(self, signal, samples, sample_rate):
        """
        Attempt to decode an FT8 signal.
        This is a simplified version - real decoding uses LDPC.
        """
        # For now, return signal info as placeholder
        return {
            'time': signal['start'] / sample_rate,
            'frequency': signal['frequency'],
            'snr': signal['energy'] / 10000,  # Simplified
            'message': 'FT8 signal detected',
            'decoded': False  # Requires full LDPC decoding
        }
    
    def _parse_wsjtx_output(self, output):
        """Parse wsjtx decode output."""
        messages = []
        
        for line in output.strip().split('\n'):
            if not line:
                continue
            
            # wsjtx format: "HH MM DD Callsign Grid dB Hz"
            parts = line.split()
            if len(parts) >= 6:
                try:
                    msg = {
                        'time': f"{parts[0]}:{parts[1]}",
                        'date': parts[2],
                        'callsign': parts[3],
                        'grid': parts[4] if len(parts) > 4 else '',
                        'snr': int(parts[5]) if len(parts) > 5 else 0,
                        'frequency': int(parts[6]) if len(parts) > 6 else 0,
                        'message': line
                    }
                    messages.append(msg)
                except (ValueError, IndexError):
                    pass
        
        return messages
    
    def set_base_frequency(self, freq):
        """Set the audio base frequency for FT8."""
        self.base_freq = freq
    
    def clear_messages(self):
        """Clear decoded message history."""
        self.decoded_messages.clear()
        self.message_history.clear()


class FT8Encoder:
    """
    FT8 message encoder for testing.
    Encodes callsign + grid + report into FT8 format.
    """
    
    # FT8 message types
    TYPE_CQ = 0
    TYPE_CALL = 1
    TYPE_REPORT = 2
    TYPE_ACK = 3
    
    # Standard messages
    CQ_MSG = "CQ CQ CQ"
    
    def __init__(self, sample_rate=12000):
        self.sample_rate = sample_rate
        self.base_freq = 1500
    
    def encode_message(self, callsign, grid=None, message_type=TYPE_CQ):
        """
        Encode a message to FT8 symbols.
        
        Args:
            callsign: Station callsign
            grid: Maidenhead grid locator
            message_type: Type of message
            
        Returns:
            List of FT8 symbols (0-7)
        """
        # Simplified encoding - real FT8 uses 77-bit messages
        # This creates a placeholder symbol sequence
        
        symbols = []
        
        # Convert callsign to symbols (simplified)
        for char in callsign:
            # Simple character to 3-bit encoding
            if char.isalnum():
                val = ord(char) % 8
                symbols.append(val)
        
        # Add message type marker
        symbols.append(message_type)
        
        # Pad to 50 symbols
        while len(symbols) < 50:
            symbols.append(0)
        
        return symbols[:50]
    
    def symbols_to_audio(self, symbols, tone_spacing=None):
        """
        Convert FT8 symbols to audio samples.
        
        Args:
            symbols: List of FT8 symbols (0-7)
            tone_spacing: Frequency spacing between tones
            
        Returns:
            Audio samples
        """
        if tone_spacing is None:
            tone_spacing = self.tone_spacing
        
        samples = []
        samples_per_symbol = int(self.sample_rate * FT8_SYMBOL_DURATION)
        
        for symbol in symbols:
            # Calculate tone frequency
            freq = self.base_freq + (symbol * tone_spacing)
            
            # Generate tone
            for i in range(samples_per_symbol):
                t = i / self.sample_rate
                sample = 0.7 * math.sin(2 * math.pi * freq * t)
                
                # Apply raised cosine window at symbol boundaries
                if i < 100:
                    sample *= i / 100
                elif i > samples_per_symbol - 100:
                    sample *= (samples_per_symbol - i) / 100
                
                samples.append(sample)
        
        return samples
    
    def encode_cq(self, callsign, grid=None):
        """Encode a CQ call."""
        symbols = self.encode_message(callsign, grid, self.TYPE_CQ)
        return self.symbols_to_audio(symbols)
    
    def encode_call(self, target_call, my_call, my_grid=None):
        """Encode a call to another station."""
        # Simplified - just encode both callsigns
        symbols = []
        
        for char in target_call:
            if char.isalnum():
                symbols.append(ord(char) % 8)
        
        symbols.append(1)  # Type marker
        
        for char in my_call:
            if char.isalnum():
                symbols.append(ord(char) % 8)
        
        while len(symbols) < 50:
            symbols.append(0)
        
        return self.symbols_to_audio(symbols[:50])
    
    def encode_report(self, target_call, my_call, snr):
        """Encode a signal report."""
        symbols = []
        
        for char in target_call:
            if char.isalnum():
                symbols.append(ord(char) % 8)
        
        symbols.append(2)  # Type marker
        
        # Encode SNR as 3 symbols
        snr_val = max(-30, min(30, snr)) + 30
        symbols.append(snr_val // 8)
        symbols.append(snr_val % 8)
        
        for char in my_call:
            if char.isalnum():
                symbols.append(ord(char) % 8)
        
        while len(symbols) < 50:
            symbols.append(0)
        
        return self.symbols_to_audio(symbols[:50])


if __name__ == '__main__':
    print("FT8 Decoder/Encoder")
    print("=" * 50)
    
    # Test encoder
    encoder = FT8Encoder()
    print("\nEncoding CQ from W1AW...")
    audio = encoder.encode_cq("W1AW")
    print(f"Generated {len(audio)} samples ({len(audio)/12000:.2f} seconds)")
    
    # Test decoder initialization
    decoder = FT8Decoder()
    print("\nDecoder initialized")
    print(f"wsjtx available: {decoder.wsjtx_path is not None}")
    print(f"ft8_lib available: {decoder.ft8_lib_path is not None}")
    
    print("\nFT8 Frequencies:")
    for band, freq in FT8_FREQUENCIES.items():
        print(f"  {band:6s}: {freq:.3f} MHz")
