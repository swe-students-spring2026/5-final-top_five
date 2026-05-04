from unittest.mock import patch, MagicMock
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
    with patch.object(main.db, "get_db", return_value=fake_db), \
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
