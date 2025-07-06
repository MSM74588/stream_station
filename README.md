# Stream Station Server

- Software for AV reciever
- Control Media playback via api
- Play audio from Youtube.
- Sync spotify liked songs


## Development

```bash
# Activate virtual env:
source .venv/bin/activate
```

```bash
# Start Server with auto reload:
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Setting up.
- Check `spotify_redirect_uri` and setup accordingly.
- Setup `spotify_auth.yaml`


### Setting up spotify player
- Install Spotify App (either via package manager or wget in docker)
- Install spotify-cli-linux (spotifycli) - is it needed though? as i will control via mpris
- Install Spicetify -> to remove the ads. (spicetify-cli)
- [Spotify Docs from AUR](https://aur.archlinux.org/packages/spotify)

> This may not work as there will be no GUI in the docker env

- Spotify first gets downloaded, then moded with spicetify. 

- if this does not work, try to use spotDL

- Opening a specific song: `xdg-open spotify:track:0FQhID3J9Hqul3X0jf9nnW`

- May need to to setup spotify as autostart.

- Cannot use with firefox in headless mode as it requires widevine

## Spotify Client way.
- Run spotify two ways, one just to launch spotify (auto kill any background spotify process first), so this then will can control spotify control.
- May need to run in a fake gui. via Xvfb.
- Then with spotify URI handling. (kill all previous Spotify clients.)
- This way i will always be compatible with spotify.
- Mod the spotify with adfree spicetify plugin.
- The spotify client data needed to be copied. 

- Or Use Firefox and login via cookie.
https://github.com/rxri/spicetify-extensions/tree/main/adblock

## Setting up Spicetify with Spotify.
- `spicetify backup apply` - TODO! add a command to run this block manually.
    - `TROUBLESHOOT: sudo chmod 777 /opt/spotify -R`
- Copy addblock.js to spicetify extension
    - `curl -L https://raw.githubusercontent.com/rxri/spicetify-extensions/main/adblock/adblock.js -o ~/.config/spicetify/Extensions/adblock.js`
- `spicetify config extensions adblock.js`
- `spicetify apply`
- `spicetify config sidebar_config 0`
- `spicetify apply`

## OR USE SPOTUBE!! (but no spotify-connect) -> but, got a legal notice.
- No longer maintained, due to legal notice, but WORK IN PROGRESS.

## TODO, choose spotify player type:
- If yt-dlp is selected, it will play the spotify song via ytdlp
- and if spotify is setup, it will play the song in spotify client.

## Setting up mpd (systemwide)
- `sudo pacman -S mpd`
- `mkdir ~/.mpd`


`systemctl --user enable --now mpd.socket`

```conf
#  ~/.config/mpd/mpd.conf
db_file		"~/.mpd/database"
log_file "syslog"
music_directory "~/Music"

playlist_directory "~/.mpd/playlists"
state_file	"~/.mpd/state"
sticker_file "~/.mpd/sticker.sql"

auto_update "yes"
auto_update_depth "0"

port "6600"

# if you want mpd to start paused
restore_paused "yes"

audio_output {
	type	"pulse"
	name	"Music"
}
```

- mpd needs to be auto-started (or start the daemon)

- trigger a refresh of db via mpc
    - `mpc update`

- TROUBLESHOOT
    - `mpd verbose` -> outputs the config file location

- Now add mpdris2 to add support for mpd control via mpris
    - `sudo pacman -S mpdris2`

- launch mpdris2 manually.

## TODO:
- [x] Download feature
- [ ] Offline Handling
- [ ] Rewrite to sockets so can communicate via IPC sockets
- [ ] MQTT paho support
- [ ] Control Host via LNXLink
- [ ] Arduino HID Media Button Controls
- [ ] HID Display Output.
- [ ] SnapCast Integration
- [ ] Google Chromecast support. via SDK.
- [ ] Queue (adding via frontend) and then auto sequnce
- [ ] Repeat Mode set, Shuffle Set.

# Needed Dependencies (incomplete)
```bash
# Test These first.

sudo pacman -Sy --needed mpd mpc mpdris2 playerctl ffmpeg yt-dlp mpv

uv tool install spotdl

sudo pacman -Sy python-mutagen

yay -S spotify
```

