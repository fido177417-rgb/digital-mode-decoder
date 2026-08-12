"""
RTTY (Radio Teletype) Decoder
FSK-based digital mode decoder using zero-crossing detection.
"""
import math
from collections import deque


# Baudot code tables (ITA2 / LTRS)
BAUDOT_LTRS = {
    0b00000: '\0',  # Blank
    0b00100: ' ',   # Space
    0b00010: '\n',  # Line Feed
    0b01000: '\r',  # Carriage Return
    0b11111: 'LTRS',  # Letters shift
    0b11011: 'FIGS',  # Figures shift
    
    0b00011: 'A', 0b11001: 'B', 0b01110: 'C', 0b01001: 'D',
    0b00001: 'E', 0b01101: 'F', 0b11010: 'G', 0b10100: 'H',
    0b00110: 'I', 0b01011: 'J', 0b01111: 'K', 0b10010: 'L',
    0b11100: 'M', 0b01100: 'N', 0b11000: 'O', 0b10110: 'P',
    0b10111: 'Q', 0b01010: 'R', 0b00101: 'S', 0b10000: 'T',
    0b00111: 'U', 0b11110: 'V', 0b10011: 'W', 0b11101: 'X',
    0b10101: 'Y', 0b10001: 'Z',
}

BAUDOT_FIGS = {
    0b00000: '\0', 0b00100: ' ', 0b00010: '\n', 0b01000: '\r',
    0b11111: 'LTRS', 0b11011: 'FIGS',
    
    0b00011: '-', 0b11001: '?', 0b01110: ':', 0b01001: '$',
    0b00001: '3', 0b01101: '!', 0b11010: '&', 0b10100: '#',
    0b00110: '8', 0b01011: '\'', 0b01111: '(', 0b10010: ')',
    0b11100: '.', 0b01100: ',', 0b11000: '9', 0b10110: '0',
    0b10111: '1', 0b01010: '4', 0b00101: '\x07',  # Bell
    0b10000: '5', 0b00111: '7', 0b11110: ';', 0b10011: '2',
    0b11101: '/', 0b10101: '6', 0b10001: '"',
}


class RTTYDecoder:
    """
    RTTY decoder using zero-crossing detection for FSK demodulation.
    
    Standard RTTY parameters:
    - Shift: 170 Hz (standard), 425 Hz, 850 Hz, etc.
    - Baud: 45.45, 50, 75, 100, etc.
    - Mark/Space frequencies
    """
    
    def __init__(self, sample_rate=8000, shift=170, baud=45.45, 
                 mark_freq=1000, space_freq=830):
        """
        Initialize RTTY decoder.
        
        Args:
            sample_rate: Audio sample rate (Hz)
            shift: Frequency shift between mark and space (Hz)
            baud: Baud rate (characters per second)
            mark_freq: Mark frequency (Hz) - typically mark = space + shift
            space_freq: Space frequency (Hz)
        """
        self.sample_rate = sample_rate
        self.shift = shift
        self.baud = baud
        self.mark_freq = mark_freq
        self.space_freq = space_freq
        
        # Calculate bit duration in samples
        self.samples_per_bit = int(sample_rate / baud)
        
        # Zero-crossing detection
        self.prev_sample = 0
        self.zero_crossings = deque(maxlen=100)
        
        # Frequency tracking
        self.instant_freq = mark_freq
        self.freq_history = deque(maxlen=10)
        
        # Bit detection state
        self.bit_buffer = []
        self.bit_count = 0
        self.current_bit = 0
        
        # Baudot decoding state
        self.shift_mode = 'LTRS'  # Current shift mode
        self.bit_position = 0
        self.current_char_bits = 0b00000
        self.in_start_bit = True
        
        # Output
        self.decoded_text = ''
        self.buffer = []
        
        # Filter parameters
        self.min_freq = min(mark_freq, space_freq) - 100
        self.max_freq = max(mark_freq, space_freq) + 100
    
    def reset(self):
        """Reset decoder state."""
        self.prev_sample = 0
        self.zero_crossings.clear()
        self.freq_history.clear()
        self.bit_buffer = []
        self.bit_count = 0
        self.bit_position = 0
        self.current_char_bits = 0b00000
        self.in_start_bit = True
        self.shift_mode = 'LTRS'
        self.decoded_text = ''
        self.buffer = []
    
    def process_samples(self, samples):
        """
        Process audio samples and decode RTTY.
        
        Args:
            samples: List of audio samples
            
        Returns:
            Decoded text
        """
        for sample in samples:
            self._process_sample(sample)
        
        return self.decoded_text
    
    def _process_sample(self, sample):
        """Process a single sample."""
        # Zero-crossing detection
        if (self.prev_sample >= 0 and sample < 0) or \
           (self.prev_sample < 0 and sample >= 0):
            self._handle_zero_crossing()
        
        self.prev_sample = sample
        
        # Accumulate samples for bit timing
        self.bit_buffer.append(sample)
        
        # Check if we have a complete bit
        if len(self.bit_buffer) >= self.samples_per_bit:
            self._process_bit()
    
    def _handle_zero_crossing(self):
        """Handle a zero crossing event."""
        now = len(self.zero_crossings) + 1
        
        if len(self.zero_crossings) > 0:
            # Calculate instantaneous frequency
            period = now - self.zero_crossings[-1]
            if period > 0:
                freq = self.sample_rate / (period * 2)
                
                # Filter reasonable frequencies
                if self.min_freq <= freq <= self.max_freq:
                    self.instant_freq = freq
                    self.freq_history.append(freq)
        
        self.zero_crossings.append(now)
    
    def _process_bit(self):
        """Process accumulated samples for one bit period."""
        if len(self.bit_buffer) < self.samples_per_bit:
            return
        
        # Calculate average frequency during this bit period
        bit_freq = self._estimate_frequency()
        
        # Determine mark or space
        # Mark = 1 (typically higher frequency)
        # Space = 0 (typically lower frequency)
        if abs(bit_freq - self.mark_freq) < abs(bit_freq - self.space_freq):
            bit = 1  # Mark
        else:
            bit = 0  # Space
        
        # Clear buffer
        self.bit_buffer = self.bit_buffer[self.samples_per_bit:]
        
        # Process bit through Baudot state machine
        self._process_baudot_bit(bit)
    
    def _estimate_frequency(self):
        """Estimate frequency of current bit using zero crossings."""
        if len(self.freq_history) > 0:
            # Use median of recent frequencies
            recent = list(self.freq_history)[-5:]
            recent.sort()
            return recent[len(recent) // 2]
        
        return self.instant_freq
    
    def _process_baudot_bit(self, bit):
        """
        Process a bit through Baudot decoder state machine.
        
        RTTY frame format:
        - 1 start bit (space/0)
        - 5 data bits
        - 1.5 stop bits (mark/1)
        """
        if self.in_start_bit:
            # Looking for start bit (should be 0/space)
            if bit == 0:
                self.in_start_bit = False
                self.bit_position = 0
                self.current_char_bits = 0
        else:
            # Collecting data bits
            if self.bit_position < 5:
                # LSB first
                self.current_char_bits |= (bit << self.bit_position)
                self.bit_position += 1
            
            if self.bit_position >= 5:
                # Complete character received
                self._decode_baudot_char(self.current_char_bits)
                self.bit_position = 0
                self.in_start_bit = True
    
    def _decode_baudot_char(self, bits):
        """Decode a Baudot character."""
        # Check for shift characters first
        if bits == 0b11111:  # LTRS shift
            self.shift_mode = 'LTRS'
            return
        elif bits == 0b11011:  # FIGS shift
            self.shift_mode = 'FIGS'
            return
        
        # Decode character based on current shift mode
        if self.shift_mode == 'LTRS':
            char = BAUDOT_LTRS.get(bits, '?')
        else:
            char = BAUDOT_FIGS.get(bits, '?')
        
        # Handle control characters
        if char == 'LTRS' or char == 'FIGS':
            self.shift_mode = char
        elif char is not None and char != '\0':
            self.decoded_text += char
    
    def detect_shift(self, samples, window_size=256):
        """
        Auto-detect the frequency shift from signal.
        
        Args:
            samples: Audio samples
            window_size: FFT window size
            
        Returns:
            Detected shift in Hz
        """
        # Simple approach: find two dominant frequencies
        freq_bins = {}
        
        for i in range(0, len(samples) - window_size, window_size // 2):
            window = samples[i:i + window_size]
            
            # Count zero crossings
            crossings = 0
            for j in range(1, len(window)):
                if (window[j-1] >= 0 and window[j] < 0) or \
                   (window[j-1] < 0 and window[j] >= 0):
                    crossings += 1
            
            # Estimate frequency
            freq = crossings * self.sample_rate / (2 * window_size)
            freq_bins[int(freq)] = freq_bins.get(int(freq), 0) + 1
        
        # Find two most prominent frequencies
        if freq_bins:
            sorted_freqs = sorted(freq_bins.items(), key=lambda x: x[1], reverse=True)
            
            if len(sorted_freqs) >= 2:
                f1 = sorted_freqs[0][0]
                f2 = sorted_freqs[1][0]
                detected_shift = abs(f1 - f2)
                
                # Update frequencies
                self.mark_freq = max(f1, f2)
                self.space_freq = min(f1, f2)
                self.shift = detected_shift
                
                return detected_shift
        
        return self.shift
    
    def detect_baud_rate(self, samples):
        """
        Auto-detect baud rate from signal.
        
        Args:
            samples: Audio samples
            
        Returns:
            Detected baud rate
        """
        # Count transitions (mark to space or space to mark)
        transitions = 0
        prev_bit = None
        
        bit_buffer = []
        
        for sample in samples:
            bit_buffer.append(sample)
            
            if len(bit_buffer) >= self.samples_per_bit:
                # Determine bit value
                freq = self._estimate_frequency_from_block(bit_buffer)
                bit = 1 if abs(freq - self.mark_freq) < abs(freq - self.space_freq) else 0
                
                if prev_bit is not None and bit != prev_bit:
                    transitions += 1
                
                prev_bit = bit
                bit_buffer = bit_buffer[self.samples_per_bit:]
        
        # Estimate baud rate from transitions
        if transitions > 0:
            duration = len(samples) / self.sample_rate
            baud = transitions / duration
            
            # Round to standard RTTY baud rates
            standard_bauds = [45.45, 50, 75, 100, 110, 150, 200, 300]
            closest = min(standard_bauds, key=lambda x: abs(x - baud))
            
            self.baud = closest
            self.samples_per_bit = int(self.sample_rate / closest)
            
            return closest
        
        return self.baud
    
    def _estimate_frequency_from_block(self, block):
        """Estimate frequency from a block of samples."""
        crossings = 0
        for i in range(1, len(block)):
            if (block[i-1] >= 0 and block[i] < 0) or \
               (block[i-1] < 0 and block[i] >= 0):
                crossings += 1
        
        if crossings > 0:
            return crossings * self.sample_rate / (2 * len(block))
        return (self.mark_freq + self.space_freq) / 2


class RTTYGenerator:
    """Generate RTTY signals for testing."""
    
    def __init__(self, sample_rate=8000, shift=170, baud=45.45,
                 mark_freq=1000, space_freq=830):
        self.sample_rate = sample_rate
        self.shift = shift
        self.baud = baud
        self.mark_freq = mark_freq
        self.space_freq = space_freq
    
    def text_to_rtty(self, text, char_gap_bits=1.5):
        """
        Convert text to RTTY audio signal.
        
        Args:
            text: Text to encode
            char_gap_bits: Gap between characters in bit periods
            
        Returns:
            List of audio samples
        """
        samples = []
        
        shift_mode = 'LTRS'
        
        for char in text.upper():
            # Determine if we need to shift
            bits = self._get_baudot_bits(char, shift_mode)
            
            if bits is None:
                continue
            
            # Send shift if needed
            new_mode = 'LTRS' if char.isalpha() else 'FIGS'
            if new_mode != shift_mode:
                shift_bits = 0b11111 if new_mode == 'LTRS' else 0b11011
                samples.extend(self._send_character(shift_bits))
                shift_mode = new_mode
            
            # Send character
            samples.extend(self._send_character(bits))
            
            # Inter-character gap
            gap_samples = int(self.samples_per_bit * char_gap_bits)
            samples.extend(self._generate_tone(self.space_freq, gap_samples))
        
        return samples
    
    def _get_baudot_bits(self, char, shift_mode):
        """Get Baudot bits for a character."""
        if shift_mode == 'LTRS':
            for bits, c in BAUDOT_LTRS.items():
                if c == char:
                    return bits
        else:
            for bits, c in BAUDOT_FIGS.items():
                if c == char:
                    return bits
        return None
    
    def _send_character(self, bits):
        """Send a Baudot character (start + 5 bits + stop)."""
        samples = []
        
        # Start bit (space/0)
        samples.extend(self._generate_tone(self.space_freq, self.samples_per_bit))
        
        # 5 data bits, LSB first
        for i in range(5):
            bit = (bits >> i) & 1
            freq = self.mark_freq if bit == 1 else self.space_freq
            samples.extend(self._generate_tone(freq, self.samples_per_bit))
        
        # Stop bit (mark/1) - 1.5 bits
        stop_samples = int(self.samples_per_bit * 1.5)
        samples.extend(self._generate_tone(self.mark_freq, stop_samples))
        
        return samples
    
    def _generate_tone(self, freq, num_samples):
        """Generate a tone."""
        samples = []
        for i in range(num_samples):
            t = i / self.sample_rate
            sample = 0.7 * math.sin(2 * math.pi * freq * t)
            samples.append(sample)
        return samples


if __name__ == '__main__':
    print("RTTY Decoder")
    print("=" * 50)
    
    # Generate test signal
    print("\nGenerating test RTTY signal...")
    gen = RTTYGenerator(sample_rate=8000, shift=170, baud=45.45)
    test_text = "CQ CQ DE TEST"
    samples = gen.text_to_rtty(test_text)
    
    # Decode
    decoder = RTTYDecoder(sample_rate=8000, shift=170, baud=45.45)
    result = decoder.process_samples(samples)
    
    print(f"Input: {test_text}")
    print(f"Decoded: {result}")
