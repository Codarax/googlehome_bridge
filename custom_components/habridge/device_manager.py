from __future__ import annotations
from typing import Dict, List
import re
from homeassistant.helpers.storage import Store

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

    def invalidate_sync_cache(self):
        self._sync_cache = None
        self._sync_cache_ts = None

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
                aliases = domain_data.get('aliases') or {}
        except Exception:  # noqa: BLE001
            aliases = {}
        area_lookup = None
        area_entity_hits = 0
        area_device_fallback = 0
        if roomhint_enabled:
            try:
                from homeassistant.helpers import area_registry as ar  # type: ignore
                from homeassistant.helpers import entity_registry as er  # type: ignore
                from homeassistant.helpers import device_registry as dr  # type: ignore
                areg = ar.async_get(self.hass)
                ereg = er.async_get(self.hass)
                dreg = dr.async_get(self.hass)
                area_lookup = {}
                for ent in ereg.entities.values():
                    area_name = None
                    if ent.area_id:
                        area = areg.async_get_area(ent.area_id)
                        if area and area.name:
                            area_name = area.name
                            area_entity_hits += 1
                    if not area_name and ent.device_id:
                        dev = dreg.devices.get(ent.device_id)
                        if dev and dev.area_id:
                            area = areg.async_get_area(dev.area_id)
                            if area and area.name:
                                area_name = area.name
                                area_device_fallback += 1
                    if area_name:
                        area_lookup[ent.entity_id] = area_name
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
                        # Detect color support: rgb_color, hs_color, color_temp
                        has_rgb = state.attributes.get("rgb_color") is not None or state.attributes.get("hs_color") is not None
                        has_ct = state.attributes.get("min_mireds") is not None and state.attributes.get("max_mireds") is not None
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
            else:
                # minimal trait assumption for missing state to keep device visible (fallbacks)
                if domain in ("switch", "light"):
                    traits.append("action.devices.traits.OnOff")
                elif domain == "climate":
                    traits.append("action.devices.traits.TemperatureSetting")
                elif domain == "sensor":
                    # unknown sensor type without state -> skip
                    continue
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

    def sync_cache_age_ms(self) -> int | None:
        import time
        if self._sync_cache_ts is None:
            return None
        return int((time.time() - self._sync_cache_ts) * 1000)

    async def execute(self, commands):
        results = []
        for cmd in commands:
            for device in cmd.get("devices", []):
                sid = device.get("id")
                if not sid:
                    continue
                eid = self.resolve_entity(sid) or sid
                state = self.hass.states.get(eid)
                if not state:
                    # state ontbreekt → log en skip
                    try:
                        self.hass.logger().info("habridge: EXECUTE skip %s no state", eid)
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                domain = state.domain
                for exec_cmd in cmd.get("execution", []):
                    ctype = exec_cmd.get("command")
                    params = exec_cmd.get("params", {})
                    if ctype == "action.devices.commands.OnOff" and domain in ("switch", "light"):
                        turn_on = params.get("on")
                        await self.hass.services.async_call(domain, f"turn_{'on' if turn_on else 'off'}", {"entity_id": eid}, blocking=False)
                        results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.OnOff" and domain == "climate":
                        turn_on = params.get("on")
                        if turn_on:
                            # Kies een werkbare modus (voorkeur huidige indien niet off, anders heat_cool/auto/heat)
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
                        results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.BrightnessAbsolute" and domain == "light" and "brightness" in params:
                        pct = params["brightness"]
                        bri = max(0, min(255, round(pct * 255 / 100)))
                        await self.hass.services.async_call("light", "turn_on", {"entity_id": eid, "brightness": bri}, blocking=False)
                        results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.ThermostatSetMode" and domain == "climate":
                        mode = params.get("thermostatMode")
                        # Map Google -> HA
                        inv_map = {
                            "off": "off",
                            "heat": "heat",
                            "cool": "cool",
                            "heatcool": "heat_cool",
                            "fan-only": "fan_only",
                            "dry": "dry",
                        }
                        ha_mode = inv_map.get(mode)
                        if ha_mode:
                            await self.hass.services.async_call("climate", "set_hvac_mode", {"entity_id": eid, "hvac_mode": ha_mode}, blocking=False)
                            results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.ThermostatTemperatureSetpoint" and domain == "climate":
                        temp = params.get("thermostatTemperatureSetpoint")
                        if temp is not None:
                            await self.hass.services.async_call("climate", "set_temperature", {"entity_id": eid, "temperature": temp}, blocking=False)
                            results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.ThermostatTemperatureSetRange" and domain == "climate":
                        low = params.get("thermostatTemperatureSetpointLow")
                        high = params.get("thermostatTemperatureSetpointHigh")
                        data = {"entity_id": eid}
                        if low is not None:
                            data["target_temp_low"] = low
                        if high is not None:
                            data["target_temp_high"] = high
                        await self.hass.services.async_call("climate", "set_temperature", data, blocking=False)
                        results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.SetFanSpeed" and domain == "climate":
                        fan_speed = params.get("fanSpeed")
                        if isinstance(fan_speed, str):
                            # strip optional prefix speed_
                            fm = fan_speed[6:] if fan_speed.lower().startswith("speed_") else fan_speed
                            await self.hass.services.async_call("climate", "set_fan_mode", {"entity_id": eid, "fan_mode": fm}, blocking=False)
                            results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.ColorAbsolute" and domain == "light":
                        color = params.get("color") or {}
                        data = {"entity_id": eid}
                        # spectrumRgb preferred
                        spec = color.get("spectrumRGB") or color.get("spectrumRgb")
                        temp_k = color.get("temperatureK") or color.get("temperaturek")
                        try:
                            if spec is not None:
                                # spec is integer 0xRRGGBB
                                if isinstance(spec, str) and spec.startswith("0x"):
                                    spec = int(spec, 16)
                                if isinstance(spec, int):
                                    r = (spec >> 16) & 0xFF
                                    g = (spec >> 8) & 0xFF
                                    b = spec & 0xFF
                                    data["rgb_color"] = [r, g, b]
                            elif temp_k is not None:
                                # convert Kelvin to mireds
                                if isinstance(temp_k, (int,float)) and temp_k > 0:
                                    mired = int(round(1000000 / float(temp_k)))
                                    data["color_temp"] = mired
                        except Exception:  # noqa: BLE001
                            pass
                        await self.hass.services.async_call("light", "turn_on", data, blocking=False)
                        results.append({"ids": [sid], "status": "SUCCESS"})
        return results

    def get_selection_map(self) -> Dict[str, bool]:
        return {eid: self._selections.get(eid, False) for eid in self.list_entities()}

    async def set_selection(self, entity_id: str, value: bool):
        self._selections[entity_id] = value
        await self.async_persist()
        self.invalidate_sync_cache()

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
            self.invalidate_sync_cache()
