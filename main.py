from fastapi.exceptions import HTTPException
import time
from fastapi import FastAPI, Body, Query, Request
from pydantic import BaseModel, Field
from urllib.parse import urlparse, unquote
import re
from typing import Optional, Any
import subprocess
import shutil
import json
from mediaplayer import MPVMediaPlayer

from command import open_sp_client, control_playerctl, IGNORE_PLAYERS

from fastapi.responses import HTMLResponse, RedirectResponse

from spotipy.oauth2 import SpotifyOAuth
import spotipy

from functions import fetch_liked_songs_from_spotify, init_spotify_db, save_songs_to_db, get_songs_from_db, load_auth, save_auth, load_config, is_spotify_setup, get_lan_ip

from constants import AUTH_PATH, CONFIG_PATH, SPOTIFY_DB_PATH, SPOTIFY_SCOPES

from functions import search_youtube_url

from templates import render_spotify_setup_page

import asyncio
from contextlib import asynccontextmanager
import signal
from pathlib import Path

from fastapi.responses import Response
import shlex

from mutagen import File as MutagenFile

import requests

MPD_PORT = "6601"
version="0.1.0"

player_type = ""

config = load_config()
spotify_mode = config["spotify_mode"]
control_mode = config["control_mode"]

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
    volume: Optional[int] = 0
    is_paused: bool = False
    cache_size: int = 0
    media_name: Optional[str] = ""
    media_uploader: Optional[Any] = ""
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
    url: Optional[str] = Field(None, description="The URL of the media to play. Supported sources: YouTube, Spotify.")
    song_name : Optional[str] = Field(
        None, 
        description="Name of the song to search and play from YouTube if URL is not provided."
    )

# ------------ Lifespan handling ------------
mpdris2_path = shutil.which("mpDris2")

if not mpdris2_path:
    raise FileNotFoundError("mpDris2 not found in PATH. Please install it (e.g., via pacman or apt).")

mpd_proc: subprocess.Popen | None = None
mpdirs2_proc: subprocess.Popen | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mpd_proc, mpdirs2_proc

    # --- Setup directories ---
    project_dir = Path(__file__).resolve().parent
    music_dir = (project_dir / "Music" ).resolve()
    music_dir.mkdir(parents=True, exist_ok=True)

    state_dir = project_dir / "state"
    state_dir.mkdir(exist_ok=True)

    # --- Write mpd.conf dynamically ---
    mpd_config = project_dir / "mpd.conf"
    mpd_config.write_text(f"""
music_directory        "{music_dir}"
playlist_directory     "{state_dir}/playlists"
db_file                "{state_dir}/database"
log_file               "{state_dir}/mpd.log"
pid_file               "{state_dir}/mpd.pid"
state_file             "{state_dir}/state"
sticker_file           "{state_dir}/sticker.sql"
bind_to_address        "127.0.0.1"
port                   "{MPD_PORT}"

auto_update "yes"
auto_update_depth "0"
""")

    # --- Start MPD ---
    mpd_proc = subprocess.Popen(
        ["mpd", "--no-daemon", str(mpd_config)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for MPD socket to become available
    for _ in range(20):
        if mpd_proc.poll() is not None:
            raise RuntimeError("MPD exited early — check mpd.conf or logs")
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 6601)
            writer.close()
            await writer.wait_closed()
            break
        except OSError:
            await asyncio.sleep(0.1)
    else:
        raise RuntimeError("MPD socket did not become available")

    print(f"✅ MPD started with music dir: {music_dir}")

    # --- Run `mpc update` to update the DB ---
    try:
        subprocess.run(["mpc", "-h", "127.0.0.1", "-p", f"{MPD_PORT}", "update"], check=True)
        print("📂 MPD music database updated")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Failed to run `mpc update`: {e}")

    # --- Start mpdirs2 bound publicly ---
    # mpdirs2_proc = subprocess.Popen([
    #     "mpDirs2",
    #     "--host", "0.0.0.0",
    #     "--port", "8080",
    #     "--mpd-host", "127.0.0.1",
    #     "--mpd-port", "6601",
    # ])
    mpdirs2_proc = subprocess.Popen([
        # HAVE TO ADD python3 as dbus is not available inside venv interpreter.
        "/usr/bin/python3",
        mpdris2_path,
        "--port", f"{MPD_PORT}",
    ])
    print("✅ mpdirs2 started at http://<your-ip>:8080")
    
    global player_instance
    if player_instance is not None:
        player_instance = None

    yield  # App is now running

    # --- On Shutdown: Stop mpdirs2 ---
    if mpdirs2_proc and mpdirs2_proc.poll() is None:
        mpdirs2_proc.send_signal(signal.SIGTERM)
        try:
            mpdirs2_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mpdirs2_proc.kill()
            mpdirs2_proc.wait()
        print("🛑 mpdirs2 stopped")

    # --- On Shutdown: Stop MPD ---
    if mpd_proc and mpd_proc.poll() is None:
        mpd_proc.send_signal(signal.SIGTERM)
        try:
            mpd_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mpd_proc.kill()
            mpd_proc.wait()
        print("🛑 MPD stopped")
        
    if player_instance is not None:
        player_instance = None
        
# ----------------------------------------------------------------------------- #

# PLAYERCTL DATA
def get_playerctl_data(player: Optional[str] = None) -> PlayerInfo:
    
    time.sleep(0.5) 
    # To settle the playing state, since dbus is updated asynchronously,
    # so calling it instantly after setting state will still return the previous value.
    
    def run_playerctl_command(args):
        cmd = ["playerctl", f"--ignore-player={IGNORE_PLAYERS}"]
        if player:
            cmd += ["--player", player]
        cmd += args
        try:
            return subprocess.check_output(cmd, text=True).strip()
        except subprocess.CalledProcessError:
            return None
        except FileNotFoundError:
            print("playerctl not found.")
            return None

    # Fetch data
    status = run_playerctl_command(["status"]) or "Stopped"
    title = run_playerctl_command(["metadata", "xesam:title"]) or ""
    artist = run_playerctl_command(["metadata", "xesam:artist"]) or ""
    url = run_playerctl_command(["metadata", "xesam:url"]) or ""
    volume = run_playerctl_command(["volume"]) or "0"
    duration_us = run_playerctl_command(["metadata", "mpris:length"]) or "0"
    position_us = run_playerctl_command(["position"]) or "0"

    # Convert microseconds to seconds
    def to_seconds(us):
        try:
            return int(float(us)) // 1_000_000
        except (ValueError, TypeError):
            return 0

    # Final object
    return PlayerInfo(
        status=status.lower(),
        current_media_type="audio",  # You can detect more accurately if needed
        volume=int(float(volume) * 100),  # Convert to 0–100 scale
        is_paused=(status.lower() != "playing"),
        cache_size=0,  # You can implement this if relevant
        media_name=title,
        media_uploader=artist,
        media_duration=to_seconds(duration_us),
        media_progress=to_seconds(position_us),
        media_url=url
    )
    
# NOTE: When using MPRIS to control set the is_live parameter manually by checking YT api


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
    openapi_tags=tags_metadata,
    lifespan=lifespan
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





# -------------------------------------- ROUTES ---------------------------------------------------------- #

@app.get("/", tags=["Server Status"], summary="Get server status")
def server_status():
    uptime_seconds = time.monotonic() - start_time
    return {
        "uptime_seconds": round(uptime_seconds, 2),
        "version": version,
        "status": "running",
        "player_status": "stopped"
        }
    
# -------------------------------------------- PLAYER ---------------------------------------------------------- #

@app.get("/player", tags=["Player"], summary="Get Player Status", response_model=PlayerInfo)
def player_status():
    """
    Get the current status of the media player.
    """
    global player_info
    global player_type
    global player_instance
    
    
    if control_mode == "mpris":
        
        player_info = get_playerctl_data(player=player_type)
        return player_info
    else:
        
        if player_instance is not None:
            player_info.volume = int(player_instance.get_volume())
            player_info.media_progress = int(player_instance.get_progress())
            
        
        return player_info
    
@app.post("/player/play")
def play_media(MediaData: Optional[MediaData] = Body(None)):
    """
    Play media in the player.
    """
    global player_instance
    global player_info
    global player_type
    
    # ----------------------------------- #
    
    
    #  TODO IF player is already initialised then just play the media
    if control_mode == "mpris" and not MediaData:
        print(f"▶️ PLAYER TYPE: {player_type}")
        control_playerctl("play-pause", player=player_type)
        player_info =  get_playerctl_data(player=player_type)
        return player_info
    else:
        if player_instance is not None and not MediaData:
            player_instance.play()
    
    if MediaData is None or (not MediaData.url and not MediaData.song_name):
        raise HTTPException(status_code=400, detail="Media URL or song name is required.")
    
    # MPD HANDLING
    if MediaData.song_name and not MediaData.url:
        song_name = MediaData.song_name.strip()
        print(f"🎵 MPD Song Name: '{song_name}'")

        # Clear MPD playlist (optional)
        subprocess.run(["mpc", f"--port={MPD_PORT}", "clear"], check=False)

        # Try to find and add song by title
        cmd = ["mpc", f"--port={MPD_PORT}", "findadd", "title", song_name]
        print("🔧 Running command:", " ".join(shlex.quote(arg) for arg in cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)

        print("stdout:", result.stdout.strip())
        print("stderr:", result.stderr.strip())

        if result.returncode != 0:
            raise HTTPException(status_code=404, detail=f"Song not found in MPD library: '{song_name}'")

        # Stop any other players
        control_playerctl("--player=mpv,spotify,mpd,firefox stop")
        if player_instance is not None:
            player_instance = None

        # Play the added song
        subprocess.run(["mpc", f"--port={MPD_PORT}", "play"], check=False)
        
        player_type = "mpd"

        # Refresh player info from playerctl
        player_info = get_playerctl_data(player=player_type)
        
        # WHY this way? bcoz when running the subprocess command, it returns blank.
        if player_info.status != "playing":
             raise HTTPException(status_code=404, detail=f"Song not found in MPD library: '{song_name}'")
        else:
            return player_info

    
    
    
    
    # is paused state update. (toggle)
    if player_info.is_paused is True:
        player_info.is_paused = False
    
    # TODO Validate URL
    # if not is_valid_url(MediaData.url):
    #     raise HTTPException(status_code=400, detail="Invalid URL format.")

    # domain = urlparse(MediaData.url).netloc.lower()
    url = MediaData.url.strip()
    # global player_instance
    
    # YOUTUBE HANDLING
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
                control_playerctl("--player=spotify,firefox,mpd stop")
                
                player_instance = MPVMediaPlayer(media.get("webpage_url"))
                
                player_info.volume = player_instance.get_volume()
                
                player_type = "mpv"
                
                
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
        
    # SPOTIFY HANDLING
    elif "spotify.com" in url:
        if not is_spotify_setup():
            raise HTTPException(status_code=403, detail="Spotify is not authenticated. Please visit /setup.")

        auth = load_auth()
        config = load_config()
        
        print("Loaded config and auth")
        
        if not config or not all(k in config for k in ("spotify_client_id", "spotify_client_secret", "spotify_redirect_uri")):
            raise HTTPException(status_code=500, detail="Spotify configuration is missing or incomplete in config.yaml.")
        
        if auth and "access_token" in auth and "expires_at" in auth:
            if auth["expires_at"] > int(time.time()):
                sp = spotipy.Spotify(auth=auth["access_token"])
            else:
                sp_oauth = SpotifyOAuth(
                    client_id=config["spotify_client_id"],
                    client_secret=config["spotify_client_secret"],
                    redirect_uri=config["spotify_redirect_uri"],
                    scope=SPOTIFY_SCOPES,
                    cache_path=AUTH_PATH
                )
                token_info = sp_oauth.refresh_access_token(auth["refresh_token"])
                save_auth(token_info)
                sp = spotipy.Spotify(auth=token_info["access_token"])
        else:
            sp_oauth = SpotifyOAuth(
                client_id=config["spotify_client_id"],
                client_secret=config["spotify_client_secret"],
                redirect_uri=config["spotify_redirect_uri"],
                scope=SPOTIFY_SCOPES,
                cache_path=AUTH_PATH
            )
            token_info = sp_oauth.get_access_token(as_dict=True)
            save_auth(token_info)
            sp = spotipy.Spotify(auth=token_info["access_token"])
            
        print("Spotify API ready")
        
        match = re.search(r"track/([A-Za-z0-9]+)", url)
        
        if not match:
            raise HTTPException(status_code=400, detail="Invalid Spotify track URL")
        
        track_id = match.group(1)
        print(f"SPOTIFY TRACK ID: {track_id}")
        
        if spotify_mode == "sp_client":
            # Stop Any previous playing media
            control_playerctl("--player=mpv,spotify,mpd,firefox stop")
            if player_instance is not None:
                player_instance = None
            
            player_type = "spotify"
            # OPEN SPOTIFY via xdg-open
            open_sp_client(track_id)
            
            player_info = get_playerctl_data(player=player_type)
            
            return player_info
        else:
            # HANDLING SPOTIFY PLAYBACK with YT-DLP
            try:
                track = sp.track(track_id)
                print("Fetched track info from Spotify")
                if not track:
                    raise HTTPException(status_code=404, detail="Could not retrieve Spotify track info")
                title = track['name']
                artist = track['artists'][0]['name']
                search_query = f"{title} {artist}"
            except Exception as e:
                print(f"Error fetching Spotify track info: {e}")
                raise HTTPException(status_code=404, detail="Could not retrieve Spotify track info")
            
            print(f"Searching YouTube for: {search_query}")
            
            yt_url = search_youtube_url(search_query)
            
            print(f"yt_url: {yt_url}")
            
            if not yt_url:
                raise HTTPException(status_code=404, detail="Could not find a matching YouTube video")
            
            print(f"{title} - {artist}")
            url = yt_url
            # THEN CONTINUE TO YOUTUBE HANDLING
            media = get_media_data(url)
            
            if yt_url and media:
                # PLAY THE PLAYER
                try:
                            
                    # SET STATE TODO
                    player_info.status = "playing"
                    player_info.media_name = str(media.get("title"))
                    player_info.media_uploader = media.get("uploader"),
                    player_info.media_duration = int(float(media.get("duration", 0)))
                    player_info.media_progress = 0
                    player_info.media_url = media.get("webpage_url")
                    
                    player_info.current_media_type = "spotify"
                    is_live = media.get("is_live", False)
                    player_info.is_live = is_live
                    
                    
                    # UNLOAD PREVIOUS MEDIA IF ANY
                    control_playerctl("--player=spotify,firefox,mpd stop")
                    player_instance = None
                    
                    player_instance = MPVMediaPlayer(yt_url)
                    
                    player_type = "mpv"
                    player_instance.play()
                    
                    player_info.volume = player_instance.get_volume()
                    
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to play media: {str(e)}")
                
                
                # SET LAST PLAYED DATA
                last_played_media.title = media.get("title")
                last_played_media.url = media.get("webpage_url")
                
                return player_info
        
        
        
        return {
            "type": "spotify",
            "url": url,
            "yt_url": yt_url
        }
    else:
        raise HTTPException(status_code=400, detail="Unsupported media source. Only YouTube is supported at this time.")
    
    
@app.post("/player/pause")
def pause_player():
    global player_info
    global player_type
    global player_instance
    
    
    if control_mode == "mpris":
        control_playerctl("pause", player=player_type)
        player_info = get_playerctl_data(player=player_type)
        return player_info
    else:
        if player_instance is None:
            raise HTTPException(status_code=400, detail="No media is currently loaded")
        try:
            
            player_info.is_paused = True
            player_info.status = "paused"
            
            player_info.volume = player_instance.get_volume()
            
            player_instance.pause()
            
            return player_info
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to execute pause: {str(e)}")

@app.post("/player/stop")
def stop_player():
    global player_info
    global player_type
    global player_instance
    
    
    if control_mode == "mpris":
        player_type = ""
        control_playerctl("--player=mpv,spotify,mpd,firefox  stop")
        
        # NOTE: May need specific, but player is empty now.
        player_info = get_playerctl_data()
        return player_info
    else:
        if player_instance is None:
            raise HTTPException(status_code=400, detail="No media is currently loaded")
        try:
            player_instance.stop()
            player_instance = None  # Reset the player instance
            
            
            # Reset the STATE
            player_info = PlayerInfo()
            player_info.status = "stopped"
            
            return player_info
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to execute stop: {str(e)}")
    
@app.post("/player/replay")
def replay_player():
    if control_mode == "mpris":
        # control_playerctl("pause")
        return {"player_info": "TODO, pending application"}
    else:
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
            
            player_info.volume = player_instance.get_volume()
            
            return player_info
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to execute replay: {str(e)}")
    
@app.post("/player/volume")
def set_volume(set: int = Query(..., ge=0, le=150, description="Volume percent (0-150)")):
    global player_info
    global player_type
    
    if control_mode == "mpris":
        # control_playerctl("pause")
        # convert the number into a decimal.
        if not (0 <= set <= 150):
            raise HTTPException(status_code=400, detail="Volume must be between 0 and 150")
        
        scaled_vol = set / 100

        control_playerctl(f"volume {scaled_vol}", player=player_type)
        player_info = get_playerctl_data(player=player_type)
        return player_info
    else:
        global player_instance
        
        if player_instance is None or not player_instance.is_running():
            raise HTTPException(status_code=400, detail="No media is currently loaded or player has stopped")
        if not (0 <= set <= 150):
            raise HTTPException(status_code=400, detail="Volume must be between 0 and 150")
        try:
            player_instance._send_ipc_command({"command": ["set_property", "volume", set]})
            player_info.volume = player_instance.get_volume()
            # return {"status": f"Volume set to {set}%"}
            return player_info
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set volume: {str(e)}")

@app.post("/player/next")
def player_next():
    global player_type
    if control_mode == "mpris":
        control_playerctl("next", player=player_type)
        return {
            "message": "player next"
        }
    else:
        raise HTTPException(status_code=501, detail="method only available in MPRIS mode")
    
@app.post("/player/previous")
def player_previous():
    global player_type
    if control_mode == "mpris":
        control_playerctl("previous", player=player_type)
        return {
            "message": "player previous"
        }
    else:
        raise HTTPException(status_code=501, detail="method only available in MPRIS mode")
# -------------------------------------------- AUTH + SPOTIFY ---------------------------------------------------------- #

@app.post("/setup")
@app.get("/setup")
def setup():
    config = load_config()
    client_id = config.get('spotify_client_id', 'NOT SET') if config else 'NOT SET'
    client_secret_status = 'SET' if config and config.get('spotify_client_secret') else 'NOT SET'
    lan_ip = get_lan_ip()
    html = render_spotify_setup_page(client_id, client_secret_status, lan_ip)
    return HTMLResponse(content=html)

@app.get("/auth/spotify")
def auth_spotify():
    config = load_config()
    if not config or not all(k in config for k in ("spotify_client_id", "spotify_client_secret", "spotify_redirect_uri")):
        return HTMLResponse("<h3>Spotify configuration is missing or incomplete in config.yaml.</h3>", status_code=500)
    sp_oauth = SpotifyOAuth(
        client_id=config["spotify_client_id"],
        client_secret=config["spotify_client_secret"],
        redirect_uri=config["spotify_redirect_uri"],
        scope=SPOTIFY_SCOPES,  # <-- use the correct scopes here
        cache_path=AUTH_PATH
    )
    auth_url = sp_oauth.get_authorize_url()
    return RedirectResponse(auth_url)

# -------------------------------------- SPOTIFY SONG FETCHING ----------------------------------------------------------- #

@app.get("/get_spotify_songs")
def get_spotify_songs():
    init_spotify_db()
    # If DB is empty, fetch from Spotify and save
    songs = get_songs_from_db()
    if not songs:
        try:
            songs = fetch_liked_songs_from_spotify()
            save_songs_to_db(songs)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch from Spotify: {e}")
    return songs

# -------------------------------------------- TASKS ------------------------------------------------------------------------ #

@app.post("/sync/spotify")
def sync_spotify_songs():
    """
    Manually fetch liked songs from Spotify and update the local database.
    """
    try:
        songs = fetch_liked_songs_from_spotify()
        save_songs_to_db(songs)
        return {"status": "success", "synced_count": len(songs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync from Spotify: {e}")

@app.get("/auth/spotify/callback")
def spotify_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("<h3>No authorization code received.</h3>", status_code=400)

    config = load_config()
    if not config or not all(k in config for k in ("spotify_client_id", "spotify_client_secret", "spotify_redirect_uri")):
        return HTMLResponse("<h3>Spotify configuration is missing or incomplete in config.yaml.</h3>", status_code=500)

    sp_oauth = SpotifyOAuth(
        client_id=config["spotify_client_id"],
        client_secret=config["spotify_client_secret"],
        redirect_uri=config["spotify_redirect_uri"],
        scope=SPOTIFY_SCOPES,
        cache_path=AUTH_PATH
    )

    try:
        token_info = sp_oauth.get_access_token(code, as_dict=True)
        if not token_info:
            return HTMLResponse("<h3>Failed to get access token from Spotify.</h3>", status_code=400)

        save_auth(token_info)

        access_token = token_info.get("access_token")
        refresh_token = token_info.get("refresh_token")
        expires_in = token_info.get("expires_in")

        return HTMLResponse(f"""
            <html>
            <head>
                <title>Spotify Auth Success</title>
                <style>
                    body {{ font-family: sans-serif; background-color: #f9f9f9; padding: 2em; }}
                    textarea {{ width: 100%; height: 100px; padding: 0.5em; font-family: monospace; }}
                    .info {{ margin-top: 1em; background: #fff; padding: 1em; border: 1px solid #ccc; }}
                </style>
            </head>
            <body>
                <h2>Spotify Authentication Successful</h2>
                <p>Copy your access token below:</p>
                <textarea readonly>{access_token}</textarea>
                <div class="info">
                    <p><strong>Refresh Token:</strong> {refresh_token}</p>
                    <p><strong>Expires In:</strong> {expires_in} seconds</p>
                </div>
                <p>You may now close this page.</p>
            </body>
            </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h3>Error exchanging code for token: {e}</h3>", status_code=500)
    
@app.get("/youtube")
def yt_feed():
    pass

@app.get("/songs")
def list_songs():
    try:
        output = subprocess.check_output([
            "mpc", "-h", "127.0.0.1", "-p", "6601",
            "--format", "%file%|%title%|%artist%|%album%|%track%|%time%",
            "listall"
        ], text=True)
    except subprocess.CalledProcessError as e:
        return {"error": "Failed to query MPD", "details": str(e)}

    project_dir = Path(__file__).resolve().parent
    music_dir = (project_dir / "Music").resolve()
    songs = []

    for line in output.strip().split("\n"):
        if not line.strip():
            continue

        parts = (line.split("|") + [""] * 6)[:6]
        file_rel, title, artist, album, track, time_str = parts
        file_path = music_dir / file_rel

        # Fallback title
        title = title or Path(file_rel).stem

        # Get file size
        try:
            size_bytes = file_path.stat().st_size
        except FileNotFoundError:
            size_bytes = None

        # Read metadata using Mutagen
        duration = None
        try:
            audio = MutagenFile(file_path, easy=True)
            if audio:
                metadata = audio.tags or {}

                artist = metadata.get('artist', [artist])[0] or None
                album = metadata.get('album', [album])[0] or None
                title = metadata.get('title', [title])[0] or title
                track = metadata.get('tracknumber', [track])[0] or None

                if hasattr(audio.info, 'length'):
                    duration = int(audio.info.length)
        except Exception:
            # fallback to MPD's time
            duration = int(time_str) if time_str.isdigit() else None

        songs.append({
            "file": file_rel,
            "title": title,
            "artist": artist,
            "album": album,
            "track": track,
            "duration": duration,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2) if size_bytes else None
        })

    return {"songs": songs}

@app.get("/album_art")
def album_art():
    global player_type

    valid_states_by_player = {
        "spotify": ["playing", "paused"],
        "mpd": ["playing"],
        "mpv": ["playing", "paused"]  # if supported via playerctl
    }

    valid_states = valid_states_by_player.get(player_type, [])

    try:
        status = subprocess.check_output(
            ["playerctl", "--player=" + player_type, "status"],
            text=True
        ).strip().lower()
        print(f"{player_type} status: {status}")

        if status not in valid_states:
            return {"error": f"{player_type} not in a valid state"}

        url = subprocess.check_output(
            ["playerctl", "--player=" + player_type, "metadata", "mpris:artUrl"],
            text=True
        ).strip()
        print(f"{player_type} artUrl: {url}")

        if url.startswith("file://"):
            parsed = urlparse(url)
            local_path = Path(unquote(parsed.path))
            print(f"Trying local path: {local_path}")

            if not local_path.exists():
                return {"error": "File not found at local path"}

            mime = "image/jpeg"
            if local_path.suffix.lower() == ".png":
                mime = "image/png"

            return Response(content=local_path.read_bytes(), media_type=mime)

        elif url.startswith("http"):
            print(f"Downloading remote image from: {url}")
            response = requests.get(url, timeout=5)

            if response.status_code != 200:
                return {"error": f"HTTP request failed with status: {response.status_code}"}

            mime = response.headers.get("Content-Type", "image/jpeg")
            return Response(content=response.content, media_type=mime)

        else:
            return {"error": f"Unrecognized art URL format: {url}"}

    except subprocess.CalledProcessError as e:
        print(f"{player_type} command failed: {e}")
        return {"error": f"{player_type} command failed: {e}"}
    except Exception as e:
        print(f"Unexpected error for {player_type}: {e}")
        return {"error": f"Unexpected error for {player_type}: {e}"}