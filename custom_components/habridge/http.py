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
        # Start metrics sampling if available
        try:
            if hasattr(self.device_mgr, 'start_metrics'):
                self.device_mgr.start_metrics()
        except Exception:  # noqa: BLE001
            pass

    def _push_log(self, intent: str, detail: str, request_id: str | None = None):
        import time
        self._log_buf.append({
            "ts": int(time.time()*1000),
            "intent": intent,
            "detail": detail[:800],
            "rid": request_id or "-"
        })
        if len(self._log_buf) > 50:
            self._log_buf.pop(0)

    async def post(self, request):
        logger = logging.getLogger(__name__)
        import time as _t
        t_start = _t.perf_counter()
        # Debounced invalidation (was invalidate_sync_cache previously)
        try:
            self.device_mgr.debounce_invalidate()
        except Exception:  # noqa: BLE001
            pass
        raw_bytes = await request.read()
        try:
            # Probeer directe json.loads voor meer controle / fout logging
            body = json.loads(raw_bytes.decode('utf-8', errors='replace'))
        except Exception as exc:  # noqa: BLE001
            preview = raw_bytes[:200]
            logger.warning("habridge: invalid JSON body (%s) raw=%r", exc, preview)
            self._push_log("ERROR", f"invalid_json len={len(raw_bytes)}")
            return web.json_response({"requestId": "invalid", "payload": {"errorCode": "protocolError"}}, status=400)
        inputs = body.get("inputs") if isinstance(body, dict) else None
        if not inputs or not isinstance(inputs, list) or not inputs:
            logger.warning("habridge: malformed body missing inputs key: %s", body)
            self._push_log("ERROR", "malformed_payload_no_inputs")
            return web.json_response({"requestId": body.get("requestId", "invalid"), "payload": {"errorCode": "protocolError"}}, status=400)
        intent = inputs[0].get("intent")
        request_id = body.get("requestId", "req")
        logger.debug("habridge: intent=%s requestId=%s raw=%s", intent, request_id, body)
        try:
            if intent == "action.devices.SYNC":
                devices = self.device_mgr.build_sync()
                dt = int(( _t.perf_counter() - t_start)*1000)
                logger.info("habridge: SYNC returns %d devices in %dms", len(devices), dt)
                self._push_log("SYNC", f"devices={len(devices)} timeMs={dt}", request_id)
                try:
                    self.device_mgr.record_latency('sync', dt)
                except Exception:  # noqa: BLE001
                    pass
                return web.json_response({"requestId": request_id, "payload": {"agentUserId": "user", "devices": devices}})
            if intent == "action.devices.QUERY":
                devices = {}
                for eid in self.device_mgr.selected():
                    st = self.hass.states.get(eid)
                    if not st:
                        continue
                    domain = st.domain
                    sid = self.device_mgr.stable_id(eid)
                    if domain in ("switch", "light"):
                        resp = {"on": st.state == "on", "online": True}
                        if domain == "light" and st.attributes.get("brightness") is not None:
                            bri = st.attributes.get("brightness")
                            try:
                                pct = int(round(bri * 100 / 255))
                                resp["brightness"] = pct
                            except Exception:  # noqa: BLE001
                                pass
                        if domain == "light":
                            # Color reporting
                            rgb = st.attributes.get("rgb_color")
                            hs = st.attributes.get("hs_color")
                            ct = st.attributes.get("color_temp")
                            cur = {}
                            if rgb and isinstance(rgb,(list,tuple)) and len(rgb)==3:
                                try:
                                    r,g,b = rgb
                                    spec = (int(r)<<16) + (int(g)<<8) + int(b)
                                    cur["spectrumRgb"] = spec
                                except Exception:  # noqa: BLE001
                                    pass
                            elif hs and isinstance(hs,(list,tuple)) and len(hs)==2:
                                # convert hs to approximate RGB using HA util if desired (skip – minimal)
                                pass
                            if ct and isinstance(ct,(int,float)) and ct>0:
                                try:
                                    k = int(round(1000000/ct))
                                    # Provide temperatureK only if no RGB present or both supported
                                    cur["temperatureK"] = k
                                except Exception:  # noqa: BLE001
                                    pass
                            if cur:
                                resp["currentColor"] = cur
                        devices[sid] = resp
                    elif domain == "climate":
                        cur = st.attributes.get("current_temperature")
                        hvac = st.state
                        fan_mode = st.attributes.get("fan_mode")
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
                        if fan_mode:
                            resp["currentFanSpeedSetting"] = f"speed_{fan_mode.lower()}"
                        resp["on"] = g_mode != "off"
                        devices[sid] = resp
                    elif domain == "sensor":
                        dclass = st.attributes.get("device_class")
                        if dclass == "temperature":
                            try:
                                val = float(st.state)
                            except Exception:  # noqa: BLE001
                                continue
                            devices[sid] = {
                                "online": True,
                                "thermostatMode": "off",
                                "thermostatTemperatureAmbient": val,
                            }
                        elif dclass == "humidity":
                            try:
                                val = float(st.state)
                            except Exception:  # noqa: BLE001
                                continue
                            devices[sid] = {
                                "online": True,
                                "humidityAmbientPercent": val,
                            }
                logger.debug("habridge: QUERY devices=%d", len(devices))
                self._push_log("QUERY", f"devices={len(devices)}", request_id)
                dt = int(( _t.perf_counter() - t_start)*1000)
                self._push_log("QUERY", f"count={len(devices)} timeMs={dt}", request_id)
                try:
                    self.device_mgr.record_latency('query', dt)
                except Exception:  # noqa: BLE001
                    pass
                return web.json_response({"requestId": request_id, "payload": {"devices": devices}})
            if intent == "action.devices.EXECUTE":
                raw_group = inputs[0].get("payload", {}) if isinstance(inputs[0], dict) else {}
                commands = raw_group.get("commands", []) if isinstance(raw_group, dict) else []
                if not isinstance(commands, list):
                    logger.warning("habridge: EXECUTE malformed commands structure: %s", commands)
                    self._push_log("ERROR", "EXECUTE malformed commands struct")
                    return web.json_response({"requestId": request_id, "payload": {"errorCode": "protocolError"}}, status=400)
                results = await self.device_mgr.execute(commands)
                # Build detailed log: list every execution with entity + command
                detail_parts = []
                try:
                    for group in commands:
                        ds = group.get("devices", [])
                        exs = group.get("execution", [])
                        for d in ds:
                            did = d.get("id") or d.get("deviceId")
                            for ex in exs:
                                cname = ex.get("command", "?").split('.')[-1]
                                params = ex.get("params", {})
                                mini = []
                                if "on" in params:
                                    mini.append(f"on={params['on']}")
                                if "brightness" in params:
                                    mini.append(f"bri={params['brightness']}")
                                if "thermostatMode" in params:
                                    mini.append(f"mode={params['thermostatMode']}")
                                if "thermostatTemperatureSetpoint" in params:
                                    mini.append(f"temp={params['thermostatTemperatureSetpoint']}")
                                if "fanSpeed" in params:
                                    mini.append(f"fan={params['fanSpeed']}")
                                if "color" in params:
                                    col = params["color"] or {}
                                    if isinstance(col, dict):
                                        if 'spectrumRGB' in col:
                                            mini.append(f"rgb={col['spectrumRGB']}")
                                        elif 'spectrumRgb' in col:
                                            mini.append(f"rgb={col['spectrumRgb']}")
                                        elif 'temperatureK' in col:
                                            mini.append(f"k={col['temperatureK']}")
                                detail_parts.append(f"{did}:{cname}({','.join(mini)})")
                except Exception:  # noqa: BLE001
                    pass
                short_detail = ';'.join(detail_parts)[:600]
                logger.info("habridge: EXECUTE processed %d groups %s", len(commands), short_detail)
                dt = int(( _t.perf_counter() - t_start)*1000)
                self._push_log("EXECUTE", f"groups={len(commands)} results={len(results)} timeMs={dt} {short_detail}", request_id)
                try:
                    self.device_mgr.record_latency('exec', dt)
                except Exception:  # noqa: BLE001
                    pass
                return web.json_response({"requestId": request_id, "payload": {"commands": [{"ids": r["ids"], "status": r["status"]} for r in results]}})
            logger.warning("habridge: unknown intent '%s'", intent)
            self._push_log("UNKNOWN", intent or '', request_id)
            return web.json_response({"requestId": request_id, "payload": {}}, status=200)
        except Exception as exc:  # noqa: BLE001
            logger.exception("habridge: exception processing intent %s", intent)
            self._push_log("ERROR", str(exc), request_id)
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
header{background:#243447;color:#fff;padding:10px 18px;display:flex;align-items:center;gap:24px;position:sticky;top:0;z-index:100;box-shadow:0 2px 4px rgba(0,0,0,.15);} 
header h1{font-size:18px;margin:0;font-weight:600;}
nav a{color:#cfd6dd;text-decoration:none;margin-right:16px;font-size:14px;}
nav a.active{color:#fff;font-weight:600;}
.wrap{padding:16px 22px;}
table{border-collapse:separate;border-spacing:0;width:100%;background:#fff;border:1px solid #d9dee3;border-radius:8px;overflow:hidden;margin-bottom:18px;}
th{background:#eef1f4;text-align:left;padding:6px 10px;font-size:12px;letter-spacing:.5px;text-transform:uppercase;color:#4a5560;}
td{padding:6px 10px;font-size:14px;border-top:1px solid #edf0f2;}
tbody tr:nth-child(odd){background:#fafbfc;}
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
.sticky{position:sticky;top:0;z-index:9;background:#f6f7f9;padding-top:6px;padding-bottom:4px;}
/* Toggle */
.tgl{position:relative;display:inline-block;width:38px;height:20px;}
.tgl input{opacity:0;width:0;height:0;}
.tgl span{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#ccd3da;transition:.25s;border-radius:20px;}
.tgl span:before{position:absolute;content:"";height:16px;width:16px;left:2px;top:2px;background:#fff;border-radius:50%;transition:.25s;box-shadow:0 1px 3px rgba(0,0,0,.3);}
.tgl input:checked+span{background:#3b82f6;}
.tgl input:checked+span:before{transform:translateX(18px);}
.value-col{font-family:SFMono-Regular,Consolas,monospace;font-size:12px;color:#334058;}
.empty{padding:22px;text-align:center;color:#55606d;font-size:14px;}
.counts-extended{font-size:12px;color:#cfd6dd;margin-left:auto;}
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
    <div class="toolbar sticky">
            <div class="filter-row">
                <input id='q' placeholder='Search...' type='search' />
                <select id='domainFilter'><option value=''>All domains</option></select>
                <select id='areaFilter'><option value=''>Area: all</option><option value='with'>Area: with</option><option value='without'>Area: without</option></select>
                <label class='toggle-wrap'><input type='checkbox' id='onlySel'/> Selected only</label>
                <button onclick='bulk(true)'>Select All</button>
                <button onclick='bulk(false)'>Clear All</button>
            </div>
        </div>
    <table id='tbl'><thead><tr><th style='width:34px;'>#</th><th>Stable ID</th><th>Name</th><th>Alias</th><th>Area</th><th>Domain</th><th>Value</th><th style='width:90px;'>Selected</th><th style='width:70px;'>Edit</th></tr></thead><tbody></tbody></table>
    </div>
    <div id="view-logs" style="display:none;">
        <div class='toolbar'>
            <button onclick='refreshLogs()'>Refresh Logs</button>
            <button onclick='clearLogs()'>Clear</button>
        </div>
    <table id='logtbl'><thead><tr><th style='width:40px;'>#</th><th style='width:95px;'>Date</th><th style='width:80px;'>Time</th><th style='width:90px;'>ReqID</th><th style='width:90px;'>Intent</th><th>Detail</th></tr></thead><tbody></tbody></table>
    </div>
    <div id="view-settings" style="display:none;max-width:760px;">
        <h3>Settings</h3>
        <div style='background:#fff;border:1px solid #d9dee3;border-radius:6px;padding:14px;margin-bottom:16px;'>
            <p class='muted'>Client ID & Secret pas je aan via Integratie → Opties in Home Assistant.</p>
            <h4 style='margin-top:0;'>Debug / Tools</h4>
            <button onclick='showSyncPreview()'>Force SYNC Preview</button>
            <button style='margin-left:8px;' onclick='triggerSync()'>Re-SYNC (Google)</button>
            <pre id='syncPreview' style='margin-top:12px;display:none;max-height:300px;overflow:auto;background:#243447;color:#d6e4f2;padding:10px;font-size:12px;border-radius:6px;'></pre>
            <div id='roomHintBadge' style='margin-top:8px;font-size:12px;color:#334058;'></div>
        </div>
        <div style='background:#fff;border:1px solid #d9dee3;border-radius:6px;padding:14px;margin-bottom:16px;'>
            <h4 style='margin-top:0;'>OAuth Client Config</h4>
            <div style='display:flex;flex-direction:column;gap:10px;max-width:480px;'>
                <label style='font-size:13px;'>Client ID<br><input id='cid' type='text' style='width:100%;padding:6px;'></label>
                <label style='font-size:13px;'>Client Secret<br><div style='display:flex;gap:6px;'><input id='csec' type='password' style='flex:1;padding:6px;'><button type='button' onclick='toggleSecret()' style='padding:4px 8px;'>Show</button></div></label>
                <div style='display:flex;gap:8px;'>
                    <button type='button' onclick='genClientId()'>Gen ID</button>
                    <button type='button' onclick='genClientSecret()'>Gen Secret</button>
                    <button type='button' style='margin-left:auto;background:#3b82f6;color:#fff;' onclick='saveClientCreds()'>Save</button>
                </div>
                <div id='credStatus' class='muted'></div>
            </div>
            <p class='muted' style='margin-top:10px;'>Wijzigingen werken direct voor nieuwe OAuth flows en tokens. Bestaande refresh tokens blijven geldig maar nieuwe access tokens worden met de nieuwe secret ondertekend.</p>
        </div>
        <div style='background:#fff;border:1px solid #d9dee3;border-radius:6px;padding:14px;margin-bottom:16px;'>
            <h4 style='margin-top:0;'>Google Home Room Mapping</h4>
            <label style='display:flex;align-items:center;gap:8px;font-size:14px;margin-bottom:6px;'><input type='checkbox' id='roomhint_toggle'/> Stuur Home Assistant Area naam mee als roomHint</label>
            <p class='muted'>Indien ingeschakeld krijgen apparaten in Google Home automatisch de kamer toegewezen op basis van de Home Assistant Area. Daarna kan een nieuwe SYNC nodig zijn.</p>
            <button onclick='toggleRoomHint()'>Opslaan</button>
            <span id='roomhint_status' class='muted' style='margin-left:10px;'></span>
        </div>
        <div style='background:#fff;border:1px solid #d9dee3;border-radius:6px;padding:14px;'>
            <h4 style='margin-top:0;'>Device List Filters</h4>
            <p class='muted'>Beheer welke domeinen zichtbaar zijn in het Devices overzicht. Wordt lokaal opgeslagen (browser).</p>
            <div id='domainSettings'></div>
            <button style='margin-top:10px;' onclick='resetDomainVisibility()'>Reset naar standaard</button>
        </div>
    </div>
</div>
<script>
const urlParams=new URLSearchParams(window.location.search);const ADMIN_TOKEN=urlParams.get('token');
let _rows=[];let _filtered=[];let _domainSet=new Set();
let _aliasEditing=false; // block device list refresh while editing alias
let _pendingAliasSaves={}; // sid -> alias while saving
const icons={switch:'⏻',light:'💡',climate:'🌡️',sensor:'📟',scene:'🎬',script:'📜'};
let _logs=[];let _logTimer=null;let _devTimer=null;
let _pendingSelections={}; // id -> desired state
let _pendingLocks={}; // id -> lock until timestamp (ms)
let _backgroundUpdates=true; // default aan; kan via settings uit
let _domainVisibility = JSON.parse(localStorage.getItem('habridge_domain_visibility')||'{}');
function isDomainVisible(d){ if(Object.keys(_domainVisibility).length===0) return true; return _domainVisibility[d]!==false; }
document.getElementById('q').addEventListener('input',filter);
document.getElementById('domainFilter').addEventListener('change',filter);
document.getElementById('onlySel').addEventListener('change',filter);
const areaFilterEl = document.getElementById('areaFilter'); if(areaFilterEl) areaFilterEl.addEventListener('change',filter);
function showView(v){
    ['devices','logs','settings'].forEach(x=>document.getElementById('view-'+x).style.display=x===v?'block':'none');
    document.querySelectorAll('nav a').forEach(a=>a.classList.remove('active'));
    document.querySelectorAll('nav a')[v==='devices'?0:(v==='logs'?1:2)].classList.add('active');
    if(v==='logs'){refreshLogs(); startLogTimer(); stopDevTimer();}
    else if(v==='devices'){refreshDevicesValue(); if(_backgroundUpdates) startDevTimer(); stopLogTimer();}
    else {stopLogTimer(); stopDevTimer();}
}
async function loadSettings(){
    try{
        const r=await fetch('/habridge/settings?token='+encodeURIComponent(ADMIN_TOKEN));
        if(!r.ok) return; const data=await r.json();
        const s=data.settings||{}; const cb=document.getElementById('roomhint_toggle'); if(cb) cb.checked=!!s.roomhint_enabled;
        const cid=document.getElementById('cid'); if(cid && s.client_id) cid.value=s.client_id;
        const csec=document.getElementById('csec'); if(csec && s.client_secret) csec.value=s.client_secret;
    }catch(e){}
}
async function toggleRoomHint(){
    const cb=document.getElementById('roomhint_toggle'); if(!cb) return; const val=cb.checked; const st=document.getElementById('roomhint_status');
    st.textContent='Bezig...';
    try {
        const r=await fetch('/habridge/settings?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({roomhint_enabled:val})});
        if(r.ok){ st.textContent='Opgeslagen'; setTimeout(()=>{st.textContent='';},2000);} else { st.textContent='Fout'; }
    } catch(e){ st.textContent='Fout'; }
}
async function load(){
    await refreshDevicesValue();
    if(_backgroundUpdates) startDevTimer();
}
async function refreshDevicesValue(){
    if(_aliasEditing) return; // do not overwrite row being edited
    const previous = Object.fromEntries(_rows.map(r=>[r.id,r.selected]));
    const r=await fetch('/habridge/devices?token='+encodeURIComponent(ADMIN_TOKEN));
    if(!r.ok) return;
    const data=await r.json();
    const now=Date.now();
    _rows=data.devices.map(d=>{
        if(_pendingSelections.hasOwnProperty(d.id) && _pendingLocks[d.id] && _pendingLocks[d.id] > now){
            return { ...d, selected: _pendingSelections[d.id] };
        }
        // Preserve pending alias save display if server not yet updated
        let aliasOverride = undefined;
        const sid = d.stable_id || d.id;
        if(_pendingAliasSaves[sid] !== undefined){ aliasOverride = _pendingAliasSaves[sid]; }
        const base = { ...d, selected: (_pendingSelections.hasOwnProperty(d.id)? _pendingSelections[d.id] : d.selected ) };
        if(aliasOverride !== undefined){ base.alias = aliasOverride; }
        return base;
    });
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
    const areaF= areaFilterEl? areaFilterEl.value: '';
    _filtered=_rows.filter(r=>{
        if(onlySel && !r.selected) return false;
        if(domainF && r.domain!==domainF) return false;
        if(!isDomainVisible(r.domain)) return false;
        if(areaF==='with' && !r.area) return false;
        if(areaF==='without' && r.area) return false;
        if(!q) return true;
    const target=[r.stable_id||'', r.id||'', r.name||'', (r.alias||''), r.domain||'', r.value||''].join(' ').toLowerCase();
        return target.includes(q);
    });
    render();
}
function render(){
    const tb=document.querySelector('#tbl tbody');tb.innerHTML='';
    if(!_filtered.length){
        const tr=document.createElement('tr');
    const td=document.createElement('td');td.colSpan=9;td.className='empty';td.textContent='No devices match filters';
        tr.appendChild(td);tb.appendChild(tr);
    } else {
        _filtered.forEach((r,idx)=>{
            const tr=document.createElement('tr');
            const icon=icons[r.domain]||'🔘';
            const aliasCell = (r.alias && r.alias.length) ? `<span class='alias-text' title="Alias for ${r.orig_name.replace(/"/g,'&quot;')}">${r.alias}</span>` : '';
            const colorBadge = r.has_color ? `<span style='display:inline-block;width:10px;height:10px;border-radius:50%;margin-left:6px;vertical-align:middle;background:${r.color_preview?('#'+('000000'+r.color_preview.toString(16)).slice(-6)):'#f5c542'};border:1px solid #ccc;' title='Color capable light'></span>` : '';
            let areaTitle='';
            let areaDisplay = r.area||'';
            if(!r.area){ areaDisplay=''; }
            tr.innerHTML=`<td>${idx+1}</td>
                <td title="${r.id}">${r.stable_id||r.id}</td>
                <td class='nm'><span class='domain-icon'>${icon}</span><span class='orig-name'>${r.name||''}</span>${colorBadge}</td>
                <td class='alias-col'>${aliasCell}</td>
                <td ${areaTitle?`title='${areaTitle.replace(/'/g,"&#39;")}'`:''}>${areaDisplay}</td>
                <td>${r.domain}</td>
                <td class='value-col'>${r.value||''}</td>
                <td style='text-align:center;'><label class='tgl'><input type='checkbox' data-id='${r.id}' ${r.selected?'checked':''} onchange='toggleDevice("${r.id}",this.checked)'><span></span></label></td>
                <td style='text-align:center;'><button style='padding:2px 6px;font-size:12px;' onclick='startRename("${r.id}","${r.stable_id||r.id}",this)'>Rename</button></td>`;
            tb.appendChild(tr);
        });
    }
    document.getElementById('counts').textContent=`${_filtered.length} / ${_rows.length}`;
}
async function toggleDevice(id,val){
    // Optimistisch
    _pendingSelections[id]=val;
    _pendingLocks[id]=Date.now()+4000; // 4s lock window
    const row=_rows.find(r=>r.id===id); if(row) row.selected=val;
    // UI direct updaten zonder volledige filter run om flicker te vermijden
    const el=document.querySelector(`input[type=checkbox][data-id='${id}']`);
    if(el) el.checked=val;
    try {
        const resp=await fetch('/habridge/devices?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates:{[id]:val}})});
    if(!resp.ok) throw new Error('HTTP '+resp.status);
    // direct een refresh triggeren (niet wachten op interval)
    refreshDevicesValue();
    // shorten lock window on success
    _pendingLocks[id]=Date.now()+800; // allow server value to flow soon
    // remove pending once a confirming refresh passes (handled in refresh merge logic)
    } catch(e){
        // revert bij fout
        const prev=!val; _pendingSelections[id]=prev; if(row) row.selected=prev; if(el) el.checked=prev;
    }
}
async function bulk(val){
    const actionLabel = val ? 'Select ALL' : 'Clear ALL';
    const affected = _filtered.length;
    if(affected===0) return;
    if(!confirm(`${actionLabel} (${affected} devices)?`)) return;
    const ups={};
    const now=Date.now();
    _filtered.forEach(r=>{ups[r.id]=val; _pendingSelections[r.id]=val; _pendingLocks[r.id]=now+4000;});
    // Optimistic UI update
    _rows.forEach(r=>{ if(ups[r.id]!==undefined) r.selected=val; });
    filter();
    try{
        const resp=await fetch('/habridge/devices?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates:ups})});
        if(!resp.ok) throw new Error('HTTP '+resp.status);
        // shorten locks to allow server truth to flow in
        Object.keys(ups).forEach(id=>{ _pendingLocks[id]=Date.now()+800; });
        refreshDevicesValue();
    }catch(e){
        // revert on failure
        Object.keys(ups).forEach(id=>{ _pendingSelections[id]=!val; const row=_rows.find(r=>r.id===id); if(row) row.selected=!val; });
        filter();
    }
}
async function refreshLogs(){
    const r=await fetch('/habridge/logs?token='+encodeURIComponent(ADMIN_TOKEN));
    if(!r.ok) return; const data=await r.json(); _logs=data.logs||[]; renderLogs();
}
function renderLogs(){
    const tb=document.querySelector('#logtbl tbody'); if(!tb) return; tb.innerHTML='';
    _logs.forEach((l,i)=>{
        const dt=new Date(l.ts);
        const d=dt.toLocaleDateString();
        const t=dt.toLocaleTimeString();
        const tr=document.createElement('tr');
        tr.innerHTML=`<td>${i+1}</td><td>${d}</td><td>${t}</td><td>${l.rid||'-'}</td><td>${l.intent}</td><td><code style='font-size:11px;'>${(l.detail||'').replace(/[<>]/g,'')}</code></td>`;
        tb.appendChild(tr);
    });
}
async function clearLogs(){ await fetch('/habridge/logs?token='+encodeURIComponent(ADMIN_TOKEN),{method:'DELETE'}); _logs=[]; renderLogs(); }
function startLogTimer(){ if(_logTimer) return; _logTimer=setInterval(refreshLogs,5000); }
function stopLogTimer(){ if(_logTimer){clearInterval(_logTimer); _logTimer=null;} }
function startDevTimer(){ if(_devTimer) return; _devTimer=setInterval(()=>{ if(document.hidden) return; refreshDevicesValue(); },10000); }
function stopDevTimer(){ if(_devTimer){clearInterval(_devTimer); _devTimer=null;} }
async function showSyncPreview(){
    const pre=document.getElementById('syncPreview');
    if(pre.style.display==='none'){
         const r=await fetch('/habridge/sync_preview?token='+encodeURIComponent(ADMIN_TOKEN));
         if(r.ok){ const data=await r.json(); pre.textContent=JSON.stringify(data,null,2); pre.style.display='block'; }
    } else { pre.style.display='none'; }
}
async function triggerSync(){
    const btns=document.querySelectorAll('button');
    try{
        const r=await fetch('/habridge/trigger_sync?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST'});
        if(r.ok){
            const data=await r.json();
            updateRoomHintBadge(data.roomhint_count, data.count);
            // update preview if open
            const pre=document.getElementById('syncPreview');
            if(pre && pre.style.display!=='none'){
                pre.textContent=JSON.stringify({devices:data.devices},null,2);
            }
        }
    }catch(e){}
}
function updateRoomHintBadge(rh,total){
    const el=document.getElementById('roomHintBadge'); if(!el) return;
    if(total===undefined||total===0){ el.textContent=''; return; }
    el.textContent=`roomHint toegepast op ${rh}/${total} devices`;
}
function genRandom(len){const chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';let o='';for(let i=0;i<len;i++)o+=chars[Math.floor(Math.random()*chars.length)];return o;}
function genClientId(){ const cid=document.getElementById('cid'); if(cid) cid.value='cid_'+genRandom(10); }
function genClientSecret(){ const csec=document.getElementById('csec'); if(csec) csec.value='sec_'+genRandom(30); }
function toggleSecret(){ const csec=document.getElementById('csec'); if(!csec) return; if(csec.type==='password'){ csec.type='text'; event.target.textContent='Hide'; } else { csec.type='password'; event.target.textContent='Show'; } }
async function saveClientCreds(){ const cid=document.getElementById('cid'); const csec=document.getElementById('csec'); const st=document.getElementById('credStatus'); if(!cid||!csec||!st) return; st.textContent='Opslaan...';
    try{ const r=await fetch('/habridge/settings?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:cid.value,client_secret:csec.value})}); if(r.ok){ st.textContent='Opgeslagen'; setTimeout(()=>st.textContent='',2500);} else { st.textContent='Fout'; } }catch(e){ st.textContent='Fout'; }
}
// Settings pane uitbreiden met toggle voor background updates
const settingsDiv=document.getElementById('view-settings');
if(settingsDiv){
    const opt=document.createElement('div');
    opt.style.marginTop='16px';
    opt.innerHTML=`<label style='display:flex;align-items:center;gap:8px;font-size:14px;'><input type='checkbox' id='bgupd' ${_backgroundUpdates?'checked':''}/> Background auto updates</label><p class='muted'>Schakel uit als je absolute rust wilt tijdens scrollen; handmatig verversen blijft mogelijk.</p>`;
    settingsDiv.appendChild(opt);
    document.addEventListener('visibilitychange',()=>{
        if(!document.hidden && _backgroundUpdates){
            refreshDevicesValue();
            refreshLogs();
        }
    });
    opt.querySelector('#bgupd').addEventListener('change',e=>{_backgroundUpdates=e.target.checked; if(!_backgroundUpdates){ stopDevTimer(); stopLogTimer(); } else { if(document.getElementById('view-devices').style.display!=='none') startDevTimer(); if(document.getElementById('view-logs').style.display!=='none') startLogTimer(); }});
}
function buildDomainSettings(){
    const host=document.getElementById('domainSettings'); if(!host) return; const all=Array.from(_domainSet).sort();
    if(all.length===0){ host.innerHTML='<p class="muted">Nog geen devices geladen.</p>'; return; }
    host.innerHTML=all.map(d=>{
        const chk= isDomainVisible(d)?'checked':'';
        return `<label style='display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px;'><input type='checkbox' data-dom='${d}' ${chk}/> ${d}</label>`;
    }).join('');
    host.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.addEventListener('change',e=>{
            const dom=e.target.getAttribute('data-dom');
            _domainVisibility[dom]=e.target.checked; // false when unchecked
            if(e.target.checked) delete _domainVisibility[dom];
            localStorage.setItem('habridge_domain_visibility', JSON.stringify(_domainVisibility));
            filter();
    }));
}
function resetDomainVisibility(){ _domainVisibility={}; localStorage.removeItem('habridge_domain_visibility'); filter(); buildDomainSettings(); }
// Rebuild domain settings whenever domains change
const origPopulateDomainFilter = populateDomainFilter;
populateDomainFilter = function(){ origPopulateDomainFilter(); buildDomainSettings(); };
load();
loadSettings();
// Also fetch initial sync preview silently to compute roomHint badge
(async()=>{try{const r=await fetch('/habridge/sync_preview?token='+encodeURIComponent(ADMIN_TOKEN)); if(r.ok){const data=await r.json(); const devices=data.devices||[]; const rh=devices.filter(d=>d.roomHint).length; updateRoomHintBadge(rh, devices.length);} }catch(e){}})();

async function startRename(eid, sid, btn){
    const row = btn.closest('tr'); if(!row) return; const aliasCell=row.querySelector('.alias-col'); if(!aliasCell) return;
    const existing = aliasCell.querySelector('.alias-text');
    const current = existing ? existing.textContent : '';
    const input = document.createElement('input'); input.type='text'; input.value=current; input.style.width='140px'; input.style.fontSize='12px'; input.placeholder='(empty to clear)';
    aliasCell.innerHTML=''; aliasCell.appendChild(input);
    btn.textContent='Save'; btn.onclick=()=>finishRename(eid,sid,input,btn,current);
    _aliasEditing=true; stopDevTimer();
    input.addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ finishRename(eid,sid,input,btn,current); } else if(e.key==='Escape'){ cancelRename(eid,sid,input,btn,current); } });
    setTimeout(()=>{ try{ input.focus(); input.select(); }catch(e){} }, 30);
}
async function finishRename(eid, sid, input, btn, oldAlias){
    const raw = input.value; // preserve spaces; empty clears
    const payload = {id:sid, alias: raw};
    btn.disabled=true; _pendingAliasSaves[sid]=raw; 
    const aliasCell=input.parentElement;
    let statusEl = null;
    if(aliasCell){
        statusEl = document.createElement('span');
        statusEl.style.marginLeft='6px';
        statusEl.style.fontSize='11px';
        statusEl.style.color='#555';
        statusEl.textContent='Saving...';
        aliasCell.appendChild(statusEl);
    }
    try{
        const r=await fetch('/habridge/aliases?token='+encodeURIComponent(ADMIN_TOKEN),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        if(!r.ok){
            let msg='Save failed ('+r.status+')';
            if(r.status===401) msg='Unauthorized (token?)';
            throw new Error(msg);
        }
        const data=await r.json();
        if(aliasCell){ aliasCell.innerHTML=''; if(data.alias){ const span=document.createElement('span'); span.className='alias-text'; span.textContent=data.alias; aliasCell.appendChild(span);} else { /* cleared */ } }
        btn.textContent='Rename'; btn.onclick=( )=>startRename(eid,sid,btn); _aliasEditing=false; if(_backgroundUpdates) startDevTimer(); refreshDevicesValue();
    }catch(e){
        if(statusEl){ statusEl.textContent=e.message||'Error'; statusEl.style.color='#b00020'; setTimeout(()=>{ if(statusEl&&statusEl.parentElement){ statusEl.parentElement.removeChild(statusEl);} },3000); }
        // laat tijdelijke error zien maar herstel oude alias pas na korte delay
        setTimeout(()=>{ cancelRename(eid,sid,input,btn,oldAlias); },800);
    }finally {
        delete _pendingAliasSaves[sid]; btn.disabled=false; _aliasEditing=false; if(_backgroundUpdates) startDevTimer();
    }
}
function cancelRename(eid,sid,input,btn,oldAlias){ const cell=input.parentElement; if(cell){ cell.innerHTML=''; if(oldAlias){ const span=document.createElement('span'); span.className='alias-text'; span.textContent=oldAlias; cell.appendChild(span);} } btn.textContent='Rename'; btn.onclick=( )=>startRename(eid,sid,btn); _aliasEditing=false; if(_backgroundUpdates) startDevTimer(); }
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

    def __init__(self, hass: HomeAssistant, device_mgr: DeviceManager, admin_token: str, smart_view: SmartHomeView):
        self.hass = hass
        self.device_mgr = device_mgr
        self._token = admin_token
        self._smart = smart_view

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        data = self.hass.data.get('habridge') or {}
        aliases = data.get('aliases') or {}
        # Unified area lookup with fallback + optional debug
        debug = request.query.get('debug') == '1'
        area_lookup = {}
        area_sources = {}
        try:
            if debug:
                area_lookup, stats, area_sources = self.device_mgr.compute_area_lookup(debug=True)
            else:
                area_lookup, _stats = self.device_mgr.compute_area_lookup()
        except Exception:  # noqa: BLE001
            area_lookup = {}
            area_sources = {}
        out = []
        for eid in self.device_mgr.list_entities():
            st = self.hass.states.get(eid)
            domain = st.domain if st else eid.split('.')[0]
            stable_id = self.device_mgr.stable_id(eid)
            value = None
            has_color = False
            color_preview = None
            if st:
                if domain in ("switch", "light"):
                    if domain == "light" and st.attributes.get("brightness") is not None:
                        try:
                            pct = int(round(st.attributes.get("brightness") * 100 / 255))
                            value = f"{pct}%"
                        except Exception:  # noqa: BLE001
                            value = st.state
                    else:
                        value = st.state
                    if domain == "light":
                        # derive color capability
                        try:
                            scm = st.attributes.get("supported_color_modes") or []
                            scm_l = {str(x).lower() for x in scm} if isinstance(scm, (list,set,tuple)) else set()
                            if any(m in scm_l for m in ("hs","rgb","rgbw","rgbww","xy")) or st.attributes.get("rgb_color") or st.attributes.get("hs_color"):
                                has_color = True
                                rgb = st.attributes.get("rgb_color")
                                if rgb and isinstance(rgb,(list,tuple)) and len(rgb)==3:
                                    r,g,b = rgb
                                    color_preview = (int(r)<<16) + (int(g)<<8) + int(b)
                        except Exception:  # noqa: BLE001
                            pass
                elif domain == "climate":
                    cur = st.attributes.get("current_temperature")
                    mode = st.state
                    if cur is not None:
                        value = f"{cur}° ({mode})"
                    else:
                        value = mode
                elif domain == "sensor":
                    value = st.state
            orig_name = st.name if st else eid
            alias = aliases.get(stable_id) or aliases.get(eid)
            area_name = area_lookup.get(eid)
            out.append({
                "id": eid,
                "stable_id": stable_id,
                "name": orig_name,
                "orig_name": orig_name,
                "alias": alias,
                "area": area_name,
                "area_source": area_sources.get(eid) if debug else None,
                "domain": domain,
                "value": value,
                "has_color": has_color,
                "color_preview": color_preview,
                "selected": eid in self.device_mgr.selected()
            })
        resp = {"devices": out}
        if debug:
            resp["area_sources"] = area_sources
        return web.json_response(resp)

    async def post(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        updates = data.get("updates", {})
        await self.device_mgr.bulk_update(updates)
        if getattr(self, '_smart', None):
            changed = ",".join([f"{k}={v}" for k,v in updates.items()][:10])
            self._smart._push_log("SELECT", f"updates={len(updates)} sample={changed}")
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

class SettingsView(HomeAssistantView):
    url = "/habridge/settings"
    name = "habridge:settings"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, admin_token: str, smart_view: SmartHomeView):
        self.hass = hass
        self._token = admin_token
        self._smart = smart_view

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        data = self.hass.data.get('habridge') or {}
        settings = data.get('settings') or {}
        return web.json_response({"settings": settings})

    async def post(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"error": "invalid_json"}, status=400)
        data = self.hass.data.get('habridge') or {}
        settings = data.get('settings') or {}
        changed = False
        if 'roomhint_enabled' in body:
            val = bool(body['roomhint_enabled'])
            if settings.get('roomhint_enabled') != val:
                settings['roomhint_enabled'] = val
                changed = True
        if 'client_id' in body and isinstance(body.get('client_id'), str):
            new_id = body['client_id'].strip()
            if new_id and settings.get('client_id') != new_id:
                settings['client_id'] = new_id
                # reflect runtime copy
                data['client_id'] = new_id
                changed = True
        if 'client_secret' in body and isinstance(body.get('client_secret'), str):
            new_secret = body['client_secret'].strip()
            if new_secret and settings.get('client_secret') != new_secret:
                settings['client_secret'] = new_secret
                # update token manager secret in-memory for new JWT signing going forward
                tm = data.get('token_mgr')
                if tm:
                    tm.client_secret = new_secret
                data['client_secret'] = new_secret
                changed = True
        if changed:
            # persist
            store = data.get('settings_store')
            if store:
                await store.async_save(settings)
            # invalidate sync cache if roomhint or credentials changed (safe to always invalidate on any setting change)
            dm = data.get('device_mgr')
            if dm:
                try:
                    if hasattr(dm, 'debounce_invalidate'):
                        dm.debounce_invalidate()
                    else:
                        dm.invalidate_sync_cache()
                except Exception:  # noqa: BLE001
                    pass
            # safe log (mask secrets)
            log_parts = []
            if 'roomhint_enabled' in body:
                log_parts.append(f"roomhint_enabled={settings.get('roomhint_enabled')}")
            if 'client_id' in body:
                cid = settings.get('client_id') or ''
                log_parts.append(f"client_id={cid}")
            if 'client_secret' in body:
                cs = settings.get('client_secret') or ''
                mask = (cs[:4] + '***' + cs[-4:]) if len(cs) > 8 else '***'
                log_parts.append(f"client_secret={mask}")
            self._smart._push_log("SET", ' '.join(log_parts))
        return web.json_response({"settings": settings, "changed": changed})

class TriggerSyncView(HomeAssistantView):
    url = "/habridge/trigger_sync"
    name = "habridge:trigger_sync"
    requires_auth = False

    def __init__(self, device_mgr: DeviceManager, admin_token: str, smart_view: SmartHomeView):
        self._dm = device_mgr
        self._token = admin_token
        self._smart = smart_view

    async def post(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        devices = self._dm.build_sync()
        roomhint_count = sum(1 for d in devices if 'roomHint' in d)
        self._smart._push_log("SYNC_TRIGGER", f"devices={len(devices)} roomhints={roomhint_count}")
        return web.json_response({"devices": devices, "count": len(devices), "roomhint_count": roomhint_count})

class AliasesView(HomeAssistantView):
    url = "/habridge/aliases"
    name = "habridge:aliases"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, admin_token: str, smart_view: SmartHomeView):
        self.hass = hass
        self._token = admin_token
        self._smart = smart_view

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        data = self.hass.data.get('habridge') or {}
        aliases = data.get('aliases') or {}
        return web.json_response({"aliases": aliases})

    async def post(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"error": "invalid_json"}, status=400)
        sid = body.get('id')  # stable id or entity id
        new_name = body.get('alias')
        if not sid:
            return web.json_response({"error": "missing_id"}, status=400)
        if new_name is None:
            return web.json_response({"error": "missing_alias"}, status=400)
        if not isinstance(new_name, str):
            return web.json_response({"error": "alias_not_string"}, status=400)
        data = self.hass.data.get('habridge') or {}
        aliases = data.get('aliases') or {}
        dm = data.get('device_mgr')
        if dm and sid in getattr(dm, '_entity_to_stable', {}):  # raw entity id provided
            sid_key = dm._entity_to_stable.get(sid)
        else:
            sid_key = sid
        trimmed = new_name.strip()
        removed = False
        if trimmed == '':  # clear alias
            if sid_key in aliases:
                del aliases[sid_key]
                removed = True
        else:
            # preserve exact whitespace user entered
            aliases[sid_key] = new_name
        store = data.get('alias_store')
        if store:
            await store.async_save(aliases)
        if dm:
            try:
                if hasattr(dm, 'debounce_invalidate'):
                    dm.debounce_invalidate()
                else:
                    dm.invalidate_sync_cache()
            except Exception:  # noqa: BLE001
                pass
        log_val = '(cleared)' if removed else new_name
        self._smart._push_log("ALIAS", f"{sid_key}={log_val}")
        return web.json_response({"id": sid_key, "alias": '' if removed else new_name})

class StatusView(HomeAssistantView):
    url = "/habridge/status"
    name = "habridge:status"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, admin_token: str, device_mgr: DeviceManager):
        self.hass = hass
        self._token = admin_token
        self._dm = device_mgr

    async def get(self, request):
        supplied = request.query.get('token')
        if supplied != self._token:
            return web.json_response({"error": "unauthorized"}, status=401)
        data = self.hass.data.get('habridge') or {}
        aliases = data.get('aliases') or {}
        settings = data.get('settings') or {}
        # Build area map quickly (non blocking: rely on existing state & registries if available)
        area_lookup = {}
        try:
            from homeassistant.helpers import area_registry, entity_registry, device_registry
            er = entity_registry.async_get(self.hass)
            ar = area_registry.async_get(self.hass)
            dr = device_registry.async_get(self.hass)
            for ent in er.entities.values():
                area_id = ent.area_id
                if not area_id and ent.device_id:
                    dev = dr.devices.get(ent.device_id)
                    if dev and dev.area_id:
                        area_id = dev.area_id
                if area_id and area_id in ar.areas:
                    area_lookup[ent.entity_id] = ar.areas[area_id].name
        except Exception:  # noqa: BLE001
            pass
        sync_devices = self._dm.build_sync()
        total = len(sync_devices)
        with_roomhint = sum(1 for d in sync_devices if 'roomHint' in d)
        with_alias = 0
        for d in sync_devices:
            names = d.get('name') or {}
            if names.get('name') and d.get('id') in aliases:
                with_alias += 1
        # area coverage (by entity list)
        all_entities = list(self._dm.list_entities())
        with_area = sum(1 for e in all_entities if e in area_lookup)
        stats = {}
        try:
            if hasattr(self._dm, 'latency_stats'):
                stats = self._dm.latency_stats() or {}
        except Exception:  # noqa: BLE001
            stats = {}
        return web.json_response({
            "devices": total,
            "withAlias": with_alias,
            "withArea": with_area,
            "roomHintApplied": with_roomhint,
            "roomHintEnabled": bool(settings.get('roomhint_enabled')),
            "cacheAgeMs": self._dm.sync_cache_age_ms(),
            "latency": stats,
        })
