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