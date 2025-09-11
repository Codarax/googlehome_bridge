"""Turn switch.woonkamer_lamp on for a few seconds, then off (OAuth->token->EXECUTE->QUERY)."""
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


def execute(on):
    token = get_token()
    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'}
    payload={'requestId':'burn','inputs':[{'intent':'action.devices.EXECUTE','payload':{'commands':[{'devices':[{'id':'switch.woonkamer_lamp'}],'execution':[{'command':'action.devices.commands.OnOff','params':{'on':on}}]}]}}]}
    r=requests.post(f"{BASE}/smarthome", headers=headers, json=payload)
    print(f'EXECUTE {"ON" if on else "OFF"}:', r.status_code, r.text)
    return token


def query(token):
    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'}
    payload={'requestId':'q','inputs':[{'intent':'action.devices.QUERY','payload':{'devices':[{'id':'switch.woonkamer_lamp'}]}}]}
    r=requests.post(f"{BASE}/smarthome", headers=headers, json=payload)
    print('QUERY:', r.status_code, r.text)

if __name__=='__main__':
    token = execute(True)
    time.sleep(3)
    query(token)
    execute(False)
    time.sleep(0.5)
    query(token)
