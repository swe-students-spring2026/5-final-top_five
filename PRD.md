# Top Five — Product Requirements Document

> AI-powered video clipping. User uploads a long video + a natural-language prompt + N. System returns the top-N moments from the video that match the prompt.

**Status:** in progress. Web app skeleton exists; MongoDB and AI service are unbuilt.

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

**Already partially built.**

- Routes:
  - `GET /` — upload page (drag-and-drop video)
  - `GET|POST /upload` — prompt + clip-count form, kicks off a job
  - `GET /jobs/<job_id>` *(new)* — job status + clip results page
  - `GET /clips/<clip_id>` *(new)* — serve clip file (or redirect to storage)
- Talks to:
  - **MongoDB**: writes the new `Job` document, polls for status
  - **ai-service**: enqueues a job (HTTP POST to `/jobs`)
- Stack: Python 3.11+, Flask, pymongo, requests
- Container: `Dockerfile` + image on Docker Hub
- Deployed: Digital Ocean (the only public-facing service)

### 2.2 `ai-service/` — Clip ranking worker (custom subsystem #2)

**To be built.**

- Stack: Python 3.11+, FastAPI (or Flask), `ffmpeg-python`, `faster-whisper`, an LLM SDK (`anthropic` or `openai`), pymongo
- Endpoints:
  - `POST /jobs` — accepts `{job_id, video_path_or_bytes, prompt, num_clips}`. Returns 202 Accepted; processes async via background task.
  - `GET /healthz` — liveness
- Pipeline (per job):
  1. Save the uploaded video to local/temp storage
  2. Extract audio with `ffmpeg`
  3. Transcribe with `faster-whisper` → list of `(start, end, text)` segments
  4. Group segments into ~30s windows
  5. Send windows + prompt to the LLM → score each window 0–10 against the prompt
  6. Pick top-N non-overlapping windows
  7. `ffmpeg` cuts each window into a clip file
  8. Write clip metadata + file path/URL into MongoDB; update job status
- Container: `Dockerfile` + image on Docker Hub. **Must include `ffmpeg`** in the image.
- Deployed: Digital Ocean droplet (or kept private depending on cost — see Open Questions)

### 2.3 `mongodb/` — Database (subsystem #3)

- Stack: official `mongo:7` image
- No custom Dockerfile (uses upstream image), but a `mongodb/` subdir with init scripts, seed data, and a `docker-compose.yml` snippet for local dev
- Hosts: locally via Docker, and a managed MongoDB instance on Digital Ocean (or Atlas free tier) for prod

---

## 3. Data Model

All collections in a single database `topfive`.

### `videos`
```jsonc
{
  "_id": ObjectId,
  "filename": "podcast-ep42.mp4",
  "size_bytes": 524288000,
  "duration_sec": 7200.0,
  "uploaded_at": ISODate,
  "storage_path": "/data/videos/<id>.mp4"
}
```

### `jobs`
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
```jsonc
{
  "_id": ObjectId,
  "job_id": ObjectId,
  "video_id": ObjectId,
  "rank": 1,
  "score": 8.7,
  "start_sec": 1234.5,
  "end_sec": 1264.5,
  "transcript": "...the segment's transcript text...",
  "storage_path": "/data/clips/<clip_id>.mp4",
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

- `/data/videos/<video_id>.mp4` — uploaded source videos
- `/data/clips/<clip_id>.mp4` — generated clips

MongoDB holds metadata only (paths, timestamps, scores, prompts). Videos are too large for Mongo documents (16MB cap) and a poor fit for GridFS at this scale.

In production on Digital Ocean, the volume is a persistent block storage volume attached to the droplet. If we ever need to scale beyond one droplet, swap to DO Spaces / S3 — but that's not v1.

---

## 5. Tech Stack Summary

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Web framework | Flask (webapp), FastAPI or Flask (ai-service) |
| DB | MongoDB 7, accessed via `pymongo` |
| Video tooling | `ffmpeg` (CLI) + `ffmpeg-python` |
| Transcription | `faster-whisper` (CPU-friendly, no API key) |
| LLM ranking | Anthropic Claude API (`anthropic` SDK) — see §9 |
| Containers | Docker, images on Docker Hub |
| CI/CD | GitHub Actions (one workflow per subsystem) |
| Hosting | Digital Ocean (webapp + ai-service); Mongo via DO managed or Atlas |
| Tests | `pytest` + `pytest-cov` (≥80% coverage per subsystem) |
| Local orchestration | `docker-compose.yml` at repo root |

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

1. **M1 — Schema + skeletons**: docker-compose with all 3 services, MongoDB connected from webapp, ai-service `/healthz` reachable from webapp.
2. **M2 — End-to-end happy path with mocks**: webapp creates a job → ai-service receives it → returns canned clips → webapp displays them. No real Whisper or LLM yet.
3. **M3 — Real transcription**: swap mock for `faster-whisper`.
4. **M4 — Real LLM ranking**: swap mock for Claude/OpenAI call.
5. **M5 — Real ffmpeg cuts**: swap clip-stub for actual cut files served from storage.
6. **M6 — CI/CD green**: workflows passing, ≥80% coverage, images on Docker Hub.
7. **M7 — Deployed**: webapp live on Digital Ocean.
8. **M8 — README polish**: badges, setup instructions, teammate links.

---

## 12. Team

*(fill in)* — list of teammates with GitHub profile links goes here, mirrored into [README.md](README.md) at the end of the project.