import pytest
from scanwise import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_api_health(client):
    res = client.get('/api/health')
    assert res.status_code == 200
    assert res.get_json()["status"] == "healthy"

def test_api_profiles(client):
    res = client.get('/api/profiles')
    assert res.status_code == 200
    data = res.get_json()
    assert "epic_emr" in data["profiles"]

def test_api_analyze(client):
    payload = {
        "raw_input": "/DATA/]d201003012345678961725123110BATCH999\u001d21SER12345\r",
        "profile_id": "epic_emr",
        "keystroke_timings": [0, 5, 10, 15, 20]
    }
    res = client.post('/api/analyze', json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["verdict"]["category"] == "PASS"
    assert data["framing"]["profile_matched"] is True
    assert data["gs1_data"]["valid"] is True

def test_dashboard_view(client):
    res = client.get('/')
    assert res.status_code == 200
    assert b"ScanWise" in res.data
