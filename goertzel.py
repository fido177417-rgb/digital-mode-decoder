"""
Pure Python Goertzel Algorithm Implementation
Efficient single-frequency DFT for tone detection.
"""
import math
import cmath


class GoertzelFilter:
    """
    Goertzel filter for detecting a single frequency in a signal.
    Uses direct DFT calculation for numerical stability.
    """
    
    def __init__(self, target_freq, sample_rate, block_size=None):
        """
        Initialize Goertzel filter.
        
        Args:
            target_freq: Frequency to detect (Hz)
            sample_rate: Audio sample rate (Hz)
            block_size: Number of samples per analysis block
        """
        self.target_freq = target_freq
        self.sample_rate = sample_rate
        self.block_size = block_size or 256
        
        # Pre-calculate phase increments
        self.omega = 2.0 * math.pi * target_freq / sample_rate
    
    def reset(self):
        """Reset filter state (no-op for this implementation)."""
        pass
    
    def process_block(self, samples):
        """
        Process a block of samples and return magnitude.
        Uses direct DFT calculation for numerical stability.
        
        Args:
            samples: List of sample values
            
        Returns:
            Normalized magnitude of the target frequency
        """
        n = len(samples)
        real_sum = 0.0
        imag_sum = 0.0
        
        for i, sample in enumerate(samples):
            angle = self.omega * i
            real_sum += sample * math.cos(angle)
            imag_sum += sample * math.sin(angle)
        
        # Normalize by block size
        magnitude = math.sqrt(real_sum * real_sum + imag_sum * imag_sum) / n
        
        return magnitude


class GoertzelAnalyzer:
    """
    Multi-frequency Goertzel analyzer for simultaneous tone detection.
    """
    
    def __init__(self, frequencies, sample_rate, block_size=None):
        """
        Initialize analyzer with multiple target frequencies.
        
        Args:
            frequencies: List of frequencies to detect (Hz)
            sample_rate: Audio sample rate (Hz)
            block_size: Number of samples per analysis block
        """
        self.sample_rate = sample_rate
        self.block_size = block_size or int(sample_rate / min(frequencies))
        
        # Create Goertzel filter for each frequency
        self.filters = {}
        for freq in frequencies:
            self.filters[freq] = GoertzelFilter(freq, sample_rate, self.block_size)
        
        # Sample buffer
        self.buffer = []
        self.buffer_size = self.block_size
    
    def reset(self):
        """Reset all filters."""
        for f in self.filters.values():
            f.reset()
        self.buffer = []
    
    def process_sample(self, sample):
        """
        Process a sample and check if block is complete.
        
        Args:
            sample: Input sample
            
        Returns:
            Dict of {frequency: magnitude} if block complete, None otherwise
        """
        self.buffer.append(sample)
        
        if len(self.buffer) >= self.buffer_size:
            return self.process_block(self.buffer)
        
        return None
    
    def process_block(self, samples):
        """
        Process a block of samples through all filters.
        
        Args:
            samples: List of sample values
            
        Returns:
            Dict of {frequency: magnitude}
        """
        results = {}
        for freq, filt in self.filters.items():
            filt.reset()
            for s in samples:
                filt.s1 = s + (filt.coeff * filt.s1) - filt.s2
                filt.s2 = filt.s1 * filt.coeff - filt.s2 + s
            results[freq] = filt.get_magnitude()
        
        return results
    
    def find_peak_frequency(self, magnitudes):
        """
        Find the frequency with highest magnitude.
        
        Args:
            magnitudes: Dict of {frequency: magnitude}
            
        Returns:
            Tuple of (frequency, magnitude)
        """
        if not magnitudes:
            return (0, 0)
        
        peak_freq = max(magnitudes, key=magnitudes.get)
        return (peak_freq, magnitudes[peak_freq])


class ToneDetector:
    """
    High-level tone detector using Goertzel algorithm.
    Detects on/off keying (OOK) like in Morse code.
    """
    
    def __init__(self, freq, sample_rate, threshold=0.3, block_size=None):
        """
        Initialize tone detector.
        
        Args:
            freq: Tone frequency to detect (Hz)
            sample_rate: Audio sample rate (Hz)
            threshold: Detection threshold (0.0-1.0)
            block_size: Samples per analysis block
        """
        self.freq = freq
        self.sample_rate = sample_rate
        self.threshold = threshold
        
        # Use provided block size or default to 256
        if block_size is None:
            block_size = 256
        
        self.filter = GoertzelFilter(freq, sample_rate, block_size)
        self.block_size = block_size
        
        # Calibration
        self.max_magnitude = 1.0
        self.min_magnitude = 0.0
        self.calibrated = False
        
        # State
        self.is_on = False
        self.on_count = 0
        self.off_count = 0
        self.buffer = []
    
    def reset(self):
        """Reset detector state."""
        self.filter.reset()
        self.is_on = False
        self.on_count = 0
        self.off_count = 0
        self.buffer = []
    
    def calibrate(self, samples, has_tone=True):
        """
        Calibrate the detector with known signal.
        
        Args:
            samples: Audio samples
            has_tone: True if samples contain the tone, False for silence
        """
        mag = self.filter.process_block(samples)
        
        if has_tone:
            self.max_magnitude = max(mag, self.max_magnitude)
        else:
            self.min_magnitude = max(mag, self.min_magnitude)
        
        # Set threshold midway
        mid = (self.max_magnitude + self.min_magnitude) / 2
        self.threshold = mid / self.max_magnitude if self.max_magnitude > 0 else 0.3
        self.calibrated = True
    
    def detect(self, samples):
        """
        Detect tone presence in samples.
        
        Args:
            samples: Audio samples
            
        Returns:
            True if tone detected, False otherwise
        """
        mag = self.filter.process_block(samples)
        
        # Auto-calibrate on first call
        if not self.calibrated and self.max_magnitude <= 1.0:
            self.max_magnitude = max(mag, 1.0)
        
        # Normalize
        if self.max_magnitude > 0:
            normalized = mag / self.max_magnitude
        else:
            normalized = mag
        
        return normalized > self.threshold
