# API

The WSL HTTP service lives in `backend/api`. Run it during development with:

```powershell
uv run --project backend/api uvicorn vcontainer_api.main:app --host 127.0.0.1 --port 8010
```

Interactive documentation is available at `http://127.0.0.1:8010/docs`.
