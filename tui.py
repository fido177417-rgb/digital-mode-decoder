"""
Terminal User Interface for Digital Mode Decoder
Provides curses-based interactive interface with spectrum visualization.
"""
import curses
import time
import math
import sys
from collections import deque
from fft_module import SpectrumAnalyzer, detect_pitch_fft, freq_to_musical


class SpectrumDisplay:
    """ASCII spectrum display with multiple visualization modes."""
    
    def __init__(self, width=60, height=10):
        self.width = width
        self.height = height
        self.bins = [0.0] * width
        self.max_val = 1.0
        self.min_db = -80
        self.max_db = 0
    
    def update(self, magnitudes, min_freq=0, max_freq=8000):
        """Update display with new magnitude data (in dB)."""
        if not magnitudes:
            return
        
        # Resample to fit width
        step = len(magnitudes) / self.width
        for i in range(self.width):
            idx = int(i * step)
            if idx < len(magnitudes):
                self.bins[i] = magnitudes[idx]
        
        # Update range
        if self.bins:
            self.max_db = max(self.bins) if max(self.bins) > self.min_db else self.min_db + 10
    
    def render(self, mode='bars'):
        """Render spectrum as ASCII art."""
        if mode == 'bars':
            return self._render_bars()
        elif mode == 'waterfall':
            return self._render_waterfall_simple()
        else:
            return self._render_bars()
    
    def _render_bars(self):
        """Render as vertical bars."""
        lines = []
        
        # Normalize to dB range
        db_range = self.max_db - self.min_db
        if db_range <= 0:
            db_range = 1
        
        for row in range(self.height - 1, -1, -1):
            threshold_db = self.min_db + (row / self.height) * db_range
            line = ''
            for val in self.bins:
                if val >= threshold_db:
                    # Color intensity based on level
                    intensity = (val - self.min_db) / db_range
                    if intensity > 0.8:
                        line += '█'
                    elif intensity > 0.6:
                        line += '▓'
                    elif intensity > 0.4:
                        line += '▒'
                    elif intensity > 0.2:
                        line += '░'
                    else:
                        line += '·'
                else:
                    line += ' '
            lines.append(line)
        
        return lines
    
    def _render_waterfall_simple(self):
        """Render simple waterfall (last row only)."""
        lines = []
        
        db_range = self.max_db - self.min_db
        if db_range <= 0:
            db_range = 1
        
        line = ''
        for val in self.bins:
            intensity = (val - self.min_db) / db_range
            if intensity > 0.8:
                line += '█'
            elif intensity > 0.6:
                line += '▓'
            elif intensity > 0.4:
                line += '▒'
            elif intensity > 0.2:
                line += '░'
            else:
                line += ' '
        
        lines.append(line)
        return lines


class WaterfallDisplay:
    """Scrolling waterfall spectrogram."""
    
    def __init__(self, width=60, height=15):
        self.width = width
        self.height = height
        self.rows = deque(maxlen=height)
        self.min_db = -80
        self.max_db = 0
    
    def update(self, magnitudes):
        """Add a new row to the waterfall."""
        if not magnitudes:
            return
        
        # Resample to width
        row = []
        step = len(magnitudes) / self.width
        for i in range(self.width):
            idx = int(i * step)
            if idx < len(magnitudes):
                row.append(magnitudes[idx])
            else:
                row.append(self.min_db)
        
        self.rows.append(row)
        
        # Update range
        all_vals = [v for row in self.rows for v in row]
        if all_vals:
            self.max_db = max(all_vals) if max(all_vals) > self.min_db else self.min_db + 10
    
    def render(self):
        """Render waterfall display."""
        lines = []
        db_range = self.max_db - self.min_db
        if db_range <= 0:
            db_range = 1
        
        # Render rows (newest at bottom)
        for row in list(self.rows):
            line = ''
            for val in row:
                intensity = (val - self.min_db) / db_range
                # Use different characters for intensity
                if intensity > 0.9:
                    line += '@'
                elif intensity > 0.7:
                    line += '#'
                elif intensity > 0.5:
                    line += '*'
                elif intensity > 0.3:
                    line += '+'
                elif intensity > 0.1:
                    line += '.'
                else:
                    line += ' '
            lines.append(line)
        
        # Pad to height
        while len(lines) < self.height:
            lines.insert(0, ' ' * self.width)
        
        return lines
    
    def clear(self):
        """Clear waterfall."""
        self.rows.clear()


class CursesUI:
    """Curses-based terminal UI with spectrum visualization."""
    
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.height, self.width = stdscr.getmaxyx()
        
        # Setup colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)    # Decoded text
        curses.init_pair(2, curses.COLOR_CYAN, -1)     # Spectrum
        curses.init_pair(3, curses.COLOR_YELLOW, -1)   # Status
        curses.init_pair(4, curses.COLOR_RED, -1)      # Errors
        curses.init_pair(5, curses.COLOR_WHITE, -1)    # Normal
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)  # Waterfall
        
        # Layout
        self.spectrum_height = 12
        self.waterfall_height = 10
        self.status_height = 3
        self.input_height = 3
        self.output_height = self.height - self.spectrum_height - self.waterfall_height - self.status_height - self.input_height - 6
        
        # Create windows
        self.spectrum_win = curses.newwin(self.spectrum_height, self.width, 1, 0)
        self.waterfall_win = curses.newwin(self.waterfall_height, self.width, 
                                          self.spectrum_height + 2, 0)
        self.output_win = curses.newwin(self.output_height, self.width,
                                        self.spectrum_height + self.waterfall_height + 3, 0)
        self.status_win = curses.newwin(self.status_height, self.width,
                                        self.height - self.status_height - self.input_height - 2, 0)
        self.input_win = curses.newwin(self.input_height, self.width,
                                       self.height - self.input_height - 1, 0)
        
        # Displays
        self.spectrum = SpectrumDisplay(self.width - 2, self.spectrum_height - 2)
        self.waterfall = WaterfallDisplay(self.width - 2, self.waterfall_height - 2)
        
        # Input buffer
        self.input_buffer = ''
        self.input_prompt = '> '
        
        # Message log
        self.messages = deque(maxlen=100)
        self.decoded_text = ''
        
        # Status
        self.mode = 'CW'
        self.frequency = '700 Hz'
        self.sample_rate = '8000 Hz'
        self.pitch = ''
        self.status_msg = 'Ready'
        
        # Hide cursor
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.nodelay(True)
        stdscr.timeout(50)
    
    def update_spectrum(self, magnitudes, use_waterfall=True):
        """Update spectrum and waterfall displays."""
        self.spectrum.update(magnitudes)
        if use_waterfall:
            self.waterfall.update(magnitudes)
        self.render_spectrum()
        self.render_waterfall()
    
    def update_pitch(self, freq):
        """Update pitch display."""
        if freq and freq > 0:
            self.pitch = freq_to_musical(freq)
        else:
            self.pitch = ''
        self.update_status()
    
    def render_spectrum(self):
        """Render spectrum window."""
        self.spectrum_win.clear()
        self.spectrum_win.border()
        self.spectrum_win.addstr(0, 2, ' SPECTRUM ', curses.color_pair(2) | curses.A_BOLD)
        
        lines = self.spectrum.render('bars')
        for i, line in enumerate(lines):
            if i + 1 < self.spectrum_height - 1:
                try:
                    self.spectrum_win.addstr(i + 1, 1, line[:self.width-2], curses.color_pair(2))
                except curses.error:
                    pass
        
        # Add frequency labels
        try:
            self.spectrum_win.addstr(self.spectrum_height - 1, 1, 
                                    '0Hz', curses.color_pair(5))
            self.spectrum_win.addstr(self.spectrum_height - 1, self.width - 6,
                                    '8kHz', curses.color_pair(5))
        except curses.error:
            pass
        
        self.spectrum_win.refresh()
    
    def render_waterfall(self):
        """Render waterfall window."""
        self.waterfall_win.clear()
        self.waterfall_win.border()
        self.waterfall_win.addstr(0, 2, ' WATERFALL ', curses.color_pair(6) | curses.A_BOLD)
        
        lines = self.waterfall.render()
        for i, line in enumerate(lines):
            if i + 1 < self.waterfall_height - 1:
                try:
                    self.waterfall_win.addstr(i + 1, 1, line[:self.width-2], curses.color_pair(6))
                except curses.error:
                    pass
        
        self.waterfall_win.refresh()
    
    def add_decoded_char(self, char):
        """Add a decoded character to output."""
        self.decoded_text += char
        self.render_output()
    
    def set_decoded_text(self, text):
        """Set the complete decoded text."""
        self.decoded_text = text
        self.render_output()
    
    def add_message(self, msg, msg_type='info'):
        """Add a message to the log."""
        timestamp = time.strftime('%H:%M:%S')
        self.messages.append((timestamp, msg, msg_type))
        self.render_output()
    
    def render_output(self):
        """Render output window."""
        self.output_win.clear()
        self.output_win.border()
        self.output_win.addstr(0, 2, ' DECODED OUTPUT ', curses.color_pair(1) | curses.A_BOLD)
        
        y = 1
        max_y = self.output_height - 2
        
        # Show decoded text
        if self.decoded_text:
            text = self.decoded_text[-500:]
            words = text.split()
            line = ''
            for word in words:
                test_line = line + ' ' + word if line else word
                if len(test_line) < self.width - 4:
                    line = test_line
                else:
                    if y < max_y:
                        try:
                            self.output_win.addstr(y, 2, line, curses.color_pair(1))
                        except curses.error:
                            pass
                        y += 1
                    line = word
            if line and y < max_y:
                try:
                    self.output_win.addstr(y, 2, line, curses.color_pair(1))
                except curses.error:
                    pass
                y += 1
        
        # Show recent messages
        for timestamp, msg, msg_type in list(self.messages)[-5:]:
            if y >= max_y:
                break
            color = curses.color_pair(5)
            if msg_type == 'error':
                color = curses.color_pair(4)
            elif msg_type == 'status':
                color = curses.color_pair(3)
            try:
                self.output_win.addstr(y, 2, f"[{timestamp}] {msg}", color)
            except curses.error:
                pass
            y += 1
        
        self.output_win.refresh()
    
    def update_status(self):
        """Update status window."""
        self.status_win.clear()
        self.status_win.border()
        self.status_win.addstr(0, 2, ' STATUS ', curses.color_pair(3) | curses.A_BOLD)
        
        # Main status line
        pitch_str = f" | Pitch: {self.pitch}" if self.pitch else ""
        status_line = f"Mode: {self.mode} | Freq: {self.frequency} | Rate: {self.sample_rate}{pitch_str}"
        try:
            self.status_win.addstr(1, 2, status_line[:self.width-4], curses.color_pair(3))
            self.status_win.addstr(2, 2, self.status_msg[:self.width-4], curses.color_pair(5))
        except curses.error:
            pass
        
        self.status_win.refresh()
    
    def render_input(self):
        """Render input window."""
        self.input_win.clear()
        self.input_win.border()
        self.input_win.addstr(0, 2, ' COMMANDS ', curses.color_pair(3) | curses.A_BOLD)
        
        try:
            self.input_win.addstr(1, 1, self.input_prompt + self.input_buffer, curses.color_pair(5))
        except curses.error:
            pass
        
        self.input_win.refresh()
    
    def get_input(self):
        """Get user input."""
        try:
            key = self.stdscr.getch()
        except:
            return None
        
        if key == -1:
            return None
        
        if key == ord('\n') or key == curses.KEY_ENTER:
            cmd = self.input_buffer
            self.input_buffer = ''
            self.render_input()
            return cmd
        elif key == curses.KEY_BACKSPACE or key == 127:
            self.input_buffer = self.input_buffer[:-1]
            self.render_input()
        elif 32 <= key <= 126:
            self.input_buffer += chr(key)
            self.render_input()
        
        return None
    
    def render_all(self):
        """Render all windows."""
        self.render_spectrum()
        self.render_waterfall()
        self.render_output()
        self.update_status()
        self.render_input()
    
    def set_mode(self, mode):
        """Set decoder mode."""
        self.mode = mode
        self.update_status()
    
    def set_frequency(self, freq):
        """Set displayed frequency."""
        self.frequency = freq
        self.update_status()
    
    def set_status(self, msg):
        """Set status message."""
        self.status_msg = msg
        self.update_status()
    
    def clear_decoded(self):
        """Clear decoded text."""
        self.decoded_text = ''
        self.render_output()
    
    def clear_waterfall(self):
        """Clear waterfall display."""
        self.waterfall.clear()
        self.render_waterfall()


class SimpleTUI:
    """Simple terminal UI without curses."""
    
    def __init__(self):
        self.mode = 'CW'
        self.frequency = '700 Hz'
        self.decoded_text = ''
        self.messages = []
        self.spectrum_data = []
    
    def render(self):
        """Render simple text output."""
        print('\033[2J\033[H')
        print('=' * 60)
        print(' DIGITAL MODE DECODER')
        print('=' * 60)
        print(f' Mode: {self.mode} | Frequency: {self.frequency}')
        print('-' * 60)
        
        # Simple spectrum
        if self.spectrum_data:
            print(' Spectrum:')
            max_val = max(self.spectrum_data) if self.spectrum_data else 1
            for i in range(0, len(self.spectrum_data), 4):
                val = self.spectrum_data[i]
                bar_len = int((val / max_val) * 40) if max_val > 0 else 0
                print(f'   {"█" * bar_len}')
        
        print('-' * 60)
        print(' Decoded:')
        if self.decoded_text:
            lines = self.decoded_text.split('\n')
            for line in lines[-10:]:
                print(f'   {line}')
        
        print('-' * 60)
        print(' Commands: (q)uit (m)ode (f)requency (c)lear (s)pectrum')
        print('=' * 60)
    
    def add_decoded_char(self, char):
        self.decoded_text += char
    
    def set_decoded_text(self, text):
        self.decoded_text = text
    
    def add_message(self, msg, msg_type='info'):
        timestamp = time.strftime('%H:%M:%S')
        self.messages.append(f"[{timestamp}] {msg}")
    
    def update_spectrum(self, magnitudes):
        self.spectrum_data = magnitudes
    
    def update_pitch(self, freq):
        pass
    
    def set_mode(self, mode):
        self.mode = mode
    
    def set_frequency(self, freq):
        self.frequency = freq
    
    def set_status(self, msg):
        pass
    
    def clear_decoded(self):
        self.decoded_text = ''
    
    def clear_waterfall(self):
        self.spectrum_data = []


def create_ui(use_curses=True):
    """Create appropriate UI based on environment."""
    if use_curses:
        try:
            import curses
            return curses.wrapper(CursesUI)
        except Exception:
            return SimpleTUI()
    return SimpleTUI()
