import threading
import queue
import time
import os
from yt_dlp import YoutubeDL

# === CONFIGURATION ===
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class YTDLPDownloader:
    def __init__(self):
        self.download_queue = queue.Queue()
        self.current_progress = "All downloads complete"
        self.lock = threading.Lock()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            speed = d.get('_speed_str', '0 B/s').strip()
            eta = d.get('_eta_str', '--:--').strip()
            total = d.get('_total_bytes_str', '?').strip()

            with self.lock:
                self.current_progress = (
                    # LOG OUT THE DETAILS
                    
                    f"{percent} | Speed: {speed} | ETA: {eta} | Size: {total}"
                )
        elif d['status'] == 'finished':
            with self.lock:
                self.current_progress = "All downloads complete"

    def _worker(self):
        while True:
            url = self.download_queue.get()
            if url is None:
                break

            print(f"\n=== Starting download: {url} ===")
            with self.lock:
                self.current_progress = "Starting..."

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
                'progress_hooks': [self._progress_hook],
                'quiet': True,
                'noplaylist': True,
                'nooverwrites': False,
                'retries': 1,
                'force_overwrites': True,
                'ignoreerrors': True,
                'continuedl': False,
                'writethumbnail': True,
                'postprocessors': [
                    {
                        # Convert to mp3
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '0',
                    },
                    {
                        # Embed the thumbnail as album art
                        'key': 'EmbedThumbnail',
                        'already_have_thumbnail': False,
                    },
                    {
                        # Add basic metadata
                        'key': 'FFmpegMetadata',
                    }
                ],
                'prefer_ffmpeg': True,
                'verbose': False
            }

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                print(f"⚠️ Error downloading {url}: {e}")
                with self.lock:
                    self.current_progress = f"Download failed: {url}"

            self.download_queue.task_done()

    def add_to_queue(self, url: str):
        self.download_queue.put(url)
        print(f"➕ Added to queue: {url}")

    def get_current_progress(self):
        with self.lock:
            return self.current_progress

    def wait_until_done(self):
        self.download_queue.join()

    def stop(self):
        self.download_queue.put(None)
        self.worker_thread.join()

# === Example Usage ===
if __name__ == "__main__":
    downloader = YTDLPDownloader()

    downloader.add_to_queue("https://www.youtube.com/watch?v=eB3eXQOUvA8")
    downloader.add_to_queue("https://www.youtube.com/watch?v=wJJZUXWde-A")

    while True:
        progress = downloader.get_current_progress()
        print(f"[Progress] {progress}")
        if progress == "All downloads complete":
            break
        time.sleep(1)

    downloader.wait_until_done()
    downloader.stop()
    print("✅ All downloads finished.")
