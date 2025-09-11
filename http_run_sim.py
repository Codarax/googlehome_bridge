import requests
from urllib.parse import urljoin
import os

SERVER = 'http://127.0.0.1:3001'
CLIENT_ID = os.getenv('CLIENT_ID', 'CHANGEME_CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET', 'CHANGEME_CLIENT_SECRET')

# 1) GET /oauth (follow redirect manually)
params = {'client_id': CLIENT_ID, 'redirect_uri': 'https://example.com/redirect', 'state': 'state123'}
r = requests.get(urljoin(SERVER, '/oauth'), params=params, allow_redirects=False)
print('/oauth ->', r.status_code)
loc = r.headers.get('Location')
print('Location:', loc)
if not loc:
    print('No Location header, body:', r.text)
    raise SystemExit(1)

# extract code
from urllib.parse import urlparse, parse_qs
qs = parse_qs(urlparse(loc).query)
code = qs.get('code', [None])[0]
print('code:', code)

# 2) POST /token
data = {'grant_type':'authorization_code','code':code,'client_id':CLIENT_ID,'client_secret':CLIENT_SECRET}
tr = requests.post(urljoin(SERVER, '/token'), data=data)
print('/token ->', tr.status_code, tr.text[:1000])
if tr.status_code != 200:
    raise SystemExit(1)
access_token = tr.json().get('access_token')
print('access token prefix:', access_token[:20])

# 3) /smarthome SYNC
payload = {'requestId':'req_1','inputs':[{'intent':'action.devices.SYNC'}]}
headers = {'Authorization': f'Bearer {access_token}'}
sr = requests.post(urljoin(SERVER, '/smarthome'), json=payload, headers=headers)
print('/smarthome ->', sr.status_code)
print(sr.text[:2000])

if sr.status_code == 200:
    devices = sr.json().get('payload', {}).get('devices', [])
    print('Found', len(devices), 'devices. IDs:', [d.get('id') for d in devices])
else:
    print('smarthome failed')
