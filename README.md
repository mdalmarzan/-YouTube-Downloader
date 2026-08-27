# 🎬 YouTube Downloader

A simple and fast **YouTube Downloader desktop application** built with **Python and Tkinter**. It provides an easy point-and-click interface for downloading YouTube videos as MP4 or audio as MP3, with support for different resolutions including **4K/8K when available**.

The application uses **yt-dlp** for downloading, **FFmpeg** for media processing, and optionally **aria2c** for faster multi-connection downloads.

## ✨ Features

* 🎥 Video download in MP4
* 🎵 Audio download in MP3
* ⚡ Fast original-format audio download
* 💎 4K / 2160p support
* 🔥 2K / 1440p support
* 📺 1080p, 720p, 480p and 360p
* 🏆 Best quality up to 4K/8K
* 📋 One-click URL paste
* 📁 Custom download folder
* 📊 Real-time progress bar
* 🚀 Parallel fragment downloading
* ⚡ Optional aria2c acceleration
* 🔧 Automatic FFmpeg detection
* 🔄 yt-dlp update checking
* 🔍 Smart quality/format detection
* 🧹 Automatic temporary-file cleanup

## 🛠️ Built With

* **Python**
* **Tkinter**
* **yt-dlp**
* **FFmpeg**
* **imageio-ffmpeg**
* **aria2c** *(optional)*

## 📋 Requirements

Before running the project, make sure you have:

* Python installed
* `yt-dlp`
* `imageio-ffmpeg`
* FFmpeg support
* Optional: `aria2c`

## ▶️ How to Run

### 1. Open the project

Open the folder containing:

```text
youtube-downloader/
│
├── youtube_downloader.py
└── README.md
```

### 2. Open VS Code Terminal

Open the project folder in **VS Code**.

Go to:

```text
Terminal → New Terminal
```

Make sure the terminal is inside your project folder.

Check with:

```powershell
pwd
```

### 3. Install Dependencies

Run:

```powershell
python -m pip install yt-dlp imageio-ffmpeg
```

If `python` doesn't work, try:

```powershell
py -m pip install yt-dlp imageio-ffmpeg
```

### 4. Run the Application

Run:

```powershell
python youtube_downloader.py
```

Or:

```powershell
py youtube_downloader.py
```

The **YouTube Downloader** window will open.

### 🖱️ Run by Double-Clicking

After installing the dependencies, you can also double-click:

```text
youtube_downloader.py
```

The program creates its Tkinter window automatically when started.

## 🎯 How to Use

1. Open the application.
2. Copy a YouTube video URL.
3. Click **Paste**.
4. Select **Video (MP4)** or an audio option.
5. Select your desired quality.
6. Choose where you want to save the file.
7. Click **Download**.
8. Monitor the progress in the log box.
9. Your downloaded file will be saved in the selected folder.

## 🎞️ Quality Options

```text
Best (up to 4K/8K)
2160p (4K)
1440p (2K)
1080p
720p
480p
360p
```

The project explicitly provides these quality choices and maps them to their corresponding video heights.

## 🎵 Audio Options

### Audio Only — MP3

Downloads the best available audio and converts it to **MP3 at 192 kbps**.

### Audio Only — Fastest

Downloads the original audio stream without re-encoding, making it the fastest audio option.

## ⚡ Performance

The downloader uses up to **24 concurrent fragment downloads** and 20 MB HTTP chunks to improve download performance.

If `aria2c` is installed, the application can use multiple connections for downloading:

```text
16 connections
16 splits
4 MB split size
```

## 🔧 FFmpeg

FFmpeg is used when the application needs to merge video and audio streams or convert audio to MP3.

The project can automatically locate an FFmpeg executable through `imageio-ffmpeg`, reducing the need for manual PATH configuration.

Install it with:

```powershell
python -m pip install imageio-ffmpeg
```

## 🔄 Update yt-dlp

YouTube can change how its video streams are delivered. Keeping `yt-dlp` updated can help maintain compatibility.

Update it with:

```powershell
python -m pip install -U yt-dlp
```

The application also checks PyPI for a newer installed-version match when it starts.

## ⚠️ Notes

* Maximum quality depends on what the individual YouTube video actually provides.
* Download speed depends on your internet connection and server conditions.
* 4K/8K cannot improve the original quality of an upscaled video.
* Very high concurrency can sometimes cause throttling.
* Some older devices may have limited support for VP9/AV1 inside MP4.

## 🔐 Responsible Use

Use this project only for content you have permission to download or content that is otherwise legally available for downloading.

Respect copyright, creators' rights, and YouTube's applicable terms.

## 👨‍💻 Author

**Al Marzan**

Built with ❤️ using Python.

---

⭐ **If you like this project, consider giving the repository a star!**
