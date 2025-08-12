import asyncio
import os
import re
import sys
import mimetypes
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS
import threading
import tkinter as tk
from tkinter import ttk
import ctypes

myappid = "ro.snapsync"  # arbitrary string
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

DATE_PATTERNS = [
    r"(\d{4})[-_:.\\](\d{2})[-_:.\\](\d{2})[ T_:.\\](\d{2})[-_:.\\](\d{2})[-_:.\\](\d{2})",    # YYYY-MM-DD HH-MM-SS
    r"(\d{2})[-_:.\\](\d{2})[-_:.\\](\d{4})[ T_:.\\](\d{2})[-_:.\\](\d{2})[-_:.\\](\d{2})",    # DD-MM-YYYY HH-MM-SS
    r"(\d{8})[ T_:.\\](\d{6})",                                                        # YYYYMMDD HHMMSS
    r"(\d{14})",                                                                     # YYYYMMDDHHMMSS
    r"(\d{4})(\d{2})(\d{2})[-_:.\\]?(\d{2})(\d{2})(\d{2})",                             # YYYYMMDD-HHMMSS or YYYYMMDDHHMMSS no separator
]

DATE_ONLY_PATTERNS = [
    r"(\d{4})[-_:.\\](\d{2})[-_:.\\](\d{2})",  # YYYY-MM-DD
    r"(\d{2})[-_:.\\](\d{2})[-_:.\\](\d{4})",  # DD-MM-YYYY
    r"(\d{8})",                            # YYYYMMDD
    r"(\d{4})(\d{2})(\d{2})",             # YYYYMMDD no separator
]

TIME_PATTERNS = [
    r"(\d{2})[-_:.\\](\d{2})[-_:.\\](\d{2})",  # HH-MM-SS
    r"(\d{6})",                            # HHMMSS
    r"(\d{2})(\d{2})(\d{2})",              # HHMMSS alternative group capture
]

def parse_datetime_from_filename(name):
    # Try full datetime first
    for pat in DATE_PATTERNS:
        # print("File name:", name)
        m = re.search(pat, name)
        if m:
            if len(m.groups()) == 6:
                # date parts and time parts separated
                g = m.groups()
                if int(g[0]) > 31:  # YYYY first
                    y,mth,d,h,mi,s = map(int, g)
                else:  # DD first
                    d,mth,y,h,mi,s = map(int, g)
                return datetime(y,mth,d,h,mi,s)
            elif len(m.groups()) == 1:
                # YYYYMMDDHHMMSS
                s = m.group(1)
                return datetime.strptime(s, "%Y%m%d%H%M%S")

    # Try date only
    for pat in DATE_ONLY_PATTERNS:
        m = re.search(pat, name)
        if m:
            if len(m.groups()) == 3:
                g = m.groups()
                if int(g[0]) > 31:  # YYYY first
                    y,mth,d = map(int, g)
                else:
                    d,mth,y = map(int, g)
                return datetime(y,mth,d)
            elif len(m.groups()) == 1:
                s = m.group(1)
                return datetime.strptime(s, "%Y%m%d")

    return None

def extract_earliest_metadata_datetime(filepath):
    times = []

    # Filesystem times
    try:
        stat = os.stat(filepath)
        times.append(datetime.fromtimestamp(stat.st_mtime))
        times.append(datetime.fromtimestamp(stat.st_ctime))
    except Exception:
        pass

    # EXIF for images
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type and mime_type.startswith("image"):
        try:
            with Image.open(filepath) as img:
                exif = img._getexif()
                if exif:
                    for tag_id, val in exif.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                            try:
                                dt = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                                times.append(dt)
                            except Exception:
                                pass
        except Exception:
            pass

    if times:
        return min(times)
    return None

def is_image(filepath):
    mime_type, _ = mimetypes.guess_type(filepath)
    # print(f"Checking if {filepath} is an image: {mime_type}")
    return mime_type is not None and mime_type.startswith("image")

def is_video(filepath):
    mime_type, _ = mimetypes.guess_type(filepath)
    # print(f"Checking if {filepath} is a video: {mime_type}")
    return mime_type is not None and mime_type.startswith("video")

def safe_rename(old_path, new_path):
    if old_path == new_path:
        return
    if os.path.exists(new_path):
        # Avoid overwrite by adding a counter
        base, ext = os.path.splitext(new_path)
        i = 1
        while True:
            candidate = f"{base}_{i}{ext}"
            if not os.path.exists(candidate):
                new_path = candidate
                break
            i += 1
    # print(f"Renaming:\n  {old_path} ->\n  {new_path}")
    os.rename(old_path, new_path)

import subprocess

async def update_metadata_async(fpath, dt):
    # Prevent console window popups on Windows
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW
    proc = await asyncio.create_subprocess_exec(
        "exiftool", fpath,
        "-overwrite_original_in_place",
        f"-DateTimeOriginal={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-CreateDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-ModifyDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-TrackCreateDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-TrackModifyDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-MediaCreateDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-MediaModifyDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=creationflags
    )
    await proc.communicate()


class ProgressBarWindow:
    def run(self):
        self.root.mainloop()
    def __init__(self, total):
        self.value = 0
        self.total = total
        
        self.root = tk.Tk()
        self.root.title("Processing files")
        self.set_icon()
        self.set_style()
        
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate", maximum=self.total, style="TProgressbar")
        self.progress.pack(padx=20, pady=20)
        self.label = ttk.Label(self.root, text="0 / {} files".format(self.total), style="Modern.TLabel")
        self.label.pack(pady=(0, 20))
        
        self.closed = False
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.center_window()

    def set_icon(self):
        # Set window icon
        try:
            if hasattr(sys, '_MEIPASS'):
                # Running in a PyInstaller bundle
                icon_path = os.path.join(sys._MEIPASS, "icon.ico")
            else:
                icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.ico")
            self.root.iconbitmap(icon_path, icon_path)
        except Exception:
            pass

    def set_style(self):
        # Detect Windows light/dark mode and set colors, use only ttk widgets, and set a modern theme
        bg = "#f3f3f3"
        fg = "#2d2d30"
        style = ttk.Style(self.root)
        # Try to use the most modern theme available
        try:
            if "vista" in style.theme_names():
                style.theme_use("vista")
            else:
                style.theme_use("clam")
        except Exception:
            pass

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize") as key:
                apps_use_light_theme = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
                if apps_use_light_theme == 0:
                    # Dark mode
                    bg = "#2d2d30"
                    fg = "#f3f3f3"
        except Exception:
            pass

        self.root.configure(bg=bg)
        style.configure("TProgressbar", background="#0078d7", troughcolor=bg)
        style.configure("Modern.TLabel", background=bg, foreground=fg)

    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def update(self, value):
        self.value = value
        self.progress['value'] = value
        self.label.config(text=f"{value} / {self.total} files")
        self.root.update_idletasks()

    def on_close(self):
        self.closed = True
        self.root.quit()


def process_files(folder, progress_window):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    files = [fname for fname in os.listdir(folder) if os.path.isfile(os.path.join(folder, fname)) and (is_image(os.path.join(folder, fname)) or is_video(os.path.join(folder, fname)))]
    total = len(files)

    import multiprocessing
    max_threads = max(1, multiprocessing.cpu_count() - 2)
    semaphore = asyncio.Semaphore(max_threads)
    processed = 0

    async def process_one(fname):
        nonlocal processed
        if progress_window.closed:
            return
        fpath = os.path.join(folder, fname)
        dt = parse_datetime_from_filename(fname)
        if dt and (dt.hour == 0 and dt.minute == 0 and dt.second == 0):
            meta_dt = extract_earliest_metadata_datetime(fpath)
            if meta_dt:
                dt = dt.replace(hour=meta_dt.hour, minute=meta_dt.minute, second=meta_dt.second)
                base_prefix = "IMG" if is_image(fpath) else "VID" if is_video(fpath) else None
                if base_prefix:
                    new_name = f"{base_prefix}-{dt.strftime('%Y%m%d-%H%M%S')}{os.path.splitext(fname)[1].lower()}"
                    new_path = os.path.join(folder, new_name)
                    safe_rename(fpath, new_path)
                    fpath = new_path
                    fname = new_name
        elif not dt:
            meta_dt = extract_earliest_metadata_datetime(fpath)
            if meta_dt:
                base_prefix = "IMG" if is_image(fpath) else "VID" if is_video(fpath) else None
                if base_prefix:
                    new_name = f"{base_prefix}-{meta_dt.strftime('%Y%m%d-%H%M%S')}{os.path.splitext(fname)[1].lower()}"
                    new_path = os.path.join(folder, new_name)
                    safe_rename(fpath, new_path)
                    fpath = new_path
                    fname = new_name
                dt = meta_dt
        if dt:
            async with semaphore:
                await update_metadata_async(fpath, dt)
        processed += 1
        progress_window.root.after(0, progress_window.update, processed)

    async def runner():
        await asyncio.gather(*(process_one(fname) for fname in files))
        progress_window.root.after(0, progress_window.update, total)
        progress_window.root.after(0, progress_window.on_close)

    loop.run_until_complete(runner())

def main_with_gui(folder):
    files = [fname for fname in os.listdir(folder) if os.path.isfile(os.path.join(folder, fname)) and (is_image(os.path.join(folder, fname)) or is_video(os.path.join(folder, fname)))]
    total = len(files)
    progress_window = ProgressBarWindow(total)
    thread = threading.Thread(target=process_files, args=(folder, progress_window), daemon=True)
    thread.start()
    progress_window.run()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python snapsync.py <folder>")
        sys.exit(1)
    main_with_gui(sys.argv[1])