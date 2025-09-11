import json
from urllib.parse import urlparse, parse_qs
import server

# Load device selections from devices.json
with open('devices.json', 'r') as f:
    selections = json.load(f)

# Build fake Home Assistant entities based on selections
entities = []
for eid, allowed in selections.items():
    if not allowed:
        continue
    # create a reasonable friendly name
    name = eid.split('.', 1)[1].replace('_', ' ').title()
    attrs = {'friendly_name': name}
    state = 'unknown'

    if 'temperature' in eid.lower():
        state = '21.5'
        attrs['device_class'] = 'temperature'
        attrs['unit_of_measurement'] = 'C'
    elif 'humidity' in eid.lower() or 'vochtigheid' in eid.lower():
        state = '45.0'
        attrs['device_class'] = 'humidity'
        attrs['unit_of_measurement'] = '%'
    elif 'battery' in eid.lower():
        state = '88'
        attrs['device_class'] = 'battery'
        attrs['unit_of_measurement'] = '%'
    else:
        state = '1'

    entities.append({
        'entity_id': eid,
        'state': state,
        'attributes': attrs
    })

# Monkeypatch HA client methods to return our fake entities
server.ha_client.get_entities = lambda: entities

def get_entity_state(entity_id):
    for e in entities:
        if e['entity_id'] == entity_id:
            return e
    return None

server.ha_client.get_entity_state = get_entity_state

# Use Flask test client to exercise endpoints without network
with server.app.test_client() as c:
    # 1) /oauth
    params = {
        'client_id': server.CLIENT_ID,
        'redirect_uri': 'https://example.com/redirect',
        'state': 'state123'
    }
    resp = c.get('/oauth', query_string=params, follow_redirects=False)
    print('/oauth ->', resp.status_code)
    loc = resp.headers.get('Location')
    if not loc:
        print('No Location header on /oauth; body:', resp.get_data(as_text=True))
        raise SystemExit(1)
    qs = parse_qs(urlparse(loc).query)
    code = qs.get('code', [None])[0]
    print('Auth code:', code)

    # 2) /token (exchange code)
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': server.CLIENT_ID,
        'client_secret': server.CLIENT_SECRET
    }
    token_resp = c.post('/token', data=data)
    print('/token ->', token_resp.status_code, token_resp.get_data(as_text=True))
    if token_resp.status_code != 200:
        raise SystemExit(1)
    token = token_resp.get_json().get('access_token')
    print('Access token (prefix):', token[:20] + '...')

    # 3) /smarthome SYNC
    payload = {
        'requestId': 'req_1',
        'inputs': [{'intent': 'action.devices.SYNC'}]
    }
    headers = {'Authorization': f'Bearer {token}'}
    sync_resp = c.post('/smarthome', json=payload, headers=headers)
    print('/smarthome ->', sync_resp.status_code)
    print(sync_resp.get_data(as_text=True))

    # Summarize devices and verify they match selections
    body = sync_resp.get_json()
    devices = body.get('payload', {}).get('devices', []) if body else []
    print(f'Found {len(devices)} devices from SYNC')
    print('Device IDs exported:')
    for d in devices:
        print(' -', d.get('id'))

    expected = [k for k, v in selections.items() if v]
    missing = [e for e in expected if e not in [d.get('id') for d in devices]]
    extra = [d.get('id') for d in devices if d.get('id') not in expected]
    print('\nValidation:')
    print(' Expected (from devices.json):', len(expected), 'items')
    print(' Missing in SYNC:', missing)
    print(' Extra in SYNC:', extra)
