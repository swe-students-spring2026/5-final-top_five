# Top Five — Product Requirements Document

> AI-powered video clipping. User uploads a long video + a natural-language prompt + N. System returns the top-N moments from the video that match the prompt.

**Status:** in progress. Webapp + MongoDB integration shipped to `main`. AI service skeleton (FastAPI + mocks + tests) shipped to `main`. Real Whisper/Claude/ffmpeg, the webapp→ai-service wire, Dockerfiles, and CI/CD still to do.

---

## 1. Product Overview

### What it does

A user uploads a long-form video (podcast, lecture, game footage, etc.), types a prompt describing what they're looking for ("moments where the guest talks about aliens"), and picks a number N (1–10). The system analyzes the video, ranks segments by how well they match the prompt, and returns the top-N as standalone clips the user can preview and download.

### Why this framing

This differs from the original GPT-drafted overview, which described generic auto-captioning + tagging across all clips. Our actual UI ([webapp/templates/upload.html](webapp/templates/upload.html)) is built for prompt-driven ranking: a prompt textbox and a clip-count dropdown. The PRD reflects what the UI implies.

### Example use cases

- **Podcasters**: "Pull the 5 funniest moments from this 2-hour episode."
- **Students**: "Find the 3 segments where the lecturer explains backpropagation."
- **Sports fans**: "Top 5 dunks in this 4th quarter."

### Out of scope (v1)

- Multi-video batch ingest
- User accounts / login
- Real-time streams (only uploaded files)
- Mobile app
- Multimodal visual scoring — v1 ranks on **transcript text only** (the user's "text-first, then audio/visual" guidance)

---

## 2. System Architecture

Three subsystems (assignment minimum):

```
┌────────────┐         ┌────────────┐         ┌──────────────┐
│   webapp   │ ──────> │ ai-service │ ──────> │   mongodb    │
│  (Flask)   │ <────── │  (Python)  │ <────── │              │
└────────────┘         └────────────┘         └──────────────┘
      │                                              ▲
      └──────────────────────────────────────────────┘
                  (reads job/clip status)
```

### 2.1 `webapp/` — Flask user interface (custom subsystem #1)

**Built.** Mongo integration on `main`. Two-step UX (upload, then prompt). The webapp→ai-service POST is the next missing wire.

- Routes (current, on `main`):
  - `GET /` — upload page (drag-and-drop video)
  - `POST /upload-video` — saves the file to `webapp/uploads/`, inserts a `videos` doc into Mongo, redirects to the prompt page
  - `POST /generate-clips` — accepts prompt + num_clips, updates the `videos` doc with prompt info
  - `GET /test-db` — debug-only Mongo ping (remove before deploy)
- Routes still to build:
  - **In `/generate-clips`: create a `jobs` doc and POST to `ai-service /jobs`** — currently missing; this is the wire that actually kicks off processing
  - `GET /jobs/<job_id>` — job status + clip results page (poll Mongo)
  - `GET /clips/<clip_id>` — serve clip file from the shared volume
- Talks to:
  - **MongoDB**: writes the `videos` doc on upload; will write `jobs` and read clip status
  - **ai-service**: enqueues a job via `POST /jobs` (not wired yet — `requests` dep needed)
- Stack: Python 3.11+, Flask, pymongo, python-dotenv, werkzeug; `requests` to add for ai-service call
- Container: `Dockerfile` + image on Docker Hub *(to add)*
- Deployed: Digital Ocean (the only public-facing service)

### 2.2 `ai-service/` — Clip ranking worker (custom subsystem #2)

**Skeleton built and on `main`.** FastAPI app with `/healthz` and `POST /jobs`. Pure-logic (windowing, top-N selection) implemented and tested. Three external steps (transcribe, score, cut) are mocks that need to be replaced with real implementations.

- Module layout (flat, no `app/` subdir):
  - [ai-service/main.py](ai-service/main.py) — FastAPI app, routes, `BackgroundTasks` orchestration
  - [ai-service/pipeline.py](ai-service/pipeline.py) — `Segment`/`Window`/`ScoredWindow` dataclasses, `pack_windows`, `select_top_n`, plus mocks `transcribe_mock`, `score_windows_mock`, `cut_clip_mock`
  - [ai-service/db.py](ai-service/db.py) — Mongo client + `set_job_status`, `insert_clip`
  - [ai-service/env.example](ai-service/env.example) — env-var template
  - `ai-service/tests/` — `test_main.py` (FastAPI TestClient), `test_pipeline.py` (pure-logic)
- Stack: Python 3.11, FastAPI, uvicorn, pymongo, python-dotenv, pydantic, `ffmpeg-python`, `faster-whisper`, `anthropic`
- Endpoints (current):
  - `POST /jobs` — accepts `{job_id, video_path, prompt, num_clips, video_id?}`. Validates `1 ≤ num_clips ≤ 10` and non-empty prompt. Returns 202; processes async via `BackgroundTasks`.
  - `GET /healthz` — liveness, returns `{ok: true}`
- Pipeline (per job, current — mocks marked `*`):
  1. Save the uploaded video to the shared volume *(handled by webapp)*
  2. Extract audio with `ffmpeg` *(to add)*
  3. Transcribe with `faster-whisper` → `[Segment(start, end, text), ...]` *(currently `transcribe_mock`)*
  4. Group segments into ~30s windows via `pack_windows` (real)
  5. Send windows + prompt to Claude → score each window 0–10 *(currently `score_windows_mock`)*
  6. Pick top-N non-overlapping windows via `select_top_n` (real)
  7. `ffmpeg` cuts each window into a clip file *(currently `cut_clip_mock`)*
  8. Write clip metadata + file path into MongoDB; update job status (real)
- Replacement plan: add `transcribe_real`, `score_windows_real`, `cut_clip_real` alongside the mocks. Use `USE_MOCKS` env flag (already in [env.example](ai-service/env.example)) to switch. Keeps the test suite stable while real implementations land.
- Container: `Dockerfile` + image on Docker Hub *(to add — must apt-install `ffmpeg`)*
- Deployed: Digital Ocean droplet

### 2.3 `mongodb/` — Database (subsystem #3)

- Stack: official `mongo:7` image
- No custom Dockerfile (uses upstream image), but a `mongodb/` subdir with init scripts, seed data, and a `docker-compose.yml` snippet for local dev
- Hosts: locally via Docker, and a managed MongoDB instance on Digital Ocean (or Atlas free tier) for prod

---

## 3. Data Model

All collections in a single database `topfive`.

### `videos`
Currently written by webapp [`/upload-video`](webapp/app.py#L32). The webapp adds `prompt` and `num_clips` later via `/generate-clips`. Plan: move `prompt` + `num_clips` to the `jobs` doc when the webapp→ai-service wire goes in.
```jsonc
{
  "_id": ObjectId,
  "filename": "podcast-ep42.mp4",
  "filepath": "uploads/podcast-ep42.mp4",  // current — will become "/data/videos/<id>.mp4" after shared-volume migration
  "uploaded_at": ISODate,
  "prompt": "...",       // currently set on this doc; will move to jobs
  "num_clips": 5         // currently set on this doc; will move to jobs
}
```

### `jobs`
Currently NOT written — will be added when webapp posts to ai-service. The ai-service's `set_job_status` already expects this shape ([ai-service/db.py:13-19](ai-service/db.py#L13-L19)).
```jsonc
{
  "_id": ObjectId,
  "video_id": ObjectId,
  "prompt": "moments where the guest discusses aliens",
  "num_clips": 5,
  "status": "queued" | "transcribing" | "ranking" | "cutting" | "done" | "failed",
  "error": null,
  "created_at": ISODate,
  "completed_at": ISODate | null,
  "clip_ids": [ObjectId, ...]
}
```

### `clips`
Already written by ai-service ([ai-service/db.py:22-49](ai-service/db.py#L22-L49)).
```jsonc
{
  "_id": ObjectId,
  "job_id": ObjectId,
  "video_id": ObjectId | null,
  "rank": 1,
  "score": 8.7,
  "start_sec": 1234.5,
  "end_sec": 1264.5,
  "transcript": "...the segment's transcript text...",
  "storage_path": "/data/clips/<job_id>_<rank>.mp4",
  "caption": null  // optional, future
}
```

---

## 4. Inter-service Contracts

### webapp → ai-service

`POST /jobs`

```json
{
  "job_id": "65f...",
  "video_path": "/data/videos/65f....mp4",
  "prompt": "moments where the guest discusses aliens",
  "num_clips": 5
}
```

Response: `202 Accepted` with `{"job_id": "65f..."}`.

The ai-service updates `jobs.status` in MongoDB as it progresses; the webapp polls `GET /jobs/<id>` (its own route, reading from Mongo).

### Storage

**Decision: shared Docker volume** mounted at `/data` in both containers.

- `/data/videos/<video_id>.<ext>` — uploaded source videos
- `/data/clips/<job_id>_<rank>.mp4` — generated clips

MongoDB holds metadata only (paths, timestamps, scores, prompts). Videos are too large for Mongo documents (16MB cap) and a poor fit for GridFS at this scale.

**Current state (drift from this decision):** webapp saves to `webapp/uploads/`, ai-service expects `./data/`. This works while both run locally but breaks once containerized. **Action:**
1. Webapp's `UPLOAD_FOLDER` becomes `STORAGE_DIR/videos` (default `/data/videos`, env-driven).
2. Webapp passes the absolute path to ai-service's `POST /jobs` — ai-service reads it as-is.
3. ai-service writes clips to `STORAGE_DIR/clips`.
4. `docker-compose.yml` mounts the same named volume into both at `/data`.

In production on Digital Ocean, the volume is a persistent block storage volume attached to the droplet. If we ever need to scale beyond one droplet, swap to DO Spaces / S3 — but that's not v1.

---

## 5. Tech Stack Summary

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Web framework | Flask (webapp), FastAPI (ai-service) |
| Env loading | `python-dotenv` (both subsystems) |
| File handling | `werkzeug.utils.secure_filename` (webapp) |
| DB | MongoDB 7, accessed via `pymongo` |
| Video tooling | `ffmpeg` (CLI) + `ffmpeg-python` |
| Transcription | `faster-whisper` (CPU-friendly, no API key) |
| LLM ranking | Anthropic Claude API (`anthropic` SDK) — see §9 |
| Containers | Docker, images on Docker Hub |
| CI/CD | GitHub Actions (one workflow per subsystem) |
| Hosting | Digital Ocean (webapp + ai-service); Mongo via DO managed or Atlas |
| Tests | `pytest` + `pytest-cov` (≥80% coverage per subsystem); `httpx` for FastAPI TestClient |
| Local orchestration | `docker-compose.yml` at repo root *(to add)* |

---

## 6. CI/CD

One workflow file per custom subsystem under `.github/workflows/`:

- `webapp.yml`
- `ai-service.yml`

Each triggers on `push` and `pull_request` targeting `main`, with `paths:` filters so a webapp-only change doesn't rebuild the ai-service.

Stages per workflow:
1. Checkout
2. Set up Python
3. Install deps (`pipenv` or `pip`)
4. Run `pytest --cov` and **fail if coverage < 80%**
5. Build Docker image
6. Push to Docker Hub (tagged `latest` and `<git-sha>`)
7. (webapp only, on `main`) SSH or `doctl` deploy to Digital Ocean droplet

Required GitHub secrets:
- `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`
- `DO_SSH_KEY` or `DIGITALOCEAN_ACCESS_TOKEN`
- `MONGO_URI` (for integration tests, if any)
- `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`)

---

## 7. Local Development

A single `docker-compose.yml` at repo root brings up all three services:

```bash
git clone <repo>
cp .env.example .env  # fill in ANTHROPIC_API_KEY etc.
docker compose up --build
# webapp on http://localhost:3000
# ai-service on http://localhost:8000
# mongo on localhost:27017
```

### `.env.example` (to commit)

```
MONGO_URI=mongodb://mongo:27017/topfive
AI_SERVICE_URL=http://ai-service:8000
ANTHROPIC_API_KEY=sk-ant-...
WHISPER_MODEL=base.en
STORAGE_DIR=/data
```

---

## 8. Testing Strategy

Per assignment: **≥80% coverage per custom subsystem.**

### webapp
- Flask test client for routes (`/`, `/upload`, `/jobs/<id>`)
- `mongomock` or a test Mongo container for persistence
- Mock the HTTP call to ai-service

### ai-service
- Mock `faster-whisper` (return a canned transcript)
- Mock the LLM call (return canned scores)
- Mock `ffmpeg` invocations (assert command shape, don't actually cut)
- Test the windowing + top-N selection logic with real inputs — this is the highest-value pure-Python logic to cover

---

## 9. AI Implementation Plan (v1)

**Approach:** transcript text → LLM scoring → top-N.

### Why this approach

- Maps directly to the user's example ("find clips that discuss aliens" — that's a topical/semantic query, perfectly served by transcript matching).
- "Text-first, then audio/visual" matches the user's stated rollout.
- Cheap and CPU-only for the heaviest step (transcription).
- Easy to mock in tests.

### Pipeline detail

1. **Audio extract** (`ffmpeg -i input.mp4 -vn -acodec pcm_s16le -ar 16000 audio.wav`)
2. **Transcribe** with `faster-whisper` (model `base.en` for speed, `medium.en` for accuracy)
   - Output: list of `(start_sec, end_sec, text)` from Whisper's segment API
3. **Window**: greedily pack Whisper segments into ~30s windows, never splitting a segment. Each window: `{start, end, text}`.
4. **Rank**: send the prompt + ALL windows in one Claude API call:
   - System prompt: "You score video transcript windows 0–10 against a user query. Return JSON only."
   - User prompt: `{prompt, windows: [{idx, text}, ...]}`
   - Use **prompt caching** on the system prompt (it's identical across jobs).
   - Response: `[{idx, score, reason}, ...]`
5. **Select top-N** non-overlapping windows by score (greedy: pick highest, drop overlaps, repeat).
6. **Cut** each selection: `ffmpeg -ss <start> -to <end> -i input.mp4 -c copy clip_<i>.mp4`
7. **Persist**: write clip docs to Mongo, return paths.

### Alternative approaches considered

- **Embeddings + cosine similarity**: cheaper at scale but worse on nuanced prompts ("find emotional moments"). Skip for v1.
- **Multimodal scoring on keyframes** (CLIP / vision LLM): captures silent visual content but adds GPU cost and complexity. Defer.

### Locked decisions

1. **LLM**: Claude (Anthropic). Prompt-caching the scoring system prompt across jobs.
2. **Transcription**: `faster-whisper` running locally inside the ai-service container. Same model as OpenAI Whisper, just on a faster inference engine. No API key, no per-call cost.
3. **Binary storage**: shared Docker volume mounted at `/data` in both webapp and ai-service containers. MongoDB stores metadata + the file path; the actual `.mp4` bytes live on the volume.
4. **Async**: FastAPI `BackgroundTasks` in the ai-service. POST returns 202 immediately; the task runs in the same process; webapp polls Mongo for `jobs.status`.

---

## 10. Open Questions / Decisions Needed

Resolved:
- [x] **3 subsystems** (webapp + ai-service + mongo). No artificial split.
- [x] **LLM**: Claude (Anthropic).
- [x] **Transcription**: `faster-whisper` locally.
- [x] **Storage**: shared Docker volume at `/data`.
- [x] **Async**: FastAPI `BackgroundTasks`.

Still open:
- [ ] Max video size + max duration we'll commit to supporting in v1 (Whisper time grows roughly linearly with audio length — a 2-hour podcast on CPU is ~10–20 min)
- [ ] Do we want a "Caption" field on each clip (LLM-generated short title)? Useful UX, cheap to add.
- [ ] Whisper model size: `base.en` (fast, less accurate) vs `medium.en` (slow, more accurate)

---

## 11. Milestones

1. ~~**M1 — Schema + skeletons**~~: ✅ webapp + Mongo on `main`, ai-service skeleton + tests on `main`. Outstanding: docker-compose to actually run them together.
2. **M2 — End-to-end happy path with mocks** *(current focus)*: wire `/generate-clips` to create a `jobs` doc and `POST` to ai-service `/jobs`. Add a `GET /jobs/<id>` page to webapp. Confirm a job moves through `queued → transcribing → ranking → cutting → done` end-to-end on mocks.
3. **M3 — Shared volume**: align webapp upload dir and ai-service storage dir under a single `STORAGE_DIR` env var. Mount one named volume into both containers via `docker-compose.yml`.
4. **M4 — Real transcription**: add `transcribe_real` using `faster-whisper`. Gate on `USE_MOCKS` env flag.
5. **M5 — Real LLM ranking**: add `score_windows_real` using `anthropic` SDK with prompt caching (see §9). Gate on `USE_MOCKS`.
6. **M6 — Real ffmpeg cuts**: add `cut_clip_real` using `ffmpeg-python`.
7. **M7 — Containerization**: `Dockerfile` for webapp and ai-service (latter must apt-install `ffmpeg`). Push to Docker Hub.
8. **M8 — CI/CD green**: GitHub Actions per subsystem; build + test + push image; coverage ≥ 80% gate.
9. **M9 — Deployed**: webapp live on Digital Ocean droplet behind the ai-service.
10. **M10 — README polish**: badges, setup instructions, teammate links.

---

## 12. Team

*(fill in)* — list of teammates with GitHub profile links goes here, mirrored into [README.md](README.md) at the end of the project.