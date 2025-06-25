import yaml
import os
import sqlite3
import spotipy
from spotipy.oauth2 import SpotifyOAuth

import subprocess

from constants import AUTH_PATH, CONFIG_PATH, SPOTIFY_DB_PATH, SPOTIFY_SCOPES

import socket

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Doesn't send data, just opens socket
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def is_spotify_setup():
    return os.path.exists(AUTH_PATH)

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def save_auth(data):
    with open(AUTH_PATH, "w") as f:
        yaml.safe_dump(data, f)

def load_auth():
    if not os.path.exists(AUTH_PATH):
        return None
    with open(AUTH_PATH, "r") as f:
        return yaml.safe_load(f)

def init_spotify_db():
    conn = sqlite3.connect(SPOTIFY_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS liked_songs (
            id TEXT PRIMARY KEY,
            name TEXT,
            artist TEXT,
            album_art TEXT,
            spotify_url TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_songs_to_db(songs):
    conn = sqlite3.connect(SPOTIFY_DB_PATH)
    c = conn.cursor()
    for song in songs:
        c.execute("""
            INSERT OR REPLACE INTO liked_songs (id, name, artist, album_art, spotify_url)
            VALUES (?, ?, ?, ?, ?)
        """, (song["id"], song["name"], song["artist"], song["album_art"], song["spotify_url"]))
    conn.commit()
    conn.close()

def get_songs_from_db():
    conn = sqlite3.connect(SPOTIFY_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, artist, album_art, spotify_url FROM liked_songs")
    rows = c.fetchall()
    conn.close()
    return [
        {"id": row[0], "name": row[1], "artist": row[2], "album_art": row[3], "spotify_url": row[4]}
        for row in rows
    ]

def fetch_liked_songs_from_spotify():
    auth = load_auth()
    config = load_config()
    import time
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

    songs = []
    results = sp.current_user_saved_tracks(limit=50)
    while results:
        for item in results["items"]:
            track = item["track"]
            song = {
                "id": track["id"],
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                "spotify_url": track["external_urls"]["spotify"]
            }
            songs.append(song)
        if results["next"]:
            results = sp.next(results)
        else:
            break
    return songs

def search_youtube_url(query: str) -> str | None:
    """
    Use yt-dlp to search YouTube and return the URL of the best match.
    """
    try:
        search_cmd = [
            "yt-dlp",
            f"ytsearch1:{query}",
            "--print", "webpage_url"
        ]
        result = subprocess.run(search_cmd, capture_output=True, text=True, check=True, timeout=60)  # timeout 60s
        url = result.stdout.strip().splitlines()[0]
        return url
    except subprocess.TimeoutExpired:
        print("yt-dlp search timed out")
        return None
    except Exception as e:
        print(f"Error searching YouTube: {e}")
        return None