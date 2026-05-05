# Top Five

> AI-powered video clipping. Upload a long-form video, describe what you're looking for, and get the top matching moments cut out and ready to download.

---

## CI / CD

| Subsystem | Build & Test |
|---|---|
| **webapp** | [![webapp CI](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/webapp.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/webapp.yml) |
| **ai-service** | [![ai-service CI](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/ai-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/ai-service.yml) |

## Container Images

| Subsystem | Docker Hub |
|---|---|
| **webapp** | [`swe-students-spring2026/topfive-webapp`](https://hub.docker.com/r/swe-students-spring2026/topfive-webapp) |
| **ai-service** | [`swe-students-spring2026/topfive-ai-service`](https://hub.docker.com/r/swe-students-spring2026/topfive-ai-service) |

## Team

| Name | GitHub |
|---|---|
| Gavin Chen | [@gavinchen8706](https://github.com/gavinchen8706) |
| Zhihui | [@zhihui](https://github.com/zhihui) |
| Alan | [@alan](https://github.com/alan) |
| Wonden | [@wonden](https://github.com/wonden) |

---

## What It Does

A user uploads a long-form video (podcast, lecture, game footage, etc.), types a prompt describing what they want ("moments where the guest talks about product-market fit"), and picks how many clips to extract. Top Five transcribes the audio with Whisper, scores every ~30-second window against the prompt using Claude, and cuts the top-N non-overlapping segments out as standalone `.mp4` clips the user can preview and download.

**Example use cases:**
- "Pull the 5 funniest moments from this 2-hour podcast."
- "Find the 3 segments where the lecturer explains backpropagation."
- "Top 5 dunks in this 4th-quarter game footage."

---

## Architecture

```
┌─────────────────────────────┐
│           Browser           │
└──────────────┬──────────────┘
               │ HTTP
┌──────────────▼──────────────┐
│   webapp  (Flask, port 3000)│   Upload → Prompt → Results
└──────────────┬──────────────┘
               │ POST /jobs  (enqueue)
               │ GET  /jobs/:id (poll status)
┌──────────────▼──────────────┐      ┌──────────────────┐
│  ai-service (FastAPI, 8000) │◄────►│   MongoDB        │
│  • faster-whisper (transcr.)│      │   topfive DB     │
│  • Claude API (scoring)     │      │   videos / jobs  │
│  • ffmpeg (clip cutting)    │      │   clips          │
└─────────────────────────────┘      └──────────────────┘
               │ writes clips
          /data/clips/
   (Docker named volume, shared
    by webapp and ai-service)
```

The webapp delegates all processing to the ai-service via a single `POST /jobs` call and then polls MongoDB for status updates — the ai-service writes progress directly to the database as it moves through each pipeline stage.

---

## Quick Start (Docker Compose)

This is the recommended way to run the project. All three services start together with one command.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac / Windows / Linux)
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Clone the repo

```bash
git clone https://github.com/swe-students-spring2026/5-final-top_five.git
cd 5-final-top_five
```

### 2. Create the root `.env` file

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
MONGO_URI=mongodb://mongo:27017/topfive
AI_SERVICE_URL=http://ai-service:8000
ANTHROPIC_API_KEY=sk-ant-api03-...    # required — get one at console.anthropic.com
WHISPER_MODEL=base.en                  # tiny.en | base.en | small.en | medium.en
STORAGE_DIR=/data
USE_MOCKS=false
```

> **Note:** `MONGO_URI` and `AI_SERVICE_URL` use Docker Compose service names (`mongo`, `ai-service`), not `localhost`. Only change these if you know what you are doing.

### 3. Start everything

```bash
docker compose up --build
```

- Webapp → [http://localhost:3000](http://localhost:3000)
- AI service → [http://localhost:8000](http://localhost:8000)
- MongoDB → `localhost:27017`

### 4. Use the app

1. Open [http://localhost:3000](http://localhost:3000)
2. Drag and drop (or click to browse) a video file and click **Upload**
3. Enter a natural-language prompt and choose how many clips to extract (1–10)
4. Click **Generate Clips** — the page refreshes automatically as the job progresses
5. When done, each clip is shown with its rank, relevance score, and transcript excerpt; click to play or download

---

## Local Development (without Docker)

Use this if you want to iterate on the code without rebuilding containers every time.

### Prerequisites

- Python 3.11
- `pipenv` (`pip install pipenv`)
- MongoDB 7 — easiest via Docker: `docker run -d -p 27017:27017 --name mongo mongo:7`
- `ffmpeg` on your `$PATH` — [download here](https://ffmpeg.org/download.html)
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Install dependencies for each service

```bash
cd webapp && pipenv install && cd ..
cd ai-service && pipenv install && cd ..
```

### 2. Configure the webapp

```bash
cp webapp/env.example webapp/.env
```

`webapp/.env`:

```
FLASK_ENV=development
PORT=3000
MONGO_URI=mongodb://localhost:27017/topfive
AI_SERVICE_URL=http://localhost:8000
```

### 3. Configure the AI service

```bash
cp ai-service/env.example ai-service/.env
```

`ai-service/.env`:

```
MONGO_URI=mongodb://localhost:27017/topfive
ANTHROPIC_API_KEY=sk-ant-api03-...
WHISPER_MODEL=base.en
STORAGE_DIR=./data
USE_MOCKS=false
```

### 4. Run both services

**Terminal 1 — webapp**

```bash
cd webapp
pipenv run python app.py
# Listening on http://localhost:3000
```

**Terminal 2 — AI service**

```bash
cd ai-service
pipenv run uvicorn main:app --reload --port 8000
# Listening on http://localhost:8000
```

---

## Environment Variables Reference

### webapp

| Variable | Example | Description |
|---|---|---|
| `FLASK_ENV` | `development` | Flask run mode |
| `PORT` | `3000` | Port to listen on |
| `MONGO_URI` | `mongodb://localhost:27017/topfive` | MongoDB connection string |
| `AI_SERVICE_URL` | `http://localhost:8000` | Base URL of the AI service |

### ai-service

| Variable | Example | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017/topfive` | MongoDB connection string |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | Claude API key (required for real scoring) |
| `WHISPER_MODEL` | `base.en` | Whisper model size — `tiny.en` is fastest, `medium.en` is most accurate |
| `STORAGE_DIR` | `./data` | Root directory for uploaded videos and generated clips |
| `USE_MOCKS` | `false` | Set `true` to skip real transcription/LLM calls (useful for offline dev and testing) |

---

## How the Pipeline Works

Once a job is submitted, the AI service runs this pipeline asynchronously:

| Step | What happens |
|---|---|
| **1 — Transcribe** | `faster-whisper` converts the video's audio to timestamped text segments |
| **2 — Window** | Segments are packed into ~30-second windows without splitting mid-sentence |
| **3 — Score** | All windows are sent to Claude in a single API call; Claude returns a 0–10 relevance score for each window against the user's prompt |
| **4 — Select** | The top-N highest-scoring, non-overlapping windows are chosen |
| **5 — Cut** | `ffmpeg` extracts each window from the original video as a standalone `.mp4` |
| **6 — Store** | Clip metadata (rank, score, timestamps, transcript, file path) is saved to MongoDB |

The webapp polls `GET /jobs/:id` (its own route, reading from MongoDB) and re-renders the page as the status moves from `queued → transcribing → ranking → cutting → done`.

---

## Running Tests

Each subsystem targets ≥ 80 % line coverage.

**webapp**

```bash
cd webapp
pipenv run pytest test_app.py -v --cov --cov-report=term-missing
```

**AI service**

```bash
cd ai-service
pipenv run pytest tests/ -v --cov --cov-report=term-missing
```

Set `USE_MOCKS=true` in `ai-service/.env` (or prefix the command) to run tests without real Whisper or Claude calls:

```bash
USE_MOCKS=true pipenv run pytest tests/ -v --cov
```

---

## Project Structure

```
5-final-top_five/
├── webapp/                      # Flask web app (port 3000)
│   ├── app.py                   # Routes: /, /upload-video, /generate-clips, /jobs/:id, /history
│   ├── test_app.py              # Pytest test suite
│   ├── templates/
│   │   ├── index.html           # Video upload page (drag-and-drop)
│   │   ├── upload.html          # Prompt + clip-count form
│   │   ├── job.html             # Live job status and results
│   │   └── history.html         # Recent jobs list
│   ├── static/                  # CSS (base.css, index.css, upload.css)
│   ├── env.example              # Environment variable template
│   └── Pipfile
│
├── ai-service/                  # FastAPI AI service (port 8000)
│   ├── main.py                  # Routes: POST /jobs, GET /jobs/:id, GET /healthz
│   ├── pipeline.py              # Transcription, windowing, scoring, cutting logic
│   ├── db.py                    # MongoDB helpers (set_job_status, insert_clip)
│   ├── tests/
│   │   ├── test_main.py         # Endpoint tests (FastAPI TestClient)
│   │   └── test_pipeline.py     # Pure-logic tests (windowing, top-N selection)
│   ├── env.example              # Environment variable template
│   └── Pipfile
│
├── .env.example                 # Root env template (for Docker Compose)
├── docker-compose.yml           # Brings up webapp + ai-service + MongoDB
├── pyproject.toml               # Root pytest config
└── PRD.md                       # Full product requirements document
```

---

## API Reference (AI Service)

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Liveness check — returns `{"ok": true}` |
| `POST` | `/jobs` | Enqueue a new clip job (returns `202 Accepted`) |
| `GET` | `/jobs/:job_id` | Get job status and all associated clips |

**POST /jobs — request body**

```json
{
  "job_id":   "65f0000000000000000000aa",
  "video_id": "65f0000000000000000000bb",
  "filepath": "/data/videos/podcast.mp4",
  "prompt":   "moments where they discuss product-market fit",
  "num_clips": 5
}
```

**Job status progression:** `queued → transcribing → ranking → cutting → done` (or `failed`)

---

## Database Collections

All collections live in the `topfive` MongoDB database. No manual seeding is required — collections are created automatically on first use.

### `videos`

Inserted by the webapp on file upload.

```json
{
  "_id": "ObjectId",
  "filename": "podcast-ep42.mp4",
  "filepath": "/data/videos/podcast-ep42.mp4",
  "uploaded_at": "ISODate"
}
```

### `jobs`

Created by the webapp when the user submits a prompt; updated by the AI service as it processes.

```json
{
  "_id": "ObjectId",
  "job_id": "65f...",
  "video_id": "ObjectId",
  "prompt": "moments where they discuss product-market fit",
  "num_clips": 5,
  "status": "done",
  "error": null,
  "created_at": "ISODate",
  "completed_at": "ISODate",
  "clip_ids": ["ObjectId"]
}
```

### `clips`

Inserted by the AI service, one document per generated clip.

```json
{
  "_id": "ObjectId",
  "job_id": "ObjectId",
  "video_id": "ObjectId",
  "rank": 1,
  "score": 8.7,
  "start_sec": 1234.5,
  "end_sec": 1264.5,
  "transcript": "...the segment's transcript text...",
  "storage_path": "/data/clips/65f..._1.mp4"
}
```
