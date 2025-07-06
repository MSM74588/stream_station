import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
AUTH_PATH = os.path.join(os.path.dirname(__file__), "spotify_auth.yaml")
SPOTIFY_DB_PATH = os.path.join(os.path.dirname(__file__), "spotify_liked_songs.db")
SPOTIFY_SCOPES = "user-library-read user-read-playback-state user-modify-playback-state"
LIKED_SONGS_DB_PATH = os.path.join(os.path.dirname(__file__), "liked_songs.db")