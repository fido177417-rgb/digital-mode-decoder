"""
Virtual SDR (Software Defined Radio) Simulator
Simulates SDR input for testing without hardware.
Provides IQ sample generation with fading, noise, and multiple signal types.
"""
import math
import random
import cmath
from collections import deque


class VirtualSDR:
    """
    Virtual SDR that simulates radio signals for testing.
    Generates IQ samples with configurable signal types.
    """
    
    def __init__(self, sample_rate=48000):
        """
        Initialize Virtual SDR.
        
        Args:
            sample_rate: Sample rate in Hz (default: 48000)
        """
        self.sample_rate = sample_rate
        self.phase = 0.0
        self.time_offset = 0.0
        
        # Signal parameters
        self.signal_freq = 600  # Hz (audio tone)
        self.signal_amplitude = 1.0
        self.noise_level = 0.2
        self.fade_rate = 0.5  # Hz
        
        # State for complex signals
        self.morse_state = 'off'
        self.morse_dot_duration = 0.1  # seconds
        self.morse_buffer = []
        
        # RTTY state
        self.rtty_bit_duration = 1.0 / 45.45  # 45.45 baud
        self.rtty_shift = 170  # Hz
        self.rtty_mark_freq = 1000
        self.rtty_space_freq = 830
        self.rtty_current_bit = 0
        
        # FT8 state
        self.ft8_symbol_duration = 0.625  # seconds
        self.ft8_tone_spacing = 6.25  # Hz
        self.ft8_base_freq = 1500  # Hz
        self.ft8_symbols = []
        self.ft8_symbol_index = 0
    
    def read_samples(self, num_samples):
        """
        Read IQ samples from virtual SDR.
        
        Args:
            num_samples: Number of samples to generate
            
        Returns:
            List of complex IQ samples
        """
        samples = []
        
        t_start = self.time_offset
        t_end = t_start + num_samples / self.sample_rate
        
        for i in range(num_samples):
            t = t_start + i / self.sample_rate
            
            # Generate base signal (600 Hz tone with fading)
            freq = self.signal_freq
            fade = 1.0 + 0.3 * math.sin(2 * math.pi * self.fade_rate * t)
            
            # IQ signal (complex exponential)
            angle = 2 * math.pi * freq * t + self.phase
            iq = complex(
                math.cos(angle) * fade * self.signal_amplitude,
                math.sin(angle) * fade * self.signal_amplitude
            )
            
            # Add noise
            if self.noise_level > 0:
                noise_real = random.gauss(0, self.noise_level)
                noise_imag = random.gauss(0, self.noise_level)
                iq += complex(noise_real, noise_imag)
            
            samples.append(iq)
        
        # Update phase for continuity
        self.phase += 2 * math.pi * self.signal_freq * num_samples / self.sample_rate
        self.phase %= 2 * math.pi
        self.time_offset = t_end
        
        return samples
    
    def read_samples_morse(self, num_samples, morse_sequence='... --- ...'):
        """
        Generate IQ samples with Morse code modulation.
        
        Args:
            num_samples: Number of samples to generate
            morse_sequence: Morse code to transmit
            
        Returns:
            List of complex IQ samples
        """
        samples = []
        samples_per_unit = int(self.sample_rate * self.morse_dot_duration)
        
        # Convert morse to on/off pattern
        pattern = self._morse_to_pattern(morse_sequence)
        
        sample_index = 0
        pattern_index = 0
        pattern_position = 0
        
        for i in range(num_samples):
            t = self.time_offset + i / self.sample_rate
            
            # Check if we're in a tone
            in_tone = False
            if pattern_index < len(pattern):
                element, duration = pattern[pattern_index]
                if element in ['.', '-']:
                    if pattern_position < duration * samples_per_unit:
                        in_tone = True
            
            # Generate signal
            if in_tone:
                angle = 2 * math.pi * self.signal_freq * t + self.phase
                fade = 1.0 + 0.1 * math.sin(2 * math.pi * 0.5 * t)
                iq = complex(
                    math.cos(angle) * fade * self.signal_amplitude,
                    math.sin(angle) * fade * self.signal_amplitude
                )
            else:
                # Just noise
                iq = complex(
                    random.gauss(0, self.noise_level),
                    random.gauss(0, self.noise_level)
                )
            
            samples.append(iq)
            
            # Update pattern position
            pattern_position += 1
            if pattern_index < len(pattern):
                element, duration = pattern[pattern_index]
                if pattern_position >= duration * samples_per_unit:
                    pattern_index += 1
                    pattern_position = 0
        
        # Update phase
        self.phase += 2 * math.pi * self.signal_freq * num_samples / self.sample_rate
        self.phase %= 2 * math.pi
        self.time_offset += num_samples / self.sample_rate
        
        return samples
    
    def read_samples_rtty(self, num_samples, text='CQ'):
        """
        Generate IQ samples with RTTY (FSK) modulation.
        
        Args:
            num_samples: Number of samples
            text: Text to transmit
            
        Returns:
            List of complex IQ samples
        """
        samples = []
        
        # Generate RTTY bit pattern
        bits = self._text_to_rtty_bits(text)
        
        samples_per_bit = int(self.sample_rate * self.rtty_bit_duration)
        
        bit_index = 0
        bit_position = 0
        
        for i in range(num_samples):
            t = self.time_offset + i / self.sample_rate
            
            # Determine current frequency
            if bit_index < len(bits):
                if bits[bit_index] == 1:
                    freq = self.rtty_mark_freq
                else:
                    freq = self.rtty_space_freq
            else:
                freq = self.rtty_mark_freq  # Idle
            
            # Generate signal with fading
            fade = 1.0 + 0.2 * math.sin(2 * math.pi * 0.3 * t)
            angle = 2 * math.pi * freq * t + self.phase
            
            iq = complex(
                math.cos(angle) * fade * self.signal_amplitude,
                math.sin(angle) * fade * self.signal_amplitude
            )
            
            # Add noise
            if self.noise_level > 0:
                iq += complex(
                    random.gauss(0, self.noise_level),
                    random.gauss(0, self.noise_level)
                )
            
            samples.append(iq)
            
            # Update bit position
            bit_position += 1
            if bit_position >= samples_per_bit:
                bit_index += 1
                bit_position = 0
        
        # Update phase
        self.phase += 2 * math.pi * self.rtty_mark_freq * num_samples / self.sample_rate
        self.phase %= 2 * math.pi
        self.time_offset += num_samples / self.sample_rate
        
        return samples
    
    def read_samples_ft8(self, num_samples):
        """
        Generate IQ samples with FT8 (8-FSK) modulation.
        
        Args:
            num_samples: Number of samples
            
        Returns:
            List of complex IQ samples
        """
        samples = []
        
        samples_per_symbol = int(self.sample_rate * self.ft8_symbol_duration)
        
        symbol_index = 0
        symbol_position = 0
        
        for i in range(num_samples):
            t = self.time_offset + i / self.sample_rate
            
            # Get current FT8 symbol (0-7)
            if symbol_index < len(self.ft8_symbols):
                symbol = self.ft8_symbols[symbol_index]
            else:
                symbol = 0
            
            # Calculate tone frequency
            freq = self.ft8_base_freq + symbol * self.ft8_tone_spacing
            
            # Generate signal
            angle = 2 * math.pi * freq * t + self.phase
            
            # Raised cosine window at symbol boundaries
            window = 1.0
            if symbol_position < 100:
                window = symbol_position / 100
            elif symbol_position > samples_per_symbol - 100:
                window = (samples_per_symbol - symbol_position) / 100
            
            iq = complex(
                math.cos(angle) * window * self.signal_amplitude,
                math.sin(angle) * window * self.signal_amplitude
            )
            
            # Add noise
            if self.noise_level > 0:
                iq += complex(
                    random.gauss(0, self.noise_level),
                    random.gauss(0, self.noise_level)
                )
            
            samples.append(iq)
            
            # Update symbol position
            symbol_position += 1
            if symbol_position >= samples_per_symbol:
                symbol_index += 1
                symbol_position = 0
        
        # Update phase
        if self.ft8_symbols:
            last_symbol = self.ft8_symbols[-1] if self.ft8_symbols else 0
            last_freq = self.ft8_base_freq + last_symbol * self.ft8_tone_spacing
            self.phase += 2 * math.pi * last_freq * num_samples / self.sample_rate
        else:
            self.phase += 2 * math.pi * self.ft8_base_freq * num_samples / self.sample_rate
        self.phase %= 2 * math.pi
        self.time_offset += num_samples / self.sample_rate
        
        return samples
    
    def set_morse_sequence(self, sequence, wpm=15):
        """Set Morse code sequence to transmit."""
        self.morse_dot_duration = 1.2 / wpm  # seconds per dot
        self.morse_buffer = sequence
    
    def set_rtty_text(self, text):
        """Set RTTY text to transmit."""
        self.rtty_buffer = text
    
    def set_ft8_symbols(self, symbols):
        """Set FT8 symbols to transmit."""
        self.ft8_symbols = symbols
    
    def set_frequency(self, freq):
        """Set the signal frequency."""
        self.signal频率 = freq
    
    def set_noise(self, level):
        """Set noise level (0.0 = no noise, 1.0 = high noise)."""
        self.noise_level = level
    
    def set_amplitude(self, amp):
        """Set signal amplitude."""
        self.signal_amplitude = amp
    
    def set_fade_rate(self, rate):
        """Set fading rate in Hz."""
        self.fade_rate = rate
    
    def _morse_to_pattern(self, sequence):
        """Convert morse code to on/off pattern."""
        pattern = []
        unit = self.morse_dot_duration
        
        for char in sequence:
            if char == '.':
                pattern.append(('.', 1))
                pattern.append((' ', 1))  # Element gap
            elif char == '-':
                pattern.append(('-', 3))
                pattern.append((' ', 1))  # Element gap
            elif char == ' ':
                pattern.append((' ', 4))  # Word gap
        
        return pattern
    
    def _text_to_rtty_bits(self, text):
        """Convert text to RTTY bit pattern."""
        # Simplified Baudot encoding
        bits = []
        
        for char in text.upper():
            # Start bit
            bits.append(0)
            
            # Data bits (simplified - just ASCII)
            ascii_val = ord(char) if char.isalnum() else 0
            for i in range(5):
                bits.append((ascii_val >> i) & 1)
            
            # Stop bit
            bits.append(1)
        
        return bits


class SDRSource:
    """
    Abstraction layer for SDR sources (real or virtual).
    """
    
    def __init__(self, source_type='virtual', sample_rate=48000):
        """
        Initialize SDR source.
        
        Args:
            source_type: 'virtual' or 'hardware'
            sample_rate: Sample rate
        """
        self.source_type = source_type
        self.sample_rate = sample_rate
        
        if source_type == 'virtual':
            self.sdr = VirtualSDR(sample_rate)
        else:
            self.sdr = None  # Hardware SDR would go here
    
    def read(self, num_samples):
        """
        Read IQ samples.
        
        Args:
            num_samples: Number of samples
            
        Returns:
            List of complex IQ samples
        """
        if self.source_type == 'virtual':
            return self.sdr.read_samples(num_samples)
        else:
            # Placeholder for hardware SDR
            raise NotImplementedError("Hardware SDR not implemented")
    
    def configure(self, **kwargs):
        """Configure SDR parameters."""
        if self.source_type == 'virtual':
            for key, value in kwargs.items():
                if hasattr(self.sdr, key):
                    setattr(self.sdr, key, value)


class IQToAudio:
    """
    Convert IQ samples to audio samples for decoding.
    """
    
    def __init__(self, sample_rate=48000, audio_rate=8000):
        """
        Initialize converter.
        
        Args:
            sample_rate: IQ sample rate
            audio_rate: Audio output sample rate
        """
        self.sample_rate = sample_rate
        self.audio_rate = audio_rate
        self.decimation = sample_rate // audio_rate
    
    def convert(self, iq_samples):
        """
        Convert IQ samples to audio samples.
        
        Args:
            iq_samples: List of complex IQ samples
            
        Returns:
            List of float audio samples
        """
        audio = []
        
        for i in range(0, len(iq_samples), self.decimation):
            if i < len(iq_samples):
                # Take real part and normalize
                sample = iq_samples[i].real
                audio.append(sample)
        
        return audio
    
    def convert_with_lowpass(self, iq_samples, cutoff_freq=3000):
        """
        Convert with simple lowpass filter.
        
        Args:
            iq_samples: IQ samples
            cutoff_freq: Lowpass cutoff frequency
            
        Returns:
            Filtered audio samples
        """
        # Simple moving average lowpass
        window_size = self.sample_rate // cutoff_freq
        if window_size < 1:
            window_size = 1
        
        audio = []
        buffer = []
        
        for i in range(0, len(iq_samples), self.decimation):
            if i < len(iq_samples):
                sample = iq_samples[i].real
                buffer.append(sample)
                
                if len(buffer) > window_size:
                    buffer.pop(0)
                
                filtered = sum(buffer) / len(buffer)
                audio.append(filtered)
        
        return audio


if __name__ == '__main__':
    print("Virtual SDR Simulator")
    print("=" * 50)
    
    # Create SDR
    sdr = VirtualSDR(sample_rate=48000)
    
    # Generate CW samples
    print("\nGenerating CW (SOS) signal...")
    samples = sdr.read_samples_morse(48000, '... --- ...')
    print(f"Generated {len(samples)} IQ samples")
    print(f"Duration: {len(samples)/48000:.2f} seconds")
    
    # Generate RTTY samples
    print("\nGenerating RTTY signal...")
    sdr2 = VirtualSDR(sample_rate=48000)
    samples = sdr2.read_samples_rtty(48000, 'CQ')
    print(f"Generated {len(samples)} IQ samples")
    
    # Generate FT8 samples
    print("\nGenerating FT8 signal...")
    sdr3 = VirtualSDR(sample_rate=48000)
    sdr3.set_ft8_symbols([0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4, 5, 6, 7,
                          0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4, 5, 6, 7,
                          0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4, 5, 6, 7, 0, 1])
    samples = sdr3.read_samples_ft8(48000 * 3)
    print(f"Generated {len(samples)} IQ samples")
    
    # Test SDRSource
    print("\nTesting SDRSource...")
    source = SDRSource('virtual', 48000)
    samples = source.read(1024)
    print(f"Read {len(samples)} samples from SDRSource")
    
    print("\nDone!")
