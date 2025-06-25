import subprocess
import json
import os
import socket
import time
import uuid
import threading
from typing import Optional

class MPVMediaPlayer:
    def __init__(self, url):
        if not url:
            raise ValueError("A valid URL must be provided to initialize MediaPlayerManager.")

        self.url = url
        self.info = {}
        self.ipc_path = f"/tmp/mpv_socket_{uuid.uuid4().hex[:8]}"  # Unique socket path
        self.process: 'Optional[subprocess.Popen]' = None

        # Only fetch metadata if it's a YouTube link
        if "youtube.com" in url or "youtu.be" in url:
            print(f"🌍 URL: {url}")
            try:
                result = subprocess.run(
                    ['yt-dlp', '--dump-json', url],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self.info = json.loads(result.stdout)
                print("Metadata loaded successfully.")
            except Exception as e:
                print("Failed to fetch metadata:", e)
        

        # Start mpv with IPC enabled
        try:
            self.process = subprocess.Popen([
                'mpv',
                url,
                '--no-terminal',
                '--no-video',
                '--force-window=no',
                '--player-operation-mode=pseudo-gui',
                f'--input-ipc-server={self.ipc_path}'
            ])
            print(f"Started mpv with IPC at {self.ipc_path}")

            # Wait for the socket to appear
            for _ in range(20):
                if os.path.exists(self.ipc_path):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("IPC socket not created in time.")

        except Exception as e:
            print("❌ Failed to start mpv:", e)

        self._monitor_thread = threading.Thread(target=self._monitor_cache, daemon=True)
        self._stop_monitor = threading.Event()
        self._monitor_thread.start()

    def _send_ipc_command(self, command: dict):
        """Send a command to the mpv IPC socket."""
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(self.ipc_path)
                client.sendall((json.dumps(command) + '\n').encode('utf-8'))
        except Exception as e:
            print(f"⚠️ IPC command failed: {e}")

    def play(self):
        self._send_ipc_command({"command": ["set_property", "pause", False]})
        print("▶️ Resumed playback.")

    def pause(self):
        self._send_ipc_command({"command": ["set_property", "pause", True]})
        print("⏸️ Paused playback.")

    def stop(self):
        self._stop_monitor.set()
        self._send_ipc_command({"command": ["quit"]})
        print("⏹️ Stopped playback.")

    def _monitor_cache(self):
        """Monitor mpv's cache size and stop if it exceeds 1GB."""
        MAX_CACHE = 1073741824  # 1GB in bytes
        while not self._stop_monitor.is_set():
            try:
                cache_size = self._get_cache_size()
                paused = self._get_paused()
                if cache_size is not None and cache_size > MAX_CACHE:
                    print(f"⚠️ Cache size exceeded 1GB: {cache_size} bytes. Stopping player.")
                    self.stop()
                    break
                if paused and cache_size is not None and cache_size > MAX_CACHE:
                    print(f"⚠️ Cache size exceeded 1GB while paused: {cache_size} bytes. Stopping player.")
                    self.stop()
                    break
            except Exception as e:
                print(f"⚠️ Cache monitor error: {e}")
            self._stop_monitor.wait(2)  # Check every 2 seconds

    def _get_cache_size(self):
        """Get the current cache size from mpv via IPC."""
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(self.ipc_path)
                command = {"command": ["get_property", "demuxer-cache-state"]}
                client.sendall((json.dumps(command) + '\n').encode('utf-8'))
                response = client.recv(4096)
                result = json.loads(response.decode('utf-8'))
                cache_state = result.get("data", {})
                return cache_state.get("cache-size", 0)
        except Exception as e:
            print(f"⚠️ Failed to get cache size: {e}")
            return None

    def _get_paused(self):
        """Check if mpv is paused via IPC."""
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(self.ipc_path)
                command = {"command": ["get_property", "pause"]}
                client.sendall((json.dumps(command) + '\n').encode('utf-8'))
                response = client.recv(1024)
                result = json.loads(response.decode('utf-8'))
                return result.get("data", False)
        except Exception as e:
            print(f"⚠️ Failed to get paused state: {e}")
            return False

    # def get_state(self):
    #     return {
    #         'title': self.info.get('title'),
    #         'uploader': self.info.get('uploader'),
    #         'duration': self.info.get('duration')
    #     }
    def get_state(self):
        progress = None
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(self.ipc_path)
                command = {"command": ["get_property", "time-pos"]}
                client.sendall((json.dumps(command) + '\n').encode('utf-8'))
                
                # Receive response
                response = client.recv(1024)
                result = json.loads(response.decode('utf-8'))
                progress = result.get("data")
        except Exception as e:
            print(f"⚠️ Failed to get playback progress: {e}")
        
        return {
            'title': self.info.get('title'),
            'uploader': self.info.get('uploader'),
            'duration': self.info.get('duration'),
            'progress_seconds': progress,
            'media_type': 'live' if self.info.get('is_live') else 'video'
        }

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def get_volume(self) -> Optional[float]:
        """Get the current volume level of mpv."""
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(self.ipc_path)
                command = {"command": ["get_property", "volume"]}
                client.sendall((json.dumps(command) + '\n').encode('utf-8'))
                response = client.makefile().readline()
                result = json.loads(response)
                return result.get("data")
        except Exception as e:
            print(f"⚠️ Failed to get volume: {e}")
            return None

    def get_progress(self) -> Optional[float]:
        """Get the current playback position (in seconds) from mpv."""
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(self.ipc_path)
                command = {"command": ["get_property", "time-pos"]}
                client.sendall((json.dumps(command) + '\n').encode('utf-8'))
                response = client.makefile().readline()
                result = json.loads(response)
                return result.get("data")
        except Exception as e:
            print(f"⚠️ Failed to get playback progress: {e}")
            return None



# Test runner
if __name__ == "__main__":
    # test_url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    test_url = 'https://www.youtube.com/watch?v=jfKfPfyJRdk'
    player = MPVMediaPlayer(test_url)

    print("\n=== get_state() ===")
    state = player.get_state()
    for key, value in state.items():
        print(f"{key.capitalize()}: {value if value is not None else 'N/A'}")

    # Optional controls for testing
    print(player.get_state().get('media_type'))
    time.sleep(120)
    player.pause()
    time.sleep(10)
    player.play()
    print(player.get_state().get('progress_seconds', 'N/A'))
    time.sleep(10)
    player.stop()
