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