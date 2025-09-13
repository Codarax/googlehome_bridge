# Changelog

## [2.3.4] - 2025-09-13
### Added
- Settings optie: Background auto updates toggle (devices + logs) met respect voor verborgen tabbladen (document.hidden).
- Logs UI: kolommen (#, datum, tijd, requestId, intent, detail) + requestId logging.
### Changed
- Devices refresh overschrijft selectie niet; optimistisch pending mechanisme.
### Fixed
- Toggle flikkeren door race met refresh opgelost via `_pendingSelections` merge.
- Ontbrekende climate entity (zoals `climate.air_conditioner_4ed9e7_air_conditioner`) nu zichtbaar door entity_registry fallback en inclusion zonder state.
- SYNC logging bevat nu requestId voor betere traceability.
### Notes
- Max 50 log items (rolling); kan later configurabel worden.
- Background updates pauzeren automatisch wanneer tab niet actief is.

## [2.3.3] - 2025-09-13
### Fixed
- Admin UI: toggles bleven niet visueel aan door refresh overwrite; vorige selectie wordt nu gemerged.
- SYNC: devices zonder (nog) geladen state werden geskipt → veroorzaakt verdwijnen of pas later tonen in Google Home; nu minimale traits zodat Google ze behoudt.
- Migratie: bestaande installaties met oude default (alleen switch/light) krijgen automatisch climate & sensor toegevoegd tenzij expliciet aangepast.
### Notes
- Overwegen om later een configurabele optie toe te voegen voor het includen van entities zonder state.

## [2.3.2] - 2025-09-13
### Added
- Admin UI: Value kolom met actuele status (state / brightness %, climate mode + temp, sensor waarde).
- Admin UI: Toggle switches i.p.v. standaard checkboxes voor selectie.
- Auto-refresh: Devices (10s) & Logs (5s) alleen wanneer betreffende tab actief is.
### Changed
- Uitgebreidere search: zoekt nu in stable_id, entity_id, naam, domein en value.
- Tabel styling: sticky toolbar, afwisselende rij achtergrond, compactere layout.
- Default expose domains uitgebreid (switch, light, climate, sensor) voor nieuwe installaties.
### Fixed
- Logs view correcte registratie (geen lege lijst meer bij nieuwe sessies).
### Notes
- Stable IDs + QUERY key alignment uit eerdere versie blijven intact.
- Refresh interval is bewust licht gehouden om belasting te minimaliseren; pas aan indien nodig in toekomstige versie.

## [2.3.1] - 2025-09-13
### Fixed
- Import error: verwijderde `ATTR_BRIGHTNESS` import uit `homeassistant.const` vervangen door lokale fallback string om compatibiliteit met nieuwere HA versies te behouden.


## [2.3.0] - 2025-09-13
### Added
- Temperatuur & luchtvochtigheid sensoren (device_class temperature / humidity) exposed als Google SENSOR devices.
- Temperatuur sensoren: TemperatureSetting (read-only) met alleen ambient & mode off.
- Luchtvochtigheid sensoren: HumiditySetting (read-only) met ambient % waarde.
### Changed
- QUERY gebruikt nu stabiele IDs als keys (in lijn met SYNC ids) i.p.v. originele entity_id.
### Notes
- Sensors zijn read-only; geen setpoints. Niet-ondersteunde sensor device_class wordt overgeslagen.

## [2.2.0] - 2025-09-13
### Added
- Climate domain ondersteuning: Thermostat (TemperatureSetting trait) met modes (off/heat/cool/heatcool/fan-only/dry indien beschikbaar).
- EXECUTE support: ThermostatSetMode, ThermostatTemperatureSetpoint, ThermostatTemperatureSetRange.
- QUERY uitgebreid voor climate: huidige mode, ambient temperatuur, setpoint of range.
- Admin UI: werkende Logs (rolling 50 intent events) + Settings sectie met Force SYNC Preview tool.
### Changed
- SYNC voegt thermostat attributen toe (availableThermostatModes, thermostatTemperatureUnit) voor climate devices.
- QUERY voor lights bevat nu brightness percentage indien beschikbaar.
### Notes
- Force SYNC Preview toont actuele payload zonder Google call; handig voor debug.
- Log buffer wordt niet persistently opgeslagen (alleen runtime).


## [2.1.0] - 2025-09-13
### Added
- Stable device IDs met persistent mapping; Google devices verdwijnen niet meer bij entity_id wijziging.
- Brightness trait ondersteuning voor lights (SYNC/QUERY/EXECUTE).
- Admin UI verbeterd: header navigatie, live search (case-insensitive), domain filter, selected-only toggle, icons, telling (#filtered/#total).
### Changed
- SYNC levert nu `otherDeviceIds` met originele Home Assistant entity_id voor compatibiliteit.
- EXECUTE vertaalt stable IDs terug naar entity IDs.
### Notes
- Eerste run genereert mapping; bestaande gekoppelde apparaten kunnen één refresh vereisen in Google Home om nieuwe capabilities te tonen.


## [2.0.7] - 2025-09-13
### Added / Fixed
- Smart Home fulfillment logging (intent, device counts, exceptions) voor diagnose van Google koppelfouten.
- Foutafhandeling in `/habridge/smarthome` met `internalError` bij onverwachte exceptions.
- `token_type` naar `Bearer` (casing) voor OAuth compatibiliteit.


## [2.0.6] - 2025-09-13
### Security / Changed
- Admin & devices endpoint nu token-based i.p.v. HA sessie afhankelijk: random `admin_token` query parameter wordt gegenereerd en aan panel URL toegevoegd.
- Views `AdminPageView` en `DevicesView` vereisen geen HA login meer (`requires_auth=False`) maar valideren token; voorkomt 401 issues in iframe.
- Fetch calls in admin pagina sturen token automatisch mee.


## [2.0.5] - 2025-09-13
### Fixed
- Sidebar panel registratie: ontbrak vereiste `hass` argument bij fallback `async_register_built_in_panel`, veroorzaakt warning en geen panel. Correcte aanroep + extra debug logging toegevoegd.
- Voorkomt dubbele registratie met duidelijke debug melding.

## [2.0.1] - 2025-09-13
### Fixed
- Config flow crash (500) door Voluptuous serialisatie van lijst `[str]`. Expose domains veld verplaatst naar opties en nu als CSV str opgeslagen.

## [2.0.3] - 2025-09-13
### Fixed
- Panel registratie AttributeError (hass.components.frontend niet beschikbaar tijdens setup entry) nu uitgesteld tot HA start event.

## [2.0.4] - 2025-09-13
### Fixed
- Definitieve sidebar panel registratie via `frontend.async_register_panel` met logging en fallback; panel verschijnt nu consequent.

## [2.0.2] - 2025-09-13
### Changed
- Versiebump voor distributie; bevat config flow stabilisatie (CSV domains) en voorbereidingen voor toekomstige multi-select UI.

## [2.0.0] - 2025-09-12
### Breaking / Major
- Volledige herbouw als geïntegreerde Home Assistant custom component (geen losse add-on poort /5000 meer nodig).
- Endpoints verplaatst naar pad binnen HA domein: `/habridge/*` (oauth, token, smarthome, health, admin, devices).
- UI-config (config flow) vervangt YAML configuratie (client_id, client_secret, expose_domains).

### Added
- Config Flow + Options Flow.
- Sidebar panel (iframe) met embedded admin pagina voor device selectie.
- Automatische initiële selectie van eerste batch entiteiten (switch/light) voor directe SYNC response.
- Bulk device selectie endpoint (`POST /habridge/devices`).

### Changed
- Token opslag via Home Assistant Storage API (`.storage/habridge_tokens`).
- Device selectie opslag via `.storage/habridge_devices`.
- JWT signing secret = opgegeven client_secret.

### Removed / Deprecated
- Losse Docker add-on noodzaak (oude add-on functionaliteit is geïntegreerd).
- Externe reverse proxy configuratie stappen.
- React/Vite frontend build (vervangen door lichtgewicht inline admin page).

### Migration Notes
Zie `MIGRATION.md` voor stappen van add-on naar geïntegreerde component.

## [1.x.x]
- Oorspronkelijke add-on implementatie met Flask server, losse poort 5000, React admin UI en Docker multi-arch build.
