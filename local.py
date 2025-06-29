import os
from mutagen import File
import musicbrainzngs

# Setup MusicBrainz API
musicbrainzngs.set_useragent("SongMetadataFetcher", "1.0", "msm74588@gmail.com")

def list_files_in_directory(directory):
    """Return a list of file paths in the given directory (excluding subfolders)."""
    try:
        return [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))
        ]
    except Exception as e:
        print(f"Error reading directory: {e}")
        return []

def fetch_metadata_from_musicbrainz(query):
    """Try to fetch song metadata from MusicBrainz using file name as query."""
    try:
        result = musicbrainzngs.search_recordings(query, limit=1)
        recordings = result.get("recording-list", [])
        if recordings:
            rec = recordings[0]
            title = rec.get("title", query)
            artist = rec.get("artist-credit", [{}])[0].get("name", "Unknown Artist")
            return f"{title} - {artist}"
    except Exception as e:
        pass
    return None

def print_song_metadata(file_path):
    """Try local metadata, then MusicBrainz, else fallback to filename."""
    try:
        audio = File(file_path, easy=True)
        if audio is not None and audio.tags:
            title = audio.get("title", [None])[0]
            artist = audio.get("artist", [None])[0]
            if title and artist:
                print(f"{title} - {artist}")
                return
    except Exception:
        pass  # continue to MusicBrainz fallback

    # Try online metadata using filename
    base_name = os.path.basename(file_path)
    name_without_ext = os.path.splitext(base_name)[0]
    fetched = fetch_metadata_from_musicbrainz(name_without_ext)
    if fetched:
        print(fetched)
    else:
        print(base_name)

# === Usage ===
if __name__ == "__main__":
    directory_path = "./songs"  # ← Change this
    files = list_files_in_directory(directory_path)
    for file_path in files:
        print_song_metadata(file_path)
