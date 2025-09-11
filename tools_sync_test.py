import requests
import json, os
from urllib.parse import urlparse, parse_qs

BASE = 'http://127.0.0.1:3001'
CLIENT_ID = os.getenv('CLIENT_ID', 'CHANGEME_CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET', 'CHANGEME_CLIENT_SECRET')

print('Reading devices.json')
with open('devices.json') as f:
    sel = json.load(f)
print('Selected devices:', sel)

s = requests.Session()
# Step 1: request auth code (no redirects)
r = s.get(f"{BASE}/oauth", params={'client_id': CLIENT_ID, 'redirect_uri': 'http://localhost/cb', 'state': 'xyz'}, allow_redirects=False)
print('OAuth status:', r.status_code)
loc = r.headers.get('Location')
if not loc:
    print('No Location header; abort')
    raise SystemExit(1)
print('Redirect Location:', loc)
qs = parse_qs(urlparse(loc).query)
code = qs.get('code', [None])[0]
print('Code:', code)

# Step 2: exchange code for token
resp = s.post(f"{BASE}/token", data={'grant_type': 'authorization_code', 'code': code, 'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET})
print('Token status:', resp.status_code)
print('Token response:', resp.text)
if resp.status_code != 200:
    raise SystemExit(2)
js = resp.json()
access = js.get('access_token')
print('Access token length:', len(access) if access else 0)

# Step 3: SYNC
hdr = {'Authorization': f'Bearer {access}', 'Content-Type': 'application/json'}
body = {'requestId': 'r1', 'inputs': [{'intent': 'action.devices.SYNC'}]}
resp = s.post(f"{BASE}/smarthome", json=body, headers=hdr)
print('SYNC status:', resp.status_code)
print('SYNC response (truncated):', resp.text[:1000])
if resp.status_code == 200:
    devices = resp.json().get('payload', {}).get('devices', [])
    print('SYNC device count:', len(devices))
    for d in devices:
        print(d.get('id'))
else:
    print('SYNC failed')
