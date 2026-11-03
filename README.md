# SLING SHORTS AI

A free, local-first AI Shorts maker starter project.

## Features
- Premium dark-purple web interface.
- Upload local MP4/MOV/WebM videos.
- Create multiple vertical 9:16 clips.
- Generate subtitles with faster-whisper when installed.
- Face-aware crop positioning using OpenCV.
- Export MP4 clips without adding a watermark.

## Hosting reality
The frontend can be hosted publicly for free. Video processing runs on each user's own computer; unlimited public cloud processing is not free. Visitors must run their own backend unless you pay for server compute.

YouTube URL processing is intended only for videos you own or have permission to download. Respect YouTube's terms, copyright, and local law.

## Requirements
- Windows 10/11
- Python 3.10+
- FFmpeg on PATH

## Windows setup
1. Install Python and enable Add Python to PATH.
2. Install FFmpeg and add its `bin` folder to PATH.
3. Open `backend` and run `start_windows.bat`.
4. Open `http://127.0.0.1:8000`.

## Public frontend
The `web` folder can be deployed as a static site. A public backend needs compute, authentication, upload limits, abuse protection, and storage controls. Do not expose port 8000 directly to the public internet.

## Notes
The clip ranking is heuristic, not a guarantee of virality. Face detection is lightweight, not cinematic-grade tracking.