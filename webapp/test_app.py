from unittest.mock import patch, MagicMock
import pytest
from bson import ObjectId
import app as app_module
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_upload_no_file(client):
    response = client.post("/upload-video", data={})
    assert response.status_code == 200
    assert b"Please upload a video" in response.data


def test_generate_no_prompt(client):
    response = client.post("/generate-clips", data={
        "filename": "test.mp4",
        "num_clips": "1"
    })
    assert response.status_code == 200
    assert b"Please enter a prompt" in response.data


def test_generate_clips_creates_job_and_calls_ai_service(client):
    video_id = ObjectId()
    job_id = ObjectId()

    fake_videos = MagicMock()
    fake_videos.find_one.return_value = {"_id": video_id, "filename": "x.mp4", "filepath": "uploads/x.mp4"}

    fake_jobs = MagicMock()
    fake_jobs.insert_one.return_value = MagicMock(inserted_id=job_id)

    fake_db = MagicMock()
    fake_db.videos = fake_videos
    fake_db.jobs = fake_jobs

    with patch.object(app_module, "db", fake_db), \
         patch.object(app_module, "requests") as fake_requests:
        fake_requests.post.return_value.raise_for_status = MagicMock()

        resp = client.post("/generate-clips", data={
            "prompt": "aliens",
            "num_clips": "3",
            "filename": "x.mp4",
        })

    assert resp.status_code == 302
    assert f"/jobs/{job_id}" in resp.headers["Location"]

    fake_jobs.insert_one.assert_called_once()
    job_doc = fake_jobs.insert_one.call_args.args[0]
    assert job_doc["video_id"] == video_id
    assert job_doc["prompt"] == "aliens"
    assert job_doc["num_clips"] == 3
    assert job_doc["status"] == "queued"

    fake_requests.post.assert_called_once()
    body = fake_requests.post.call_args.kwargs["json"]
    assert body["job_id"] == str(job_id)
    assert body["video_id"] == str(video_id)
    assert body["prompt"] == "aliens"
    assert body["num_clips"] == 3


def test_generate_clips_marks_failed_when_ai_service_unreachable(client):
    import requests as real_requests

    video_id = ObjectId()
    job_id = ObjectId()

    fake_videos = MagicMock()
    fake_videos.find_one.return_value = {"_id": video_id, "filename": "x.mp4", "filepath": "uploads/x.mp4"}

    fake_jobs = MagicMock()
    fake_jobs.insert_one.return_value = MagicMock(inserted_id=job_id)

    fake_db = MagicMock()
    fake_db.videos = fake_videos
    fake_db.jobs = fake_jobs

    with patch.object(app_module, "db", fake_db), \
         patch.object(app_module, "requests") as fake_requests:
        fake_requests.RequestException = real_requests.RequestException
        fake_requests.post.side_effect = real_requests.ConnectionError("boom")

        resp = client.post("/generate-clips", data={
            "prompt": "aliens",
            "num_clips": "2",
            "filename": "x.mp4",
        })

    assert resp.status_code == 302
    failure_calls = [
        c for c in fake_jobs.update_one.call_args_list
        if c.args[1]["$set"].get("status") == "failed"
    ]
    assert len(failure_calls) == 1
    update = failure_calls[0].args[1]["$set"]
    assert "ai-service unreachable" in update["error"]


def test_generate_clips_video_not_found(client):
    fake_videos = MagicMock()
    fake_videos.find_one.return_value = None

    fake_db = MagicMock()
    fake_db.videos = fake_videos

    with patch.object(app_module, "db", fake_db):
        resp = client.post("/generate-clips", data={
            "prompt": "aliens",
            "num_clips": "1",
            "filename": "missing.mp4",
        })

    assert resp.status_code == 200
    assert b"Video not found" in resp.data


def test_job_status_renders_in_progress(client):
    job_id = ObjectId()
    fake_jobs = MagicMock()
    fake_jobs.find_one.return_value = {"_id": job_id, "status": "transcribing", "prompt": "p"}

    fake_db = MagicMock()
    fake_db.jobs = fake_jobs

    with patch.object(app_module, "db", fake_db):
        resp = client.get(f"/jobs/{job_id}")

    assert resp.status_code == 200
    assert b"Generating clips" in resp.data
    assert b"transcribing" in resp.data
    assert b"http-equiv=\"refresh\"" in resp.data


def test_job_status_renders_done_with_clips(client):
    job_id = ObjectId()

    fake_jobs = MagicMock()
    fake_jobs.find_one.return_value = {
        "_id": job_id,
        "status": "done",
        "prompt": "aliens",
    }

    fake_clips = MagicMock()
    cursor = MagicMock()
    cursor.sort.return_value = [
        {"rank": 1, "score": 9.0, "start_sec": 10.0, "end_sec": 30.0, "transcript": "alien stuff", "storage_path": "/data/clips/abc_1.mp4"},
        {"rank": 2, "score": 7.5, "start_sec": 50.0, "end_sec": 70.0, "transcript": "more aliens", "storage_path": "/data/clips/abc_2.mp4"},
    ]
    fake_clips.find.return_value = cursor

    fake_db = MagicMock()
    fake_db.jobs = fake_jobs
    fake_db.clips = fake_clips

    with patch.object(app_module, "db", fake_db):
        resp = client.get(f"/jobs/{job_id}")

    assert resp.status_code == 200
    assert b"Top 2 clips" in resp.data
    assert b"alien stuff" in resp.data
    assert b"http-equiv=\"refresh\"" not in resp.data


def test_job_status_invalid_id(client):
    resp = client.get("/jobs/not-a-real-id")
    assert resp.status_code == 404
    assert b"Invalid job id" in resp.data


def test_job_status_not_found(client):
    job_id = ObjectId()
    fake_jobs = MagicMock()
    fake_jobs.find_one.return_value = None

    fake_db = MagicMock()
    fake_db.jobs = fake_jobs

    with patch.object(app_module, "db", fake_db):
        resp = client.get(f"/jobs/{job_id}")

    assert resp.status_code == 404
    assert b"Job not found" in resp.data