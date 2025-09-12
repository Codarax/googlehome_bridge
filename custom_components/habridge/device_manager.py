from __future__ import annotations
from typing import Dict, List

from .const import DEFAULT_EXPOSE

SUPPORTED_DOMAINS = {"switch": ["action.devices.types.SWITCH"], "light": ["action.devices.types.LIGHT"]}

class DeviceManager:
    def __init__(self, hass, store, expose_domains):
        self.hass = hass
        self.store = store
        self.expose_domains = expose_domains or DEFAULT_EXPOSE
        self._selections: Dict[str, bool] = {}

    async def async_load(self):
        data = await self.store.async_load()
        if data:
            self._selections = data

    async def async_persist(self):
        await self.store.async_save(self._selections)

    def list_entities(self) -> List[str]:
        return [e.entity_id for e in self.hass.states.async_all() if e.domain in self.expose_domains]

    def selected(self) -> List[str]:
        return [eid for eid, v in self._selections.items() if v]

    async def auto_select_if_empty(self, limit=50):
        if not self._selections:
            for eid in self.list_entities()[:limit]:
                self._selections[eid] = True
            await self.async_persist()

    def build_sync(self):
        devices = []
        for eid in self.selected():
            state = self.hass.states.get(eid)
            if not state:
                continue
            domain = state.domain
            if domain not in SUPPORTED_DOMAINS:
                continue
            devices.append({
                "id": eid,
                "type": SUPPORTED_DOMAINS[domain][0],
                "traits": ["action.devices.traits.OnOff"],
                "name": {"name": state.name or eid},
                "willReportState": False,
            })
        return devices

    async def execute(self, commands):
        results = []
        for cmd in commands:
            for device in cmd.get("devices", []):
                eid = device.get("id")
                if not eid:
                    continue
                state = self.hass.states.get(eid)
                if not state:
                    continue
                domain = state.domain
                if domain in ("switch", "light"):
                    turn_on = any(c.get("command") == "action.devices.commands.OnOff" and c.get("params", {}).get("on") for c in [cmd])
                    await self.hass.services.async_call(domain, f"turn_{'on' if turn_on else 'off'}", {"entity_id": eid}, blocking=False)
                    results.append({"ids": [eid], "status": "SUCCESS"})
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
