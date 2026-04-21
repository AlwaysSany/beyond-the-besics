# Flask APScheduler App

A simple Flask application with background job scheduling using [APScheduler](https://github.com/agronholm/apscheduler), managed with the [uv](https://docs.astral.sh/uv/) package manager.

---

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed on your system
- Python 3.13+ (to match `pyproject.toml`)
- A `.venv` virtual environment already created and active via `uv`

---

## Project Structure

```
.
├── app.py                        # Dev entrypoint (debug server)
├── wsgi.py                       # WSGI entrypoint (Gunicorn)
├── run_scheduler.py              # Standalone scheduler process
├── flask_ap_scheduler_app/
│   ├── __init__.py               # create_app()
│   ├── config.py                 # Settings & Flask config
│   ├── routes.py                 # HTTP routes
│   └── scheduler.py              # APScheduler jobs and wiring
├── Dockerfile
├── docker-compose.yml
├── k8s/
│   ├── base/
│   │   ├── deployment-web.yaml
│   │   ├── deployment-scheduler.yaml
│   │   ├── service.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── dev/kustomization.yaml
│       └── prod/kustomization.yaml
├── k8s.yaml                      # Convenience: kustomize entry (dev)
├── requirements.txt
└── README.md
```

---

## Project Demo

[app scheduler](./app-scheduler-apidocs.png)


---

## Setup & Run

### Step 1 — Initialize the project with uv (first time only)

If you haven't already created a `pyproject.toml` for this project, run:

```bash
uv init
```

> Skip this step if `pyproject.toml` already exists in your project folder.

---

### Step 2 — Create and activate the virtual environment

```bash
uv venv
```

This creates a `.venv` folder in your project directory. uv will automatically use it for subsequent commands.

---

### Step 3 — Install dependencies

Install the required packages from `requirements.txt`:

```bash
uv pip install -r requirements.txt
```

Optionally install `gunicorn` if you want to run the production-style setup locally:

```bash
uv pip install gunicorn
```

You should see `flask`, `flask-apscheduler`, and (optionally) `gunicorn` installed into `.venv`.

---

### Step 4 — Run the application

#### Option A — Dev server (single process)

```bash
uv run app.py
```

#### Option B — Production style (separate web + scheduler)

```bash
# Web (Gunicorn)
uv run gunicorn -b 0.0.0.0:5000 wsgi:app

# Scheduler (separate terminal)
uv run python run_scheduler.py
```

---

## Using the API

Once the server is running, open a browser or use `curl` to interact with it.

| Endpoint                                 | Method | Description                                |
| ---------------------------------------- | ------ | ------------------------------------------ |
| `http://127.0.0.1:5000/`                 | GET    | Overview and available endpoints           |
| `http://127.0.0.1:5000/logs`             | GET    | View recent job execution logs             |
| `http://127.0.0.1:5000/jobs`             | GET    | List all scheduled jobs and next run times |
| `http://127.0.0.1:5000/jobs/<id>/pause`  | POST   | Pause a specific job                       |
| `http://127.0.0.1:5000/jobs/<id>/resume` | POST   | Resume a paused job                        |

**Examples using curl:**

```bash
# View all scheduled jobs
curl http://127.0.0.1:5000/jobs

# View job logs
curl http://127.0.0.1:5000/logs

# Pause the heartbeat job
curl -X POST http://127.0.0.1:5000/jobs/heartbeat/pause

# Resume the heartbeat job
curl -X POST http://127.0.0.1:5000/jobs/heartbeat/resume
```

---

## Scheduled Jobs

| Job ID          | Trigger                  | Description                               |
| --------------- | ------------------------ | ----------------------------------------- |
| `heartbeat`     | Every 10 seconds         | Logs a heartbeat tick entry               |
| `cleanup`       | Every 30 seconds         | Trims log history to the last 50 entries  |
| `hourly_report` | Cron — top of every hour | Logs a summary of total entries on record |

---

## Stopping the Server

- **Dev server**: `Ctrl + C` in the terminal running `uv run app.py`
- **Gunicorn**: `Ctrl + C` in the terminal running Gunicorn
- **Scheduler**: `Ctrl + C` in the terminal running `run_scheduler.py`

---

## Docker

Build and run with Docker:

```bash
docker build -t flask-ap-scheduler:latest .
docker run -p 5000:5000 flask-ap-scheduler:latest
```

Use `docker-compose` for separate web + scheduler containers:

```bash
docker-compose up --build
```

- Web UI/API: `http://localhost:5000/`
- Scheduler runs in a separate `scheduler` service container.

---

## Kubernetes (Kustomize)

This repo includes a Kustomize-based Kubernetes layout.

**Directory layout:**

- `k8s/base/`
  - `deployment-web.yaml` — web deployment (Gunicorn, `SCHEDULER_ENABLED=0`)
  - `deployment-scheduler.yaml` — scheduler worker deployment
  - `service.yaml` — ClusterIP service on port 80 → 5000
- `k8s/overlays/dev/` — dev overlay
- `k8s/overlays/prod/` — prod overlay

The root `k8s.yaml` is a convenience Kustomization pointing to the dev overlay.

### Build manifests

```bash
# Dev
kustomize build k8s/overlays/dev

# Prod
kustomize build k8s/overlays/prod
```

### Apply to a cluster

```bash
# Dev
kubectl apply -k k8s/overlays/dev

# Prod
kubectl apply -k k8s/overlays/prod
```

Make sure you push the Docker image to a registry and update the `image:` fields in `k8s/base/deployment-*.yaml` (for example: `ghcr.io/<user>/flask-ap-scheduler:latest`).

---

## Troubleshooting

**Port already in use:**
```bash
# Find and kill the process using port 5000
lsof -i :5000
kill -9 <PID>
```

**Dependencies not found after install:**
Make sure you're running commands from the project root where `.venv` lives. uv automatically picks up the local `.venv`.

**Re-install all dependencies from scratch:**
```bash
uv pip install -r requirements.txt --reinstall
```
