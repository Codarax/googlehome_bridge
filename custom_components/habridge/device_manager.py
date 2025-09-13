from __future__ import annotations
from typing import Dict, List
import re
from homeassistant.const import ATTR_BRIGHTNESS
from homeassistant.helpers.storage import Store

from .const import DEFAULT_EXPOSE, STORAGE_IDMAP

SUPPORTED_DOMAINS = {"switch": ["action.devices.types.SWITCH"], "light": ["action.devices.types.LIGHT"]}

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
        return [e.entity_id for e in self.hass.states.async_all() if e.domain in self.expose_domains]

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
        devices = []
        for eid in self.selected():
            state = self.hass.states.get(eid)
            if not state:
                continue
            domain = state.domain
            if domain not in SUPPORTED_DOMAINS:
                continue
            sid = self.stable_id(eid)
            traits = ["action.devices.traits.OnOff"]
            if domain == "light" and state.attributes.get(ATTR_BRIGHTNESS) is not None:
                traits.append("action.devices.traits.Brightness")
            dev = {
                "id": sid,
                "type": SUPPORTED_DOMAINS[domain][0],
                "traits": traits,
                "name": {"name": state.name or eid},
                "willReportState": False,
                "otherDeviceIds": [{"deviceId": eid}],
            }
            devices.append(dev)
        return devices

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
                    continue
                domain = state.domain
                for exec_cmd in cmd.get("execution", []):
                    ctype = exec_cmd.get("command")
                    params = exec_cmd.get("params", {})
                    if ctype == "action.devices.commands.OnOff" and domain in ("switch", "light"):
                        turn_on = params.get("on")
                        await self.hass.services.async_call(domain, f"turn_{'on' if turn_on else 'off'}", {"entity_id": eid}, blocking=False)
                        results.append({"ids": [sid], "status": "SUCCESS"})
                    elif ctype == "action.devices.commands.BrightnessAbsolute" and domain == "light" and "brightness" in params:
                        pct = params["brightness"]
                        bri = max(0, min(255, round(pct * 255 / 100)))
                        await self.hass.services.async_call("light", "turn_on", {"entity_id": eid, "brightness": bri}, blocking=False)
                        results.append({"ids": [sid], "status": "SUCCESS"})
        return results

    def get_selection_map(self) -> Dict[str, bool]:
        return {eid: self._selections.get(eid, False) for eid in self.list_entities()}

    async def set_selection(self, entity_id: str, value: bool):
        self._selections[entity_id] = value
        await self.async_persist()

    async def bulk_update(self, updates: Dict[str, bool]):
        changed = False
        for eid, val in updates.items():
            if eid in self.list_entities():
                if self._selections.get(eid) != val:
                    self._selections[eid] = val
                    changed = True
        if changed:
            await self.async_persist()
