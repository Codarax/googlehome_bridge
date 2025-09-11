"""Test toggling switch.woonkamer_lamp via OAuth -> token -> EXECUTE -> QUERY"""
import requests, time, os
BASE='http://127.0.0.1:3001'
CLIENT_ID=os.getenv('CLIENT_ID','CHANGEME_CLIENT_ID')
CLIENT_SECRET=os.getenv('CLIENT_SECRET','CHANGEME_CLIENT_SECRET')

from urllib.parse import urlparse, parse_qs

def get_token():
    r = requests.get(f"{BASE}/oauth", params={'client_id':CLIENT_ID,'redirect_uri':'http://localhost/callback','state':'x'}, allow_redirects=False)
    loc = r.headers.get('Location')
    code = parse_qs(urlparse(loc).query).get('code',[None])[0]
    resp = requests.post(f"{BASE}/token", data={'grant_type':'authorization_code','code':code,'client_id':CLIENT_ID,'client_secret':CLIENT_SECRET})
    return resp.json()['access_token']


def execute_on(token):
    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'}
    payload={'requestId':'r1','inputs':[{'intent':'action.devices.EXECUTE','payload':{'commands':[{'devices':[{'id':'switch.woonkamer_lamp'}],'execution':[{'command':'action.devices.commands.OnOff','params':{'on':True}}]}]}}]}
    r=requests.post(f"{BASE}/smarthome", headers=headers, json=payload)
    print('EXECUTE ON', r.status_code, r.text)


def execute_off(token):
    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'}
    payload={'requestId':'r2','inputs':[{'intent':'action.devices.EXECUTE','payload':{'commands':[{'devices':[{'id':'switch.woonkamer_lamp'}],'execution':[{'command':'action.devices.commands.OnOff','params':{'on':False}}]}]}}]}
    r=requests.post(f"{BASE}/smarthome", headers=headers, json=payload)
    print('EXECUTE OFF', r.status_code, r.text)


def query(token):
    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'}
    payload={'requestId':'rq','inputs':[{'intent':'action.devices.QUERY','payload':{'devices':[{'id':'switch.woonkamer_lamp'}]}}]}
    r=requests.post(f"{BASE}/smarthome", headers=headers, json=payload)
    print('QUERY', r.status_code, r.text)

if __name__=='__main__':
    t=get_token()
    execute_on(t)
    time.sleep(0.3)
    query(t)
    execute_off(t)
    time.sleep(0.3)
    query(t)
