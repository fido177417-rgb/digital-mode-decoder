"""
Audio Input Handler
Supports both file input and microphone input via pyaudio.
"""
import struct
import wave
import os
from pathlib import Path


class AudioFileReader:
    """Read audio from WAV files."""
    
    def __init__(self):
        self.sample_rate = None
        self.channels = None
        self.sample_width = None
    
    def read_wav(self, filepath):
        """
        Read a WAV file and return audio samples.
        
        Args:
            filepath: Path to WAV file
            
        Returns:
            Tuple of (samples, sample_rate)
            samples: List of float samples (-1.0 to 1.0)
        """
        with wave.open(filepath, 'rb') as wf:
            self.channels = wf.getnchannels()
            self.sample_width = wf.getsampwidth()
            self.sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            
            raw_data = wf.readframes(n_frames)
        
        # Convert to samples based on bit depth
        if self.sample_width == 1:
            # 8-bit unsigned
            samples = [((b - 128) / 128.0) for b in raw_data]
        elif self.sample_width == 2:
            # 16-bit signed
            n_samples = len(raw_data) // 2
            samples = struct.unpack(f'<{n_samples}h', raw_data)
            samples = [s / 32768.0 for s in samples]
        elif self.sample_width == 3:
            # 24-bit signed (packed)
            samples = []
            for i in range(0, len(raw_data), 3):
                val = int.from_bytes(raw_data[i:i+3], byteorder='little', signed=True)
                samples.append(val / 8388608.0)
        elif self.sample_width == 4:
            # 32-bit signed
            n_samples = len(raw_data) // 4
            samples = struct.unpack(f'<{n_samples}i', raw_data)
            samples = [s / 2147483648.0 for s in samples]
        else:
            raise ValueError(f"Unsupported sample width: {self.sample_width}")
        
        # Convert to mono if stereo
        if self.channels == 2:
            mono_samples = []
            for i in range(0, len(samples), 2):
                mono_samples.append((samples[i] + samples[i+1]) / 2.0)
            samples = mono_samples
        
        return samples, self.sample_rate
    
    def read_raw_audio(self, filepath, sample_rate=8000, sample_width=2, channels=1):
        """
        Read raw audio file.
        
        Args:
            filepath: Path to raw audio file
            sample_rate: Sample rate
            sample_width: Bytes per sample
            channels: Number of channels
            
        Returns:
            Tuple of (samples, sample_rate)
        """
        with open(filepath, 'rb') as f:
            raw_data = f.read()
        
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.channels = channels
        
        if sample_width == 2:
            n_samples = len(raw_data) // 2
            samples = struct.unpack(f'<{n_samples}h', raw_data)
            samples = [s / 32768.0 for s in samples]
        elif sample_width == 1:
            samples = [((b - 128) / 128.0) for b in raw_data]
        else:
            raise ValueError(f"Unsupported sample width: {sample_width}")
        
        # Convert to mono if needed
        if channels == 2:
            mono_samples = []
            for i in range(0, len(samples), 2):
                mono_samples.append((samples[i] + samples[i+1]) / 2.0)
            samples = mono_samples
        
        return samples, sample_rate
    
    def generate_tone(self, freq, duration, sample_rate=8000, amplitude=0.8):
        """
        Generate a test tone.
        
        Args:
            freq: Frequency (Hz)
            duration: Duration (seconds)
            sample_rate: Sample rate (Hz)
            amplitude: Amplitude (0.0-1.0)
            
        Returns:
            List of audio samples
        """
        import math
        n_samples = int(sample_rate * duration)
        samples = []
        
        for i in range(n_samples):
            t = i / sample_rate
            sample = amplitude * math.sin(2 * math.pi * freq * t)
            samples.append(sample)
        
        return samples
    
    def generate_noise(self, duration, sample_rate=8000, amplitude=0.1):
        """
        Generate white noise.
        
        Args:
            duration: Duration (seconds)
            sample_rate: Sample rate (Hz)
            amplitude: Amplitude (0.0-1.0)
            
        Returns:
            List of audio samples
        """
        import random
        n_samples = int(sample_rate * duration)
        samples = [random.uniform(-amplitude, amplitude) for _ in range(n_samples)]
        return samples
    
    def save_wav(self, samples, filepath, sample_rate=8000):
        """
        Save audio samples to WAV file.
        
        Args:
            samples: List of float samples (-1.0 to 1.0)
            filepath: Output path
            sample_rate: Sample rate
        """
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            
            # Convert to 16-bit
            int_samples = [int(s * 32767) for s in samples]
            raw_data = struct.pack(f'<{len(int_samples)}h', *int_samples)
            wf.writeframes(raw_data)


class AudioInputProcessor:
    """Process audio input from various sources."""
    
    def __init__(self, sample_rate=8000):
        self.sample_rate = sample_rate
        self.reader = AudioFileReader()
        self.buffer = []
    
    def process_file(self, filepath, processor_func, chunk_size=1024):
        """
        Process an audio file in chunks.
        
        Args:
            filepath: Path to audio file
            processor_func: Function to call with each chunk
            chunk_size: Number of samples per chunk
            
        Returns:
            Aggregated results from processor_func
        """
        samples, sample_rate = self.reader.read_wav(filepath)
        self.sample_rate = sample_rate
        
        results = []
        for i in range(0, len(samples), chunk_size):
            chunk = samples[i:i + chunk_size]
            result = processor_func(chunk)
            if result:
                results.append(result)
        
        return results
    
    def create_test_signal(self, mode='cw', freq=700, duration=5.0):
        """
        Create a test signal for decoder testing.
        
        Args:
            mode: 'cw', 'rtty', or 'ft8'
            freq: Base frequency (Hz)
            duration: Duration in seconds
            
        Returns:
            List of audio samples
        """
        if mode == 'cw':
            return self._create_cw_test_signal(freq, duration)
        elif mode == 'rtty':
            return self._create_rtty_test_signal(freq, duration)
        elif mode == 'ft8':
            return self._create_ft8_test_signal(freq, duration)
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    def _create_cw_test_signal(self, freq, duration):
        """Create CW test signal (SOS)."""
        import math
        
        # SOS pattern: ... --- ...
        unit = 0.1  # 100ms per unit
        samples = []
        
        pattern = [
            ('on', unit), ('off', unit),     # .
            ('on', unit), ('off', unit),     # .
            ('on', unit), ('off', unit),     # .
            ('on', unit * 3), ('off', unit), # -
            ('on', unit * 3), ('off', unit), # -
            ('on', unit * 3), ('off', unit), # -
            ('on', unit), ('off', unit),     # .
            ('on', unit), ('off', unit),     # .
            ('on', unit), ('off', unit * 3), # .
        ]
        
        total_time = 0
        while total_time < duration:
            for state, dur in pattern:
                n_samples = int(self.sample_rate * dur)
                
                if state == 'on':
                    for i in range(n_samples):
                        t = i / self.sample_rate
                        sample = 0.7 * math.sin(2 * math.pi * freq * t)
                        samples.append(sample)
                else:
                    samples.extend([0.0] * n_samples)
                
                total_time += dur
                if total_time >= duration:
                    break
        
        return samples[:int(self.sample_rate * duration)]
    
    def _create_rtty_test_signal(self, freq, duration):
        """Create RTTY test signal."""
        # RTTY not implemented in detail here
        return self.generate_tone(freq, duration)
    
    def _create_ft8_test_signal(self, freq, duration):
        """Create FT8 test signal."""
        # FT8 not implemented in detail here
        return self.generate_tone(freq, duration)
    
    def generate_tone(self, freq, duration, amplitude=0.7):
        """Generate a simple tone."""
        import math
        n_samples = int(self.sample_rate * duration)
        samples = []
        
        for i in range(n_samples):
            t = i / self.sample_rate
            sample = amplitude * math.sin(2 * math.pi * freq * t)
            samples.append(sample)
        
        return samples


class MicrophoneInput:
    """
    Microphone input handler using pyaudio.
    Falls back to file input if pyaudio not available.
    """
    
    def __init__(self, sample_rate=8000, chunk_size=1024):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.stream = None
        self.pa = None
        
        try:
            import pyaudio
            self.pa = pyaudio.PyAudio()
            self.available = True
        except ImportError:
            self.available = False
            print("pyaudio not available - microphone input disabled")
    
    def open(self, device_index=None):
        """Open microphone stream."""
        if not self.available:
            raise RuntimeError("pyaudio not available")
        
        self.stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            input_device_index=device_index
        )
    
    def read_chunk(self):
        """Read a chunk of audio from microphone."""
        if not self.stream:
            raise RuntimeError("Stream not open")
        
        import pyaudio
        data = self.stream.read(self.chunk_size, exception_on_overflow=False)
        
        # Convert to float samples
        int_samples = struct.unpack(f'<{self.chunk_size}h', data)
        samples = [s / 32768.0 for s in int_samples]
        
        return samples
    
    def close(self):
        """Close microphone stream."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.pa:
            self.pa.terminate()
    
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    print("Audio Input Handler")
    print("=" * 50)
    
    reader = AudioFileReader()
    
    # Generate test tone
    print("\nGenerating test tone...")
    samples = reader.generate_tone(700, 2.0, sample_rate=8000)
    print(f"Generated {len(samples)} samples")
    
    # Save to file
    reader.save_wav(samples, '/tmp/test_tone.wav', sample_rate=8000)
    print("Saved to /tmp/test_tone.wav")
    
    # Read it back
    samples2, rate = reader.read_wav('/tmp/test_tone.wav')
    print(f"Read back {len(samples2)} samples at {rate} Hz")
    
    # Check microphone availability
    mic = MicrophoneInput()
    print(f"\nMicrophone available: {mic.available}")
