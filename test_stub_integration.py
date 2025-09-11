import os
import time
from server import HAClient


def test_ha_stub_returns_entities(monkeypatch):
    # Ensure HA_URL points to the local stub
    monkeypatch.setenv('HA_URL', 'http://127.0.0.1:8123')
    client = HAClient()
    entities = client.get_entities()
    assert isinstance(entities, list)
    # Expect at least the kitchen light from ha_stub
    ids = [e.get('entity_id') for e in entities]
    assert 'light.kitchen' in ids
