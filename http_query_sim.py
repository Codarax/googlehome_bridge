import requests
from urllib.parse import urljoin, urlparse, parse_qs
import json

SERVER = 'http://127.0.0.1:3001'
CLIENT_ID = 'Yew6FCGaG5ALIfNaZzWBZXBBLkaOnP8e'
CLIENT_SECRET = 'HtHL5dDmYqtMpHWduEdHjkA0nOVJByNg'

# load devices.json to get device ids
with open('devices.json','r') as f:
    selections = json.load(f)

device_ids = [k for k,v in selections.items() if v]

# 1) get auth code
params = {'client_id': CLIENT_ID, 'redirect_uri': 'https://example.com/redirect', 'state': 'state123'}
r = requests.get(urljoin(SERVER, '/oauth'), params=params, allow_redirects=False)
if r.status_code not in (301,302):
    print('/oauth failed', r.status_code, r.text)
    raise SystemExit(1)
loc = r.headers.get('Location')
qs = parse_qs(urlparse(loc).query)
code = qs.get('code',[None])[0]
print('Got code:', code)

# 2) exchange code for token
data = {'grant_type':'authorization_code','code':code,'client_id':CLIENT_ID,'client_secret':CLIENT_SECRET}
tr = requests.post(urljoin(SERVER, '/token'), data=data)
print('/token ->', tr.status_code, tr.text[:1000])
if tr.status_code != 200:
    raise SystemExit(1)
access_token = tr.json().get('access_token')

# 3) send QUERY for all device_ids
payload = {
    'requestId': 'req_query_1',
    'inputs':[{
        'intent': 'action.devices.QUERY',
        'payload': {
            'devices': [{'id': did} for did in device_ids]
        }
    }]
}
headers = {'Authorization': f'Bearer {access_token}'}
qr = requests.post(urljoin(SERVER, '/smarthome'), json=payload, headers=headers)
print('/smarthome QUERY ->', qr.status_code)
print(qr.text)

# Pretty-print device states
if qr.status_code == 200:
    body = qr.json()
    devices = body.get('payload', {}).get('devices', {})
    print('\nDevice states:')
    for did, state in devices.items():
        print(did, '->', state)
