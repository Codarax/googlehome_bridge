from __future__ import annotations
from typing import Dict, List
import re
try:
    from homeassistant.helpers.storage import Store  # type: ignore
except Exception:  # noqa: BLE001
    # Dev / lint fallback: minimal Store stub so type checkers stop complaining outside HA runtime
    class Store:  # type: ignore
        def __init__(self, hass=None, version=1, key=""):
            self._data = None
        async def async_load(self):  # noqa: D401
            return self._data
        async def async_save(self, data):  # noqa: D401
            self._data = data

from .const import DEFAULT_EXPOSE, STORAGE_IDMAP

# HA Core >= 2025.x heeft ATTR_BRIGHTNESS mogelijk niet meer in homeassistant.const.
# We gebruiken een lokale fallback string zodat de integratie niet breekt.
ATTR_BRIGHTNESS = "brightness"

SUPPORTED_DOMAINS = {
    "switch": ["action.devices.types.SWITCH"],
    "light": ["action.devices.types.LIGHT"],
    # Voor climate kiezen we standaard THERMOSTAT; als fan_modes aanwezig zijn gebruiken we AC_UNIT dynamisch.
    "climate": ["action.devices.types.THERMOSTAT", "action.devices.types.AC_UNIT"],
    "sensor": ["action.devices.types.SENSOR"],
    # Scenes & scripts stateless → Google SCENE type + Scene trait (activate only)
    "scene": ["action.devices.types.SCENE"],
    "script": ["action.devices.types.SCENE"],
}

def _slugify_entity(eid: str) -> str:
    if '.' in eid:
        domain, obj = eid.split('.', 1)
        base = f"{domain}_{obj}"
    else:
        base = eid
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", base)
    return base[:50].strip('_')

class DeviceManager:
    def __init__(self, hass, store, expose_domains):
        self.hass = hass
        self.store = store
        self.expose_domains = expose_domains or DEFAULT_EXPOSE
        self._selections: Dict[str, bool] = {}
        self._idmap_store: Store | None = None
        self._stable_to_entity: Dict[str, str] = {}
        self._entity_to_stable: Dict[str, str] = {}
        # SYNC cache
        self._sync_cache: list[dict] | None = None
        self._sync_cache_ts: float | None = None
        self._sync_cache_ttl = 8.0  # seconds
        # Debounce invalidation
        self._invalidate_handle = None
        self._invalidate_delay = 1.0
        # Latency metrics (simple ring buffers)
        self._lat_sync = []  # ms samples
        self._lat_exec = []
        self._lat_query = []
        self._lat_max = 100
        # Event loop lag samples
        self._lag_samples = []  # ms
        self._lag_max = 120
        self._lag_task = None
        # Per-device EXECUTE timing (recent durations ms)
        self._exec_device_timings = {}
        self._exec_device_last = {}

    def start_metrics(self):
        self._ensure_exec_metrics()
        if self._lag_task is None:
            self._lag_task = self.hass.loop.create_task(self._sample_loop_lag())

    async def _sample_loop_lag(self):
        import asyncio, time
        interval = 1.0
        last = time.perf_counter()
        while True:
            await asyncio.sleep(interval)
            now = time.perf_counter()
            drift = (now - last - interval) * 1000.0
            last = now
            if drift < 0:
                drift = 0
            self._lag_samples.append(drift)
            if len(self._lag_samples) > self._lag_max:
                self._lag_samples.pop(0)

    def record_latency(self, kind: str, ms: float):
        buf = None
        if kind == 'sync':
            buf = self._lat_sync
        elif kind == 'exec':
            buf = self._lat_exec
        elif kind == 'query':
            buf = self._lat_query
        if buf is not None:
            buf.append(ms)
            if len(buf) > self._lat_max:
                buf.pop(0)

    def latency_stats(self):
        def stats(arr):
            if not arr:
                return {"count":0}
            s = sorted(arr)
            import math
            def pct(p):
                if not s:
                    return None
                idx = int(math.ceil(p/100.0 * len(s))) -1
                idx = max(0, min(idx, len(s)-1))
                return s[idx]
            return {"count":len(s),"p50":pct(50),"p95":pct(95),"max":s[-1]}
        return {
            "sync": stats(self._lat_sync),
            "execute": stats(self._lat_exec),
            "query": stats(self._lat_query),
            "loopLagMs": stats(self._lag_samples),
        }

    def invalidate_sync_cache(self):
        # Immediate (legacy) path kept for direct forcing
        self._sync_cache = None
        self._sync_cache_ts = None

    def debounce_invalidate(self):
        # Schedule invalidate after short delay; collapse bursts
        import asyncio
        def do():
            self.invalidate_sync_cache()
        if self._invalidate_handle:
            self._invalidate_handle.cancel()
        async def later():
            try:
                await asyncio.sleep(self._invalidate_delay)
                do()
            except Exception:  # noqa: BLE001
                pass
        self._invalidate_handle = self.hass.loop.create_task(later())

    async def async_load(self):
        data = await self.store.async_load()
        if data:
            self._selections = data
        self._idmap_store = Store(self.hass, 1, STORAGE_IDMAP)
        iddata = await self._idmap_store.async_load()
        if iddata:
            self._stable_to_entity = iddata.get("entities", {})
            self._entity_to_stable = iddata.get("reverse", {})
        else:
            self._stable_to_entity = {}
            self._entity_to_stable = {}

    async def async_persist(self):
        await self.store.async_save(self._selections)
        if self._idmap_store:
            await self._idmap_store.async_save({"entities": self._stable_to_entity, "reverse": self._entity_to_stable})

    def list_entities(self) -> List[str]:
        # Prefer runtime states; fallback to entity registry for domains that may not yet have a state
        seen = set()
        entities = []
        for e in self.hass.states.async_all():
            if e.domain in self.expose_domains:
                entities.append(e.entity_id)
                seen.add(e.entity_id)
        try:
            # entity_registry gives us entities that might not have states yet (e.g. some climate integrations on startup)
            from homeassistant.helpers import entity_registry as er  # type: ignore
            reg = er.async_get(self.hass)
            for ent in reg.entities.values():
                if ent.domain in self.expose_domains and ent.entity_id not in seen:
                    entities.append(ent.entity_id)
        except Exception:  # noqa: BLE001
            pass
        return entities

    def selected(self) -> List[str]:
        return [eid for eid, v in self._selections.items() if v]

    async def auto_select_if_empty(self, limit=50):
        if not self._selections:
            for eid in self.list_entities()[:limit]:
                self._selections[eid] = True
            await self.async_persist()
        # ensure mapping for selected
        for eid in self.selected():
            self._ensure_mapping(eid)
        await self.async_persist()

    def _ensure_mapping(self, eid: str) -> str:
        if eid in self._entity_to_stable:
            return self._entity_to_stable[eid]
        base = _slugify_entity(eid)
        candidate = base
        i = 1
        while candidate in self._stable_to_entity and self._stable_to_entity[candidate] != eid:
            i += 1
            candidate = f"{base}_{i}"
        self._stable_to_entity[candidate] = eid
        self._entity_to_stable[eid] = candidate
        return candidate

    def stable_id(self, eid: str) -> str:
        return self._entity_to_stable.get(eid) or self._ensure_mapping(eid)

    def resolve_entity(self, sid: str) -> str | None:
        return self._stable_to_entity.get(sid)

    def build_sync(self):
        # Return cached result if still fresh
        import time
        if self._sync_cache is not None and self._sync_cache_ts is not None:
            if (time.time() - self._sync_cache_ts) < self._sync_cache_ttl:
                return self._sync_cache
        devices = []
        # Read global settings for roomHint toggle if available
        settings = {}
        try:
            domain_data = self.hass.data.get('habridge')
            if domain_data:
                settings = domain_data.get('settings') or {}
        except Exception:  # noqa: BLE001
            settings = {}
        roomhint_enabled = bool(settings.get('roomhint_enabled'))
        aliases = {}
        try:
            if domain_data:
                aliases_ref = domain_data.get('aliases')
                if aliases_ref is None:
                    aliases_ref = {}
                    domain_data['aliases'] = aliases_ref
                aliases = aliases_ref
        except Exception:  # noqa: BLE001
            aliases = {}
        area_lookup = None
        area_entity_hits = 0
        area_device_fallback = 0
        if roomhint_enabled:
            try:
                area_lookup, stats = self.compute_area_lookup()
                area_entity_hits = stats.get('entity_hits', 0)
                area_device_fallback = stats.get('device_fallback', 0)
            except Exception:  # noqa: BLE001
                area_lookup = None
        for eid in self.selected():
            state = self.hass.states.get(eid)
            # Allow inclusion even if state not yet loaded (e.g. after restart) so Google keeps device
            domain = state.domain if state else eid.split('.')[0]
            if domain not in SUPPORTED_DOMAINS:
                continue
            sid = self.stable_id(eid)
            traits = []
            attrs = {}
            if state:  # derive traits only if we have attributes
                if domain in ("switch", "light"):
                    traits.append("action.devices.traits.OnOff")
                    if domain == "light" and state.attributes.get(ATTR_BRIGHTNESS) is not None:
                        traits.append("action.devices.traits.Brightness")
                    if domain == "light":
                        # Detect color support: prefer capability list over current state attributes
                        supported_modes = state.attributes.get("supported_color_modes")
                        if isinstance(supported_modes, (list, set)):
                            sm_lower = {str(m).lower() for m in supported_modes}
                        else:
                            sm_lower = set()
                        # If light supports hs/rgb/xy modes we expose color even if currently off (attributes absent)
                        has_rgb = any(m in sm_lower for m in ("hs", "rgb", "xy", "rgbw", "rgbww")) or \
                                  state.attributes.get("rgb_color") is not None or state.attributes.get("hs_color") is not None
                        # Color temperature via supported modes or mired range
                        has_ct = ("color_temp" in sm_lower) or (state.attributes.get("min_mireds") is not None and state.attributes.get("max_mireds") is not None)
                        if has_rgb or has_ct:
                            traits.append("action.devices.traits.ColorSetting")
                            cattrs = {}
                            # Support both RGB and Temperature
                            if has_rgb and has_ct:
                                cattrs["colorModel"] = "rgb"
                                # convert mireds to Kelvin range (inverse)
                                try:
                                    min_m = state.attributes.get("min_mireds")
                                    max_m = state.attributes.get("max_mireds")
                                    if isinstance(min_m, (int,float)) and isinstance(max_m,(int,float)) and min_m>0 and max_m>0:
                                        min_k = int(round(1000000/max_m))
                                        max_k = int(round(1000000/min_m))
                                        cattrs["temperatureMinK"] = min_k
                                        cattrs["temperatureMaxK"] = max_k
                                except Exception:  # noqa: BLE001
                                    pass
                            elif has_rgb:
                                cattrs["colorModel"] = "rgb"
                            elif has_ct:
                                # Only temperature
                                try:
                                    min_m = state.attributes.get("min_mireds")
                                    max_m = state.attributes.get("max_mireds")
                                    if isinstance(min_m, (int,float)) and isinstance(max_m,(int,float)) and min_m>0 and max_m>0:
                                        min_k = int(round(1000000/max_m))
                                        max_k = int(round(1000000/min_m))
                                        cattrs["temperatureMinK"] = min_k
                                        cattrs["temperatureMaxK"] = max_k
                                except Exception:  # noqa: BLE001
                                    pass
                            # merge with existing attrs (if any)
                            if cattrs:
                                if attrs:
                                    attrs.update(cattrs)
                                else:
                                    attrs = cattrs
                elif domain == "climate":
                    # Temperature + optioneel OnOff + FanSpeed
                    traits.append("action.devices.traits.TemperatureSetting")
                    traits.append("action.devices.traits.OnOff")
                    hvac_modes = state.attributes.get("hvac_modes", [])
                    fan_modes = state.attributes.get("fan_modes")
                    if fan_modes:
                        traits.append("action.devices.traits.FanSpeed")
                    mode_map = {
                        "off": "off",
                        "heat": "heat",
                        "cool": "cool",
                        "heat_cool": "heatcool",
                        "auto": "heatcool",
                        "fan_only": "fan-only",
                        "dry": "dry",
                    }
                    g_modes = []
                    for m in hvac_modes:
                        gm = mode_map.get(m)
                        if gm and gm not in g_modes:
                            g_modes.append(gm)
                    if not g_modes:
                        g_modes = ["off", "heat", "cool"]
                    unit = getattr(self.hass.config.units, 'temperature_unit', 'C')
                    attrs = {
                        "availableThermostatModes": ",".join(g_modes),
                        "thermostatTemperatureUnit": unit,
                    }
                    if fan_modes:
                        speeds = []
                        for fm in fan_modes:
                            sname = f"speed_{fm.lower()}"
                            speeds.append({
                                "speed_name": sname,
                                "speed_values": [{"speed_synonym": [fm], "lang": "en"}]
                            })
                        if speeds:
                            attrs["availableFanSpeeds"] = {"speeds": speeds, "ordered": True}
                            attrs["reversible"] = False
                elif domain == "sensor":
                    device_class = state.attributes.get("device_class") if state else None
                    if device_class == "temperature":
                        traits.append("action.devices.traits.TemperatureSetting")
                        unit = getattr(self.hass.config.units, 'temperature_unit', 'C')
                        attrs = {
                            "availableThermostatModes": "off",
                            "thermostatTemperatureUnit": unit,
                        }
                    elif device_class == "humidity":
                        traits.append("action.devices.traits.HumiditySetting")
                        attrs = {}
                    else:
                        # if state exists but unsupported sensor, skip
                        if state:
                            continue
                elif domain in ("scene", "script"):
                    # Stateless scene activation
                    traits.append("action.devices.traits.Scene")
                    attrs = {"sceneReversible": False}
            else:
                # minimal trait assumption for missing state to keep device visible (fallbacks)
                if domain in ("switch", "light"):
                    traits.append("action.devices.traits.OnOff")
                elif domain == "climate":
                    traits.append("action.devices.traits.TemperatureSetting")
                elif domain == "sensor":
                    # unknown sensor type without state -> skip
                    continue
                elif domain in ("scene", "script"):
                    traits.append("action.devices.traits.Scene")
                    attrs = {"sceneReversible": False}
            name = state.name if state and getattr(state, 'name', None) else eid
            # Allow alias override by stable id or original entity id
            alias = aliases.get(sid) or aliases.get(eid)
            if alias:
                name = alias
            # Device type switch voor climate als fan_modes (met FanSpeed trait) aanwezig → AC_UNIT gebruiken
            dtype = SUPPORTED_DOMAINS[domain][0]
            if domain == "climate" and state and state.attributes.get("fan_modes"):
                # tweede element in lijst is AC_UNIT
                if len(SUPPORTED_DOMAINS["climate"]) > 1:
                    dtype = SUPPORTED_DOMAINS["climate"][1]
            if domain in ("scene", "script"):
                # Use SCENE device type always
                dtype = SUPPORTED_DOMAINS[domain][0]
            dev = {
                "id": sid,
                "type": dtype,
                "traits": traits,
                "name": {"name": name},
                "willReportState": False,
                "otherDeviceIds": [{"deviceId": eid}],
            }
            if roomhint_enabled and area_lookup and eid in area_lookup:
                dev["roomHint"] = area_lookup[eid]
            if attrs:
                dev["attributes"] = attrs
            devices.append(dev)
        # store cache
        self._sync_cache = devices
        try:
            import time as _t
            self._sync_cache_ts = _t.time()
        except Exception:  # noqa: BLE001
            self._sync_cache_ts = None
        # Lightweight debug log (avoid large payload) – only when cache freshly built
        try:
            import logging as _lg
            lg = _lg.getLogger(__name__)
            lg.debug("habridge: build_sync devices=%d roomHint=%s area_entity_hits=%d area_device_fb=%d aliases=%d", len(devices), roomhint_enabled, area_entity_hits, area_device_fallback, sum(1 for d in devices if 'name' in d and d['name'].get('name')))
        except Exception:  # noqa: BLE001
            pass
        return devices

    def compute_area_lookup(self, debug: bool = False):
        """Return mapping of entity_id -> area name with stats.

        If debug True, also include source map entity_id -> 'entity'|'device'.
        """
        lookup = {}
        stats = {"entity_hits": 0, "device_fallback": 0}
        source_map = {} if debug else None
        try:
            from homeassistant.helpers import area_registry as ar  # type: ignore
            from homeassistant.helpers import entity_registry as er  # type: ignore
            from homeassistant.helpers import device_registry as dr  # type: ignore
            areg = ar.async_get(self.hass)
            ereg = er.async_get(self.hass)
            dreg = dr.async_get(self.hass)
            for ent in ereg.entities.values():
                area_name = None
                used_source = None
                if ent.area_id:
                    area = areg.async_get_area(ent.area_id)
                    if area and area.name:
                        area_name = area.name
                        stats["entity_hits"] += 1
                        used_source = 'entity'
                if not area_name and ent.device_id:
                    dev = dreg.devices.get(ent.device_id)
                    if dev and dev.area_id:
                        area = areg.async_get_area(dev.area_id)
                        if area and area.name:
                            area_name = area.name
                            stats["device_fallback"] += 1
                            used_source = 'device'
                if area_name:
                    lookup[ent.entity_id] = area_name
                    if source_map is not None:
                        source_map[ent.entity_id] = used_source or 'unknown'
        except Exception:  # noqa: BLE001
            return {}, stats if not debug else ({}, stats, {})
        if debug:
            return lookup, stats, source_map or {}
        return lookup, stats

    def sync_cache_age_ms(self) -> int | None:
        import time
        if self._sync_cache_ts is None:
            return None
        return int((time.time() - self._sync_cache_ts) * 1000)

    async def execute(self, commands):
        import asyncio
        self._ensure_exec_metrics()
        results = []
        service_calls = []  # list of (sid, coroutine)
        sid_tracking = []   # parallel list of stable id for each coroutine
        for cmd in commands:
            exec_list = cmd.get("execution", [])
            devices = cmd.get("devices", [])
            if not isinstance(exec_list, list) or not isinstance(devices, list):
                continue
            for device in devices:
                sid = device.get("id") if isinstance(device, dict) else None
                if not sid:
                    continue
                eid = self.resolve_entity(sid) or sid
                state = self.hass.states.get(eid)
                if not state:
                    continue
                domain = state.domain
                for exec_cmd in exec_list:
                    if not isinstance(exec_cmd, dict):
                        continue
                    ctype = exec_cmd.get("command")
                    params = exec_cmd.get("params", {}) or {}
                    # Build coroutine per action
                    if ctype == "action.devices.commands.OnOff" and domain in ("switch", "light"):
                        turn_on = params.get("on")
                        async def _do(eid=eid, domain=domain, turn_on=turn_on):
                            await self.hass.services.async_call(domain, f"turn_{'on' if turn_on else 'off'}", {"entity_id": eid}, blocking=True)
                        service_calls.append((sid, _do()))
                        sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.OnOff" and domain == "climate":
                        turn_on = params.get("on")
                        async def _climate_toggle(eid=eid, state=state, turn_on=turn_on):
                            if turn_on:
                                cur = state.state
                                if cur and cur not in ("off", "unavailable", "unknown"):
                                    next_mode = cur
                                else:
                                    pref = ["heat_cool", "auto", "cool", "heat"]
                                    hvac_modes = state.attributes.get("hvac_modes", [])
                                    next_mode = None
                                    for m in pref:
                                        if m in hvac_modes:
                                            next_mode = m
                                            break
                                    if not next_mode:
                                        next_mode = "heat"
                                await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": eid, "hvac_mode": next_mode}, blocking=False)
                            else:
                                await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": eid, "hvac_mode": "off"}, blocking=False)
                        service_calls.append((sid, _climate_toggle()))
                        sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.BrightnessAbsolute" and domain == "light" and "brightness" in params:
                        pct = params["brightness"]
                        bri = max(0, min(255, round(pct * 255 / 100)))
                        async def _do_bri(eid=eid, bri=bri):
                            await self.hass.services.async_call("light", "turn_on", {"entity_id": eid, "brightness": bri}, blocking=True)
                        service_calls.append((sid, _do_bri()))
                        sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.ThermostatSetMode" and domain == "climate":
                        mode = params.get("thermostatMode")
                        inv_map = {"off": "off", "heat": "heat", "cool": "cool", "heatcool": "heat_cool", "fan-only": "fan_only", "dry": "dry"}
                        ha_mode = inv_map.get(mode)
                        if ha_mode:
                            async def _do_mode(eid=eid, ha_mode=ha_mode):
                                await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": eid, "hvac_mode": ha_mode}, blocking=True)
                            service_calls.append((sid, _do_mode()))
                            sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.ThermostatTemperatureSetpoint" and domain == "climate":
                        temp = params.get("thermostatTemperatureSetpoint")
                        if temp is not None:
                            async def _do_temp(eid=eid, temp=temp):
                                await self.hass.services.async_call("climate", "set_temperature", {"entity_id": eid, "temperature": temp}, blocking=True)
                            service_calls.append((sid, _do_temp()))
                            sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.ThermostatTemperatureSetRange" and domain == "climate":
                        low = params.get("thermostatTemperatureSetpointLow")
                        high = params.get("thermostatTemperatureSetpointHigh")
                        data = {"entity_id": eid}
                        if low is not None:
                            data["target_temp_low"] = low
                        if high is not None:
                            data["target_temp_high"] = high
                        async def _do_range(eid=eid, data=data):
                            await self.hass.services.async_call("climate", "set_temperature", data, blocking=True)
                        service_calls.append((sid, _do_range()))
                        sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.SetFanSpeed" and domain == "climate":
                        fan_speed = params.get("fanSpeed")
                        if isinstance(fan_speed, str):
                            fm = fan_speed[6:] if fan_speed.lower().startswith("speed_") else fan_speed
                            async def _do_fan(eid=eid, fm=fm):
                                await self.hass.services.async_call("climate", "set_fan_mode", {"entity_id": eid, "fan_mode": fm}, blocking=True)
                            service_calls.append((sid, _do_fan()))
                            sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.ColorAbsolute" and domain == "light":
                        color = params.get("color") or {}
                        spec = color.get("spectrumRGB") or color.get("spectrumRgb")
                        temp_k = color.get("temperatureK") or color.get("temperaturek")
                        async def _apply_color(eid=eid, spec=spec, temp_k=temp_k):
                            data = {"entity_id": eid}
                            try:
                                if spec is not None:
                                    if isinstance(spec, str):
                                        if spec.startswith("0x"):
                                            spec_int = int(spec, 16)
                                        else:
                                            spec_int = int(spec)
                                    else:
                                        spec_int = spec
                                    if isinstance(spec_int, int):
                                        r = (spec_int >> 16) & 0xFF
                                        g = (spec_int >> 8) & 0xFF
                                        b = spec_int & 0xFF
                                        data["rgb_color"] = [r, g, b]
                                elif temp_k is not None and isinstance(temp_k, (int,float)) and temp_k>0:
                                    mired = int(round(1000000/float(temp_k)))
                                    data["color_temp"] = mired
                            except Exception:
                                pass
                            await self.hass.services.async_call("light", "turn_on", data, blocking=False)
                        service_calls.append((sid, _apply_color()))
                        sid_tracking.append(sid)
                    elif ctype == "action.devices.commands.ActivateScene" and domain in ("scene", "script"):
                        deactivate = params.get("deactivate")
                        async def _activate_scene(eid=eid, domain=domain, deactivate=deactivate):
                            if not deactivate:
                                if domain == "script":
                                    try:
                                        if self.hass.services.has_service("script", "turn_on"):
                                            await self.hass.services.async_call("script", "turn_on", {"entity_id": eid}, blocking=False)
                                        elif self.hass.services.has_service("script", "run"):
                                            await self.hass.services.async_call("script", "run", {"entity_id": eid}, blocking=False)
                                    except Exception:
                                        try:
                                            await self.hass.services.async_call("script", "run", {"entity_id": eid}, blocking=False)
                                        except Exception:
                                            pass
                                else:
                                    await self.hass.services.async_call("scene", "turn_on", {"entity_id": eid}, blocking=False)
                        service_calls.append((sid, _activate_scene()))
                        sid_tracking.append(sid)
        # Execute all service calls concurrently
        if service_calls:
            import time
            tasks = []
            for sid, coro in service_calls:
                async def _timed(sid=sid, coro=coro):
                    t0 = time.perf_counter()
                    try:
                        await coro
                    except Exception:  # noqa: BLE001
                        pass
                    dt = int((time.perf_counter()-t0)*1000)
                    lst = self._exec_device_timings.setdefault(sid, [])
                    lst.append(dt)
                    if len(lst) > 20:
                        lst.pop(0)
                    self._exec_device_last[sid] = dt
                tasks.append(_timed())
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:  # noqa: BLE001
                pass
        # Build success results per sid (deduplicate)
        seen = set()
        for sid in sid_tracking:
            if sid not in seen:
                results.append({"ids": [sid], "status": "SUCCESS"})
                seen.add(sid)
        return results

    def exec_device_stats(self):
        """Return per-device execute timing stats (last, p50, p95, max)."""
        import math
        self._ensure_exec_metrics()
        out = {}
        for sid, arr in self._exec_device_timings.items():
            if not arr:
                continue
            s = sorted(arr)
            def pct(p):
                idx = int(math.ceil(p/100.0 * len(s))) - 1
                if idx < 0: idx = 0
                if idx >= len(s): idx = len(s)-1
                return s[idx]
            out[sid] = {
                "count": len(s),
                "last": self._exec_device_last.get(sid),
                "p50": pct(50),
                "p95": pct(95),
                "max": s[-1],
            }
        return out

    def _ensure_exec_metrics(self):
        # Defensive: create attrs if missing (older cached module / partial deploy)
        if not hasattr(self, '_exec_device_timings'):
            self._exec_device_timings = {}
        if not hasattr(self, '_exec_device_last'):
            self._exec_device_last = {}

    def get_selection_map(self) -> Dict[str, bool]:
        return {eid: self._selections.get(eid, False) for eid in self.list_entities()}

    async def set_selection(self, entity_id: str, value: bool):
        self._selections[entity_id] = value
        await self.async_persist()
        self.debounce_invalidate()

    async def bulk_update(self, updates: Dict[str, bool]):
        changed = False
        current_entities = set(self.list_entities())
        for eid, val in updates.items():
            # Allow setting even if entity not yet in current_entities (race with HA startup)
            if self._selections.get(eid) != val:
                self._selections[eid] = val
                changed = True
            # ensure stable mapping early (so SYNC won't drop it)
            if eid in current_entities:
                self._ensure_mapping(eid)
        if changed:
            await self.async_persist()
            self.debounce_invalidate()
