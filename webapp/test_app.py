import pytest
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