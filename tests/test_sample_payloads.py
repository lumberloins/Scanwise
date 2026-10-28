import json
import os
import pytest
from scanwise import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_sample_payloads_integration(client):
    payloads_path = os.path.join(os.path.dirname(__file__), 'sample_payloads.json')
    with open(payloads_path, 'r') as f:
        samples = json.load(f)

    for name, sample in samples.items():
        res = client.post('/api/analyze', json={
            "raw_input": sample["raw_input"],
            "profile_id": sample["profile_id"],
            "keystroke_timings": [0, 5, 10, 15]
        })
        assert res.status_code == 200, f"Failed on sample {name}"
        data = res.get_json()
        assert data["verdict"]["category"] == sample["expected_category"], f"Mismatch on sample {name}: got {data['verdict']['category']}, expected {sample['expected_category']}"
