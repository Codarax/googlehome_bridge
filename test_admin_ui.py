import os
import json
import importlib

import pytest

# Use the HA stub started by conftest (port 8123)

def test_admin_devices_and_select(monkeypatch):
    # Ensure server reads the stub URL and an admin key at import time
    monkeypatch.setenv('HA_URL', 'http://127.0.0.1:8123')
    monkeypatch.setenv('ADMIN_API_KEY', 'adminkey123')

    # Import (or reload) the server module so it picks up env vars
    server = importlib.reload(__import__('server'))
    app = server.app
    client = app.test_client()

    # Without header, admin endpoint should require key
    r = client.get('/admin/devices')
    assert r.status_code == 401

    # With header, should return list of devices
    r = client.get('/admin/devices', headers={'X-ADMIN-KEY': 'adminkey123'})
    assert r.status_code == 200
    data = r.get_json()
    assert 'devices' in data
    devices = data['devices']
    assert isinstance(devices, list)

    # ha_stub defines light.kitchen; ensure present
    ids = [d['entity_id'] for d in devices]
    assert 'light.kitchen' in ids

    # Select a device via POST
    payload = {'entity_id': 'light.kitchen', 'allowed': True}
    r = client.post('/admin/devices/select', headers={'X-ADMIN-KEY': 'adminkey123', 'Content-Type': 'application/json'}, data=json.dumps(payload))
    assert r.status_code == 200
    resp = r.get_json()
    assert resp.get('ok') is True
    assert 'light.kitchen' in resp.get('selections', {})
