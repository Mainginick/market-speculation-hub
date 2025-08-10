# Market Speculation Hub (Render-ready)

A tiny Flask app with login, image posts, and a market snapshot.

## Key fixes
- Renamed main file to `app.py` and ensured Gunicorn points to it.
- Added missing dependency `Flask-SQLAlchemy` and Postgres driver.
- Added minimal Jinja2 templates.
- Added `/healthz` route for Render health checks.
- Guarded APScheduler behind `ENABLE_SCHEDULER` env var to avoid multiple instances on Gunicorn.
- Added a persistent disk mount for uploads (and for SQLite if you stay on SQLite).

## Deploy to Render

1. Push this folder to a **new GitHub repo**.
2. In Render:
   - **New > Web Service** → connect your repo.
   - Environment: `Python`.
   - Build command: `pip install -r requirements.txt` (already in `render.yaml`).
   - Start command: `gunicorn -w 1 -t 120 app:app` (already in `render.yaml`).
   - Add env var `ENABLE_SCHEDULER=1` if you want background market fetches.
   - Add a **Disk** with mount path `/opt/render/project/src/static/uploads` (render.yaml does this automatically).
3. Click deploy.

### Using Postgres (optional but recommended)
- Create a **Render Postgres** instance, attach it to the service. Render will inject `DATABASE_URL`.
- The app auto-detects `DATABASE_URL` and uses it instead of SQLite. No code changes required.

### Local dev
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_DEBUG=1 SECRET_KEY=dev ENABLE_SCHEDULER=0
python app.py
```
