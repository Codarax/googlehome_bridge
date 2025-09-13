from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    STORAGE_TOKENS,
    STORAGE_DEVICES,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_EXPOSE_DOMAINS,
)
from .token_manager import TokenManager
from .device_manager import DeviceManager
from .http import OAuthView, TokenView, SmartHomeView, HealthView, AdminPageView, DevicesView
import secrets
import logging

LOGGER = logging.getLogger(__name__)

PANEL_ID = "habridge_panel"

async def _async_setup_internal(hass: HomeAssistant, *, client_id: str, client_secret: str, expose_domains):
    # Reuse existing managers if already initialized (prevent duplicate registration)
    existing = hass.data.get(DOMAIN)
    if existing:
        return existing

    token_store = Store(hass, 1, STORAGE_TOKENS)
    device_store = Store(hass, 1, STORAGE_DEVICES)

    token_mgr = TokenManager(hass, token_store, client_secret)
    await token_mgr.async_load()
    device_mgr = DeviceManager(hass, device_store, expose_domains)
    await device_mgr.async_load()
    await device_mgr.auto_select_if_empty()

    hass.data[DOMAIN] = {
        "token_mgr": token_mgr,
        "device_mgr": device_mgr,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    hass.http.register_view(OAuthView(hass, token_mgr))
    hass.http.register_view(TokenView(hass, token_mgr))
    hass.http.register_view(SmartHomeView(hass, token_mgr, device_mgr, client_secret))
    admin_token = secrets.token_urlsafe(16)
    hass.data[DOMAIN]["admin_token"] = admin_token

    hass.http.register_view(HealthView())
    hass.http.register_view(AdminPageView(admin_token))
    hass.http.register_view(DevicesView(hass, device_mgr, admin_token))

    async def _register_panel(*_):
        if hass.data.get(PANEL_ID):
            LOGGER.debug("habridge: panel '%s' already registered, skipping", PANEL_ID)
            return
        try:
            # Import in executor to avoid blocking warning in event loop on some cores
            def _import_frontend():
                from homeassistant.components import frontend  # type: ignore
                return frontend
            frontend = await hass.async_add_executor_job(_import_frontend)
            LOGGER.debug("habridge: attempting sidebar panel registration")
            fn = getattr(frontend, "async_register_panel", None)
            if fn:
                fn(
                    hass,
                    component_name="iframe",
                    frontend_url_path=PANEL_ID,
                    sidebar_title="HA Bridge",
                    sidebar_icon="mdi:bridge",
                    config={"url": f"/habridge/admin?token={admin_token}"},
                    require_admin=True,
                )
                LOGGER.info("habridge: sidebar panel registered as '%s' -> /habridge/admin", PANEL_ID)
                hass.data[PANEL_ID] = True
                return
            built_in = getattr(frontend, "async_register_built_in_panel", None)
            if built_in:
                built_in(
                    hass,
                    component_name="iframe",
                    sidebar_title="HA Bridge",
                    sidebar_icon="mdi:bridge",
                    frontend_url_path=PANEL_ID,
                    config={"url": f"/habridge/admin?token={admin_token}"},
                    require_admin=True,
                )
                LOGGER.info("habridge: sidebar built_in panel registered '%s'", PANEL_ID)
                hass.data[PANEL_ID] = True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("habridge: failed to register panel (%s). Admin page still at /habridge/admin", exc)

    if hass.is_running:
        hass.async_create_task(_register_panel())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_panel)
    return hass.data[DOMAIN]

async def async_setup(hass: HomeAssistant, config: ConfigType):
    # Backwards compatibility: allow (temporary) YAML for early adopters
    conf = config.get(DOMAIN, {})
    if conf:
        client_id = conf.get(CONF_CLIENT_ID, "client-id")
        client_secret = conf.get(CONF_CLIENT_SECRET, "client-secret")
        expose_domains = conf.get(CONF_EXPOSE_DOMAINS, []) or None
        await _async_setup_internal(hass, client_id=client_id, client_secret=client_secret, expose_domains=expose_domains)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = entry.data
    client_id = data.get(CONF_CLIENT_ID, "client-id")
    client_secret = data.get(CONF_CLIENT_SECRET, "client-secret")
    # Options override expose domains if present
    expose_raw = entry.options.get(CONF_EXPOSE_DOMAINS) if entry.options else data.get(CONF_EXPOSE_DOMAINS)
    if isinstance(expose_raw, str):
        expose_domains = [d.strip() for d in expose_raw.split(',') if d.strip()]
    else:
        expose_domains = expose_raw
    await _async_setup_internal(hass, client_id=client_id, client_secret=client_secret, expose_domains=expose_domains)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    # For simplicity we do not tear down views; just refresh device exposure domain list
    stored = hass.data.get(DOMAIN)
    if not stored:
        return
    device_mgr = stored.get("device_mgr")
    if device_mgr:
        new_raw = entry.options.get(CONF_EXPOSE_DOMAINS) if entry.options else entry.data.get(CONF_EXPOSE_DOMAINS)
        if isinstance(new_raw, str):
            new_domains = [d.strip() for d in new_raw.split(',') if d.strip()]
        else:
            new_domains = new_raw
        if new_domains:
            device_mgr.expose_domains = new_domains
            await device_mgr.auto_select_if_empty()
