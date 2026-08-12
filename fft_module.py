"""
Pure Python FFT Implementation
Cooley-Tukey radix-2 DIT algorithm with windowing functions.
No external dependencies required.
"""
import math
import cmath
from typing import List, Tuple, Optional


# Window functions
def window_none(n: int) -> List[float]:
    """No window (rectangular)."""
    return [1.0] * n

def window_hanning(n: int) -> List[float]:
    """Hanning window - good general purpose."""
    return [0.5 * (1 - math.cos(2 * math.pi * i / (n - 1))) for i in range(n)]

def window_hamming(n: int) -> List[float]:
    """Hamming window - better side lobe suppression."""
    return [0.54 - 0.46 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]

def window_blackman(n: int) -> List[float]:
    """Blackman window - excellent side lobe suppression."""
    return [0.42 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) + 
            0.08 * math.cos(4 * math.pi * i / (n - 1)) for i in range(n)]

def window_blackman_harris(n: int) -> List[float]:
    """Blackman-Harris window - minimum side lobe level."""
    return [0.35875 - 0.48829 * math.cos(2 * math.pi * i / (n - 1)) +
            0.14128 * math.cos(4 * math.pi * i / (n - 1)) -
            0.01168 * math.cos(6 * math.pi * i / (n - 1)) for i in range(n)]

def window_flattop(n: int) -> List[float]:
    """Flat-top window - best amplitude accuracy."""
    return [0.21557895 - 0.41663158 * math.cos(2 * math.pi * i / (n - 1)) +
            0.277263158 * math.cos(4 * math.pi * i / (n - 1)) -
            0.083578947 * math.cos(6 * math.pi * i / (n - 1)) +
            0.006947368 * math.cos(8 * math.pi * i / (n - 1)) for i in range(n)]


# Window function registry
WINDOWS = {
    'none': window_none,
    'hanning': window_hanning,
    'hamming': window_hamming,
    'blackman': window_blackman,
    'blackman_harris': window_blackman_harris,
    'flattop': window_flattop,
}


def fft_radix2(x: List[float]) -> List[complex]:
    """
    Radix-2 Cooley-Tukey FFT.
    Input length must be power of 2.
    
    Args:
        x: Input signal (real values)
        
    Returns:
        Complex FFT coefficients
    """
    n = len(x)
    
    if n == 1:
        return [complex(x[0], 0)]
    
    if n & (n - 1) != 0:
        raise ValueError("Input length must be power of 2")
    
    # Bit reversal permutation
    result = [complex(x[i], 0) for i in range(n)]
    j = 0
    for i in range(n):
        if i < j:
            result[i], result[j] = result[j], result[i]
        m = n >> 1
        while m >= 1 and j >= m:
            j -= m
            m >>= 1
        j += m
    
    # FFT butterfly operations
    size = 2
    while size <= n:
        half_size = size // 2
        angle = -2 * math.pi / size
        w_size = cmath.rect(1, angle)
        
        for i in range(0, n, size):
            w = complex(1, 0)
            for j in range(i, i + half_size):
                u = result[j]
                v = result[j + half_size] * w
                result[j] = u + v
                result[j + half_size] = u - v
                w *= w_size
        
        size *= 2
    
    return result


def fft(x: List[float]) -> List[complex]:
    """
    FFT with zero-padding to next power of 2.
    
    Args:
        x: Input signal
        
    Returns:
        Complex FFT coefficients
    """
    n = len(x)
    
    # Find next power of 2
    n_padded = 1
    while n_padded < n:
        n_padded <<= 1
    
    # Zero-pad
    x_padded = x + [0.0] * (n_padded - n)
    
    return fft_radix2(x_padded)


def ifft(X: List[complex]) -> List[float]:
    """
    Inverse FFT.
    
    Args:
        X: Complex FFT coefficients
        
    Returns:
        Real time-domain signal
    """
    n = len(X)
    
    # Conjugate, FFT, conjugate, scale
    X_conj = [complex(c.real, -c.imag) for c in X]
    x = fft_radix2([c.real for c in X_conj])
    
    return [c.real / n for c in x]


def rfft(x: List[float]) -> List[complex]:
    """
    Real-valued FFT (returns only positive frequencies).
    
    Args:
        x: Input signal
        
    Returns:
        Complex coefficients for positive frequencies
    """
    X = fft(x)
    n = len(X)
    return X[:n // 2 + 1]


def fft_magnitude(x: List[float], window: str = 'hanning') -> List[float]:
    """
    FFT magnitude spectrum.
    
    Args:
        x: Input signal
        window: Window function name
        
    Returns:
        Magnitude values (linear scale)
    """
    n = len(x)
    
    # Apply window
    if window in WINDOWS:
        w = WINDOWS[window](n)
        x_windowed = [x[i] * w[i] for i in range(n)]
    else:
        x_windowed = x
    
    # Compute FFT
    X = rfft(x_windowed)
    
    # Calculate magnitude
    scale = 2.0 / n  # Scale for one-sided spectrum
    magnitudes = [abs(c) * scale for c in X]
    
    return magnitudes


def fft_power(x: List[float], window: str = 'hanning') -> List[float]:
    """
    FFT power spectrum (magnitude squared).
    
    Args:
        x: Input signal
        window: Window function name
        
    Returns:
        Power values
    """
    magnitudes = fft_magnitude(x, window)
    return [m ** 2 for m in magnitudes]


def fft_db(x: List[float], window: str = 'hanning', ref: float = 1.0) -> List[float]:
    """
    FFT magnitude in decibels.
    
    Args:
        x: Input signal
        window: Window function name
        ref: Reference level for 0 dB
        
    Returns:
        Magnitude in dB
    """
    magnitudes = fft_magnitude(x, window)
    
    db_values = []
    for m in magnitudes:
        if m > 0:
            db = 20 * math.log10(m / ref)
        else:
            db = -120  # Floor
        db_values.append(max(db, -120))
    
    return db_values


def fft_frequencies(n: int, sample_rate: float) -> List[float]:
    """
    Generate frequency bins for FFT output.
    
    Args:
        n: FFT size
        sample_rate: Sample rate in Hz
        
    Returns:
        List of frequency values
    """
    n_bins = n // 2 + 1
    freq_per_bin = sample_rate / n
    return [i * freq_per_bin for i in range(n_bins)]


class FFTAnalyzer:
    """
    Real-time FFT analyzer with overlap and averaging.
    """
    
    def __init__(self, fft_size: int = 1024, sample_rate: float = 48000,
                 window: str = 'hanning', overlap: float = 0.5):
        """
        Initialize FFT analyzer.
        
        Args:
            fft_size: FFT size (must be power of 2)
            sample_rate: Sample rate in Hz
            window: Window function
            overlap: Overlap between frames (0.0-1.0)
        """
        # Ensure power of 2
        self.fft_size = 1
        while self.fft_size < fft_size:
            self.fft_size <<= 1
        
        self.sample_rate = sample_rate
        self.window = window
        self.overlap = overlap
        
        # Calculate hop size
        self.hop_size = int(self.fft_size * (1 - overlap))
        
        # Buffer for overlapping
        self.buffer = [0.0] * self.fft_size
        self.buffer_pos = 0
        
        # Frequency bins
        self.frequencies = fft_frequencies(self.fft_size, sample_rate)
        
        # Averaging
        self.averaging = 0.3  # Exponential moving average factor
        self.avg_magnitudes = None
    
    def process(self, samples: List[float]) -> Tuple[List[float], List[float]]:
        """
        Process audio samples and return spectrum.
        
        Args:
            samples: Audio samples
            
        Returns:
            Tuple of (frequencies, magnitudes)
        """
        all_magnitudes = []
        
        for sample in samples:
            # Add to buffer
            self.buffer[self.buffer_pos] = sample
            self.buffer_pos += 1
            
            # Process when buffer is full
            if self.buffer_pos >= self.fft_size:
                # Compute FFT
                magnitudes = fft_magnitude(list(self.buffer), self.window)
                
                # Apply averaging
                if self.avg_magnitudes is None:
                    self.avg_magnitudes = magnitudes
                else:
                    self.avg_magnitudes = [
                        self.averaging * m + (1 - self.averaging) * old
                        for m, old in zip(magnitudes, self.avg_magnitudes)
                    ]
                
                all_magnitudes.append(self.avg_magnitudes.copy())
                
                # Shift buffer for overlap
                shift = self.fft_size - self.hop_size
                self.buffer[:shift] = self.buffer[self.hop_size:]
                self.buffer_pos = shift
        
        # Return latest spectrum
        if all_magnitudes:
            return self.frequencies, all_magnitudes[-1]
        return self.frequencies, [0.0] * (self.fft_size // 2 + 1)
    
    def reset(self):
        """Reset analyzer state."""
        self.buffer = [0.0] * self.fft_size
        self.buffer_pos = 0
        self.avg_magnitudes = None


class SpectrumAnalyzer:
    """
    Spectrum analyzer with waterfall display data.
    """
    
    def __init__(self, fft_size: int = 1024, sample_rate: float = 48000,
                 num_rows: int = 50):
        """
        Initialize spectrum analyzer.
        
        Args:
            fft_size: FFT size
            sample_rate: Sample rate
            num_rows: Number of waterfall rows to keep
        """
        self.fft_analyzer = FFTAnalyzer(fft_size, sample_rate)
        self.num_rows = num_rows
        
        # Waterfall data (list of magnitude arrays)
        self.waterfall = []
        
        # Frequency axis
        self.frequencies = self.fft_analyzer.frequencies
        
        # Display range
        self.min_freq = 0
        self.max_freq = sample_rate / 2
        self.min_db = -80
        self.max_db = 0
    
    def process(self, samples: List[float]) -> dict:
        """
        Process samples and return display data.
        
        Returns:
            Dict with 'spectrum' and 'waterfall' data
        """
        freqs, magnitudes = self.fft_analyzer.process(samples)
        
        # Convert to dB
        db_values = []
        for m in magnitudes:
            if m > 0:
                db = 20 * math.log10(m)
            else:
                db = self.min_db
            db_values.append(max(db, self.min_db))
        
        # Add to waterfall
        self.waterfall.append(db_values)
        if len(self.waterfall) > self.num_rows:
            self.waterfall.pop(0)
        
        return {
            'frequencies': freqs,
            'spectrum': db_values,
            'waterfall': self.waterfall.copy()
        }
    
    def set_range(self, min_freq: float = 0, max_freq: float = None,
                  min_db: float = -80, max_db: float = 0):
        """Set display range."""
        self.min_freq = min_freq
        self.max_freq = max_freq or self.fft_analyzer.sample_rate / 2
        self.min_db = min_db
        self.max_db = max_db
    
    def reset(self):
        """Reset analyzer."""
        self.fft_analyzer.reset()
        self.waterfall.clear()


# Pitch detection using FFT
def detect_pitch_fft(x: List[float], sample_rate: float, 
                     min_freq: float = 50, max_freq: float = 2000) -> Optional[float]:
    """
    Detect pitch using FFT peak picking.
    
    Args:
        x: Audio samples
        sample_rate: Sample rate
        min_freq: Minimum detectable frequency
        max_freq: Maximum detectable frequency
        
    Returns:
        Detected frequency in Hz or None
    """
    # Compute FFT
    magnitudes = fft_magnitude(x, 'hanning')
    frequencies = fft_frequencies(len(x), sample_rate)
    
    # Find peak in frequency range
    max_mag = 0
    max_freq_idx = 0
    
    for i, (freq, mag) in enumerate(zip(frequencies, magnitudes)):
        if min_freq <= freq <= max_freq and mag > max_mag:
            max_mag = mag
            max_freq_idx = i
    
    if max_mag < 0.01:  # Threshold
        return None
    
    # Parabolic interpolation for better accuracy
    if 0 < max_freq_idx < len(magnitudes) - 1:
        alpha = magnitudes[max_freq_idx - 1]
        beta = magnitudes[max_freq_idx]
        gamma = magnitudes[max_freq_idx + 1]
        
        p = 0.5 * (alpha - gamma) / (alpha - 2 * beta + gamma)
        
        if abs(p) < 1:
            return frequencies[max_freq_idx] + p * (sample_rate / len(x))
    
    return frequencies[max_freq_idx]


# Note detection
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def freq_to_note(freq: float) -> Tuple[str, int, float]:
    """
    Convert frequency to note name, octave, and cents deviation.
    
    Args:
        freq: Frequency in Hz
        
    Returns:
        Tuple of (note_name, octave, cents)
    """
    if freq <= 0:
        return ('', 0, 0)
    
    # A4 = 440 Hz
    a4 = 440.0
    
    # Calculate semitones from A4
    semitones = 12 * math.log2(freq / a4)
    
    # Round to nearest semitone
    note_index = int(round(semitones)) % 12
    octave = 4 + (int(round(semitones)) + 9) // 12  # A4 is note 9 in octave 4
    
    # Cents deviation
    cents = (semitones - round(semitones)) * 100
    
    note_name = NOTE_NAMES[note_index % 12]
    
    return (note_name, octave, cents)


def freq_to_musical(freq: float) -> str:
    """
    Convert frequency to musical notation string.
    
    Args:
        freq: Frequency in Hz
        
    Returns:
        String like "A4 (440.0 Hz)"
    """
    note, octave, cents = freq_to_note(freq)
    
    cents_str = ""
    if abs(cents) > 5:
        cents_str = f" ({cents:+.0f} cents)"
    
    return f"{note}{octave} ({freq:.1f} Hz){cents_str}"


if __name__ == '__main__':
    print("FFT Module - Pure Python Implementation")
    print("=" * 50)
    
    # Test with sine wave
    sample_rate = 1000
    n = 1024
    freq = 100  # Hz
    
    # Generate test signal
    t = [i / sample_rate for i in range(n)]
    signal = [math.sin(2 * math.pi * freq * ti) for ti in t]
    
    # Compute FFT
    print(f"\nTest signal: {freq} Hz sine wave")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"FFT size: {n}")
    
    magnitudes = fft_magnitude(signal, 'hanning')
    frequencies = fft_frequencies(n, sample_rate)
    
    # Find peak
    peak_idx = magnitudes.index(max(magnitudes))
    peak_freq = frequencies[peak_idx]
    peak_mag = magnitudes[peak_idx]
    
    print(f"\nDetected peak: {peak_freq:.1f} Hz (magnitude: {peak_mag:.3f})")
    
    # Pitch detection
    pitch = detect_pitch_fft(signal, sample_rate)
    print(f"Pitch detection: {pitch:.1f} Hz" if pitch else "No pitch detected")
    
    # Musical notation
    if pitch:
        print(f"Musical note: {freq_to_musical(pitch)}")
    
    # Test window functions
    print("\nWindow functions:")
    for name in WINDOWS:
        w = WINDOWS[name](64)
        print(f"  {name:20s}: min={min(w):.3f}, max={max(w):.3f}")
