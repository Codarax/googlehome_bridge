from __future__ import annotations
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.const import __version__ as HA_VERSION
from aiohttp import web
import json
import logging

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
        self._log_buf: list[dict] = []

    def _push_log(self, intent: str, detail: str):
        self._log_buf.append({"ts": self.hass.loop.time()*1000, "intent": intent, "detail": detail[:500]})
        if len(self._log_buf) > 50:
            self._log_buf.pop(0)

    async def post(self, request):
        logger = logging.getLogger(__name__)
        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("habridge: invalid JSON body on smarthome endpoint (%s)", exc)
            return web.json_response({"requestId": "invalid", "payload": {"errorCode": "protocolError"}}, status=400)
        intent = body.get("inputs", [{}])[0].get("intent")
        request_id = body.get("requestId", "req")
        logger.debug("habridge: intent=%s requestId=%s raw=%s", intent, request_id, body)
        try:
            if intent == "action.devices.SYNC":
                devices = self.device_mgr.build_sync()
                logger.info("habridge: SYNC returns %d devices", len(devices))
                self._push_log("SYNC", f"devices={len(devices)}")
                return web.json_response({"requestId": request_id, "payload": {"agentUserId": "user", "devices": devices}})
            if intent == "action.devices.QUERY":
                devices = {}
                for eid in self.device_mgr.selected():
                    st = self.hass.states.get(eid)
                    if not st:
                        continue
                    domain = st.domain
                    if domain in ("switch", "light"):
                        devices[eid] = {"on": st.state == "on", "online": True}
                        if domain == "light" and st.attributes.get("brightness") is not None:
                            bri = st.attributes.get("brightness")
                            pct = int(round(bri * 100 / 255))
                            devices[eid]["brightness"] = pct
                    elif domain == "climate":
                        cur = st.attributes.get("current_temperature")
                        hvac = st.state
                        # Map HA hvac state -> Google mode
                        mode_map = {
                            "off": "off",
                            "heat": "heat",
                            "cool": "cool",
                            "heat_cool": "heatcool",
                            "auto": "heatcool",
                            "fan_only": "fan-only",
                            "dry": "dry",
                        }
                        g_mode = mode_map.get(hvac, "off")
                        resp = {"online": True, "thermostatMode": g_mode}
                        if cur is not None:
                            resp["thermostatTemperatureAmbient"] = cur
                        target = st.attributes.get("temperature")
                        if target is not None:
                            resp["thermostatTemperatureSetpoint"] = target
                        low = st.attributes.get("target_temp_low")
                        high = st.attributes.get("target_temp_high")
                        if low is not None and high is not None:
                            resp["thermostatTemperatureSetpointLow"] = low
                            resp["thermostatTemperatureSetpointHigh"] = high
                        devices[eid] = resp
                logger.debug("habridge: QUERY devices=%d", len(devices))
                self._push_log("QUERY", f"devices={len(devices)}")
                return web.json_response({"requestId": request_id, "payload": {"devices": devices}})
            if intent == "action.devices.EXECUTE":
                commands = body.get("inputs", [{}])[0].get("payload", {}).get("commands", [])
                results = await self.device_mgr.execute(commands)
                logger.info("habridge: EXECUTE processed %d command groups", len(commands))
                self._push_log("EXECUTE", f"groups={len(commands)} results={len(results)}")
                return web.json_response({"requestId": request_id, "payload": {"commands": [{"ids": r["ids"], "status": r["status"]} for r in results]}})
            logger.warning("habridge: unknown intent '%s'", intent)
            self._push_log("UNKNOWN", intent or '')
            return web.json_response({"requestId": request_id, "payload": {}}, status=200)
        except Exception as exc:  # noqa: BLE001
            logger.exception("habridge: exception processing intent %s", intent)
            self._push_log("ERROR", str(exc))
            return web.json_response({"requestId": request_id, "payload": {"errorCode": "internalError"}}, status=500)

class HealthView(HomeAssistantView):
    url = HEALTH_PATH
    name = "habridge:health"
    requires_auth = False

    async def get(self, request):
        return web.json_response({"status": "ok", "ha_version": HA_VERSION})

# ---- Admin / Devices ----

ADMIN_HTML_BASE = """<!DOCTYPE html><html><head><meta charset='utf-8'/><title>HA Bridge Admin</title>
<style>
body{font-family:Inter,Arial,sans-serif;margin:0;background:#f6f7f9;color:#222;}
header{background:#243447;color:#fff;padding:10px 18px;display:flex;align-items:center;gap:24px;}
header h1{font-size:18px;margin:0;font-weight:600;}
nav a{color:#cfd6dd;text-decoration:none;margin-right:16px;font-size:14px;}
nav a.active{color:#fff;font-weight:600;}
.wrap{padding:16px 22px;}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid #d9dee3;border-radius:6px;overflow:hidden;margin-bottom:18px;}
th{background:#eef1f4;text-align:left;padding:6px 10px;font-size:12px;letter-spacing:.5px;text-transform:uppercase;color:#4a5560;}
td{padding:6px 10px;font-size:14px;border-top:1px solid #edf0f2;}
tr:hover{background:#f2f6fb;}
input[type=search]{width:260px;padding:6px 10px;border:1px solid #c7ccd1;border-radius:4px;}
button,select{padding:6px 12px;border:1px solid #c7ccd1;border-radius:4px;background:#fff;cursor:pointer;font-size:13px;}
button:hover{background:#f0f3f5;}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px;}
.pill{display:inline-block;padding:2px 8px;font-size:11px;border-radius:12px;background:#243447;color:#fff;margin-left:8px;}
.domain-icon{font-size:16px;width:22px;display:inline-block;text-align:center;}
.badge{background:#e1e6eb;padding:2px 6px;border-radius:10px;font-size:11px;margin-left:4px;}
.muted{color:#6a737d;font-size:12px;margin-left:4px;}
.toggle-wrap{display:flex;align-items:center;gap:6px;font-size:13px;}
.filter-row{display:flex;flex-wrap:wrap;gap:14px;align-items:center;}
</style></head>
<body>
<header>
    <h1>HA Bridge</h1>
    <nav>
        <a href="#" class="active" onclick="showView('devices');return false;">Devices</a>
        <a href="#" onclick="showView('logs');return false;">Logs</a>
        <a href="#" onclick="showView('settings');return false;">Settings</a>
    </nav>
    <span id="counts" class="pill"></span>
</header>
<div class="wrap">
    <div id="view-devices">
        <div class="toolbar">
            <div class="filter-row">
                <input id='q' placeholder='Search...' type='search' />
                <select id='domainFilter'><option value=''>All domains</option></select>
                <label class='toggle-wrap'><input type='checkbox' id='onlySel'/> Selected only</label>
                <button onclick='bulk(true)'>Select All</button>
                <button onclick='bulk(false)'>Clear All</button>
            </div>
        </div>
        <table id='tbl'><thead><tr><th style='width:34px;'>#</th><th>Stable ID</th><th>Name</th><th>Domain</th><th style='width:80px;'>Selected</th></tr></thead><tbody></tbody></table>
    </div>
    <div id="view-logs" style="display:none;">
        <div class='toolbar'>
            <button onclick='refreshLogs()'>Refresh Logs</button>
            <button onclick='clearLogs()'>Clear</button>
        </div>
        <table id='logtbl'><thead><tr><th style='width:160px;'>Time</th><th>Intent</th><th>Info</th></tr></thead><tbody></tbody></table>
    </div>
    <div id="view-settings" style="display:none;max-width:640px;">
        <h3>Settings</h3>
        <div style='background:#fff;border:1px solid #d9dee3;border-radius:6px;padding:14px;'>
            <p class='muted'>Client ID & Secret pas je aan via Integratie → Opties in Home Assistant.</p>
            <h4>Debug / Tools</h4>
            <button onclick='showSyncPreview()'>Force SYNC Preview</button>
            <pre id='syncPreview' style='margin-top:12px;display:none;max-height:300px;overflow:auto;background:#243447;color:#d6e4f2;padding:10px;font-size:12px;border-radius:6px;'></pre>
        </div>
    </div>
</div>
<script>
const urlParams=new URLSearchParams(window.location.search);const ADMIN_TOKEN=urlParams.get('token');
let _rows=[];let _filtered=[];let _domainSet=new Set();
const icons={switch:'⏻',light:'💡',climate:'🌡️',sensor:'📟'};
let _logs=[];
document.getElementById('q').addEventListener('input',filter);
document.getElementById('domainFilter').addEventListener('change',filter);
document.getElementById('onlySel').addEventListener('change',filter);
function showView(v){['devices','logs','settings'].forEach(x=>document.getElementById('view-'+x).style.display=x===v?'block':'none');document.querySelectorAll('nav a').forEach(a=>a.classList.remove('active'));document.querySelectorAll('nav a')[v==='devices'?0:(v==='logs'?1:2)].classList.add('active'); if(v==='logs'){refreshLogs();}}
async function load(){
    const r=await fetch('/habridge/devices?token='+encodeURIComponent(ADMIN_TOKEN));
    const data=await r.json();
    _rows=data.devices.map((d,i)=>({...d, stable:d.id}));
    _domainSet=new Set(_rows.map(r=>r.domain));
    populateDomainFilter();
    filter();
}
function populateDomainFilter(){
    const sel=document.getElementById('domainFilter');
    const cur=sel.value; sel.innerHTML='<option value="">All domains</option>' + Array.from(_domainSet).sort().map(d=>`<option value="${d}">${d}</option>`).join('');
    if([...sel.options].some(o=>o.value===cur)) sel.value=cur;
}
function filter(){
    const q=document.getElementById('q').value.trim().toLowerCase();
    const onlySel=document.getElementById('onlySel').checked;
    const domainF=document.getElementById('domainFilter').value;
    _filtered=_rows.filter(r=>{
         if(onlySel && !r.selected) return false;
         if(domainF && r.domain!==domainF) return false;
         if(!q) return true;
         return (r.id.toLowerCase().includes(q) || (r.name||'').toLowerCase().includes(q) || r.domain.toLowerCase().includes(q));
    });
    render();
}
function render(){
    const tb=document.querySelector('#tbl tbody');tb.innerHTML='';
    _filtered.forEach((r,idx)=>{
        const tr=document.createElement('tr');
        const icon=icons[r.domain]||'🔘';
        tr.innerHTML=`<td>${idx+1}</td><td>${r.id}</td><td><span class='domain-icon'>${icon}</span>${r.name||''}</td><td>${r.domain}</td><td style='text-align:center;'><input type='checkbox' ${r.selected?'checked':''} onchange='toggleDevice("${r.id}",this.checked)'/></td>`;
        tb.appendChild(tr);
    });
    document.getElementById('counts').textContent=`${_filtered.length} / ${_rows.length}`;
}
async function toggleDevice(id,val){
    await fetch('/habridge/devices?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates:{[id]:val}})});
    const row=_rows.find(r=>r.id===id); if(row) row.selected=val; filter();
}
async function bulk(val){
    const ups={};_filtered.forEach(r=>ups[r.id]=val);await fetch('/habridge/devices?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates:ups})});
    _filtered.forEach(r=>r.selected=val);_rows.forEach(r=>{if(ups[r.id]!==undefined) r.selected=val}); filter();
}
async function refreshLogs(){
    const r=await fetch('/habridge/logs?token='+encodeURIComponent(ADMIN_TOKEN));
    if(!r.ok) return; const data=await r.json(); _logs=data.logs||[]; renderLogs();
}
function renderLogs(){
    const tb=document.querySelector('#logtbl tbody'); if(!tb) return; tb.innerHTML='';
    _logs.forEach(l=>{const tr=document.createElement('tr'); tr.innerHTML=`<td>${new Date(l.ts).toLocaleTimeString()}</td><td>${l.intent}</td><td><code style='font-size:11px;'>${(l.detail||'').replace(/[<>]/g,'')}</code></td>`; tb.appendChild(tr);});
}
async function clearLogs(){ await fetch('/habridge/logs?token='+encodeURIComponent(ADMIN_TOKEN),{method:'DELETE'}); _logs=[]; renderLogs(); }
async function showSyncPreview(){
    const pre=document.getElementById('syncPreview');
    if(pre.style.display==='none'){
         const r=await fetch('/habridge/sync_preview?token='+encodeURIComponent(ADMIN_TOKEN));
         if(r.ok){ const data=await r.json(); pre.textContent=JSON.stringify(data,null,2); pre.style.display='block'; }
    } else { pre.style.display='none'; }
}
load();
</script></body></html>"""

class AdminPageView(HomeAssistantView):
    url = "/habridge/admin"
    name = "habridge:admin"
    requires_auth = False

    def __init__(self, admin_token: str):
        self._token = admin_token

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.Response(status=401, text="Unauthorized")
        return web.Response(text=ADMIN_HTML_BASE, content_type='text/html')

class DevicesView(HomeAssistantView):
    url = "/habridge/devices"
    name = "habridge:devices"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, device_mgr: DeviceManager, admin_token: str):
        self.hass = hass
        self.device_mgr = device_mgr
        self._token = admin_token

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
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
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        updates = data.get("updates", {})
        await self.device_mgr.bulk_update(updates)
        return web.json_response({"status": "ok"})

class LogsView(HomeAssistantView):
    url = "/habridge/logs"
    name = "habridge:logs"
    requires_auth = False

    def __init__(self, smart_view: SmartHomeView, admin_token: str):
        self._smart = smart_view
        self._token = admin_token

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response({"logs": self._smart._log_buf})

    async def delete(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        self._smart._log_buf.clear()
        return web.json_response({"status": "cleared"})

class SyncPreviewView(HomeAssistantView):
    url = "/habridge/sync_preview"
    name = "habridge:sync_preview"
    requires_auth = False

    def __init__(self, device_mgr: DeviceManager, admin_token: str):
        self._dm = device_mgr
        self._token = admin_token

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        devices = self._dm.build_sync()
        return web.json_response({"devices": devices})
