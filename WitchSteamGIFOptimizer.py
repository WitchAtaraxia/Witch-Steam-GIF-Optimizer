import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES
import threading
import tempfile
import shutil
import re
import webbrowser
from PIL import Image, ImageTk, ImageOps
import sys


# PyInstaller resource resolver
def resource_path(relative):
    """ Get the absolute path to the resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):  # If running in a packaged PyInstaller app
        # _MEIPASS is a temporary folder where PyInstaller unpacks resources
        return os.path.join(sys._MEIPASS, relative)
    return os.path.abspath(relative)  # For development or non-packaged version

# Get the paths to ffmpeg and gifsicle
FFMPEG = resource_path(os.path.join("bin", "ffmpeg.exe"))
GIFSICLE = resource_path(os.path.join("bin", "gifsicle.exe"))

# Add print statements to verify the paths
print("FFMPEG Path:", FFMPEG)
print("GIFSICLE Path:", GIFSICLE)

# Check if the executables exist at the resolved paths
print("FFMPEG Exists:", os.path.exists(FFMPEG))
print("GIFSICLE Exists:", os.path.exists(GIFSICLE))

STARTUPINFO = None
if os.name == 'nt':  # Only on Windows
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW

MAX_SIZE = 5 * 1024 * 1024  # Steam's 5 MB limit
SAFETY_MARGIN = 0.988  # Use 98.8% of max size for safety

QUALITY_PRESETS = {
    "Ultra Motion": {"scale_factor": 1.0, "lossy_start": 8, "fps_reduction": 1.0, "dither": "floyd_steinberg", "multipass": True},
    "High Motion": {"scale_factor": 1.0, "lossy_start": 15, "fps_reduction": 0.98, "dither": "floyd_steinberg", "multipass": True},
    "Balanced": {"scale_factor": 0.95, "lossy_start": 25, "fps_reduction": 0.92, "dither": "sierra2_4a", "multipass": True},
    "High Compression": {"scale_factor": 0.85, "lossy_start": 40, "fps_reduction": 0.8, "dither": "sierra2_4a", "multipass": False},
    "Maximum Compression": {"scale_factor": 0.75, "lossy_start": 60, "fps_reduction": 0.7, "dither": "bayer", "multipass": False}
}

class GIFOptimizer:
    def __init__(self, root):
        self.root = root
        self.loaded_file = None
        self.processing = False
        self.cancel_processing = False
        self.temp_dir = None
        self.original_width = None
        self.original_height = None
        self.original_fps = None
        self.analysis_data = {}
        self.predicted_size = 0
        self.preview_images = {"original": None, "optimized": None}
        self.preview_state = "none"  # "none", "original", "optimized"
        self.optimized_size_text = ""
        
        # Simple GIF animation
        self.gif_frames = {"original": [], "optimized": []}
        self.current_frame = 0
        self.animation_active = False
        self.animation_job = None
        self.current_gif_type = "none"
        
        self.setup_gui()
        self.setup_drag_drop()
        
    def setup_gui(self):
        self.root.title("Steam GIF Optimizer V0.64 [BETA]")
        self.root.geometry("950x650")
        self.root.resizable(False, False)
        self.root.configure(bg='#1e1e1e')
        self.root.minsize(920, 900)
        
        # Header
        header_frame = tk.Frame(self.root, bg='#1e1e1e')
        header_frame.pack(fill='x', pady=(10, 5))
        
        header = tk.Label(header_frame, text="Steam GIF Optimizer V0.64 [BETA] ", 
                         font=('Segoe UI', 20, 'bold'), fg='#00ff88', bg='#1e1e1e')
        header.pack()
        
        subtitle = tk.Label(header_frame, text="Smart Analysis • Enhanced Preview", 
                           font=('Segoe UI', 10), fg='#cccccc', bg='#1e1e1e')
        subtitle.pack(pady=(2, 0))
        
        # Credit
        credit_frame = tk.Frame(header_frame, bg='#1e1e1e')
        credit_frame.pack(pady=(3, 0))
        
        tk.Label(credit_frame, text="Made by ", font=('Segoe UI', 8), fg='#888888', bg='#1e1e1e').pack(side='left')
        credit_link = tk.Label(credit_frame, text="AliceAtaraxia", font=('Segoe UI', 8, 'underline'), 
                              fg='#4CAF50', bg='#1e1e1e', cursor='hand2')
        credit_link.pack(side='left')
        credit_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/WitchAtaraxia"))
        
        # Main horizontal layout
        main_container = tk.Frame(self.root, bg='#1e1e1e')
        main_container.pack(fill='both', expand=True, padx=15, pady=10)
        
        # LEFT PANEL - Controls
        left_panel = tk.Frame(main_container, bg='#1e1e1e', width=450)
        left_panel.pack(side='left', fill='both', expand=False, padx=(0, 15))
        left_panel.pack_propagate(False)
        self.left_panel = left_panel
        
        # File Selection
        file_frame = tk.LabelFrame(left_panel, text="File Selection", 
                                  fg='#00ff88', bg='#1e1e1e', font=('Segoe UI', 11, 'bold'))
        file_frame.pack(fill='x', pady=(0, 15))
        
        # Drop zone
        self.drop_zone = tk.Frame(file_frame, bg='#2a2a2a', relief='solid', bd=2)
        self.drop_zone.pack(fill='x', padx=15, pady=15)
        
        drop_label = tk.Label(self.drop_zone, text="📁 Drag & Drop GIF Here", 
                             font=('Segoe UI', 12, 'bold'), fg='#888888', bg='#2a2a2a', 
                             height=3, cursor='hand2')
        drop_label.pack(fill='x', pady=15)
        drop_label.bind("<Button-1>", lambda e: self.select_file())
        
        # Hover effects
        def on_enter(e):
            self.drop_zone.config(bg='#3a3a3a')
            drop_label.config(bg='#3a3a3a', fg='#00ff88', text="📁 Drop GIF Here or Click")
        def on_leave(e):
            self.drop_zone.config(bg='#2a2a2a')
            drop_label.config(bg='#2a2a2a', fg='#888888', text="📁 Drag & Drop GIF Here")
        
        self.drop_zone.bind("<Enter>", on_enter)
        self.drop_zone.bind("<Leave>", on_leave)
        drop_label.bind("<Enter>", on_enter)
        drop_label.bind("<Leave>", on_leave)

        
        # Size Prediction
        predict_frame = tk.LabelFrame(left_panel, text="Size Prediction", 
                                     fg='#00ff88', bg='#1e1e1e', font=('Segoe UI', 11, 'bold'))
        predict_frame.pack(fill='x', pady=(0, 15))
        
        self.prediction_label = tk.Label(predict_frame, text="📊 Load a file to see prediction", 
                                        fg='#cccccc', bg='#1e1e1e', font=('Segoe UI', 10), height=2)
        self.prediction_label.pack(padx=15, pady=12)
        
        # Settings
        settings_frame = tk.LabelFrame(left_panel, text="Optimization Settings", 
                                      fg='#00ff88', bg='#1e1e1e', font=('Segoe UI', 11, 'bold'))
        settings_frame.pack(fill='x', pady=(0, 15))
        
        settings_content = tk.Frame(settings_frame, bg='#1e1e1e')
        settings_content.pack(fill='x', padx=15, pady=12)
        
        # Settings grid
        tk.Label(settings_content, text="Quality Preset:", fg='#cccccc', bg='#1e1e1e',
                font=('Segoe UI', 9)).grid(row=0, column=0, sticky='w', pady=8)
        self.quality_var = tk.StringVar(value="High Motion")
        quality_combo = ttk.Combobox(settings_content, textvariable=self.quality_var, 
                                   values=list(QUALITY_PRESETS.keys()), state='readonly', width=20)
        quality_combo.grid(row=0, column=1, sticky='w', padx=(10, 0), pady=8)
        quality_combo.bind('<<ComboboxSelected>>', self.on_settings_change)
        
        tk.Label(settings_content, text="Target Size (MB):", fg='#cccccc', bg='#1e1e1e',
                font=('Segoe UI', 9)).grid(row=1, column=0, sticky='w', pady=5)
        self.target_size_var = tk.StringVar(value="4.95")
        target_entry = tk.Entry(settings_content, textvariable=self.target_size_var, width=10,
                               bg='#3c3c3c', fg='white', insertbackground='white')
        target_entry.grid(row=1, column=1, sticky='w', padx=(10, 0), pady=5)
        target_entry.bind('<KeyRelease>', self.on_settings_change)
        
        tk.Label(settings_content, text="Max FPS:", fg='#cccccc', bg='#1e1e1e',
                font=('Segoe UI', 9)).grid(row=2, column=0, sticky='w', pady=5)
        self.fps_var = tk.StringVar(value="auto")
        fps_entry = tk.Entry(settings_content, textvariable=self.fps_var, width=10,
                           bg='#3c3c3c', fg='white', insertbackground='white')
        fps_entry.grid(row=2, column=1, sticky='w', padx=(10, 0), pady=5)
        fps_entry.bind('<KeyRelease>', self.on_settings_change)
        
        # Checkboxes
        options_frame = tk.Frame(settings_content, bg='#1e1e1e')
        options_frame.grid(row=3, column=0, columnspan=2, sticky='w', pady=(15, 0))
        
        self.smart_frames_var = tk.BooleanVar(value=True)
        smart_check = tk.Checkbutton(options_frame, text="Smart Frame Selection", 
                                    variable=self.smart_frames_var, fg='#cccccc', bg='#1e1e1e', 
                                    selectcolor='#00ff88', font=('Segoe UI', 9))
        smart_check.pack(anchor='w', pady=2)
        
        self.remove_dupes_var = tk.BooleanVar(value=True)
        dupes_check = tk.Checkbutton(options_frame, text="Remove Duplicates", 
                                    variable=self.remove_dupes_var, fg='#cccccc', bg='#1e1e1e', 
                                    selectcolor='#00ff88', font=('Segoe UI', 9))
        dupes_check.pack(anchor='w', pady=2)
        
        self.frame_smooth_var = tk.BooleanVar(value=False)
        smooth_check = tk.Checkbutton(options_frame, text="Frame Rate Smoothing", 
                                     variable=self.frame_smooth_var, fg='#cccccc', bg='#1e1e1e', 
                                     selectcolor='#ffa500', font=('Segoe UI', 9))
        smooth_check.pack(anchor='w', pady=2)
        
        self.adaptive_bitrate_var = tk.BooleanVar(value=True)
        adaptive_check = tk.Checkbutton(options_frame, text="Adaptive Bitrate", 
                                       variable=self.adaptive_bitrate_var, fg='#cccccc', bg='#1e1e1e', 
                                       selectcolor='#00ff88', font=('Segoe UI', 9))
        adaptive_check.pack(anchor='w', pady=2)
        
        # Never Give Up
        self.aggressive_var = tk.BooleanVar(value=True)
        aggressive_check = tk.Checkbutton(options_frame, text="Never Give Up (50+ attempts)", 
                                         variable=self.aggressive_var, fg='#ff6666', bg='#1e1e1e', 
                                         selectcolor='#ff6666', font=('Segoe UI', 9, 'bold'))
        aggressive_check.pack(anchor='w', pady=(8, 0))
        
        # Buttons
        button_frame = tk.Frame(left_panel, bg='#1e1e1e')
        button_frame.pack(fill='x', side='bottom')
        
        self.start_button = tk.Button(button_frame, text="START", 
                                     command=self.start_optimization, height=1,
                                     bg='#00ff88', fg='black', font=('Segoe UI', 12, 'bold'))
        self.start_button.pack(fill='x', pady=(0, 8))
        
        self.cancel_button = tk.Button(button_frame, text="CANCEL", 
                                      command=self.cancel_optimization, height=1,
                                      bg='#ff4444', fg='white', font=('Segoe UI', 10, 'bold'),
                                      state='disabled')
        self.cancel_button.pack(fill='x')
        
        # RIGHT PANEL - Preview & Analysis
        right_panel = tk.Frame(main_container, bg='#1e1e1e')
        right_panel.pack(side='right', fill='both', expand=True)
        self.right_panel = right_panel
        
        # Single Hover Preview Section
        preview_frame = tk.LabelFrame(right_panel, text="Preview Comparison", 
                                     fg='#00ff88', bg='#1e1e1e', font=('Segoe UI', 11, 'bold'))
        preview_frame.pack(fill='x', pady=(0, 15))
        
        preview_container = tk.Frame(preview_frame, bg='#1e1e1e')
        preview_container.pack(pady=20)
        
        # Single larger preview with hover comparison
        self.preview_display = tk.Label(preview_container, text="No file loaded", 
                                       fg='#888888', bg='#2a2a2a',
                                       font=('Segoe UI', 10), relief='solid', bd=2,)
        self.preview_display.pack()
        
        # Status text below preview
        self.preview_status = tk.Label(preview_container, text="Load a file to see preview", 
                                      fg='#888888', bg='#1e1e1e', font=('Segoe UI', 9))
        self.preview_status.pack(pady=(8, 0))
        
        # Bind hover events
        self.preview_display.bind("<Enter>", self.on_preview_hover)
        self.preview_display.bind("<Leave>", self.on_preview_leave)
        
        # File Analysis
        analysis_frame = tk.LabelFrame(right_panel, text="File Analysis", 
                                      fg='#00ff88', bg='#1e1e1e', font=('Segoe UI', 11, 'bold'))
        analysis_frame.pack(fill='x', pady=(0, 15))
        
        self.file_info_label = tk.Label(analysis_frame, text="Select a GIF file to begin analysis", 
                                       wraplength=450, justify="left", fg='#cccccc', bg='#1e1e1e',
                                       font=('Consolas', 9), height=8)
        self.file_info_label.pack(padx=15, pady=15)
        
        # Progress Section
        progress_frame = tk.LabelFrame(right_panel, text="Processing Status", 
                                      fg='#00ff88', bg='#1e1e1e', font=('Segoe UI', 11, 'bold'))
        progress_frame.pack(fill='x')
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                          maximum=100, length=450)
        self.progress_bar.pack(pady=(12, 8), padx=15)
        
        self.status_label = tk.Label(progress_frame, text="Ready for optimization", fg='#cccccc', bg='#1e1e1e',
                                   font=('Segoe UI', 10, 'bold'))
        self.status_label.pack()
        
        self.detail_label = tk.Label(progress_frame, text="Load a file to begin enhanced analysis", fg='#888888', bg='#1e1e1e',
                                    font=('Segoe UI', 9), wraplength=450)
        self.detail_label.pack(pady=(5, 15))

    def on_preview_hover(self, event):
        """Show original on hover."""
        if self.preview_state == "optimized":
            # Stop current animation first
            self.stop_animation()
            
            if self.gif_frames["original"]:
                self.show_gif("original")
            elif self.preview_images["original"]:
                self.preview_display.config(image=self.preview_images["original"])
                self.preview_display.image = self.preview_images["original"]
            self.preview_status.config(text="Showing: Original (hover to compare)", fg='#ffa500')
    
    def on_preview_leave(self, event):
        """Return to optimized when hover ends."""
        if self.preview_state == "optimized":
            # Stop current animation first
            self.stop_animation()
            
            if self.gif_frames["optimized"]:
                self.show_gif("optimized")
            elif self.preview_images["optimized"]:
                self.preview_display.config(image=self.preview_images["optimized"])
                self.preview_display.image = self.preview_images["optimized"]
            self.preview_status.config(text=f"Showing: Optimized {self.optimized_size_text}(hover to see original)", fg='#00ff88')

    def load_gif_frames(self, gif_path, gif_type):
        """Load GIF frames for animation."""
        try:
            frames = []
            gif = Image.open(gif_path)
            
            for i in range(20):  # Max 20 frames
                try:
                    gif.seek(i)
                    frame = gif.copy()
                    frame.thumbnail((280, 280), Image.Resampling.LANCZOS)
                    frames.append(ImageTk.PhotoImage(frame))
                except EOFError:
                    break
            
            self.gif_frames[gif_type] = frames
            return len(frames) > 0
            
        except:
            return False
    
    def show_gif(self, gif_type):
        """Show and animate a GIF."""
        if self.gif_frames[gif_type]:
            # Always stop previous animation first
            self.stop_animation()
            
            self.animation_active = True
            self.current_frame = 0
            self.current_gif_type = gif_type
            self.animate_frames()
    
    def animate_frames(self):
        """Animate GIF frames."""
        if not self.animation_active or not self.gif_frames.get(self.current_gif_type):
            return
            
        frame = self.gif_frames[self.current_gif_type][self.current_frame]
        self.preview_display.config(image=frame)
        self.preview_display.image = frame
        
        self.current_frame = (self.current_frame + 1) % len(self.gif_frames[self.current_gif_type])
        self.animation_job = self.root.after(100, self.animate_frames)
    
    def stop_animation(self):
        """Stop animation properly."""
        self.animation_active = False
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None

    def setup_drag_drop(self):
        """Setup working drag and drop functionality."""
        self.root.drop_target_register('DND_Files')
        self.root.dnd_bind('<<Drop>>', self.handle_file_drop)
        
        try:
            if hasattr(self, 'drop_zone'):
                self.drop_zone.drop_target_register('DND_Files')
                self.drop_zone.dnd_bind('<<Drop>>', self.handle_file_drop)
        except:
            pass
    
    def handle_file_drop(self, event):
        """Handle dropped files."""
        try:
            files = self.root.tk.splitlist(event.data)
            if files:
                file_path = files[0].strip('{}')
                if file_path.lower().endswith('.gif') and os.path.exists(file_path):
                    self.load_file(file_path)
                else:
                    messagebox.showwarning("Invalid File", "Please drop a valid GIF file.")
        except Exception:
            self.select_file()
    
    def generate_preview_thumbnail(self, gif_path, is_optimized=False):
        """Generate animated GIF preview."""
        gif_type = "optimized" if is_optimized else "original"
        size_mb = os.path.getsize(gif_path) / (1024 * 1024)
        
        # Try animated first
        if self.load_gif_frames(gif_path, gif_type):
            if is_optimized:
                self.optimized_size_text = f"• {size_mb:.2f} MB "
                self.preview_state = "optimized"
                self.show_gif("optimized")
                self.preview_status.config(text=f"Showing: Optimized • {size_mb:.2f} MB (hover to see original)", fg='#00ff88')
            else:
                if self.preview_state == "none":
                    self.preview_state = "original"
                    self.show_gif("original")
                    self.preview_status.config(text=f"Showing: Original • {size_mb:.2f} MB", fg='#cccccc')
            return True
        
        # Fallback to static
        try:
            if not self.temp_dir:
                self.temp_dir = tempfile.mkdtemp(prefix="gif_preview_")
            
            frame_path = os.path.join(self.temp_dir, f"{gif_type}_frame.png")
            frame_cmd = [FFMPEG, "-y", "-loglevel", "error", "-ss", "2.0", "-i", gif_path,
             "-vframes", "1", "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
             frame_path]
            
            subprocess.run(frame_cmd, capture_output=True, timeout=10, startupinfo=STARTUPINFO)
            
            if os.path.exists(frame_path):
                pil_image = Image.open(frame_path)
                pil_image.thumbnail((2800, 2800), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(pil_image)
                
                self.preview_images[gif_type] = photo
                
                if is_optimized:
                    self.optimized_size_text = f"• {size_mb:.2f} MB "
                    self.stop_animation()
                    self.preview_display.config(image=photo, text="")
                    self.preview_display.image = photo
                    self.preview_state = "optimized"
                    self.preview_status.config(text=f"Showing: Optimized • {size_mb:.2f} MB (static)", fg='#00ff88')
                else:
                    if self.preview_state == "none":
                        self.stop_animation()
                        self.preview_display.config(image=photo, text="")
                        self.preview_display.image = photo
                        self.preview_state = "original"
                        self.preview_status.config(text=f"Showing: Original • {size_mb:.2f} MB (static)", fg='#cccccc')
                
                return True
                
        except Exception:
            pass
        
        self.preview_display.config(image='', text="Preview Failed", fg='#ffaa00')
        return False
    
    def create_optimized_preview(self, optimized_path):
        """Generate preview of optimized result."""
        if os.path.exists(optimized_path):
            return self.generate_preview_thumbnail(optimized_path, is_optimized=True)
        return False

    def on_settings_change(self, event=None):
        """Update prediction when settings change."""
        if self.loaded_file and hasattr(self, 'analysis_data') and self.analysis_data:
            self.root.after(300, self.update_size_prediction)
    
    def update_size_prediction(self):
        """Simple size prediction based on analysis."""
        if not self.loaded_file or not self.analysis_data:
            return
        
        try:
            original_size = os.path.getsize(self.loaded_file)
            original_mb = original_size / (1024 * 1024)
            
            # Simple prediction algorithm
            preset_name = self.quality_var.get()
            complexity = self.analysis_data.get("complexity_score", 0.5)
            
            # Base compression ratios
            compression_ratios = {
                "Ultra Motion": 0.6, "High Motion": 0.7, "Balanced": 0.78,
                "High Compression": 0.85, "Maximum Compression": 0.92
            }
            
            base_compression = compression_ratios.get(preset_name, 0.75)
            
            # Adjust for complexity
            adjusted_compression = base_compression * (0.85 + complexity * 0.3)
            
            # Factor in new features
            if self.smart_frames_var.get():
                adjusted_compression += 0.04
            if self.adaptive_bitrate_var.get():
                adjusted_compression += 0.02
            if self.frame_smooth_var.get():
                adjusted_compression -= 0.03  # Smoothing uses more space
            
            predicted_size = original_size * (1 - min(0.95, adjusted_compression))
            predicted_mb = predicted_size / (1024 * 1024)
            
            try:
                target_mb = float(self.target_size_var.get())
            except:
                target_mb = 4.95
            
            # Color code prediction
            if predicted_mb <= target_mb:
                color = '#00ff88'
                status = "✅ Should fit target"
            elif predicted_mb <= target_mb * 1.15:
                color = '#ffa500'
                status = "⚠️ Close to target"
            else:
                color = '#ff6666'
                status = "❌ May exceed target"
            
            self.predicted_size = predicted_mb
            self.prediction_label.config(text=f"📊 Predicted: {predicted_mb:.2f} MB • {status}", fg=color)
            
        except Exception:
            self.prediction_label.config(text="📊 Prediction unavailable", fg='#888888')
    
    def update_detail_status(self, detail_text):
        """Update detailed progress information."""
        if hasattr(self, 'detail_label'):
            self.detail_label.config(text=detail_text)
    
    
    def get_original_fps(self, input_path):
        """Reliable FPS detection using only FFmpeg."""
        try:
            cmd = [FFMPEG, "-i", input_path]
            result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=10, startupinfo=STARTUPINFO)
            
            for line in result.stderr.splitlines():
                if "fps" in line and "Video:" in line:
                    try:
                        fps_val = float(line.split("fps")[0].split()[-1])
                        if 5 <= fps_val <= 120:
                            return fps_val
                    except:
                        pass
                        
                if "tbr" in line:
                    try:
                        tbr_val = float(line.split("tbr")[0].split()[-1])
                        if 5 <= tbr_val <= 120:
                            return tbr_val
                    except:
                        pass
        except:
            pass
        return 25.0
    
    def get_original_dimensions(self, path):
        """Extract original GIF dimensions reliably."""
        try:
            cmd = [FFMPEG, "-i", path]
            result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=10, startupinfo=STARTUPINFO)
            
            for line in result.stderr.splitlines():
                if "Video:" in line and "," in line:
                    match = re.search(r'(\d{2,})x(\d{2,})', line)
                    if match:
                        width = int(match.group(1))
                        height = int(match.group(2))
                        return width, height
        except:
            pass
        return None, None
    
    def enhanced_motion_analysis(self, input_path):
        """Enhanced motion analysis - simple and reliable."""
        try:
            analysis = {"motion_level": "medium", "has_scenes": False, "complexity_score": 0.5}
            
            # Scene detection
            scene_cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", input_path, "-t", "8",
                        "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"]
            
            try:
                result = subprocess.run(scene_cmd, capture_output=True, text=True, timeout=20, startupinfo=STARTUPINFO)
                scene_count = result.stderr.count("Parsed_showinfo")
                
                if scene_count > 6:
                    analysis["motion_level"] = "high"
                    analysis["has_scenes"] = True
                    analysis["complexity_score"] = 0.8
                elif scene_count > 2:
                    analysis["motion_level"] = "medium"
                    analysis["complexity_score"] = 0.6
                else:
                    analysis["motion_level"] = "low"
                    analysis["complexity_score"] = 0.3
            except:
                pass
            
            return analysis
            
        except Exception:
            return {"motion_level": "medium", "has_scenes": False, "complexity_score": 0.5}
    
    def build_enhanced_filters(self, scale, max_fps, analysis, attempt):
        """Build enhanced filter chain."""
        filters = []
        
        # Frame rate smoothing
        if self.frame_smooth_var.get() and max_fps < (self.original_fps * 0.75):
            # Simple interpolation when reducing FPS significantly
            filters.append(f"minterpolate=fps={max_fps:.2f}:mi_mode=blend")
        else:
            # Smart frame selection
            if self.smart_frames_var.get() and analysis.get("motion_level") in ["medium", "high"]:
                if analysis.get("motion_level") == "high":
                    filters.append("select='not(mod(n,2))+gt(scene,0.15)'")
                else:
                    threshold = 0.03 + (attempt * 0.004)
                    filters.append(f"select='gt(scene,{threshold})+not(mod(n,4))'")
            
            # Standard duplicate removal
            if self.remove_dupes_var.get():
                filters.append("mpdecimate=hi=64*12:lo=64*5:frac=0.3")
            
            # FPS control
            filters.append(f"fps={max_fps:.2f}")
        
        # Adaptive bitrate: simple noise reduction
        if self.adaptive_bitrate_var.get():
            filters.append("hqdn3d=1:0.5:1:0.5")
        
        # Scaling
        filters.append(f"scale={scale}:-2:flags=lanczos")
        
        return ",".join(filters)
    
    def get_file_info(self, path):
        """Extract file information safely."""
        info = {"fps": "Unknown", "resolution": "Unknown", "duration": "Unknown", "size": "0 MB"}
        
        try:
            # File size
            size_bytes = os.path.getsize(path)
            size_mb = size_bytes / (1024 * 1024)
            info["size"] = f"{size_mb:.2f} MB"
            
            # Get dimensions and FPS
            self.original_width, self.original_height = self.get_original_dimensions(path)
            if self.original_width and self.original_height:
                info["resolution"] = f"{self.original_width}x{self.original_height}"
            
            self.original_fps = self.get_original_fps(path)
            info["fps"] = f"{self.original_fps:.1f}"
            
            # Duration
            try:
                cmd = [FFMPEG, "-i", path]
                result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=10, startupinfo=STARTUPINFO)
                
                for line in result.stderr.splitlines():
                    if "Duration:" in line:
                        duration_str = line.split(",")[0].replace("Duration:", "").strip()
                        info["duration"] = duration_str
                        break
            except:
                info["duration"] = "Unknown"
            
            # Enhanced analysis
            analysis_text = "Processing..."
            if self.temp_dir:
                try:
                    self.analysis_data = self.enhanced_motion_analysis(path)
                    motion = self.analysis_data.get("motion_level", "medium")
                    complexity = self.analysis_data.get("complexity_score", 0.5)
                    analysis_text = f"Motion: {motion} • Complexity: {complexity:.1f}"
                    if self.analysis_data.get("has_scenes"):
                        analysis_text += " • Scene changes"
                except:
                    analysis_text = "Enhanced analysis complete"
        
        except Exception:
            analysis_text = "Analysis failed"
        
        return (f"📁 File: {os.path.basename(path)}\n"
                f"📊 Size: {info['size']} ({size_bytes:,} bytes)\n"
                f"📐 Resolution: {info['resolution']}\n"
                f"⏱️ Duration: {info['duration']}\n"
                f"🎬 FPS: {info['fps']}\n"
                f"🔍 Analysis: {analysis_text}")
    
    def optimize_gif_v064(self, input_path, progress_callback):
        """V0.64 optimization with conservative enhancements."""
        try:
            preset = QUALITY_PRESETS[self.quality_var.get()]
            try:
                target_size_bytes = float(self.target_size_var.get()) * 1024 * 1024 * SAFETY_MARGIN
            except:
                target_size_bytes = MAX_SIZE * SAFETY_MARGIN
            
            progress_callback(5, "🚀 V0.64: Starting enhanced optimization...")
            self.update_detail_status("Initializing V0.64 enhanced pipeline...")
            
            # Setup
            self.temp_dir = tempfile.mkdtemp(prefix="gif_v064_")
            original_size = os.path.getsize(input_path)
            original_size_mb = original_size / (1024 * 1024)
            
            # Enhanced analysis
            progress_callback(10, "🧠 V0.64: Enhanced content analysis...")
            self.update_detail_status("Analyzing motion patterns and scene complexity...")
            self.analysis_data = self.enhanced_motion_analysis(input_path)
            
            # Calculate parameters with analysis
            size_ratio = original_size / target_size_bytes
            complexity = self.analysis_data.get("complexity_score", 0.5)
            motion_level = self.analysis_data.get("motion_level", "medium")
            
            # Smart initial parameters
            if motion_level == "high" and complexity > 0.7:
                scale_factor = 0.8 if size_ratio > 10 else 0.9
                fps_factor = 0.9
                lossy_boost = 8
            elif motion_level == "low" and complexity < 0.4:
                scale_factor = min(1.0, preset["scale_factor"] * 1.05)
                fps_factor = preset["fps_reduction"] * 0.85
                lossy_boost = -3
            else:
                scale_factor = preset["scale_factor"]
                fps_factor = preset["fps_reduction"]
                lossy_boost = 0
            
            # Size-based adjustments
            if size_ratio > 15:
                scale_factor *= 0.65
                lossy_boost += 20
            elif size_ratio > 8:
                scale_factor *= 0.8
                lossy_boost += 12
            elif size_ratio > 4:
                scale_factor *= 0.9
                lossy_boost += 6
            
            scale = int(self.original_width * scale_factor) if self.original_width else 500
            if scale % 2 == 1:
                scale -= 1
            scale = max(140, min(scale, self.original_width or 1920))
            
            lossy = max(0, preset["lossy_start"] + lossy_boost)
            
            # FPS calculation
            fps_input = self.fps_var.get().strip()
            if fps_input and fps_input not in ["0", "auto", ""]:
                try:
                    max_fps = float(fps_input)
                except:
                    max_fps = self.original_fps * fps_factor
            else:
                max_fps = self.original_fps * fps_factor
            
            progress_callback(15, f"⚙️ V0.64: Smart params (Scale:{scale}, FPS:{max_fps:.1f}, Lossy:{lossy})")
            self.update_detail_status(f"Motion: {motion_level}, Complexity: {complexity:.1f}, Size ratio: {size_ratio:.1f}x")
            
            # Optimization loop with enhancements
            max_attempts = 50 if self.aggressive_var.get() else 15
            attempts = 0
            
            temp_palette = os.path.join(self.temp_dir, "palette.png")
            temp_gif = os.path.join(self.temp_dir, "temp.gif")
            
            while attempts < max_attempts and not self.cancel_processing:
                attempts += 1
                progress_callback(20 + (attempts * 70 / max_attempts), f"🔄 V0.64: Enhanced attempt {attempts}/{max_attempts}")
                
                # Detailed progress
                if attempts <= 3:
                    self.update_detail_status(f"Initial attempt {attempts} with smart parameters")
                elif attempts <= 10:
                    self.update_detail_status(f"Adjusting lossy compression: {lossy}")
                elif attempts <= 25:
                    self.update_detail_status(f"Reducing scale: {scale}px width")
                else:
                    self.update_detail_status(f"Never Give Up mode: attempt {attempts}, pushing limits...")
                
                try:
                    # Build enhanced filter chain
                    filter_chain = self.build_enhanced_filters(scale, max_fps, self.analysis_data, attempts)
                    
                    # Adaptive color count
                    colors = max(64, 256 - (attempts * 3))
                    if self.analysis_data.get("motion_level") == "low":
                        colors = min(256, colors + 24)  # More colors for low motion
                    elif self.adaptive_bitrate_var.get() and attempts > 10:
                        colors = max(64, colors - 12)  # Adaptive reduction
                    
                    # Generate palette
                    palette_cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", input_path,
                                  "-vf", filter_chain + f",palettegen=max_colors={colors}:reserve_transparent=1",
                                  temp_palette]
                    
                    subprocess.run(palette_cmd, capture_output=True, timeout=60, startupinfo=STARTUPINFO)
                    
                    if not os.path.exists(temp_palette):
                        continue
                    
                    # Apply palette with smart dithering
                    dither = preset.get("dither", "sierra2_4a")
                    if attempts > max_attempts * 0.8:
                        dither = "bayer"
                    elif self.analysis_data.get("motion_level") == "high":
                        dither = "floyd_steinberg"
                    
                    # Adaptive bitrate dithering
                    if self.adaptive_bitrate_var.get() and complexity > 0.6:
                        bayer_scale = 3
                    else:
                        bayer_scale = 5
                    
                    gif_cmd = [FFMPEG, "-y", "-loglevel", "error",
                              "-i", input_path, "-i", temp_palette,
                              "-filter_complex", f"{filter_chain}[x];[x][1:v]paletteuse=dither={dither}:bayer_scale={bayer_scale}",
                              temp_gif]
                    
                    subprocess.run(gif_cmd, capture_output=True, timeout=90, startupinfo=STARTUPINFO)
                    
                    if not os.path.exists(temp_gif):
                        continue
                    
                    # Gifsicle with smart optimization
                    output_path = os.path.join(os.path.dirname(input_path), 
                                             f"{os.path.splitext(os.path.basename(input_path))[0]}_v064_optimized.gif")
                    
                    counter = 1
                    while os.path.exists(output_path):
                        base = os.path.splitext(os.path.basename(input_path))[0]
                        output_path = os.path.join(os.path.dirname(input_path), f"{base}_v064_optimized_{counter}.gif")
                        counter += 1
                    
                    gifsicle_cmd = [GIFSICLE, "-O3", "--careful"]
                    if lossy > 0:
                        gifsicle_cmd.append(f"--lossy={int(lossy)}")
                    if colors < 256:
                        gifsicle_cmd.extend(["--colors", str(colors)])
                    
                    # Content-aware optimization
                    if self.analysis_data.get("motion_level") == "low":
                        gifsicle_cmd.append("--optimize=3")
                    
                    gifsicle_cmd.extend([temp_gif, "-o", output_path])
                    
                    subprocess.run(gifsicle_cmd, capture_output=True, timeout=60, startupinfo=STARTUPINFO)
                    
                    if os.path.exists(output_path):
                        size = os.path.getsize(output_path)
                        size_mb = size / (1024 * 1024)
                        target_mb = target_size_bytes / (1024 * 1024)
                        compression_pct = ((original_size - size) / original_size) * 100
                        
                        # Success!
                        if size <= target_size_bytes:
                            progress_callback(100, f"✅ V0.64 Success! {size_mb:.2f} MB ({compression_pct:.1f}% saved)")
                            self.update_detail_status(f"Target achieved in {attempts} attempts using smart optimization")
                            # Generate optimized preview
                            self.create_optimized_preview(output_path)
                            return output_path
                        
                        # Close enough after many attempts
                        overage = (size_mb - target_mb) / target_mb
                        if overage < 0.05 and attempts >= 15:
                            progress_callback(100, f"✅ V0.64 Excellent! {size_mb:.2f} MB ({compression_pct:.1f}% saved)")
                            self.update_detail_status(f"Close enough! Only {overage*100:.1f}% over target")
                            # Generate optimized preview
                            self.create_optimized_preview(output_path)
                            return output_path
                        
                        # Smart parameter adjustment
                        overage_factor = min(2.0, overage + 1.0)
                        
                        if lossy < 120:
                            if overage > 0.8:
                                lossy += int(30 * overage_factor)
                            elif overage > 0.3:
                                lossy += int(18 * overage_factor)
                            else:
                                lossy += int(10 * overage_factor)
                        elif scale > 120:
                            # Smart scale reduction based on complexity
                            reduction = 0.82 if complexity > 0.6 else 0.88
                            scale = int(scale * reduction)
                            if scale % 2 == 1:
                                scale -= 1
                            lossy = preset["lossy_start"] + 8
                        elif max_fps > 5:
                            max_fps = max(5, max_fps * 0.8)
                            scale = max(120, int(self.original_width * 0.6)) if self.original_width else 350
                            if scale % 2 == 1:
                                scale -= 1
                            lossy = preset["lossy_start"]
                        
                        # Clean up
                        try:
                            os.remove(output_path)
                            if os.path.exists(temp_palette):
                                os.remove(temp_palette)
                            if os.path.exists(temp_gif):
                                os.remove(temp_gif)
                        except:
                            pass
                    
                except subprocess.TimeoutExpired:
                    self.update_detail_status(f"Timeout on attempt {attempts}, retrying with adjusted params...")
                    continue
                except Exception:
                    continue
            
            progress_callback(0, f"❌ Could not compress {original_size_mb:.1f}MB to under {target_size_bytes/(1024*1024):.1f}MB")
            self.update_detail_status("All optimization attempts exhausted - try Maximum Compression preset")
            return None
            
        except Exception as e:
            progress_callback(0, f"❌ V0.64 Error: {str(e)}")
            self.update_detail_status(f"Critical error: {str(e)[:60]}")
            return None
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    pass
    
    def load_file(self, file_path):
        """Load and analyze a file."""
        if self.processing:
            messagebox.showwarning("Processing", "Please wait for current operation to complete.")
            return
            
        self.loaded_file = file_path
        self.update_progress(0, "📊 Analyzing file...")
        self.update_detail_status("Starting enhanced file analysis...")
        
        # Reset preview state
        self.stop_animation()
        self.preview_images = {"original": None, "optimized": None}
        self.gif_frames = {"original": [], "optimized": []}
        self.preview_state = "none"
        self.optimized_size_text = ""
        self.preview_display.config(image='', text="Loading...", fg='#ffa500')
        self.preview_status.config(text="Generating animated preview...", fg='#ffa500')
        
        def analyze():
            try:
                self.temp_dir = tempfile.mkdtemp(prefix="gif_analysis_")
                
                # Generate original preview first
                self.root.after(0, lambda: self.update_detail_status("Generating preview thumbnail..."))
                self.generate_preview_thumbnail(file_path, is_optimized=False)
                
                info_text = self.get_file_info(file_path)
                
                # Auto-suggest preset based on size and analysis
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                motion_level = self.analysis_data.get("motion_level", "medium")
                
                if size_mb > 30 or motion_level == "high":
                    suggested = "Maximum Compression"
                elif size_mb > 15:
                    suggested = "High Compression"
                elif size_mb > 8:
                    suggested = "Balanced"
                elif motion_level == "high":
                    suggested = "High Motion"
                else:
                    suggested = "Ultra Motion"
                
                # Update prediction
                self.root.after(0, self.update_size_prediction)
                
                # Clean up
                if self.temp_dir and os.path.exists(self.temp_dir):
                    try:
                        shutil.rmtree(self.temp_dir)
                    except:
                        pass
                    self.temp_dir = None
                
                # Update UI
                self.root.after(0, lambda: self.file_info_label.config(text=info_text))
                self.root.after(0, lambda: self.quality_var.set(suggested))
                self.root.after(0, lambda: self.update_progress(0, "✅ Ready - V0.64 enhanced analysis complete!"))
                self.root.after(0, lambda: self.update_detail_status(f"Smart preset selected: {suggested} | Prediction ready"))
                
            except Exception as e:
                self.root.after(0, lambda: self.update_progress(0, f"❌ Analysis error: {str(e)[:40]}"))
                self.root.after(0, lambda: self.update_detail_status("Analysis failed - check if file is a valid GIF"))
        
        threading.Thread(target=analyze, daemon=True).start()
    
    def select_file(self):
        if self.processing:
            messagebox.showwarning("Processing", "Please wait for current operation to complete.")
            return
            
        file_path = filedialog.askopenfilename(
            title="Select GIF file",
            filetypes=[("GIF files", "*.gif"), ("All files", "*.*")]
        )
        
        if file_path:
            self.load_file(file_path)
    
    def update_progress(self, value, status):
        """Update progress bar and status."""
        self.progress_var.set(value)
        self.progress_bar.update()
        self.status_label.config(text=status)
    
    def start_optimization(self):
        """Start V0.64 optimization process."""
        if not self.loaded_file:
            messagebox.showerror("Error", "No file selected.")
            return
        
        if not os.path.exists(self.loaded_file):
            messagebox.showerror("Error", "Selected file no longer exists.")
            return
        
        
        if self.processing:
            messagebox.showwarning("Processing", "Already processing a file.")
            return
        
        try:
            target_size = float(self.target_size_var.get())
            if target_size <= 0 or target_size > 5:
                raise ValueError()
        except:
            messagebox.showerror("Error", "Invalid target size. Enter 0.1 to 5.0")
            return
        
        self.processing = True
        self.cancel_processing = False
        self.start_button.config(state='disabled')
        self.cancel_button.config(state='normal')
        
        def process():
            try:
                output_path = self.optimize_gif_v064(self.loaded_file, self.update_progress)
                
                if output_path and not self.cancel_processing and os.path.exists(output_path):
                    final_size = os.path.getsize(output_path) / (1024 * 1024)
                    original_size = os.path.getsize(self.loaded_file) / (1024 * 1024)
                    compression = ((original_size - final_size) / original_size) * 100 if original_size > 0 else 0
                    
                    # Calculate prediction accuracy
                    prediction_diff = abs(final_size - self.predicted_size) if self.predicted_size > 0 else 0
                    accuracy_text = f"🎯 Prediction: ±{prediction_diff:.2f} MB" if prediction_diff < 1 else ""
                    
                    success_msg = (f"🎉 V0.64 Optimization Complete!\n\n"
                                 f"📁 Output: {os.path.basename(output_path)}\n"
                                 f"📊 Final size: {final_size:.2f} MB\n"
                                 f"📉 Compression: {compression:.1f}%\n"
                                 f"{accuracy_text}\n"
                                 f"💾 Saved to: {os.path.dirname(output_path)}")
                    
                    self.root.after(0, lambda: messagebox.showinfo("Success!", success_msg))
                
                elif self.cancel_processing:
                    self.root.after(0, lambda: self.update_progress(0, "❌ Cancelled"))
                    self.root.after(0, lambda: self.update_detail_status("Operation cancelled by user"))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Optimization Failed", "Could not optimize the GIF. Try:\n\n"
                                              "• Verify the file is a valid GIF\n"
                                              "• Check FFmpeg and Gifsicle are installed\n"
                                              "• Try 'Maximum Compression' preset\n"
                                              "• Enable 'Never Give Up' mode"))
            
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("Processing Error", f"An error occurred:\n\n{error_msg[:200]}"))
                self.root.after(0, lambda: self.update_progress(0, "❌ Processing failed"))
                self.root.after(0, lambda: self.update_detail_status(f"Critical error: {error_msg[:50]}"))
            finally:
                self.root.after(0, self.reset_ui)
        
        threading.Thread(target=process, daemon=True).start()
    
    def cancel_optimization(self):
        """Cancel current optimization."""
        self.cancel_processing = True
        self.cancel_button.config(state='disabled')
        self.update_progress(0, "⏹️ Cancelling...")
        self.update_detail_status("Cancellation requested, stopping at next safe point...")
    
    def reset_ui(self):
        """Reset UI to ready state."""
        self.processing = False
        self.cancel_processing = False
        self.start_button.config(state='normal')
        self.cancel_button.config(state='disabled')

def main():
    root = TkinterDnD.Tk()
    app = GIFOptimizer(root)
    
    # Center window
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    def on_closing():
        if app.processing:
            if messagebox.askokcancel("Quit", "Optimization in progress. Quit anyway?"):
                app.cancel_processing = True
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
