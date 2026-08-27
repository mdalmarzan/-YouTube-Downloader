#!/usr/bin/env python3
"""
YouTube Downloader - a simple point-and-click GUI.
Double-click this file to run it (no terminal needed after one-time setup).

=== Why "4K" sometimes looked blurry, and what changed ===
This wasn't a bug in the resolution-picking logic - it was YouTube. Since late
2025, YouTube has been rolling out a custom streaming protocol ("SABR") and
periodically breaking specific yt-dlp "player clients" (the different ways
yt-dlp can pretend to be the Android app, the web player, a TV, etc.) as part
of ongoing A/B tests against bot detection. When the client this script asked
for a video from has its high-resolution formats suppressed that week, yt-dlp
just downloads whatever lower-quality format IS available through that client
- silently. You'd click "Best (up to 4K/8K)" and actually get something far
worse, with no error at all.

The previous version hardcoded player_client=["android","web"], which pinned
it to exactly two clients that have both had rounds of this breakage. Fixes
here:
  1. No forced player_client anymore. yt-dlp's own built-in client fallback
     list is patched upstream (often within days) whenever YouTube breaks a
     client, which happens far more often than anyone will update this
     script. Letting yt-dlp choose is now the safer default.
  2. If the default client's available formats look genuinely capped for
     this video, the script automatically switches to a wider client list -
     see "Why downloads sometimes felt slow" below for how this now happens
     BEFORE downloading instead of after.
  3. The "Saved" dialog now tells you the exact resolution/codec/bitrate you
     got, so you can see for certain whether you actually received true 4K -
     some videos labeled 2160p on YouTube are upscaled from a lower-res
     source and will never look sharp no matter what downloads them.
  4. The app checks your installed yt-dlp version against PyPI on startup and
     tells you if an update is available. Since this whole class of problem
     gets fixed via yt-dlp updates (new releases ship every 1-3 weeks
     specifically to patch YouTube's latest changes), keeping it updated
     matters more than any setting in this script. Run this periodically:
         pip install -U yt-dlp

=== Why downloads sometimes felt slow overall, and what changed ===
Two separate things were making this feel much slower than it needed to be:

  1. The old code downloaded the ENTIRE video first, and only afterward
     checked whether the resolution it got looked "too low" compared to
     what YouTube's metadata said was available. If that heuristic tripped -
     which it could do fairly often for the default "Best" option, since the
     metadata's reported max height doesn't always exactly match what's
     actually downloadable - it silently started a SECOND full download with
     a broader client list and kept whichever one was better. For a multi-
     gigabyte 4K file, that's the entire download time again, for nothing.
     Now that check happens BEFORE downloading, using a metadata-only
     request (skip_download=True) that transfers no video data and normally
     finishes in well under a second. The real download then happens once,
     with the right client already selected. A rare safety-net retry still
     exists in case that probe itself turns out to be wrong, but it should
     now be uncommon instead of routine. Since the suppression this works
     around only ever affects the *highest* resolutions, this probe only
     runs when it's actually relevant (quality set to 1080p or above, or
     "Best") - picking 720p or lower skips the extra round-trip entirely.

  2. "Finalizing..." used to be a single static log line covering both the
     ffmpeg mux/merge step and the final file move, so a slow merge and a
     stuck app looked identical from the log. It's now split into labeled
     steps with elapsed time for each (probing, downloading+merging, moving)
     so you can see exactly where time is going on your machine. Note the
     move itself should be near-instant (it's a same-drive rename, not a
     copy) - if that step reports as slow, the most common cause is
     downloading into a folder that's actively synced by OneDrive, Google
     Drive, or Dropbox, since those watch every file write/rename in the
     folder in real time. If finalizing is still slow after this update,
     try pointing "Save to" at a plain local folder as a test.

=== Other speed/quality notes (cumulative, vs. the very first version) ===
  - Video fragments download in parallel (concurrent_fragment_downloads=24)
    instead of one chunk at a time.
  - http_chunk_size splits even single-file (non-fragmented) streams into
    pieces, so there's something to parallelize even on videos that aren't
    served as DASH chunks. Bumped to 20MB (from 10MB) since large 4K files
    do better with fewer, bigger requests - less per-request overhead.
  - Video is merged (muxed) into mp4 instead of being re-encoded - re-encoding
    was the single biggest time cost in the original version. This still
    applies at 4K: yt-dlp copies whatever video/audio streams YouTube served
    (no re-encode) into the mp4 container, so a 4K download isn't any slower
    per-byte than a 1080p one.
  - New "fastest" audio mode skips MP3 transcoding entirely and saves the
    original audio stream as-is (m4a/opus/webm) - zero encode time.
  - The scratch folder is created *inside* your chosen output folder, so the
    final "move" is an instant rename instead of a slow cross-drive copy.
  - If aria2c is installed, it's used automatically for multi-connection
    downloading, with a larger minimum split size (4MB, up from 1MB) so big
    4K files aren't sliced into thousands of tiny pieces.
  - format_sort explicitly ranks streams by resolution, then fps, then
    bitrate, so "Best" reliably grabs the actual highest-resolution/highest-
    bitrate stream YouTube has (including 4K/8K when available) rather than
    relying on yt-dlp's default codec-preference tie-breaking.
  - Higher retry counts + a socket timeout, since bigger 4K transfers spend
    more total time in flight and are more likely to hit one flaky moment.

Quality options now include explicit 2160p (4K) and 1440p (2K) entries, plus
"Best" which is uncapped and will take whatever the highest resolution
available is (4K, 8K, whatever YouTube has for that particular video).

Honest caveat: none of this can exceed your actual internet connection speed,
and pushing concurrency too high can make YouTube start throttling/erroring
instead of helping. Also: above 1080p, YouTube only serves VP9/AV1 (no
H.264), which this script copies as-is into an mp4 container - that plays
fine in any modern browser, VLC, or TV from roughly the last decade, but very
old hardware may not like VP9/AV1-in-mp4.
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

# Try to find a working ffmpeg without needing the user to touch PATH at all.
# imageio-ffmpeg bundles its own ffmpeg binary - if it's installed, use that.
FFMPEG_PATH = None
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None

# aria2c gives multi-connection downloads (much faster than yt-dlp's built-in
# downloader on a fast line). Purely optional - only used if it's on PATH.
ARIA2C_PATH = shutil.which("aria2c")

AUDIO_MP3 = "Audio only (MP3)"
AUDIO_FAST = "Audio only (Fastest, original format)"

QUALITY_BEST = "Best (up to 4K/8K)"
QUALITY_CHOICES = [QUALITY_BEST, "2160p (4K)", "1440p (2K)", "1080p", "720p", "480p", "360p"]
HEIGHT_MAP = {
    QUALITY_BEST: None,
    "2160p (4K)": 2160,
    "1440p (2K)": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}

# Client suppression (see docstring) only ever affects the highest
# resolutions a video offers. Below this, there's nothing to gain from the
# extra metadata probe, so we skip it and go straight to a normal download.
PROBE_MIN_HEIGHT = 1080

# Deliberately broad rather than a single pinned pair, since YouTube disables
# individual clients on a rotating, unpredictable basis.
FALLBACK_CLIENTS = ["default", "tv", "web_safari", "android", "web"]


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        root.title("YouTube Downloader")
        root.geometry("640x600")
        root.resizable(False, False)
        root.configure(bg="#1e1e2e")

        self.msg_queue = queue.Queue()
        self.download_folder = os.path.join(os.path.expanduser("~"), "Downloads")

        self._build_ui()
        self._poll_queue()

        if yt_dlp is None:
            self._log("yt-dlp is not installed yet.")
            self._log("In the terminal run:  pip install yt-dlp imageio-ffmpeg")
            self._log("Then reopen this app.")
            self.download_btn.config(state="disabled")
        else:
            installed_version = getattr(yt_dlp.version, "__version__", "unknown")
            self._log(f"yt-dlp version: {installed_version}")
            if FFMPEG_PATH is None:
                self._log("Tip: MP3 and high-quality video need ffmpeg.")
                self._log("Run this once in the terminal, no PATH setup needed:")
                self._log("  pip install imageio-ffmpeg")
            if ARIA2C_PATH:
                self._log("aria2c detected - using multi-connection downloads.")
            else:
                self._log("Tip: install aria2c for faster multi-connection downloads.")
            threading.Thread(target=self._check_ytdlp_update, args=(installed_version,), daemon=True).start()

    # ---------------- UI ----------------
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground="#2b2b3d", background="#2b2b3d")

        title = tk.Label(self.root, text="YouTube Downloader", font=("Segoe UI", 18, "bold"),
                          bg="#1e1e2e", fg="#f5f5f5")
        title.pack(pady=(18, 10))

        # URL entry
        url_frame = tk.Frame(self.root, bg="#1e1e2e")
        url_frame.pack(fill="x", padx=24, pady=6)
        tk.Label(url_frame, text="Video URL", bg="#1e1e2e", fg="#cccccc",
                 font=("Segoe UI", 10)).pack(anchor="w")
        entry_row = tk.Frame(url_frame, bg="#1e1e2e")
        entry_row.pack(fill="x", pady=4)
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(entry_row, textvariable=self.url_var, font=("Segoe UI", 11),
                                   bg="#2b2b3d", fg="white", insertbackground="white", relief="flat")
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        tk.Button(entry_row, text="Paste", command=self._paste, bg="#3d3d55", fg="white",
                  relief="flat", padx=12).pack(side="left")

        # Format + quality
        opt_frame = tk.Frame(self.root, bg="#1e1e2e")
        opt_frame.pack(fill="x", padx=24, pady=12)

        tk.Label(opt_frame, text="Format", bg="#1e1e2e", fg="#cccccc",
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.format_var = tk.StringVar(value="Video (MP4)")
        ttk.Combobox(opt_frame, textvariable=self.format_var, state="readonly",
                     values=["Video (MP4)", AUDIO_MP3, AUDIO_FAST], width=28
                     ).grid(row=1, column=0, sticky="w", pady=4)

        tk.Label(opt_frame, text="Quality", bg="#1e1e2e", fg="#cccccc",
                 font=("Segoe UI", 10)).grid(row=0, column=1, sticky="w", padx=(24, 0))
        self.quality_var = tk.StringVar(value=QUALITY_BEST)
        ttk.Combobox(opt_frame, textvariable=self.quality_var, state="readonly",
                     values=QUALITY_CHOICES, width=18
                     ).grid(row=1, column=1, sticky="w", padx=(24, 0), pady=4)

        # Output folder
        folder_frame = tk.Frame(self.root, bg="#1e1e2e")
        folder_frame.pack(fill="x", padx=24, pady=6)
        tk.Label(folder_frame, text="Save to", bg="#1e1e2e", fg="#cccccc",
                 font=("Segoe UI", 10)).pack(anchor="w")
        folder_row = tk.Frame(folder_frame, bg="#1e1e2e")
        folder_row.pack(fill="x", pady=4)
        self.folder_var = tk.StringVar(value=self.download_folder)
        tk.Entry(folder_row, textvariable=self.folder_var, font=("Segoe UI", 10),
                 bg="#2b2b3d", fg="white", relief="flat", state="readonly",
                 readonlybackground="#2b2b3d").pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        tk.Button(folder_row, text="Browse", command=self._browse_folder, bg="#3d3d55", fg="white",
                  relief="flat", padx=12).pack(side="left")

        # Download button
        self.download_btn = tk.Button(self.root, text="Download", command=self._start_download,
                                       bg="#7c3aed", fg="white", font=("Segoe UI", 12, "bold"),
                                       relief="flat", pady=9, activebackground="#6d28d9")
        self.download_btn.pack(fill="x", padx=24, pady=16)

        # Progress bar
        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=24, pady=(0, 10))

        # Log box
        log_frame = tk.Frame(self.root, bg="#1e1e2e")
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        self.log_text = tk.Text(log_frame, bg="#12121c", fg="#a6e3a1", font=("Consolas", 9),
                                 relief="flat", wrap="word", state="disabled", height=10)
        self.log_text.pack(fill="both", expand=True)

    # ---------------- helpers ----------------
    def _paste(self):
        try:
            clip = self.root.clipboard_get()
            self.url_var.set(clip.strip())
        except tk.TclError:
            pass

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)

    def _log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                elif kind == "done":
                    self.download_btn.config(state="normal", text="Download")
                    messagebox.showinfo("Done", payload)
                elif kind == "error":
                    self.download_btn.config(state="normal", text="Download")
                    messagebox.showerror("Download failed", payload)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _check_ytdlp_update(self, installed_version):
        # Best-effort, non-blocking. YouTube changes how it serves video
        # often enough that yt-dlp ships fixes every 1-3 weeks - an outdated
        # copy is one of the most common causes of "quality looks wrong" or
        # "downloads suddenly stopped working" reports.
        try:
            req = urllib.request.Request(
                "https://pypi.org/pypi/yt-dlp/json",
                headers={"User-Agent": "youtube-downloader-gui"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                latest_version = json.load(resp)["info"]["version"]
            if latest_version and latest_version != installed_version:
                self.msg_queue.put((
                    "log",
                    f"An yt-dlp update is available: {installed_version} -> {latest_version}. "
                    "These updates are how fixes for YouTube's constant format/streaming "
                    "changes get shipped. Run in a terminal:  pip install -U yt-dlp",
                ))
        except Exception:
            pass  # offline, PyPI unreachable, etc. - not worth bothering the user

    # ---------------- download logic ----------------
    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a YouTube URL first.")
            return
        if yt_dlp is None:
            messagebox.showerror("Missing dependency", "Install yt-dlp first (see install_windows.bat).")
            return

        self.download_btn.config(state="disabled", text="Downloading...")
        self.progress["value"] = 0
        self._log(f"Starting: {url}")

        threading.Thread(target=self._download_worker, args=(url,), daemon=True).start()

    def _download_worker(self, url):
        out_dir = self.folder_var.get()
        os.makedirs(out_dir, exist_ok=True)
        choice = self.format_var.get()
        is_audio_mp3 = choice == AUDIO_MP3
        is_audio_fast = choice == AUDIO_FAST
        is_video = not (is_audio_mp3 or is_audio_fast)
        quality = self.quality_var.get()
        target_height = HEIGHT_MAP.get(quality)

        def hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    self.msg_queue.put(("progress", downloaded / total * 100))
                pct_str = d.get("_percent_str", "").strip()
                speed = d.get("_speed_str", "").strip()
                eta = d.get("_eta_str", "").strip()
                size = (d.get("_total_bytes_str") or d.get("_total_bytes_estimate_str") or "").strip()
                line = f"  {pct_str}  {speed}"
                if eta:
                    line += f"  ETA {eta}"
                if size:
                    line += f"  of {size}"
                self.msg_queue.put(("log", line))
            elif d["status"] == "finished":
                self.msg_queue.put(("log", "  Fragment/stream fetched, handing off to ffmpeg..."))

        def pp_hook(d):
            # Gives visibility INSIDE the old opaque "Finalizing..." step, so
            # a slow merge/transcode is visibly labeled instead of looking
            # like the app hung.
            pp = d.get("postprocessor", "postprocessor")
            status = d.get("status")
            if status == "started":
                self.msg_queue.put(("log", f"  [{pp}] starting..."))
            elif status == "finished":
                self.msg_queue.put(("log", f"  [{pp}] done."))

        def build_opts(attempt_dir, client_override):
            target_ext = None
            if is_audio_mp3:
                fmt = "bestaudio/best"
                postprocessors = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
                merge_format = None
                target_ext = "mp3"
            elif is_audio_fast:
                # No postprocessor at all - whatever audio-only stream YouTube
                # serves (usually m4a or webm/opus) gets saved untouched. This
                # is the fastest possible audio path: no ffmpeg re-encode step.
                fmt = "bestaudio/best"
                postprocessors = []
                merge_format = None
                target_ext = None  # unknown ahead of time, take whatever lands
            else:
                h = target_height
                fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]" if h else "bestvideo+bestaudio/best"
                # No FFmpegVideoConvertor here on purpose - that postprocessor
                # re-encodes the whole video, which is slow and usually
                # pointless since we just want whatever YouTube already
                # encoded (h264 up to 1080p, VP9/AV1 above that).
                # merge_output_format just muxes (copies) the streams into an
                # mp4 container - same result, a fraction of the time, and it
                # applies exactly the same way at 4K as it does at 360p.
                postprocessors = []
                merge_format = "mp4"
                target_ext = "mp4"

            opts = {
                "format": fmt,
                # Make sure "Best" actually means highest resolution ->
                # highest fps -> highest bitrate, not just whatever wins
                # yt-dlp's default codec-preference tie-break. This is what
                # makes the 4K/8K "Best" option reliable.
                "format_sort": ["res", "fps", "br"],
                "outtmpl": os.path.join(attempt_dir, "%(title)s.%(ext)s"),
                "postprocessors": postprocessors,
                "progress_hooks": [hook],
                "postprocessor_hooks": [pp_hook],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                # Parallel fragment fetching for DASH-served video/audio.
                "concurrent_fragment_downloads": 24,
                # Split even single-file (non-fragmented) streams into 20MB
                # pieces - large enough to keep per-request overhead low on
                # big 4K files, small enough to still parallelize well on a
                # fast connection.
                "http_chunk_size": 20 * 1024 * 1024,
                "retries": 10,
                "fragment_retries": 10,
                "socket_timeout": 30,
                # Avoids a class of "video not available in your region"
                # retries/failures that would otherwise slow things down.
                "geo_bypass": True,
            }
            if client_override:
                # Only set when the pre-download probe (or the rare safety-
                # net retry) determined it's needed. Leaving this unset lets
                # yt-dlp use its own current default client fallback logic,
                # which upstream keeps tuned to whatever YouTube currently
                # allows - more durable than a pin baked into this script.
                opts["extractor_args"] = {"youtube": {"player_client": client_override}}
            if merge_format:
                opts["merge_output_format"] = merge_format
            if FFMPEG_PATH:
                opts["ffmpeg_location"] = FFMPEG_PATH
            if ARIA2C_PATH:
                # aria2c opens multiple connections per file, which is
                # usually the single biggest speedup available if your
                # connection can support it. Minimum split size raised to
                # 4MB (from 1MB) so multi-gigabyte 4K files aren't cut into
                # thousands of tiny pieces - that just adds HTTP overhead
                # without helping throughput.
                opts["external_downloader"] = "aria2c"
                opts["external_downloader_args"] = {
                    "aria2c": ["-x", "16", "-s", "16", "-k", "4M"]
                }
            return opts, target_ext

        def max_available_height(info):
            formats = info.get("formats") or []
            heights = [f.get("height") for f in formats
                       if f.get("height") and f.get("vcodec") not in (None, "none")]
            return max(heights) if heights else None

        def achieved_quality(info):
            reqs = info.get("requested_formats") or [info]
            vid = next((f for f in reqs if f.get("vcodec") not in (None, "none")), None)
            aud = next((f for f in reqs if f.get("acodec") not in (None, "none") and f is not vid), None)
            height = vid.get("height") if vid else info.get("height")
            parts = []
            if vid:
                w, h = vid.get("width"), vid.get("height")
                if w and h:
                    parts.append(f"{w}x{h}")
                vcodec = vid.get("vcodec")
                if vcodec:
                    parts.append(vcodec.split(".")[0])
                vbr = vid.get("vbr") or vid.get("tbr")
                if vbr:
                    parts.append(f"{vbr:.0f} kbps video")
            if aud:
                abr = aud.get("abr")
                if abr:
                    parts.append(f"{abr:.0f} kbps audio")
            return height, (", ".join(parts) if parts else "unknown")

        def probe_client_override():
            """Cheap metadata-only lookup (skip_download=True - no video
            data transferred) to decide, BEFORE downloading anything,
            whether the default client is likely to under-deliver on this
            video. This is what used to happen only AFTER a full download,
            which is what made a wrong guess cost an entire second download.
            Only runs for quality settings actually at risk (see
            PROBE_MIN_HEIGHT) - lower-quality picks skip straight through.
            """
            if not is_video:
                return None
            if target_height and target_height < PROBE_MIN_HEIGHT:
                return None

            def probe(client_override):
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "noplaylist": True,
                    "geo_bypass": True,
                }
                if client_override:
                    opts["extractor_args"] = {"youtube": {"player_client": client_override}}
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                    return max_available_height(info)
                except Exception:
                    return None

            h_default = probe(None)
            h_fallback = probe(FALLBACK_CLIENTS)
            if h_fallback and (not h_default or h_fallback > h_default * 1.1):
                self.msg_queue.put((
                    "log",
                    f"Default client exposes up to {h_default or '?'}p for this video; "
                    f"a broader client list exposes {h_fallback}p - using that one from the start.",
                ))
                return FALLBACK_CLIENTS
            return None

        try:
            # Scratch folder lives INSIDE the destination folder (not the
            # system temp dir) so the final move is a same-filesystem
            # rename, not a slow copy across drives. Still cleaned up
            # automatically, and a failed/interrupted run never leaves
            # partial files in the real output folder.
            with tempfile.TemporaryDirectory(prefix=".ytdl_", dir=out_dir) as scratch_dir:

                t_probe_start = time.time()
                client_override = probe_client_override()
                t_probe = time.time() - t_probe_start
                if t_probe > 0.05:
                    self.msg_queue.put(("log", f"Checked available formats in {t_probe:.1f}s."))

                attempt_dir = os.path.join(scratch_dir, "attempt0")
                os.makedirs(attempt_dir, exist_ok=True)
                opts, target_ext = build_opts(attempt_dir, client_override)

                self.msg_queue.put(("log", "Downloading..."))
                t_dl_start = time.time()
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                t_download = time.time() - t_dl_start

                # Rare safety net: only reached if we didn't already probe
                # with the broader client list (either quality was low
                # enough to skip probing, or the probe itself said the
                # default was fine) AND the result still looks short. This
                # should now be uncommon - most cases are caught up-front.
                if is_video and client_override is None:
                    got_height, _ = achieved_quality(info)
                    best_height = max_available_height(info)
                    if target_height and best_height:
                        expected_height = min(target_height, best_height)
                    else:
                        expected_height = target_height or best_height
                    degraded = expected_height and (got_height is None or got_height < expected_height * 0.85)

                    if degraded:
                        self.msg_queue.put(("log",
                            f"Got {got_height or '?'}p but ~{expected_height}p should be available - "
                            "retrying once with a broader client list..."))
                        self.msg_queue.put(("progress", 0))
                        attempt_dir2 = os.path.join(scratch_dir, "attempt1")
                        os.makedirs(attempt_dir2, exist_ok=True)
                        opts2, target_ext2 = build_opts(attempt_dir2, FALLBACK_CLIENTS)
                        t_retry_start = time.time()
                        with yt_dlp.YoutubeDL(opts2) as ydl2:
                            info2 = ydl2.extract_info(url, download=True)
                        t_download += time.time() - t_retry_start
                        got_height2, _ = achieved_quality(info2)
                        if got_height2 and (not got_height or got_height2 > got_height):
                            info, attempt_dir, target_ext = info2, attempt_dir2, target_ext2

                title = info.get("title", "video")

                self.msg_queue.put(("log", "Finalizing: moving file to destination folder..."))
                t_move_start = time.time()

                if target_ext:
                    finished = [f for f in os.listdir(attempt_dir) if f.lower().endswith("." + target_ext)]
                    if not finished:
                        finished = os.listdir(attempt_dir)  # fallback: move whatever exists
                else:
                    finished = os.listdir(attempt_dir)

                saved_path = None
                for fname in finished:
                    src = os.path.join(attempt_dir, fname)
                    dst = os.path.join(out_dir, fname)
                    shutil.move(src, dst)
                    saved_path = dst

                t_move = time.time() - t_move_start

            self.msg_queue.put(("progress", 100))
            timing_line = f"Timing - format check: {t_probe:.1f}s, download+merge: {t_download:.1f}s, move: {t_move:.1f}s"
            if t_move > 2:
                timing_line += (
                    "\n(That move step is normally near-instant since it's a same-drive rename. "
                    "If it's consistently slow, check whether your Save-to folder is synced by "
                    "OneDrive/Google Drive/Dropbox - those intercept every file write and can "
                    "add real delay here.)"
                )
            self.msg_queue.put(("log", timing_line))

            if is_video:
                got_height, desc = achieved_quality(info)
                best_height = max_available_height(info)
                quality_line = f"Quality: {desc}"
                if best_height and got_height and best_height > got_height * 1.1:
                    quality_line += (
                        f"\nNote: YouTube lists {best_height}p as available for this video, "
                        f"but {got_height}p was downloaded - that's most likely a real source-side "
                        "limit (e.g. an upscaled '4K' upload) rather than something this app can fix."
                    )
                self.msg_queue.put(("done", f"Saved: {title}\n\nLocation: {saved_path or out_dir}\n\n{quality_line}"))
            else:
                self.msg_queue.put(("done", f"Saved: {title}\n\nLocation: {saved_path or out_dir}"))
        except Exception as e:
            msg = str(e)
            if "ffmpeg" in msg.lower():
                msg += ("\n\nffmpeg looks like it's missing. Install it and try again "
                        "(see README.md for the one-line install command).")
            self.msg_queue.put(("error", msg))


def main():
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()