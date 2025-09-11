"""Simulate Google Home: perform OAuth flow and call /smarthome SYNC.

Run while server.py is running locally (default http://127.0.0.1:3001).
"""
import requests
from urllib.parse import urljoin, urlparse, parse_qs

SERVER = 'http://127.0.0.1:3001'
CLIENT_ID = 'Yew6FCGaG5ALIfNaZzWBZXBBLkaOnP8e'
CLIENT_SECRET = 'HtHL5dDmYqtMpHWduEdHjkA0nOVJByNg'

def get_auth_code():
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': 'https://example.com/redirect',
        'state': 'state123'
    }
    r = requests.get(urljoin(SERVER, '/oauth'), params=params, allow_redirects=False)
    if r.status_code in (301,302) and 'Location' in r.headers:
        loc = r.headers['Location']
        qs = parse_qs(urlparse(loc).query)
        code = qs.get('code', [None])[0]
        return code
    print('Failed to get auth code', r.status_code, r.text)
    return None

def exchange_code_for_token(code):
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    r = requests.post(urljoin(SERVER, '/token'), data=data)
    print('token response', r.status_code, r.text)
    if r.status_code == 200:
        return r.json().get('access_token')
    return None

def call_smarthome_sync(token):
    payload = {
        'requestId': 'req_1',
        'inputs': [{ 'intent': 'action.devices.SYNC' }]
    }
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.post(urljoin(SERVER, '/smarthome'), json=payload, headers=headers)
    print('smarthome sync', r.status_code, r.text)
    if r.status_code == 200:
        return r.json()
    return None

def main():
    code = get_auth_code()
    if not code:
        print('No code')
        return
    print('Got code:', code)
    token = exchange_code_for_token(code)
    if not token:
        print('No token')
        return
    print('Access token:', token[:20]+'...')
    res = call_smarthome_sync(token)
    if res:
        devices = res.get('payload', {}).get('devices', [])
        print(f'Found {len(devices)} devices. Sample IDs: {[d.get("id") for d in devices[:10]]}')

if __name__ == '__main__':
    main()
