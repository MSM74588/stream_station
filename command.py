"""
This file handles the commands that will be run by subprocess
"""

import subprocess
from typing import Optional

IGNORE_PLAYERS = "Gwenview,firefox,GSConnect"



def open_sp_client(track_id):
    xdg_uri = f"spotify:track:{track_id}"
    try:
        subprocess.run(["xdg-open", xdg_uri], check=True)
        print("Spotify track opened successfully.")
    except subprocess.CalledProcessError as e:
        print("Failed to open Spotify track:", e)
    except FileNotFoundError:
        print("xdg-open not found. Make sure you're on a Linux system with xdg-utils installed.")

def control_playerctl(command, player: Optional[str] = "active"):
    import shlex
    try:
        args = ["playerctl", f"--player={player}",f"--ignore-player={IGNORE_PLAYERS}"] + shlex.split(command)
        subprocess.run(args, check=True)
        print(f"Executed: {' '.join(args)}")
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")
    except FileNotFoundError:
        print("playerctl not found. Please install it first.")

if __name__ == "__main__":
    
    # Spotify track URI
    track_id = "0FQhID3J9Hqul3X0jf9nnW"
    open_sp_client(track_id)