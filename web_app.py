#!/usr/bin/env python3
"""
Digital Mode Decoder - Web UI
Flask-based web interface for CW/FT8/RTTY decoding.
"""
import os
import sys
import json
import time
import wave
import struct
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cw_decoder import CWDecoder
from rtty_decoder import RTTYDecoder
from ft8_decoder import FT8Decoder
from fft_module import FFTAnalyzer, detect_pitch_fft
from audio_input import AudioFileReader

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

UPLOAD_DIR = Path(tempfile.gettempdir()) / 'dmd_uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

def read_wav_samples(filepath):
    """Read WAV file and return samples as list of floats."""
    samples = []
    try:
        with wave.open(str(filepath), 'rb') as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
            
            if sampwidth == 2:
                fmt = f'<{n_frames * n_channels}h'
                data = struct.unpack(fmt, raw)
                samples = [s / 32768.0 for s in data]
            elif sampwidth == 1:
                samples = [(b - 128) / 128.0 for b in raw]
            
            if n_channels > 1:
                samples = samples[::n_channels]
    except Exception as e:
        print(f"Error reading WAV: {e}")
    return samples

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/decode', methods=['POST'])
def decode_audio():
    """Decode uploaded audio file."""
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    file = request.files['audio']
    mode = request.form.get('mode', 'cw')
    
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    
    ext = Path(file.filename).suffix.lower()
    if ext not in ['.wav', '.raw', '.pcm', '.txt', '.bin']:
        return jsonify({'error': f'Unsupported format: {ext}'}), 400
    
    filepath = UPLOAD_DIR / f"{int(time.time())}_{file.filename}"
    file.save(str(filepath))
    
    try:
        if ext == '.txt':
            with open(filepath, 'r') as f:
                content = f.read()
            return jsonify({
                'mode': 'text',
                'decoded': content,
                'filename': file.filename
            })
        
        samples = read_wav_samples(filepath)
        if not samples:
            return jsonify({'error': 'Could not read audio data'}), 400
        
        result = {'mode': mode, 'filename': file.filename, 'samples': len(samples)}
        
        if mode == 'cw':
            decoder = CWDecoder(sample_rate=8000, tone_freq=700)
            decoded_text = decoder.decode_samples(samples)
            result['decoded'] = decoded_text
            result['settings'] = {'tone_freq': 700, 'sample_rate': 8000}
        
        elif mode == 'rtty':
            shift = int(request.form.get('shift', 170))
            baud = float(request.form.get('baud', 45.45))
            decoder = RTTYDecoder(sample_rate=8000, shift=shift, baud=baud)
            decoded_text = decoder.decode_samples(samples)
            result['decoded'] = decoded_text
            result['settings'] = {'shift': shift, 'baud': baud}
        
        elif mode == 'ft8':
            decoder = FT8Decoder()
            result['decoded'] = 'FT8 decoding requires external tools (wsjtx)'
            result['info'] = 'Upload .wav from WSJT-X for full decoding'
        
        else:
            return jsonify({'error': f'Unknown mode: {mode}'}), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        filepath.unlink(missing_ok=True)

@app.route('/api/analyze', methods=['POST'])
def analyze_spectrum():
    """Analyze spectrum of uploaded audio."""
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    file = request.files['audio']
    filepath = UPLOAD_DIR / f"{int(time.time())}_{file.filename}"
    file.save(str(filepath))
    
    try:
        samples = read_wav_samples(filepath)
        if not samples:
            return jsonify({'error': 'Could not read audio data'}), 400
        
        fft = FFTAnalyzer(sample_rate=8000)
        magnitudes = fft.compute_magnitude(samples)
        freqs = fft.get_frequencies(len(magnitudes))
        
        peaks = []
        for i in range(len(magnitudes)):
            if magnitudes[i] > 0.1:
                peaks.append({'freq': round(freqs[i], 1), 'mag': round(magnitudes[i], 3)})
        
        top_peaks = sorted(peaks, key=lambda x: x['mag'], reverse=True)[:10]
        
        return jsonify({
            'sample_rate': 8000,
            'n_samples': len(samples),
            'duration': round(len(samples) / 8000.0, 2),
            'top_peaks': top_peaks
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        filepath.unlink(missing_ok=True)

@app.route('/api/morse-table')
def morse_table():
    """Return Morse code lookup table."""
    from cw_decoder import MORSE_TABLE
    return jsonify(MORSE_TABLE)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='127.0.0.1', port=port, debug=False)
