from fastapi.exceptions import HTTPException
import time
from fastapi import FastAPI, Body, Query
from pydantic import BaseModel, Field
from urllib.parse import urlparse
import re
from typing import Optional, Any
import subprocess
import shutil
import json
from mediaplayer import MPVMediaPlayer

version="0.1.0"

tags_metadata = [
    {
        "name": "Server Status",
        "description": "Get the status of the server.",
    },
    {
        "name": "Player",
        "description": "Manage the Player. Play Media. Control: Play, Pause, Stop",
        "externalDocs": {
            "description": "Items external docs",
            "url": "https://fastapi.tiangolo.com/",
        },
    },
]

class PlayerInfo(BaseModel):
    status: Optional[str] = None
    current_media_type: Optional[str] = None
    volume: Optional[int] = None
    is_paused: bool = False
    cache_size: int = 0
    media_name: Optional[str] = None
    media_uploader: Optional[Any] = None
    media_duration: int = 0  # string default as "0"
    media_progress: int = 0
    is_live: Optional[bool] = False
    media_url: Optional[str] = ""
    
# INITIALISE, AND USE THIS FOR STATE MANAGEMENT
player_info = PlayerInfo(
    is_paused=False,
    cache_size=0,
    media_duration=0,
    media_progress=0
)

class MediaData(BaseModel):
    url: str = Field(..., description="The URL of the media to play. Supported sources: YouTube, Spotify.")
    # media_type: str = "video"  # Default to video, can be 'audio' or 'video'
    # start_time: int = 0  # Start time in seconds
    # end_time: int = None  # End time in seconds, optional
    # volume: int = 100  # Volume level from 0 to 100
    # cache_size: int = 0  # Cache size in MB, optional

# class MediaInfo(BaseModel):
#     title: str
#     uploader: str
#     duration: int  # Duration in seconds
#     is_live: bool = False  # Whether the media is a live stream
#     media_type: str = "video"  # Default to video, can be 'audio' or 'video'
#     progress_seconds: int = 0  # Current playback position in seconds
#     media_source: str = "none"  # Source of the media (e.g., YouTube, Spotify)
#     media_name: str = None  # Name of the media file
#     media_uploader: str = None  # Uploader of the media file


class MediaInfo(BaseModel):
    title: Optional[str] = ""
    upload_date: Optional[str] = ""
    uploader: Optional[str] = ""
    channel: Optional[str] = ""
    url: Optional[str] = ""
    video_id: Optional[str] = ""
    
media_info = MediaInfo()
    
class LastPlayedMedia(BaseModel):
    title: str
    url: str
    
last_played_media = LastPlayedMedia(title="", url="")

app = FastAPI(
    title="Stream Station",
    description="System to stream media from YouTube and Spotify to local speakers or Chromecast devices.",
    version=version,
    openapi_tags=tags_metadata
)

start_time = time.monotonic()

player_instance: Optional[MPVMediaPlayer] = None

def check_ytdlp_available():
    return shutil.which("yt-dlp") is not None

def get_media_data(url: str) -> Optional[MediaInfo]:
    try:
        if not check_ytdlp_available():
            print("yt-dlp not available")
            return None

        cmd = ["yt-dlp", "-j", url]  # -j = print metadata as JSON
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        
        if result.returncode != 0:
            raise Exception(f"yt-dlp error: {result.stderr.strip()}")

        data = json.loads(result.stdout)
        
        print(data)
        
        media_info.title=data.get("title"),
        media_info.upload_date=data.get("upload_date"),
        media_info.uploader=data.get("uploader"),
        media_info.channel=data.get("channel", data.get("channel_id")),  # fallback if channel is missing
        media_info.url=data.get("webpage_url"),
        media_info.video_id=extract_youtube_id(url)  # Extract YouTube ID for reference

        return data
        


    except subprocess.TimeoutExpired:
        print("yt-dlp metadata fetch timed out")
        return None
    except Exception as e:
        print(f"Error fetching media info: {e}")
        return None
    

def extract_youtube_id(url: str) -> str | None:
    # Match typical YouTube URL formats
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^\s&]+)",
        r"(?:https?://)?youtu\.be/([^\s?/]+)",
        r"(?:https?://)?(?:www\.)?youtube\.com/embed/([^\s?/]+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@app.get("/", tags=["Server Status"], summary="Get server status")
def server_status():
    uptime_seconds = time.monotonic() - start_time
    return {
        "uptime_seconds": round(uptime_seconds, 2),
        "version": version,
        "status": "running",
        "player_status": "stopped"
        }

@app.get("/player", tags=["Player"], summary="Get Player Status", response_model=PlayerInfo)
def player_status():
    """
    Get the current status of the media player.
    """
    # Placeholder for actual player status logic
    return player_info
    
@app.post("/player/play")
def play_media(MediaData: Optional[MediaData] = Body(None)):
    """
    Play media in the player.
    """
    global player_instance
    
    # HELPER FUNCTIONS
    # def is_valid_url(url: str) -> bool:
    #     pattern = re.compile(
    #         r'^(https?:\/\/)?'                  # optional http or https
    #         r'(www\.)?'                         # optional www.
    #         r'([a-z0-9-]+\.)+[a-z]{2,}'         # domain like example.com or sub.domain.co.in
    #         r'(:\d+)?'                          # optional port
    #         r'(\/[^\s]*)?$'                     # optional path
    #         , re.IGNORECASE
    #     )
    #     return bool(pattern.match(url))
    
    # ----------------------------------- #
    
    #  TODO IF player is already initialised then just play the media
    if player_instance is not None and not MediaData:
        player_instance.play()
    
    if MediaData is None or not MediaData.url:
        raise HTTPException(status_code=400, detail="Media URL is required.")
        
    global player_info
    if player_info.is_paused is True:
        player_info.is_paused = False
    
    # TODO Validate URL
    # if not is_valid_url(MediaData.url):
    #     raise HTTPException(status_code=400, detail="Invalid URL format.")

    # domain = urlparse(MediaData.url).netloc.lower()
    url = MediaData.url.strip()
    # global player_instance
    if "youtube.com" in url or "youtu.be" in url:
        media = get_media_data(url)
        if media:
            # PLAY THE PLAYER
            try:
                
                # SET STATE TODO
                player_info.status = "playing"
                player_info.media_name = str(media.get("title"))
                player_info.media_uploader = media.get("uploader"),
                player_info.media_duration = int(float(media.get("duration", 0)))
                player_info.media_progress = 0
                player_info.media_url = media.get("webpage_url")
                
                player_info.current_media_type = "youtube"
                is_live = media.get("is_live", False)
                player_info.is_live = is_live
                
                
                # UNLOAD PREVIOUS MEDIA IF ANY
                player_instance = None
                player_instance = MPVMediaPlayer(media.get("webpage_url"))
                player_instance.play()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to play media: {str(e)}")
            
            # TODO GET LAST PLAYED DATA
            global last_played_media
            pass
            # SET LAST PLAYED DATA
            global last_played_media
            last_played_media.title = media.get("title")
            last_played_media.url = media.get("webpage_url")
            
            return player_info
        
        else:
            raise HTTPException(status_code=404, detail="Media not found or unsupported format.")
    elif "spotify.com" in url:
        return {"type": "spotify"}
    else:
        raise HTTPException(status_code=400, detail="Unsupported media source. Only YouTube is supported at this time.")
    
    
@app.post("/player/pause")
def pause_player():
    global player_instance
    if player_instance is None:
        raise HTTPException(status_code=400, detail="No media is currently loaded")
    try:
        global player_info
        player_info.is_paused = True
        player_info.status = "paused"
        
        player_instance.pause()
        
        return player_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute pause: {str(e)}")

@app.post("/player/stop")
def stop_player():
    global player_instance
    if player_instance is None:
        raise HTTPException(status_code=400, detail="No media is currently loaded")
    try:
        player_instance.stop()
        player_instance = None  # Reset the player instance
        
        global player_info
        # Reset the STATE
        player_info = PlayerInfo()
        player_info.status = "stopped"
        # player_info.current_media = ""
        # player_info.is_paused = False
        # player_info.media_duration = 0
        # player_info.media_progress = 0
        # player_info.media_name = ""
        # player_info.media_uploader = ""
        # player_info.cache_size = 0
        # player_info.volume = 0
        
        return player_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute stop: {str(e)}")
    
@app.post("/player/replay")
def replay_player():
    global player_instance
    try:
        if player_instance is not None:
        # Unloading and loading just to be safe
        # ideally it should just seek to zero.
            player_instance = None
            
        global player_info
        if player_info.is_paused is True:
            player_info.is_paused = False
        
        player_info.status = "replay"
        player_info.media_url = last_played_media.url
        player_info.media_name = last_played_media.title
        
        player_instance = MPVMediaPlayer(last_played_media.url)
        player_instance.play()
        return player_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute replay: {str(e)}")
    
@app.post("/player/volume")
def set_volume(set: int = Query(..., ge=0, le=150, description="Volume percent (0-150)")):
    global player_instance
    if player_instance is None or not player_instance.is_running():
        raise HTTPException(status_code=400, detail="No media is currently loaded or player has stopped")
    if not (0 <= set <= 150):
        raise HTTPException(status_code=400, detail="Volume must be between 0 and 150")
    try:
        player_instance._send_ipc_command({"command": ["set_property", "volume", set]})
        return {"status": f"Volume set to {set}%"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set volume: {str(e)}")

# @app.get("/player")    
# def 
# @app.get("/health", tags=["Server Status"], summary="Health check")

# if __name__ == "__main__":
#     main()
