from __future__ import annotations
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.const import __version__ as HA_VERSION
from aiohttp import web
import json

from .const import (
    OAUTH_PATH,
    TOKEN_PATH,
    SMARTHOME_PATH,
    HEALTH_PATH,
)
from .token_manager import TokenManager
from .device_manager import DeviceManager

class OAuthView(HomeAssistantView):
    url = OAUTH_PATH
    name = "habridge:oauth"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, token_mgr: TokenManager):
        self.hass = hass
        self.token_mgr = token_mgr

    async def get(self, request):
        user_id = "user"
        code = self.token_mgr.create_auth_code(user_id)
        redirect_uri = request.query.get("redirect_uri")
        state = request.query.get("state")
        if redirect_uri:
            sep = "&" if "?" in redirect_uri else "?"
            return web.HTTPFound(f"{redirect_uri}{sep}code={code}&state={state}")
        return web.Response(text=f"Authorized code: {code}")

class TokenView(HomeAssistantView):
    url = TOKEN_PATH
    name = "habridge:token"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, token_mgr: TokenManager):
        self.hass = hass
        self.token_mgr = token_mgr

    async def post(self, request):
        data = await request.post()
        grant_type = data.get("grant_type")
        if grant_type == "authorization_code":
            code = data.get("code")
            td = await self.token_mgr.exchange_code(code)
            if not td:
                return web.json_response({"error": "invalid_grant"}, status=400)
            return web.json_response(td.__dict__)
        if grant_type == "refresh_token":
            refresh_token = data.get("refresh_token")
            td = await self.token_mgr.refresh(refresh_token)
            if not td:
                return web.json_response({"error": "invalid_grant"}, status=400)
            return web.json_response(td.__dict__)
        return web.json_response({"error": "unsupported_grant_type"}, status=400)

class SmartHomeView(HomeAssistantView):
    url = SMARTHOME_PATH
    name = "habridge:smarthome"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, token_mgr: TokenManager, device_mgr: DeviceManager, client_secret: str):
        self.hass = hass
        self.token_mgr = token_mgr
        self.device_mgr = device_mgr
        self.client_secret = client_secret

    async def post(self, request):
        body = await request.json()
        intent = body.get("inputs", [{}])[0].get("intent")
        request_id = body.get("requestId", "req")
        if intent == "action.devices.SYNC":
            devices = self.device_mgr.build_sync()
            return web.json_response({"requestId": request_id, "payload": {"agentUserId": "user", "devices": devices}})
        if intent == "action.devices.QUERY":
            devices = {}
            for eid in self.device_mgr.selected():
                st = self.hass.states.get(eid)
                if st:
                    devices[eid] = {"on": st.state == "on", "online": True}
            return web.json_response({"requestId": request_id, "payload": {"devices": devices}})
        if intent == "action.devices.EXECUTE":
            commands = body.get("inputs", [{}])[0].get("payload", {}).get("commands", [])
            results = await self.device_mgr.execute(commands)
            return web.json_response({"requestId": request_id, "payload": {"commands": [{"ids": r["ids"], "status": r["status"]} for r in results]}})
        return web.json_response({"requestId": request_id, "payload": {}})

class HealthView(HomeAssistantView):
    url = HEALTH_PATH
    name = "habridge:health"
    requires_auth = False

    async def get(self, request):
        return web.json_response({"status": "ok", "ha_version": HA_VERSION})

# ---- Admin / Devices ----

ADMIN_HTML = """<!DOCTYPE html><html><head><meta charset='utf-8'/><title>HA Bridge Devices</title>
<style>body{font-family:Arial;margin:1rem;}table{border-collapse:collapse;width:100%;}th,td{padding:4px 8px;border-bottom:1px solid #ccc;}input[type=search]{width:300px;padding:4px;margin-bottom:8px;} .on{color:green;font-weight:600;} .off{color:#999;} button{padding:4px 10px;}</style></head>
<body><h2>HA Bridge Devices</h2><input id='q' placeholder='Search' type='search' oninput='filter()' /> <button onclick='bulk(true)'>Select All</button> <button onclick='bulk(false)'>Clear All</button>
<table id='tbl'><thead><tr><th>Entity</th><th>Name</th><th>Domain</th><th>Selected</th></tr></thead><tbody></tbody></table>
<script>
async function load(){
  const r=await fetch('/habridge/devices');
  const data=await r.json();
  window._rows=data.devices;render();
}
function render(){
  const q=document.getElementById('q').value.toLowerCase();
  const tb=document.querySelector('#tbl tbody');
  tb.innerHTML='';
  window._rows.filter(r=>!q||r.id.includes(q)|| (r.name||'').toLowerCase().includes(q)).forEach(r=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.id}</td><td>${r.name||''}</td><td>${r.domain}</td><td><input type='checkbox' ${r.selected?'checked':''} onchange='toggle("${r.id}",this.checked)'/></td>`;
    tb.appendChild(tr);
  });
}
async function toggle(id,val){
  await fetch('/habridge/devices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates:{[id]:val}})});load();
}
async function bulk(val){
  const ups={};window._rows.forEach(r=>ups[r.id]=val);await fetch('/habridge/devices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates:ups})});load();
}
load();
</script></body></html>"""

class AdminPageView(HomeAssistantView):
    url = "/habridge/admin"
    name = "habridge:admin"
    requires_auth = True  # Must be logged into HA UI

    async def get(self, request):
        return web.Response(text=ADMIN_HTML, content_type='text/html')

class DevicesView(HomeAssistantView):
    url = "/habridge/devices"
    name = "habridge:devices"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, device_mgr: DeviceManager):
        self.hass = hass
        self.device_mgr = device_mgr

    async def get(self, request):
        out = []
        for eid in self.device_mgr.list_entities():
            st = self.hass.states.get(eid)
            out.append({
                "id": eid,
                "name": st.name if st else eid,
                "domain": st.domain if st else eid.split('.')[0],
                "selected": eid in self.device_mgr.selected()
            })
        return web.json_response({"devices": out})

    async def post(self, request):
        data = await request.json()
        updates = data.get("updates", {})
        await self.device_mgr.bulk_update(updates)
        return web.json_response({"status": "ok"})
