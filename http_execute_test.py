"""Simple HTTP test: perform OAuth flow, obtain token, send EXECUTE to turn on light.kitchen and print response."""
import requests
import time, os

BASE = 'http://127.0.0.1:3001'
CLIENT_ID = os.getenv('CLIENT_ID', 'CHANGEME_CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET', 'CHANGEME_CLIENT_SECRET')

# Step 1: Get auth code
params = {
    'client_id': CLIENT_ID,
    'redirect_uri': 'http://localhost/callback',
    'state': 'test'
}
print('Requesting /oauth...')
r = requests.get(f"{BASE}/oauth", params=params, allow_redirects=False)
if r.status_code not in (302, 301):
    print('Failed to get auth redirect', r.status_code, r.text)
    raise SystemExit(1)

loc = r.headers.get('Location')
print('Redirect location:', loc)
# extract code param
from urllib.parse import urlparse, parse_qs
q = urlparse(loc).query
code = parse_qs(q).get('code', [None])[0]
print('Got code:', code)

# Step 2: Exchange for token
print('Requesting /token...')
resp = requests.post(f"{BASE}/token", data={
    'grant_type': 'authorization_code',
    'code': code,
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET
})
print('Token status:', resp.status_code, resp.text)
if resp.status_code != 200:
    raise SystemExit(1)

t = resp.json()['access_token']
print('Access token length:', len(t))

# Step 3: EXECUTE to turn on light.kitchen
headers = {'Authorization': f'Bearer {t}', 'Content-Type': 'application/json'}
execute_payload = {
    'requestId': 'req123',
    'inputs': [{
        'intent': 'action.devices.EXECUTE',
        'payload': {
            'commands': [{
                'devices': [{'id': 'light.kitchen'}],
                'execution': [{
                    'command': 'action.devices.commands.OnOff',
                    'params': {'on': True}
                }]
            }]
        }
    }]
}

print('Sending EXECUTE...')
r = requests.post(f"{BASE}/smarthome", headers=headers, json=execute_payload)
print('EXECUTE status:', r.status_code)
print(r.text)

# Wait and then query state
print('Sleeping 0.5s then QUERY...')
time.sleep(0.5)
query_payload = {
    'requestId': 'req124',
    'inputs': [{
        'intent': 'action.devices.QUERY',
        'payload': {
            'devices': [{'id': 'light.kitchen'}]
        }
    }]
}
q = requests.post(f"{BASE}/smarthome", headers=headers, json=query_payload)
print('QUERY status:', q.status_code)
print(q.text)
