#!/usr/bin/env python3

"""
YouTube Downloader - a simple point-and-click GUI.

Features:
- Video MP4
- Audio MP3
- Audio original format
- Quality selection up to 4K/8K
- Shows downloaded percentage
- Shows percentage remaining
- Shows downloaded size / total size
- Shows download speed
- Shows ETA
- Uses FFmpeg automatically when imageio-ffmpeg is installed
- Uses aria2c automatically if available
- Checks yt-dlp updates
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import queue
import tempfile
import shutil
import json
import time
import urllib.request

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# ---------------------------------------------------------
# FFmpeg
# ---------------------------------------------------------

FFMPEG_PATH = None

try:
    import imageio_ffmpeg

    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

except Exception:
    FFMPEG_PATH = None


# ---------------------------------------------------------
# aria2c
# ---------------------------------------------------------

ARIA2C_PATH = shutil.which("aria2c")


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

AUDIO_MP3 = "Audio only (MP3)"
AUDIO_FAST = "Audio only (Fastest, original format)"

QUALITY_BEST = "Best (up to 4K/8K)"

QUALITY_CHOICES = [
    QUALITY_BEST,
    "2160p (4K)",
    "1440p (2K)",
    "1080p",
    "720p",
    "480p",
    "360p",
]

HEIGHT_MAP = {
    QUALITY_BEST: None,
    "2160p (4K)": 2160,
    "1440p (2K)": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}

PROBE_MIN_HEIGHT = 1080

FALLBACK_CLIENTS = [
    "default",
    "tv",
    "web_safari",
    "android",
    "web",
]


# ---------------------------------------------------------
# Application
# ---------------------------------------------------------

class DownloaderApp:

    def __init__(self, root):

        self.root = root

        self.root.title("YouTube Downloader")
        self.root.geometry("640x600")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        self.msg_queue = queue.Queue()

        self.download_folder = os.path.join(
            os.path.expanduser("~"),
            "Downloads"
        )

        self._build_ui()
        self._poll_queue()

        if yt_dlp is None:

            self._log("yt-dlp is not installed yet.")
            self._log(
                "Run: pip install yt-dlp imageio-ffmpeg"
            )
            self._log("Then reopen this app.")

            self.download_btn.config(
                state="disabled"
            )

        else:

            installed_version = getattr(
                yt_dlp.version,
                "__version__",
                "unknown"
            )

            self._log(
                f"yt-dlp version: {installed_version}"
            )

            if FFMPEG_PATH is None:

                self._log(
                    "Tip: FFmpeg is not detected."
                )

                self._log(
                    "Install with:"
                )

                self._log(
                    "pip install imageio-ffmpeg"
                )

            else:

                self._log(
                    "FFmpeg detected automatically."
                )

            if ARIA2C_PATH:

                self._log(
                    "aria2c detected."
                )

                self._log(
                    "GUI progress display enabled."
                )

            else:

                self._log(
                    "aria2c not detected - using yt-dlp downloader."
                )

            threading.Thread(
                target=self._check_ytdlp_update,
                args=(installed_version,),
                daemon=True
            ).start()


    # =====================================================
    # UI
    # =====================================================

    def _build_ui(self):

        style = ttk.Style()

        style.theme_use("clam")

        style.configure(
            "TCombobox",
            fieldbackground="#2b2b3d",
            background="#2b2b3d"
        )

        title = tk.Label(
            self.root,
            text="YouTube Downloader",
            font=("Segoe UI", 18, "bold"),
            bg="#1e1e2e",
            fg="#f5f5f5"
        )

        title.pack(
            pady=(18, 10)
        )


        # -------------------------------------------------
        # URL
        # -------------------------------------------------

        url_frame = tk.Frame(
            self.root,
            bg="#1e1e2e"
        )

        url_frame.pack(
            fill="x",
            padx=24,
            pady=6
        )

        tk.Label(
            url_frame,
            text="Video URL",
            bg="#1e1e2e",
            fg="#cccccc",
            font=("Segoe UI", 10)
        ).pack(
            anchor="w"
        )

        entry_row = tk.Frame(
            url_frame,
            bg="#1e1e2e"
        )

        entry_row.pack(
            fill="x",
            pady=4
        )

        self.url_var = tk.StringVar()

        self.url_entry = tk.Entry(
            entry_row,
            textvariable=self.url_var,
            font=("Segoe UI", 11),
            bg="#2b2b3d",
            fg="white",
            insertbackground="white",
            relief="flat"
        )

        self.url_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=7,
            padx=(0, 8)
        )

        tk.Button(
            entry_row,
            text="Paste",
            command=self._paste,
            bg="#3d3d55",
            fg="white",
            relief="flat",
            padx=12
        ).pack(
            side="left"
        )


        # -------------------------------------------------
        # Format / Quality
        # -------------------------------------------------

        opt_frame = tk.Frame(
            self.root,
            bg="#1e1e2e"
        )

        opt_frame.pack(
            fill="x",
            padx=24,
            pady=12
        )

        tk.Label(
            opt_frame,
            text="Format",
            bg="#1e1e2e",
            fg="#cccccc",
            font=("Segoe UI", 10)
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        self.format_var = tk.StringVar(
            value="Video (MP4)"
        )

        ttk.Combobox(
            opt_frame,
            textvariable=self.format_var,
            state="readonly",
            values=[
                "Video (MP4)",
                AUDIO_MP3,
                AUDIO_FAST
            ],
            width=28
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=4
        )

        tk.Label(
            opt_frame,
            text="Quality",
            bg="#1e1e2e",
            fg="#cccccc",
            font=("Segoe UI", 10)
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(24, 0)
        )

        self.quality_var = tk.StringVar(
            value=QUALITY_BEST
        )

        ttk.Combobox(
            opt_frame,
            textvariable=self.quality_var,
            state="readonly",
            values=QUALITY_CHOICES,
            width=18
        ).grid(
            row=1,
            column=1,
            sticky="w",
            padx=(24, 0),
            pady=4
        )


        # -------------------------------------------------
        # Save folder
        # -------------------------------------------------

        folder_frame = tk.Frame(
            self.root,
            bg="#1e1e2e"
        )

        folder_frame.pack(
            fill="x",
            padx=24,
            pady=6
        )

        tk.Label(
            folder_frame,
            text="Save to",
            bg="#1e1e2e",
            fg="#cccccc",
            font=("Segoe UI", 10)
        ).pack(
            anchor="w"
        )

        folder_row = tk.Frame(
            folder_frame,
            bg="#1e1e2e"
        )

        folder_row.pack(
            fill="x",
            pady=4
        )

        self.folder_var = tk.StringVar(
            value=self.download_folder
        )

        tk.Entry(
            folder_row,
            textvariable=self.folder_var,
            font=("Segoe UI", 10),
            bg="#2b2b3d",
            fg="white",
            relief="flat",
            state="readonly",
            readonlybackground="#2b2b3d"
        ).pack(
            side="left",
            fill="x",
            expand=True,
            ipady=7,
            padx=(0, 8)
        )

        tk.Button(
            folder_row,
            text="Browse",
            command=self._browse_folder,
            bg="#3d3d55",
            fg="white",
            relief="flat",
            padx=12
        ).pack(
            side="left"
        )


        # -------------------------------------------------
        # Download button
        # -------------------------------------------------

        self.download_btn = tk.Button(
            self.root,
            text="Download",
            command=self._start_download,
            bg="#7c3aed",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            relief="flat",
            pady=9,
            activebackground="#6d28d9"
        )

        self.download_btn.pack(
            fill="x",
            padx=24,
            pady=16
        )


        # -------------------------------------------------
        # Progress
        # -------------------------------------------------

        self.progress = ttk.Progressbar(
            self.root,
            orient="horizontal",
            mode="determinate"
        )

        self.progress.pack(
            fill="x",
            padx=24,
            pady=(0, 10)
        )


        # -------------------------------------------------
        # Log
        # -------------------------------------------------

        log_frame = tk.Frame(
            self.root,
            bg="#1e1e2e"
        )

        log_frame.pack(
            fill="both",
            expand=True,
            padx=24,
            pady=(0, 18)
        )

        self.log_text = tk.Text(
            log_frame,
            bg="#12121c",
            fg="#a6e3a1",
            font=("Consolas", 9),
            relief="flat",
            wrap="word",
            state="disabled",
            height=10
        )

        self.log_text.pack(
            fill="both",
            expand=True
        )


    # =====================================================
    # Helpers
    # =====================================================

    def _paste(self):

        try:

            clip = self.root.clipboard_get()

            self.url_var.set(
                clip.strip()
            )

        except tk.TclError:

            pass


    def _browse_folder(self):

        folder = filedialog.askdirectory(
            initialdir=self.folder_var.get()
        )

        if folder:

            self.folder_var.set(
                folder
            )


    def _log(self, text):

        self.log_text.config(
            state="normal"
        )

        self.log_text.insert(
            "end",
            text + "\n"
        )

        self.log_text.see(
            "end"
        )

        self.log_text.config(
            state="disabled"
        )


    def _poll_queue(self):

        try:

            while True:

                kind, payload = (
                    self.msg_queue.get_nowait()
                )

                if kind == "log":

                    self._log(
                        payload
                    )

                elif kind == "progress":

                    self.progress["value"] = (
                        payload
                    )

                elif kind == "done":

                    self.download_btn.config(
                        state="normal",
                        text="Download"
                    )

                    messagebox.showinfo(
                        "Done",
                        payload
                    )

                elif kind == "error":

                    self.download_btn.config(
                        state="normal",
                        text="Download"
                    )

                    messagebox.showerror(
                        "Download failed",
                        payload
                    )

        except queue.Empty:

            pass

        self.root.after(
            150,
            self._poll_queue
        )


    # =====================================================
    # yt-dlp update check
    # =====================================================

    def _check_ytdlp_update(
        self,
        installed_version
    ):

        try:

            req = urllib.request.Request(
                "https://pypi.org/pypi/yt-dlp/json",
                headers={
                    "User-Agent":
                        "youtube-downloader-gui"
                }
            )

            with urllib.request.urlopen(
                req,
                timeout=5
            ) as resp:

                latest_version = (
                    json.load(resp)
                    ["info"]
                    ["version"]
                )

            if (
                latest_version
                and latest_version != installed_version
            ):

                self.msg_queue.put(
                    (
                        "log",
                        f"yt-dlp update available: "
                        f"{installed_version} -> "
                        f"{latest_version}"
                    )
                )

        except Exception:

            pass


    # =====================================================
    # Start download
    # =====================================================

    def _start_download(self):

        url = self.url_var.get().strip()

        if not url:

            messagebox.showwarning(
                "Missing URL",
                "Paste a YouTube URL first."
            )

            return

        if yt_dlp is None:

            messagebox.showerror(
                "Missing dependency",
                "Install yt-dlp first."
            )

            return

        self.download_btn.config(
            state="disabled",
            text="Downloading..."
        )

        self.progress["value"] = 0

        self._log(
            f"Starting: {url}"
        )

        threading.Thread(
            target=self._download_worker,
            args=(url,),
            daemon=True
        ).start()


    # =====================================================
    # Download worker
    # =====================================================

    def _download_worker(
        self,
        url
    ):

        out_dir = self.folder_var.get()

        os.makedirs(
            out_dir,
            exist_ok=True
        )

        choice = self.format_var.get()

        is_audio_mp3 = (
            choice == AUDIO_MP3
        )

        is_audio_fast = (
            choice == AUDIO_FAST
        )

        is_video = not (
            is_audio_mp3
            or is_audio_fast
        )

        quality = self.quality_var.get()

        target_height = HEIGHT_MAP.get(
            quality
        )


        # -------------------------------------------------
        # Progress hook
        # -------------------------------------------------

        def hook(d):

            status = d.get(
                "status"
            )

            if status == "downloading":

                total = (
                    d.get("total_bytes")
                    or d.get("total_bytes_estimate")
                )

                downloaded = d.get(
                    "downloaded_bytes",
                    0
                )

                speed = d.get(
                    "_speed_str",
                    ""
                ).strip()

                eta = d.get(
                    "_eta_str",
                    ""
                ).strip()

                size = (
                    d.get("_total_bytes_str")
                    or
                    d.get(
                        "_total_bytes_estimate_str"
                    )
                    or ""
                ).strip()

                downloaded_size = (
                    d.get(
                        "_downloaded_bytes_str",
                        ""
                    )
                    or ""
                ).strip()


                # -----------------------------------------
                # Calculate percentage
                # -----------------------------------------

                if total:

                    downloaded_pct = (
                        downloaded / total
                    ) * 100

                    downloaded_pct = min(
                        100,
                        max(
                            0,
                            downloaded_pct
                        )
                    )

                    left_pct = (
                        100
                        - downloaded_pct
                    )

                    self.msg_queue.put(
                        (
                            "progress",
                            downloaded_pct
                        )
                    )

                    line = (
                        f"Downloaded: "
                        f"{downloaded_pct:.0f}%"
                        f" | "
                        f"Left: "
                        f"{left_pct:.0f}%"
                    )

                else:

                    line = (
                        f"Downloading..."
                    )


                # -----------------------------------------
                # Size
                # -----------------------------------------

                if downloaded_size and size:

                    line += (
                        f" | "
                        f"{downloaded_size}"
                        f"/"
                        f"{size}"
                    )


                # -----------------------------------------
                # Speed
                # -----------------------------------------

                if speed:

                    line += (
                        f" | "
                        f"Speed: {speed}"
                    )


                # -----------------------------------------
                # ETA
                # -----------------------------------------

                if eta:

                    line += (
                        f" | "
                        f"ETA: {eta}"
                    )


                self.msg_queue.put(
                    (
                        "log",
                        line
                    )
                )


            elif status == "finished":

                self.msg_queue.put(
                    (
                        "log",
                        "Stream downloaded. Finalizing..."
                    )
                )


        # -------------------------------------------------
        # Postprocessor hook
        # -------------------------------------------------

        def pp_hook(d):

            pp = d.get(
                "postprocessor",
                "postprocessor"
            )

            status = d.get(
                "status"
            )

            if status == "started":

                self.msg_queue.put(
                    (
                        "log",
                        f"[{pp}] starting..."
                    )
                )

            elif status == "finished":

                self.msg_queue.put(
                    (
                        "log",
                        f"[{pp}] done."
                    )
                )


        # -------------------------------------------------
        # Build options
        # -------------------------------------------------

        def build_opts(
            attempt_dir,
            client_override
        ):

            target_ext = None

            if is_audio_mp3:

                fmt = (
                    "bestaudio/best"
                )

                postprocessors = [
                    {
                        "key":
                            "FFmpegExtractAudio",
                        "preferredcodec":
                            "mp3",
                        "preferredquality":
                            "192",
                    }
                ]

                merge_format = None

                target_ext = "mp3"


            elif is_audio_fast:

                fmt = (
                    "bestaudio/best"
                )

                postprocessors = []

                merge_format = None

                target_ext = None


            else:

                h = target_height

                if h:

                    fmt = (
                        f"bestvideo[height<={h}]"
                        "+"
                        f"bestaudio/"
                        f"best[height<={h}]"
                    )

                else:

                    fmt = (
                        "bestvideo+bestaudio/best"
                    )

                postprocessors = []

                merge_format = "mp4"

                target_ext = "mp4"


            opts = {

                "format": fmt,

                "format_sort": [
                    "res",
                    "fps",
                    "br"
                ],

                "outtmpl": os.path.join(
                    attempt_dir,
                    "%(title)s.%(ext)s"
                ),

                "postprocessors":
                    postprocessors,

                "progress_hooks": [
                    hook
                ],

                "postprocessor_hooks": [
                    pp_hook
                ],

                "noplaylist": True,

                # IMPORTANT:
                # Prevent yt-dlp output from
                # polluting the GUI.
                "quiet": True,

                "no_warnings": True,

                "logger": SilentLogger(),

                "concurrent_fragment_downloads":
                    24,

                "http_chunk_size":
                    20 * 1024 * 1024,

                "retries": 10,

                "fragment_retries": 10,

                "socket_timeout": 30,

                "geo_bypass": True,
            }


            if client_override:

                opts[
                    "extractor_args"
                ] = {

                    "youtube": {

                        "player_client":
                            client_override
                    }
                }


            if merge_format:

                opts[
                    "merge_output_format"
                ] = merge_format


            if FFMPEG_PATH:

                opts[
                    "ffmpeg_location"
                ] = FFMPEG_PATH


            # -------------------------------------------------
            # aria2c
            #
            # IMPORTANT:
            # We DON'T use aria2c here because aria2c
            # prints its own:
            #
            # [#3a56eb 2.1MiB/3.5MiB(59%) ...]
            #
            # directly to the console.
            #
            # yt-dlp's progress hook gives us clean GUI
            # progress instead.
            # -------------------------------------------------

            return opts, target_ext


        # -------------------------------------------------
        # Format helpers
        # -------------------------------------------------

        def max_available_height(info):

            formats = (
                info.get("formats")
                or []
            )

            heights = [

                f.get("height")

                for f in formats

                if (
                    f.get("height")
                    and
                    f.get("vcodec")
                    not in (
                        None,
                        "none"
                    )
                )
            ]

            return (
                max(heights)
                if heights
                else None
            )


        def achieved_quality(info):

            reqs = (
                info.get(
                    "requested_formats"
                )
                or [info]
            )

            vid = next(
                (
                    f
                    for f in reqs

                    if (
                        f.get("vcodec")
                        not in (
                            None,
                            "none"
                        )
                    )
                ),
                None
            )

            aud = next(
                (
                    f
                    for f in reqs

                    if (
                        f.get("acodec")
                        not in (
                            None,
                            "none"
                        )
                        and f is not vid
                    )
                ),
                None
            )

            height = (
                vid.get("height")
                if vid
                else info.get("height")
            )

            parts = []


            if vid:

                w = vid.get(
                    "width"
                )

                h = vid.get(
                    "height"
                )

                if w and h:

                    parts.append(
                        f"{w}x{h}"
                    )

                vcodec = vid.get(
                    "vcodec"
                )

                if vcodec:

                    parts.append(
                        vcodec.split(".")[0]
                    )

                vbr = (
                    vid.get("vbr")
                    or
                    vid.get("tbr")
                )

                if vbr:

                    parts.append(
                        f"{vbr:.0f} kbps video"
                    )


            if aud:

                abr = aud.get(
                    "abr"
                )

                if abr:

                    parts.append(
                        f"{abr:.0f} kbps audio"
                    )


            return (
                height,
                (
                    ", ".join(parts)
                    if parts
                    else "unknown"
                )
            )


        # -------------------------------------------------
        # Probe clients
        # -------------------------------------------------

        def probe_client_override():

            if not is_video:

                return None

            if (
                target_height
                and
                target_height < PROBE_MIN_HEIGHT
            ):

                return None


            def probe(
                client_override
            ):

                opts = {

                    "quiet": True,

                    "no_warnings": True,

                    "skip_download": True,

                    "noplaylist": True,

                    "geo_bypass": True,
                }


                if client_override:

                    opts[
                        "extractor_args"
                    ] = {

                        "youtube": {

                            "player_client":
                                client_override
                        }
                    }


                try:

                    with yt_dlp.YoutubeDL(
                        opts
                    ) as ydl:

                        info = (
                            ydl.extract_info(
                                url,
                                download=False
                            )
                        )

                    return (
                        max_available_height(
                            info
                        )
                    )

                except Exception:

                    return None


            h_default = probe(
                None
            )

            h_fallback = probe(
                FALLBACK_CLIENTS
            )


            if (
                h_fallback
                and
                (
                    not h_default
                    or
                    h_fallback
                    > h_default * 1.1
                )
            ):

                self.msg_queue.put(
                    (
                        "log",
                        f"Default client: "
                        f"{h_default or '?'}p | "
                        f"Fallback: "
                        f"{h_fallback}p"
                    )
                )

                return FALLBACK_CLIENTS


            return None


        # =================================================
        # Actual download
        # =================================================

        try:

            with tempfile.TemporaryDirectory(
                prefix=".ytdl_",
                dir=out_dir
            ) as scratch_dir:

                t_probe_start = time.time()

                client_override = (
                    probe_client_override()
                )

                t_probe = (
                    time.time()
                    -
                    t_probe_start
                )

                if t_probe > 0.05:

                    self.msg_queue.put(
                        (
                            "log",
                            f"Checked available formats "
                            f"in {t_probe:.1f}s."
                        )
                    )


                attempt_dir = os.path.join(
                    scratch_dir,
                    "attempt0"
                )

                os.makedirs(
                    attempt_dir,
                    exist_ok=True
                )


                opts, target_ext = (
                    build_opts(
                        attempt_dir,
                        client_override
                    )
                )


                self.msg_queue.put(
                    (
                        "log",
                        "Downloading..."
                    )
                )


                t_dl_start = time.time()


                with yt_dlp.YoutubeDL(
                    opts
                ) as ydl:

                    info = (
                        ydl.extract_info(
                            url,
                            download=True
                        )
                    )


                t_download = (
                    time.time()
                    -
                    t_dl_start
                )


                # -------------------------------------------------
                # Safety retry
                # -------------------------------------------------

                if (
                    is_video
                    and
                    client_override is None
                ):

                    got_height, _ = (
                        achieved_quality(
                            info
                        )
                    )

                    best_height = (
                        max_available_height(
                            info
                        )
                    )


                    if (
                        target_height
                        and
                        best_height
                    ):

                        expected_height = min(
                            target_height,
                            best_height
                        )

                    else:

                        expected_height = (
                            target_height
                            or
                            best_height
                        )


                    degraded = (
                        expected_height
                        and
                        (
                            got_height is None
                            or
                            got_height
                            < expected_height * 0.85
                        )
                    )


                    if degraded:

                        self.msg_queue.put(
                            (
                                "log",
                                f"Got "
                                f"{got_height or '?'}p "
                                f"but about "
                                f"{expected_height}p "
                                f"should be available. "
                                f"Retrying..."
                            )
                        )


                        self.msg_queue.put(
                            (
                                "progress",
                                0
                            )
                        )


                        attempt_dir2 = (
                            os.path.join(
                                scratch_dir,
                                "attempt1"
                            )
                        )

                        os.makedirs(
                            attempt_dir2,
                            exist_ok=True
                        )


                        opts2, target_ext2 = (
                            build_opts(
                                attempt_dir2,
                                FALLBACK_CLIENTS
                            )
                        )


                        t_retry_start = (
                            time.time()
                        )


                        with yt_dlp.YoutubeDL(
                            opts2
                        ) as ydl2:

                            info2 = (
                                ydl2.extract_info(
                                    url,
                                    download=True
                                )
                            )


                        t_download += (
                            time.time()
                            -
                            t_retry_start
                        )


                        got_height2, _ = (
                            achieved_quality(
                                info2
                            )
                        )


                        if (
                            got_height2
                            and
                            (
                                not got_height
                                or
                                got_height2
                                > got_height
                            )
                        ):

                            info = info2

                            attempt_dir = (
                                attempt_dir2
                            )

                            target_ext = (
                                target_ext2
                            )


                # -------------------------------------------------
                # Move file
                # -------------------------------------------------

                title = info.get(
                    "title",
                    "video"
                )


                self.msg_queue.put(
                    (
                        "log",
                        "Finalizing: moving file..."
                    )
                )


                t_move_start = time.time()


                if target_ext:

                    finished = [

                        f

                        for f in os.listdir(
                            attempt_dir
                        )

                        if f.lower().endswith(
                            "." + target_ext
                        )
                    ]


                    if not finished:

                        finished = os.listdir(
                            attempt_dir
                        )

                else:

                    finished = os.listdir(
                        attempt_dir
                    )


                saved_path = None


                for fname in finished:

                    src = os.path.join(
                        attempt_dir,
                        fname
                    )

                    dst = os.path.join(
                        out_dir,
                        fname
                    )

                    shutil.move(
                        src,
                        dst
                    )

                    saved_path = dst


                t_move = (
                    time.time()
                    -
                    t_move_start
                )


            # -------------------------------------------------
            # Complete
            # -------------------------------------------------

            self.msg_queue.put(
                (
                    "progress",
                    100
                )
            )


            timing_line = (
                f"Format check: "
                f"{t_probe:.1f}s | "
                f"Download + merge: "
                f"{t_download:.1f}s | "
                f"Move: "
                f"{t_move:.1f}s"
            )


            self.msg_queue.put(
                (
                    "log",
                    timing_line
                )
            )


            # -------------------------------------------------
            # Quality information
            # -------------------------------------------------

            if is_video:

                got_height, desc = (
                    achieved_quality(
                        info
                    )
                )

                best_height = (
                    max_available_height(
                        info
                    )
                )


                quality_line = (
                    f"Quality: {desc}"
                )


                if (
                    best_height
                    and
                    got_height
                    and
                    best_height
                    > got_height * 1.1
                ):

                    quality_line += (
                        f"\nYouTube lists "
                        f"{best_height}p, "
                        f"but {got_height}p "
                        f"was downloaded."
                    )


                self.msg_queue.put(
                    (
                        "done",
                        f"Saved: {title}\n\n"
                        f"Location: "
                        f"{saved_path or out_dir}\n\n"
                        f"{quality_line}"
                    )
                )

            else:

                self.msg_queue.put(
                    (
                        "done",
                        f"Saved: {title}\n\n"
                        f"Location: "
                        f"{saved_path or out_dir}"
                    )
                )


        except Exception as e:

            msg = str(e)


            if "ffmpeg" in msg.lower():

                msg += (
                    "\n\nFFmpeg looks like it is "
                    "missing.\n\n"
                    "Run:\n"
                    "pip install imageio-ffmpeg"
                )


            self.msg_queue.put(
                (
                    "error",
                    msg
                )
            )


# =========================================================
# Silent logger
# =========================================================

class SilentLogger:

    """
    Prevents yt-dlp from printing its own messages
    into the terminal.

    Progress is handled by the GUI progress hook.
    """

    def debug(self, msg):

        pass

    def info(self, msg):

        pass

    def warning(self, msg):

        pass

    def error(self, msg):

        pass


# =========================================================
# Main
# =========================================================

def main():

    root = tk.Tk()

    DownloaderApp(
        root
    )

    root.mainloop()


if __name__ == "__main__":

    main()