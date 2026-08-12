"""
CW (Morse Code) Decoder using Goertzel Algorithm
Detects and decodes Morse code from audio input.
"""
import time
from collections import deque
from goertzel import GoertzelFilter, ToneDetector


# International Morse Code table
MORSE_TABLE = {
    '.-': 'A', '-...': 'B', '-.-.': 'C', '-..': 'D', '.': 'E',
    '..-.': 'F', '--.': 'G', '....': 'H', '..': 'I', '.---': 'J',
    '-.-': 'K', '.-..': 'L', '--': 'M', '-.': 'N', '---': 'O',
    '.--.': 'P', '--.-': 'Q', '.-.': 'R', '...': 'S', '-': 'T',
    '..-': 'U', '...-': 'V', '.--': 'W', '-..-': 'X', '-.--': 'Y',
    '--..': 'Z',
    '-----': '0', '.----': '1', '..---': '2', '...--': '3',
    '....-': '4', '.....': '5', '-....': '6', '--...': '7',
    '---..': '8', '----.': '9',
    '.-.-.-': '.', '--..--': ',', '..--..': '?', '.----.': "'",
    '-.-.--': '!', '-..-.': '/', '-.--.': '(', '-.--.-': ')',
    '.-...': '&', '---...': ':', '-.-.-.': ';', '-...-': '=',
    '.-.-.': '+', '-....-': '-', '..--.-': '_', '.-..-.': '"',
    '...-..-': '$', '.--.-.': '@',
    '...-.-': 'SK', '-.-.-': 'CT',
}


class CWDecoder:
    """
    CW (Morse) decoder using Goertzel algorithm for tone detection.
    Supports both sample-based and time-based decoding.
    """
    
    def __init__(self, sample_rate=8000, tone_freq=700, wpm=None):
        """
        Initialize CW decoder.
        
        Args:
            sample_rate: Audio sample rate (Hz)
            tone_freq: Morse tone frequency (Hz), typically 600-800 Hz
            wpm: Words per minute (if known, for timing reference)
        """
        self.sample_rate = sample_rate
        self.tone_freq = tone_freq
        
        # Initialize Goertzel filter for tone detection
        self.detector = ToneDetector(tone_freq, sample_rate, threshold=0.3)
        
        # Timing parameters
        if wpm:
            self.unit_ms = 1200.0 / wpm
        else:
            self.unit_ms = 100.0  # Default ~12 WPM
        
        # Calculate samples per unit
        self.samples_per_unit = int(sample_rate * self.unit_ms / 1000.0)
        
        # Adaptive timing thresholds (in milliseconds)
        self.dot_max_ms = self.unit_ms * 1.5
        self.dash_min_ms = self.unit_ms * 2.0
        self.element_gap_min = self.unit_ms * 0.5
        self.element_gap_max = self.unit_ms * 2.0
        self.char_gap_min = self.unit_ms * 2.0
        self.char_gap_max = self.unit_ms * 4.0
        self.word_gap_min = self.unit_ms * 5.0
        
        # State
        self.current_char = ''
        self.decoded_text = ''
        self.in_tone = False
        self.tone_start_sample = 0
        self.last_off_sample = 0
        self.current_sample = 0
        self.gap_history = deque(maxlen=20)
        self.tone_history = deque(maxlen=50)
        
        # Buffer for audio processing
        self.sample_buffer = []
        self.block_size = int(sample_rate * 0.01)  # 10ms blocks
        
        # Detection results buffer
        self.detection_buffer = []
    
    def reset(self):
        """Reset decoder state."""
        self.current_char = ''
        self.decoded_text = ''
        self.in_tone = False
        self.tone_start_sample = 0
        self.last_off_sample = 0
        self.current_sample = 0
        self.gap_history.clear()
        self.tone_history.clear()
        self.sample_buffer = []
        self.detector.reset()
        self.detection_buffer = []
    
    def decode_block(self, samples):
        """
        Decode a complete block of audio and return text.
        This is the main method for sample-based decoding.
        
        Args:
            samples: List of audio samples
            
        Returns:
            Decoded text
        """
        decoded = []
        
        # Process samples in small blocks for tone detection
        block_size = 256  # Process in 256-sample blocks
        
        # Track tone on/off transitions
        tone_state = False
        tone_start = 0
        silence_start = 0
        current_char = ''
        
        for i in range(0, len(samples), block_size):
            block = samples[i:i + block_size]
            if len(block) < block_size:
                break
            
            # Detect tone in this block
            tone_detected = self.detector.detect(block)
            
            if tone_detected and not tone_state:
                # Tone just started
                if silence_start > 0:
                    # Calculate silence duration
                    silence_duration = i - silence_start
                    silence_ms = (silence_duration / self.sample_rate) * 1000
                    
                    # Check if this is a character or word gap
                    if silence_ms >= self.char_gap_min:
                        if current_char:
                            char = self._morse_to_char(current_char)
                            decoded.append(char)
                            current_char = ''
                        
                        if silence_ms >= self.word_gap_min:
                            decoded.append(' ')
                
                tone_state = True
                tone_start = i
                
            elif not tone_detected and tone_state:
                # Tone just ended
                tone_state = False
                silence_start = i
                
                # Calculate tone duration
                tone_duration = i - tone_start
                tone_ms = (tone_duration / self.sample_rate) * 1000
                
                # Store for timing analysis
                self.tone_history.append(tone_ms)
                
                # Determine if dot or dash based on duration
                if tone_ms < self.dot_max_ms:
                    current_char += '.'
                elif tone_ms >= self.dash_min_ms:
                    current_char += '-'
                else:
                    # Ambiguous - use average of recent tones
                    if len(self.tone_history) > 1:
                        avg = sum(self.tone_history) / len(self.tone_history)
                        if tone_ms < avg:
                            current_char += '.'
                        else:
                            current_char += '-'
                    else:
                        if tone_ms < self.unit_ms * 1.75:
                            current_char += '.'
                        else:
                            current_char += '-'
        
        # Handle any remaining character at end of audio
        if current_char:
            char = self._morse_to_char(current_char)
            decoded.append(char)
        
        self.decoded_text += ''.join(decoded)
        return ''.join(decoded)
    
    def process_samples(self, samples):
        """
        Process audio samples for real-time decoding.
        For real-time use with time-based detection.
        
        Args:
            samples: List of audio samples
            
        Returns:
            List of decoded characters
        """
        decoded = []
        
        for sample in samples:
            # Detect tone
            self.sample_buffer.append(sample)
            
            if len(self.sample_buffer) >= self.block_size:
                block = self.sample_buffer[:self.block_size]
                self.sample_buffer = self.sample_buffer[self.block_size:]
                
                tone_detected = self.detector.detect(block)
                
                if tone_detected and not self.in_tone:
                    # Tone started
                    self.in_tone = True
                    self.tone_start_sample = self.current_sample
                    
                elif not tone_detected and self.in_tone:
                    # Tone ended
                    self.in_tone = False
                    self.last_off_sample = self.current_sample
                    
                    # Calculate duration
                    duration_samples = self.current_sample - self.tone_start_sample
                    duration_ms = (duration_samples / self.sample_rate) * 1000
                    
                    self.tone_history.append(duration_ms)
                    
                    # Classify
                    if duration_ms < self.dot_max_ms:
                        self.current_char += '.'
                    else:
                        self.current_char += '-'
            
            self.current_sample += 1
        
        return decoded
    
    def check_character_gap(self):
        """
        Check if character gap has elapsed and output character.
        Call this periodically when no tone is present.
        
        Returns:
            Decoded character or None
        """
        if not self.current_char or self.in_tone:
            return None
        
        if self.last_off_sample == 0:
            return None
        
        # Calculate gap duration
        gap_samples = self.current_sample - self.last_off_sample
        gap_ms = (gap_samples / self.sample_rate) * 1000
        
        if gap_ms >= self.char_gap_min:
            # End of character
            char = self._morse_to_char(self.current_char)
            self.decoded_text += char
            self.current_char = ''
            return char
        
        return None
    
    def check_word_gap(self):
        """
        Check if word gap has elapsed.
        
        Returns:
            True if word gap detected
        """
        if self.last_off_sample == 0:
            return False
        
        gap_samples = self.current_sample - self.last_off_sample
        gap_ms = (gap_samples / self.sample_rate) * 1000
        
        if gap_ms >= self.word_gap_min and not self.current_char:
            self.decoded_text += ' '
            return True
        
        return False
    
    def _morse_to_char(self, morse):
        """Convert Morse code to character."""
        if morse in MORSE_TABLE:
            return MORSE_TABLE[morse]
        
        # Try to find closest match
        for code, char in MORSE_TABLE.items():
            if self._hamming_distance(morse, code) <= 1:
                return char
        
        return '?'  # Unknown
    
    def _hamming_distance(self, s1, s2):
        """Calculate Hamming distance between two strings."""
        if len(s1) != len(s2):
            return max(len(s1), len(s2))
        return sum(c1 != c2 for c1, c2 in zip(s1, s2))


class CWDecoderDemo:
    """Demo class showing how to use the CW decoder."""
    
    def __init__(self):
        self.decoder = CWDecoder(sample_rate=8000, tone_freq=700)
    
    def decode_from_samples(self, samples):
        """Decode directly from audio samples."""
        self.decoder.reset()
        return self.decoder.decode_block(samples)


def morse_to_audio(morse_code, wpm=15, freq=700, sample_rate=8000):
    """
    Convert Morse code to audio samples.
    
    Args:
        morse_code: Morse code string (dots, dashes, spaces)
        wpm: Words per minute
        freq: Tone frequency (Hz)
        sample_rate: Sample rate (Hz)
        
    Returns:
        List of audio samples
    """
    unit_ms = 1200.0 / wpm
    unit_samples = int(sample_rate * unit_ms / 1000)
    
    samples = []
    
    # Parse morse code into letters (separated by spaces)
    letters = morse_code.split(' ')
    
    for li, letter in enumerate(letters):
        # Generate each element in the letter
        for ei, element in enumerate(letter):
            if element == '.':
                # Dot: 1 unit
                samples.extend(_generate_tone(unit_samples, freq, sample_rate))
            elif element == '-':
                # Dash: 3 units
                samples.extend(_generate_tone(unit_samples * 3, freq, sample_rate))
            
            # Element gap: 1 unit (between elements within a letter)
            if ei < len(letter) - 1:
                samples.extend([0] * unit_samples)
        
        # Character gap: 3 units (between letters)
        if li < len(letters) - 1:
            samples.extend([0] * unit_samples * 3)
    
    # Add trailing silence
    samples.extend([0] * unit_samples * 3)
    
    return samples


def _generate_tone(num_samples, freq, sample_rate):
    """Generate a tone."""
    import math
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        sample = 0.8 * math.sin(2 * math.pi * freq * t)
        samples.append(sample)
    return samples


if __name__ == '__main__':
    # Demo
    print("CW (Morse) Decoder")
    print("=" * 50)
    
    # Example: Generate SOS
    print("\nGenerating SOS signal...")
    sos_morse = '... --- ...'
    samples = morse_to_audio(sos_morse, wpm=15)
    
    decoder = CWDecoder(sample_rate=8000, tone_freq=700)
    result = decoder.decode_block(samples)
    
    print(f"Morse input: {sos_morse}")
    print(f"Decoded: {result}")
