"""
Android MediaRecorder Integration
Uses Termux API for microphone recording on Android.
"""
import subprocess
import os
import time
import threading
import signal
from pathlib import Path


class AndroidMediaRecorder:
    """
    Record audio from Android microphone using Termux API.
    
    Termux API commands:
        termux-microphone-record - Record audio
        termux-microphone-info - Get microphone info
        termux-media-player - Play audio
    """
    
    def __init__(self, output_dir=None):
        """
        Initialize MediaRecorder.
        
        Args:
            output_dir: Directory to save recordings
        """
        self.output_dir = output_dir or os.path.expanduser('~/.digital-mode-decoder/recordings')
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.recording = False
        self.current_file = None
        self.recording_process = None
        
        # Check if Termux API is available
        self.available = self._check_termux_api()
    
    def _check_termux_api(self):
        """Check if Termux API is available."""
        try:
            result = subprocess.run(
                ['termux-microphone-info'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def get_microphone_info(self):
        """
        Get information about available microphones.
        
        Returns:
            Dict with microphone info
        """
        if not self.available:
            return {'error': 'Termux API not available'}
        
        try:
            result = subprocess.run(
                ['termux-microphone-info'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return {'info': result.stdout.strip()}
            else:
                return {'error': result.stderr.strip()}
        except Exception as e:
            return {'error': str(e)}
    
    def start_recording(self, filename=None, duration=None, format='wav'):
        """
        Start recording audio.
        
        Args:
            filename: Output filename (auto-generated if None)
            duration: Recording duration in seconds (None for manual stop)
            format: Audio format (wav, aac, ogg)
            
        Returns:
            Path to recording file
        """
        if not self.available:
            raise RuntimeError("Termux API not available")
        
        if self.recording:
            raise RuntimeError("Already recording")
        
        # Generate filename
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"recording_{timestamp}.{format}"
        
        self.current_file = os.path.join(self.output_dir, filename)
        
        # Build command
        cmd = ['termux-microphone-record']
        
        if duration:
            cmd.extend(['-l', str(duration)])
        
        cmd.extend(['-f', self.current_file])
        
        try:
            # Start recording in background
            self.recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.recording = True
            print(f"Recording started: {self.current_file}")
            
            # If duration specified, wait for completion
            if duration:
                def stop_after_delay():
                    time.sleep(duration)
                    if self.recording:
                        self.stop_recording()
                
                timer = threading.Thread(target=stop_after_delay, daemon=True)
                timer.start()
            
            return self.current_file
        
        except Exception as e:
            self.recording = False
            raise RuntimeError(f"Failed to start recording: {e}")
    
    def stop_recording(self):
        """
        Stop current recording.
        
        Returns:
            Path to recorded file
        """
        if not self.recording:
            return None
        
        try:
            # Send interrupt to stop recording
            if self.recording_process:
                self.recording_process.send_signal(signal.SIGINT)
                self.recording_process.wait(timeout=5)
            
            self.recording = False
            print(f"Recording stopped: {self.current_file}")
            
            return self.current_file
        
        except Exception as e:
            print(f"Error stopping recording: {e}")
            self.recording = False
            return None
    
    def record_seconds(self, seconds, filename=None):
        """
        Record for a specific duration.
        
        Args:
            seconds: Duration in seconds
            filename: Output filename
            
        Returns:
            Path to recorded file
        """
        return self.start_recording(filename=filename, duration=seconds)
    
    def record_until_enter(self, filename=None):
        """
        Record until user presses Enter.
        
        Args:
            filename: Output filename
            
        Returns:
            Path to recorded file
        """
        if not self.available:
            raise RuntimeError("Termux API not available")
        
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"recording_{timestamp}.wav"
        
        self.current_file = os.path.join(self.output_dir, filename)
        
        print(f"Recording to: {self.current_file}")
        print("Press Enter to stop...")
        
        # Start recording in background
        cmd = ['termux-microphone-record', '-f', self.current_file]
        
        self.recording_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self.recording = True
        
        # Wait for user input
        try:
            input()  # Wait for Enter
        except (EOFError, KeyboardInterrupt):
            pass
        
        # Stop recording
        self.stop_recording()
        
        return self.current_file
    
    def list_recordings(self):
        """
        List all recordings in output directory.
        
        Returns:
            List of recording file paths
        """
        recordings = []
        
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith(('.wav', '.aac', '.ogg', '.mp4')):
                    recordings.append(os.path.join(self.output_dir, f))
        
        return sorted(recordings)
    
    def delete_recording(self, filepath):
        """
        Delete a recording file.
        
        Args:
            filepath: Path to recording
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"Deleted: {filepath}")
                return True
            return False
        except Exception as e:
            print(f"Error deleting: {e}")
            return False


class AudioRecorderWithDecoder:
    """
    Record audio and decode digital modes in real-time.
    """
    
    def __init__(self, decoder):
        """
        Initialize with a decoder instance.
        
        Args:
            decoder: DigitalModeDecoder instance
        """
        self.recorder = AndroidMediaRecorder()
        self.decoder = decoder
        self.processing = False
    
    def record_and_decode(self, duration=10, mode='cw'):
        """
        Record audio and decode it.
        
        Args:
            duration: Recording duration in seconds
            mode: Decoder mode
            
        Returns:
            Decoded text
        """
        # Start recording
        print(f"Recording {duration} seconds of audio...")
        filepath = self.recorder.record_seconds(duration)
        
        if not filepath or not os.path.exists(filepath):
            print("Recording failed")
            return ''
        
        # Decode
        print("Decoding...")
        self.decoder.mode = mode
        result = self.decoder.decode_file(filepath)
        
        print(f"Decoded: {result}")
        return result
    
    def live_monitor(self, mode='cw', callback=None):
        """
        Live audio monitoring and decoding.
        Records continuously and decodes.
        
        Args:
            mode: Decoder mode
            callback: Function to call with decoded text
        """
        print("Live monitoring started (Ctrl+C to stop)...")
        
        self.processing = True
        chunk_duration = 2  # seconds per chunk
        
        try:
            while self.processing:
                # Record a chunk
                timestamp = time.strftime('%H%M%S')
                filename = f"live_{timestamp}.wav"
                
                filepath = self.recorder.record_seconds(
                    duration=chunk_duration,
                    filename=filename
                )
                
                if filepath and os.path.exists(filepath):
                    # Decode chunk
                    self.decoder.mode = mode
                    result = self.decoder.decode_file(filepath)
                    
                    if result and callback:
                        callback(result)
                    elif result:
                        print(result, end='', flush=True)
                    
                    # Clean up
                    os.remove(filepath)
        
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            self.processing = False


if __name__ == '__main__':
    print("Android MediaRecorder")
    print("=" * 50)
    
    recorder = AndroidMediaRecorder()
    
    print(f"\nTermux API available: {recorder.available}")
    
    if recorder.available:
        # Get mic info
        info = recorder.get_microphone_info()
        print(f"Microphone info: {info}")
        
        # List existing recordings
        recordings = recorder.list_recordings()
        print(f"\nExisting recordings: {len(recordings)}")
        for r in recordings[:5]:
            print(f"  {os.path.basename(r)}")
        
        print("\nCommands:")
        print("  record <seconds>  - Record for N seconds")
        print("  list              - List recordings")
        print("  quit              - Exit")
        
        while True:
            try:
                cmd = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            
            if not cmd:
                continue
            
            parts = cmd.split()
            
            if parts[0] == 'quit':
                break
            elif parts[0] == 'record':
                seconds = int(parts[1]) if len(parts) > 1 else 5
                filepath = recorder.record_seconds(seconds)
                print(f"Saved: {filepath}")
            elif parts[0] == 'list':
                for r in recorder.list_recordings():
                    print(f"  {r}")
    else:
        print("\nTermux API not available.")
        print("Install with: pkg install termux-api")
        print("Also install Termux:API app from F-Droid")
