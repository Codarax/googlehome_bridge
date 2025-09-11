import os
import time
import requests
import pytest

SWITCH_ID = 'switch.woonkamer_lamp'

HA_URL = os.getenv('HA_URL')
HA_TOKEN = os.getenv('HA_TOKEN')

pytestmark = pytest.mark.skipif(not HA_TOKEN, reason='HA_TOKEN not set in environment; real HA test skipped')

def get_headers():
    return {'Authorization': f'Bearer {HA_TOKEN}', 'Content-Type': 'application/json'}

def query_state():
    r = requests.get(f"{HA_URL}/api/states/{SWITCH_ID}", headers={'Authorization': f'Bearer {HA_TOKEN}'}, timeout=10, verify=False)
    r.raise_for_status()
    return r.json().get('state')

def call_service(domain, service):
    r = requests.post(f"{HA_URL}/api/services/{domain}/{service}", headers=get_headers(), json={'entity_id': SWITCH_ID}, timeout=10, verify=False)
    r.raise_for_status()
    return r.json()

def test_burn_switch_20s():
    # Pre-check entity exists
    state = None
    try:
        state = query_state()
    except requests.HTTPError as e:
        pytest.skip(f"Entity {SWITCH_ID} not present or HA unreachable: {e}")

    # Turn ON
    call_service('switch', 'turn_on')
    # Wait a short moment for HA to apply
    time.sleep(1)
    assert query_state() == 'on', 'Switch did not turn on'

    # Keep on for 20 seconds
    time.sleep(20)
    assert query_state() == 'on', 'Switch did not remain on during burn'

    # Turn OFF
    call_service('switch', 'turn_off')
    time.sleep(1)
    assert query_state() == 'off', 'Switch did not turn off'
