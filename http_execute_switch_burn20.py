"""Turn switch.woonkamer_lamp on for 20 seconds, then off (OAuth->token->EXECUTE->QUERY)."""
import requests, time
from urllib.parse import urlparse, parse_qs

BASE='http://127.0.0.1:3001'
CLIENT_ID='Yew6FCGaG5ALIfNaZzWBZXBBLkaOnP8e'
CLIENT_SECRET='HtHL5dDmYqtMpHWduEdHjkA0nOVJByNg'

def get_token():
    r = requests.get(f"{BASE}/oauth", params={'client_id':CLIENT_ID,'redirect_uri':'http://localhost/callback','state':'x'}, allow_redirects=False)
    loc = r.headers.get('Location')
    code = parse_qs(urlparse(loc).query).get('code',[None])[0]
    resp = requests.post(f"{BASE}/token", data={'grant_type':'authorization_code','code':code,'client_id':CLIENT_ID,'client_secret':CLIENT_SECRET})
    return resp.json()['access_token']


def execute(on, token):
    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'}
    payload={'requestId':'burn20','inputs':[{'intent':'action.devices.EXECUTE','payload':{'commands':[{'devices':[{'id':'switch.woonkamer_lamp'}],'execution':[{'command':'action.devices.commands.OnOff','params':{'on':on}}]}]}}]}
    r=requests.post(f"{BASE}/smarthome", headers=headers, json=payload)
    print(f'EXECUTE {"ON" if on else "OFF"}:', r.status_code, r.text)


def query(token):
    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'}
    payload={'requestId':'q20','inputs':[{'intent':'action.devices.QUERY','payload':{'devices':[{'id':'switch.woonkamer_lamp'}]}}]}
    r=requests.post(f"{BASE}/smarthome", headers=headers, json=payload)
    print('QUERY:', r.status_code, r.text)

if __name__=='__main__':
    token = get_token()
    execute(True, token)
    # verify immediately
    time.sleep(0.5)
    query(token)
    print('Sleeping 20 seconds while lamp should remain ON...')
    time.sleep(20)
    query(token)
    execute(False, token)
    time.sleep(0.5)
    query(token)
