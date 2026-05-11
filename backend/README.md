# WanderBot Backend

FastAPI + SQLite backend for the WanderBot V1 travel assistant.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 6688
```

API docs: http://127.0.0.1:6688/docs
