# Top Five

[![webapp CI](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/webapp.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/webapp.yml)
[![ai-service CI](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/ai-service.yml/badge.svg)](https://github.com/swe-students-spring2026/5-final-top_five/actions/workflows/ai-service.yml)

> _CI workflow badges are placeholders until `.github/workflows/webapp.yml` and `.github/workflows/ai-service.yml` are added._

AI-powered video clipping. Upload a long video, type a natural-language prompt ("moments where the guest discusses aliens"), pick a number `N`, and get back the top-N clips of that video that best match your prompt.

## Team

_(Add GitHub profile links for each teammate here.)_

- TBD

## Container images

- webapp — _(Docker Hub link TBD)_
- ai-service — _(Docker Hub link TBD)_

## How it works

The system has three subsystems:

| Subsystem | Stack | Purpose |
|---|---|---|
| **webapp** | Flask, pymongo, requests | User-facing UI: upload + prompt form + status/results pages. Talks to MongoDB and the ai-service. |
| **ai-service** | FastAPI, faster-whisper, ffmpeg, OpenRouter (Gemma) | Background worker: transcribes audio, ranks transcript windows against the prompt, cuts clips. |
| **mongodb** | MongoDB Atlas | Stores videos, jobs, and clip metadata. |

End-to-end flow:

1. User uploads a video → webapp saves the file + writes a `videos` doc in Mongo.
2. User types a prompt and clip count → webapp creates a `jobs` doc, then `POST`s to ai-service `/jobs`, then redirects to a status page that polls Mongo.
3. ai-service transcribes the audio with `faster-whisper` (local, CPU).
4. The transcript is grouped into ~30 second windows.
5. All windows + the prompt are sent in a single batched call to an LLM (Gemma-3-27B-IT free via OpenRouter), which scores each window 0–10 against the prompt.
6. Top-N non-overlapping windows are picked.
7. `ffmpeg` cuts each window into its own `.mp4`.
8. Clip metadata is written to Mongo; the webapp's status page renders the clips with playable HTML5 video tags.

## Local setup

### Prerequisites

- Python 3.11
- `pipenv` (`pip install pipenv`)
- `ffmpeg` (`brew install ffmpeg` on macOS, `apt install ffmpeg` on Linux)
- A free [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) account (or any reachable MongoDB)
- A free [OpenRouter](https://openrouter.ai) account for the API key (used for clip scoring)

### Configure environment variables

The repo includes `webapp/env.example` and `ai-service/env.example`. Copy each to `.env` in the same folder:

```bash
cp webapp/env.example webapp/.env
cp ai-service/env.example ai-service/.env
```

Then fill in the values.

**`webapp/.env`**
```
FLASK_ENV=development
PORT=3000
MONGO_URI=mongodb+srv://<user>:<password>@<cluster-host>/topfive?retryWrites=true&w=majority
AI_SERVICE_URL=http://localhost:8000
```

**`ai-service/.env`**
```
PORT=8000
MONGO_URI=mongodb+srv://<user>:<password>@<cluster-host>/topfive?retryWrites=true&w=majority
STORAGE_DIR=./data
WHISPER_MODEL=tiny.en
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=<your-openrouter-key>
OPENROUTER_MODEL=google/gemma-3-27b-it:free
USE_MOCKS=false
```

#### Notes on env vars

- `WHISPER_MODEL`: `tiny.en` (fastest, ~30s for a 12-min video on CPU), `base.en` (more accurate, ~3-5x slower), `medium.en` (most accurate, much slower).
- `USE_MOCKS`: when `true`, ai-service uses a canned transcript + keyword-matching score instead of real Whisper / OpenRouter. Useful if you don't have an OpenRouter key.
- Atlas IP allowlist: in Atlas → Network Access, add `0.0.0.0/0` for development.

### Install dependencies

```bash
cd webapp && pipenv install --dev
cd ../ai-service && pipenv install --dev
```

### Run both services

In two terminals:

```bash
# terminal 1
cd ai-service && KMP_DUPLICATE_LIB_OK=TRUE pipenv run uvicorn main:app --host 127.0.0.1 --port 8000
```

```bash
# terminal 2
cd webapp && pipenv run python app.py
```

Open http://localhost:3000.

> **macOS / Anaconda Python note**: `KMP_DUPLICATE_LIB_OK=TRUE` works around an OpenMP library conflict between `faster-whisper` and Anaconda's bundled numpy. Without it the ai-service aborts on the first transcription.

### Run tests

```bash
cd webapp && pipenv run pytest
cd ../ai-service && pipenv run pytest
```

## Deployment

The webapp and ai-service are containerized and can be deployed to any Docker-friendly host with **long-running compute** and **persistent storage** (i.e. not serverless function platforms like Vercel/Netlify — Whisper transcription routinely exceeds their per-invocation time limits).

Suitable free hosts:

- **Render** *(recommended)* — connect the GitHub repo, point at each subsystem's Dockerfile, configure env vars. Cold-starts after 15 min idle on the free tier.
- **Fly.io** — Docker-based, generous free tier with persistent volumes; CLI-heavy setup.
- **Koyeb** — one always-on free service.
- **Digital Ocean droplet** — $6/mo, both services + Mongo via `docker-compose`.

Container images are published to Docker Hub via CI on each merge to `main`.

_(Specific deploy targets and Docker Hub image links — to be added.)_
