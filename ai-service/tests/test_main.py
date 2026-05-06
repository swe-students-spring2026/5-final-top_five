from unittest.mock import patch, MagicMock
from datetime import datetime
from bson import ObjectId
from fastapi.testclient import TestClient

import main


def test_healthz():
    client = TestClient(main.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_create_job_validates_num_clips():
    client = TestClient(main.app)
    r = client.post(
        "/jobs",
        json={"job_id": "65f0000000000000000000aa", "video_path": "x.mp4", "prompt": "p", "num_clips": 0},
    )
    assert r.status_code == 400


def test_create_job_validates_prompt():
    client = TestClient(main.app)
    r = client.post(
        "/jobs",
        json={"job_id": "65f0000000000000000000aa", "video_path": "x.mp4", "prompt": "  ", "num_clips": 3},
    )
    assert r.status_code == 400


def test_create_job_runs_pipeline_and_writes_clips():
    fake_db = MagicMock()
    with patch.object(main, "USE_MOCKS", True), \
         patch.object(main.db, "get_db", return_value=fake_db), \
         patch.object(main.db, "set_job_status") as set_status, \
         patch.object(main.db, "insert_clip") as insert_clip:
        client = TestClient(main.app)
        r = client.post(
            "/jobs",
            json={
                "job_id": "65f0000000000000000000aa",
                "video_path": "fake.mp4",
                "prompt": "aliens ufos",
                "num_clips": 2,
            },
        )
        assert r.status_code == 202
        assert insert_clip.call_count == 2
        statuses = [c.args[2] for c in set_status.call_args_list]
        assert statuses[-1] == "done"
        assert "transcribing" in statuses
        assert "ranking" in statuses
        assert "cutting" in statuses


def test_clean_for_json_handles_objectid():
    oid = ObjectId()
    assert main.clean_for_json(oid) == str(oid)


def test_clean_for_json_handles_datetime():
    dt = datetime(2021, 1, 1, 12, 0, 0)
    assert main.clean_for_json(dt) == "2021-01-01T12:00:00"


def test_clean_for_json_handles_list():
    oid = ObjectId()
    result = main.clean_for_json([oid, "test"])
    assert result == [str(oid), "test"]


def test_clean_for_json_handles_dict():
    oid = ObjectId()
    result = main.clean_for_json({"id": oid, "name": "test"})
    assert result == {"id": str(oid), "name": "test"}


def test_clean_for_json_returns_primitives():
    assert main.clean_for_json("test") == "test"
    assert main.clean_for_json(42) == 42
    assert main.clean_for_json(None) is None


def test_get_job_returns_job_and_clips():
    job_id = "65f0000000000000000000aa"
    fake_jobs = MagicMock()
    fake_jobs.find_one.return_value = {"_id": job_id, "status": "done"}
    
    fake_clips = MagicMock()
    fake_clips.find.return_value = [{"rank": 1, "score": 0.9}]
    
    fake_db = MagicMock()
    fake_db.jobs = fake_jobs
    fake_db.clips = fake_clips
    
    with patch.object(main.db, "get_db", return_value=fake_db):
        client = TestClient(main.app)
        r = client.get(f"/jobs/{job_id}")
    
    assert r.status_code == 200
    data = r.json()
    assert data["job"]["_id"] == job_id
    assert len(data["clips"]) == 1


def test_get_job_returns_404_when_not_found():
    job_id = "65f0000000000000000000aa"
    fake_jobs = MagicMock()
    fake_jobs.find_one.return_value = None
    
    fake_db = MagicMock()
    fake_db.jobs = fake_jobs
    
    with patch.object(main.db, "get_db", return_value=fake_db):
        client = TestClient(main.app)
        r = client.get(f"/jobs/{job_id}")
    
    assert r.status_code == 404
