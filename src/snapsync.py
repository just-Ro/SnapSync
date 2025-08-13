import asyncio
import os
import re
import sys
import mimetypes
from datetime import datetime, timezone
from PIL import Image
from PIL.ExifTags import TAGS
import threading
import tkinter as tk
from tkinter import ttk
import ctypes

myappid = "ro.snapsync"  # arbitrary string
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

DATE_ONLY_PATTERNS = [
    r"(\d{4})[-_:.\\](\d{2})[-_:.\\](\d{2})",  # YYYY-MM-DD
    r"(\d{2})[-_:.\\](\d{2})[-_:.\\](\d{4})",  # DD-MM-YYYY
    r"(\d{8})",                                # YYYYMMDD
    r"(\d{4})(\d{2})(\d{2})",                  # YYYYMMDD no separator
]

TIME_PATTERNS = [
    r"(\d{2})[-_:.\\](\d{2})[-_:.\\](\d{2})",  # HH-MM-SS
    r"(\d{6})",                                # HHMMSS
    r"(\d{2})(\d{2})(\d{2})",                  # HHMMSS alternative group capture
]

def parse_datetime_from_filename(name: str) -> datetime | None:
    date_match = None
    date_info = None

    # Find date first
    for pat in DATE_ONLY_PATTERNS:
        m = re.search(pat, name)
        if m:
            if len(m.groups()) == 3:
                g = m.groups()
                if int(g[0]) > 31:  # YYYY first
                    y, mth, d = map(int, g)
                else:
                    d, mth, y = map(int, g)
                date_info = (y, mth, d)
            elif len(m.groups()) == 1:
                s = m.group(1)
                y, mth, d = int(s[:4]), int(s[4:6]), int(s[6:8])
                date_info = (y, mth, d)
            if date_info:
                date_match = m
                break

    if not date_info:
        return None

    # Find time, but not overlapping with date
    time_info = None
    for pat in TIME_PATTERNS:
        for m in re.finditer(pat, name):
            # Check if this match does not overlap with date_match
            if date_match:
                date_span = date_match.span()
                time_span = m.span()
                # If time is completely outside date
                if time_span[1] <= date_span[0] or time_span[0] >= date_span[1]:
                    if len(m.groups()) == 3:
                        h, mi, s = map(int, m.groups())
                    elif len(m.groups()) == 1:
                        s = m.group(1)
                        h, mi, s = int(s[:2]), int(s[2:4]), int(s[4:6])
                    time_info = (h, mi, s)
                    break
            else:
                # Should not happen, but fallback
                if len(m.groups()) == 3:
                    h, mi, s = map(int, m.groups())
                elif len(m.groups()) == 1:
                    s = m.group(1)
                    h, mi, s = int(s[:2]), int(s[2:4]), int(s[4:6])
                time_info = (h, mi, s)
                break
        if time_info:
            break

    if date_info and time_info:
        return datetime(date_info[0], date_info[1], date_info[2], time_info[0], time_info[1], time_info[2])
    else:
        return None

def extract_earliest_metadata_datetime(filepath):
    times: list[datetime] = []

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
                                match = re.match(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})", str(val))
                                if match:
                                    y, mth, d, h, mi, s = map(int, match.groups())
                                    dt = datetime(y, mth, d, h, mi, s)
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
    # Determine if file is a video to add QuickTimeUTC=0
    mime_type, _ = mimetypes.guess_type(fpath)
    exiftool_args = [
        "exiftool", fpath,
        "-overwrite_original_in_place",
        f"-DateTimeOriginal={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-CreateDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-ModifyDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-TrackCreateDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-TrackModifyDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-MediaCreateDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
        f"-MediaModifyDate={dt.strftime('%Y:%m:%d %H:%M:%S')}",
    ]
    # if mime_type and mime_type.startswith("video"):
    #     exiftool_args.insert(1, "-api")
    #     exiftool_args.insert(2, "QuickTimeUTC=0")
    proc = await asyncio.create_subprocess_exec(
        *exiftool_args,
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


def process_files(folder, progress_window: ProgressBarWindow):
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
        if not dt:
            meta_dt = extract_earliest_metadata_datetime(fpath)
            if meta_dt:
                dt = meta_dt
                    
        if dt:
            base_prefix = "IMG" if is_image(fpath) else "VID" if is_video(fpath) else None
            if base_prefix:
                ext = os.path.splitext(fname)[1].lower()
                y, mth, d = dt.year, dt.month, dt.day
                h, mi, s = dt.hour, dt.minute, dt.second
                new_name = f"{base_prefix}-{y:04d}{mth:02d}{d:02d}-{h:02d}{mi:02d}{s:02d}{ext}"
                new_path = os.path.join(folder, new_name)
                safe_rename(fpath, new_path)
                fpath = new_path
                fname = new_name
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