# Changelog

## [2.6.10] - 2025-09-18
### Dev / Tooling
- Voeg guarded fallback stub toe voor `homeassistant.helpers.storage.Store` zodat IDE / Pylance geen missing import meldingen geven buiten HA runtime.

### Functional Impact
- Geen runtime wijziging binnen Home Assistant (HA core levert echte `Store`).

### Upgrade Note
- Alleen nodig als je lokale ontwikkelomgeving de import warning stoorde.

## [2.6.9] - 2025-09-18
### Hotfix
- Definitieve fix voor DeviceManager init attributen (`_exec_device_timings`, `_exec_device_last`) waarin sommige installaties nog de fout "NameError: self is not defined" zagen omdat 2.6.8 mogelijk zonder correcte indentation werd gedeployed.
- Geen verdere codewijzigingen (metrics identiek aan 2.6.7/2.6.8).

### Advies
- Upgrade wanneer je de NameError tijdens toevoegen van de integratie zag.

## [2.6.8] - 2025-09-18
### Hotfix / Stability
- Herstelt `DeviceManager` init NameError (per-device EXECUTE timing dicts stonden buiten `__init__`).
- Geen functionele wijzigingen verder; uitsluitend import/startup fix.

### Notes
- Indien 2.6.7 al geïnstalleerd en werkte zonder foutmelding is update optioneel.
- Krijg je bij toevoegen integratie de fout "Invalid handler specified" / NameError → update direct naar 2.6.8.

### Metrics
- Identiek aan 2.6.7: Metrics tab, per-device EXECUTE timing & `execDeviceStats` endpoint.

## [2.6.7] - 2025-09-18
### Performance / Optimization
- QUERY endpoint bouwt nu alleen status voor expliciet gevraagde device IDs (fallback naar alle geselecteerde wanneer Google geen lijst meestuurt) → lagere CPU & latency bij grote installaties.
- EXECUTE service calls parallel uitgevoerd (asyncio gather) i.p.v. sequentieel; totale tijd ≈ langzaamste individuele call in plaats van som.

### Diagnostics & Observability
- Metrics tab in Admin UI: live p50/p95/max voor SYNC / QUERY / EXECUTE + event loop lag + per-device EXECUTE timing (last/p50/p95/max, rolling ~20 samples per device).
- Per-device EXECUTE timing instrumentatie (blocking service calls) om trage entiteiten te isoleren.
- Status endpoint (`/habridge/status`) uitgebreid met `execDeviceStats` (zelfde statistieken als UI tabel) en bestaande `latency` object.
- Nieuwe documentatie: `docs/DIAGNOSTICS.md` met interpretatie (loop lag thresholds, p95 analyse, troubleshooting stappen).
- QUERY logging uitgebreid: `parseMs`, `buildMs`, totale `timeMs`, aantal requested (`req`), aantal geselecteerd (`sel`).

### Notes
- Tag `v2.6.7` als annotated tag om HACS update notificatie te triggeren (`git tag -a v2.6.7 -m "2.6.7" && git push origin v2.6.7`).
- Gebruikers die eerder via `main` hebben geïnstalleerd: adviseer omschakeling naar vaste versie voor toekomstige notificaties.

### Future (mogelijk in 2.6.8+)
- SYNC cache hit ratio in status & UI.
- Per-device historical trend (mini sparkline) voor EXECUTE tijden.
- Exporter / Prometheus style endpoint indien behoefte ontstaat.

# [2.6.6] - 2025-09-17

# [2.6.6] - 2025-09-17
### Fixed
- Alias persist bug: lege alias dictionary werd door `or {}` telkens vervangen waardoor nieuwe aliases niet in Devices view verschenen tot herstart.

### Notes
- Aliases worden nu direct zichtbaar na opslaan; geen extra refresh nodig.

## [2.6.5] - 2025-09-17
### Added
- Latency statistieken: ringbuffers (laatste 50) voor SYNC / QUERY / EXECUTE; p50/p95/max + event loop lag sample zichtbaar via `/habridge/status` (key `latency`).
- SmartHome endpoint registreert nu elke intent latency via `record_latency`.
- Metrics sampler gestart bij initialisatie (periodieke event loop lag meting).

### Changed
- SYNC cache invalidatie gedebounced (1s) om burst rebuilds te verminderen bij snelle reeks wijzigingen (selecties, alias, settings).
- Admin UI: header nu sticky net als filter toolbar (betere navigatie tijdens scrollen).
- Status endpoint uitgebreid met `latency` object.

### Internal
- Nieuwe helpers in `device_manager`: `debounce_invalidate`, `record_latency`, `latency_stats`, `start_metrics`.
- Alle directe `invalidate_sync_cache()` aanroepen vervangen door debounced variant (fallback wanneer attribuut niet bestaat).

### Notes
- Observeer komende dagen latency (QUERY / EXECUTE). Indien nog spikes: volgende stap is gerichte QUERY optimalisatie (alleen requested ids).
- Matter QR integratie NIET geïmplementeerd; buiten scope & aanzienlijk complexer (commissioning, certificaten, clusters). OAuth pad blijft gebruikt en is eenvoudiger te beheren.

### Safety / Performance Impact
- Vermindert CPU pieken door herhaalde SYNC rebuilds bij bulk toggles of alias updates.
- Biedt onderbouwde diagnose (p95) om echte vertraging (intern vs Google) te isoleren.

## [2.6.4] - 2025-09-17
### Fixed
- Area filter in Devices view werkte niet (geen event listener + geen filterlogica); nu hersteld.
- Alias opslaan verdween soms direct door refresh race; pending alias wordt vastgehouden tot server bevestigt.

### Added
- Performance timing log (ms) voor SYNC / QUERY / EXECUTE in admin logs.

### Notes
- Gebruik admin Logs om latency te zien: zoek SYNC/QUERY/EXECUTE entries met timeMs=.. voor diagnose.

## [2.6.3] - 2025-09-17
### Added / Changed
- Alias search: zoekveld matcht nu ook op ingestelde alias.
- Bulk acties: bevestiging voor Select All / Clear All.
- Icons voor scene (🎬) en script (📜).
- Script ActivateScene: fallback naar `script.run` wanneer `script.turn_on` niet beschikbaar of faalt.

### Removed
- Source kolom uit Devices UI (Area blijft zichtbaar, bron diagnostic verwijderd voor eenvoud).

### Fixed / UX
- Alias opslaan betrouwbaarder: pending alias zichtbaar tijdens save, refresh overschrijft alias niet meer.
- Scene/script activatie betrouwbaarder door servicenaam fallback.

### Notes
- Functionaliteit verder identiek aan 2.6.2 behalve bovengenoemde UI & script verbeteringen.

## [2.6.2] - 2025-09-17
### Fixed
- CI trigger gefaald voor 2.6.1 (tag mismatch / workflow). Nieuwe `v2.6.2` tag + versie bump zodat build & publish correct draaien.

### Changed
- Alleen versie/CI correctie; functionaliteit identiek aan 2.6.0 (scenes/scripts + UI uitbreidingen).

## [2.6.1] - 2025-09-17
### Fixed
- Corrigeert release: 2.6.0 tag wees naar commit zonder wijzigingen (scenes/scripts + UI kolommen). 2.6.1 verwijst nu naar juiste code.

### Notes
- Functiewijzigingen identiek aan 2.6.0; alleen herpublicatie met correcte pointer.

## [2.6.0] - 2025-09-17
### Added
- Scene & Script ondersteuning: beide exposed als Google `SCENE` met `Scene` trait. Spraak: "Hey Google, activeer <naam>" (alias ook geldig). Scripts gebruiken eveneens ActivateScene (stateless).
- EXECUTE mapping: `ActivateScene` → `scene.turn_on` / `script.turn_on` (geen reversible scenes; `deactivate` genegeerd).
- Admin UI: Area Source kolom (entity/device), area filter (all/with/without), kleur badge voor lights (ColorSetting) met RGB preview.

### Changed
- Default expose lijst uitgebreid met `scene` en `script`. Overweeg domeinen te beperken via Options bij veel scenes.

### Internal
- Devices endpoint levert nu extra velden: `has_color`, `color_preview`, `area_source`.

### Notes
- Scenes & scripts zijn stateless: geen QUERY status; alleen activeren. Optionele toekomstige feature: scripts als OnOff wrapper.

## [2.5.0] - 2025-09-17
### Fixed
- ColorSetting trait werd niet toegevoegd wanneer de lamp wel kleur ondersteunt maar (uit) geen `rgb_color`/`hs_color` attribuut had. Detectie gebruikt nu `supported_color_modes` zodat Google kleurcommando's ("zet op rood/groen") herkent.
- Consistente verwerking van `spectrumRGB` (hex/dec) en Kelvin → mired conversie in ColorAbsolute EXECUTE.

### Added
- Uitgebreidere capability-detectie voor kleur (hs/rgb/xy/rgbw/rgbww) + color_temp combinatie.

### Internal
- Kleine refactor in ColorAbsolute handler (str → int parsing robuuster).

### Notes
- Na update: forceer een Google "Sync my devices". Controleer in SYNC preview dat de lamp de trait `ColorSetting` heeft en test daarna spraakcommando's.

## [2.4.9] - 2025-09-17
### Changed
- Gecentraliseerde area lookup: nieuwe `compute_area_lookup` helper in `device_manager` elimineert dubbele logica tussen SYNC en Devices endpoint.

### Added / Debug
- `/habridge/devices?debug=1` retourneert nu `area_sources` (per entity 'entity' of 'device' bron) voor diagnose waarom Area kolom mogelijk leeg is.

### Fixed / Internal
- SYNC build gebruikt nu dezelfde area mapping als admin UI zodat roomHint en Area kolom gegarandeerd consistent zijn.

### Notes
- Als Areas nog leeg zijn: controleer dat entities een area krijgen via HA UI (Settings → Devices & Services → Devices) en herstart daarna. Gebruik vervolgens debug query voor broncontrole.

## [2.4.8] - 2025-09-17
### Fixed
- Admin Devices Area kolom: gebruikte verouderde `async_get_registry` calls waardoor area namen leeg bleven. Gewijzigd naar `async_get` voor entity/area/device registries.

### Changed
- Versie bump voor distributie van de Area kolom fix.

### Notes
- Indien eerder geladen zonder areas: hard refresh admin panel / herstart integratie om kolom te vullen.

## [2.4.7] - 2025-09-17
### Added
- `/habridge/status` endpoint: compacte health & feature metrics (devices, withAlias, withArea, roomHintApplied, cacheAgeMs, roomHintEnabled).

### Debug / Diagnostics
- `build_sync` logging van area hits (entity vs device fallback) + alias telling wanneer cache vernieuwt.

### Changed
- Admin Devices UI toont nu aparte kolommen: Name (origineel), Alias, Area.

### Notes
- Gebruik `/habridge/status?token=<admin_token>` voor snelle controle zonder volledige SYNC payload.

## [2.4.6] - 2025-09-17
### Added
- Admin Devices UI: alias badge indicator (tooltip shows original name) wanneer een alias actief is.

### Changed
- Aliases: bewaren nu exacte ingevoerde whitespace (geen strip behalve voor leeg detectie). Lege / whitespace-only invoer wist bestaande alias.
- Devices endpoint (`/habridge/devices`) levert nu `orig_name` en `alias` velden naast weergegeven naam.

### Fixed
- roomHint: fallback naar device registry area wanneer entity area ontbreekt (meer apparaten krijgen juiste kamer).
- Front-end rename flow: inline edit placeholder en automatische refresh zodat alias meteen zichtbaar is.

### Notes
- Forceer een Google "Sync my devices" na aanpassen van meerdere aliases om namen in Google Home te vernieuwen.
- Clearing an alias (leeg veld) herstelt originele Home Assistant naam in volgende SYNC.

## [2.4.5] - 2025-09-17
### Added
- roomHint toggle + area → Google `roomHint` mapping (instelbaar in Settings) met Re-SYNC knop en badge telling hoeveel devices een roomHint kregen.
- ColorSetting trait voor kleurlampen (RGB + kleurtemperatuur) inclusief QUERY `currentColor` en EXECUTE `ColorAbsolute`.
- Alias (rename) functionaliteit: persistent aliases store, inline Rename knop per device, SYNC naam override, `ALIAS` log events.
- OAuth client configuratie in admin UI: Client ID & Secret inzien/genereren/opslaan (masked secret logging).
- Re-SYNC endpoint (`/habridge/trigger_sync`) voor directe payload inspectie + logging.

### Performance
- SYNC payload caching (8s TTL) met invalidatie bij wijzigingen (selectie, alias, settings) vermindert CPU load op Raspberry Pi.

### Changed
- EXECUTE logging uitgebreid met kleurparameters (rgb / kelvin) en alias / settings updates (gemaskt secret).

### Notes
- Na inschakelen van roomHint kan een Google “Sync my devices” nodig zijn om kamers toe te wijzen.
- Bestaande refresh tokens blijven geldig na het wijzigen van client_secret; nieuw secret ondertekent nieuwe access tokens.
- Caching is bewust kort; forceer Re-SYNC of wijzig een instelling voor directe vernieuwing.


## [2.4.1] - 2025-09-13
## [2.4.2] - 2025-09-17
### Added / Diagnostics
- SmartHome endpoint: raw body validation & expliciete logging bij malformed JSON of ontbrekende `inputs`.
- EXECUTE: stricte commands-structuur validatie + foutmelding bij protocolError.
- Log buffer krijgt ERROR entries `invalid_json`, `malformed_payload_no_inputs`, `EXECUTE malformed commands struct` voor snellere debug.
### Changed
- JSON parsing gebruikt nu handmatige decode en behoudt raw preview bij fouten.
### Notes
- Huidige `protocolError` bij SYNC test was veroorzaakt door malformed of leeg request body; na deploy 2.4.2 zullen logs exact aangeven wat er ontbrak.

### Fixed / Changed
- Climate: apparaat type dynamisch AC_UNIT wanneer fan_modes aanwezig → Google herkent FanSpeed beter.
- Climate: OnOff trait toegevoegd zodat "zet airco uit / aan" werkt (EXECUTE omzet naar hvac_mode off of herstelt/kiest geschikte modus).
- EXECUTE: SetFanSpeed & temperatuur setpoint handling uitgebreid; QUERY geeft nu `on` flag + `currentFanSpeedSetting`.
- FanSpeed mapping: accepteert zowel `speed_medium` als `medium` vanuit Google.
- Logging: skip log toegevoegd wanneer climate state ontbreekt tijdens EXECUTE.
### Notes
- Als bestaande gekoppelde apparaten nog THERMOSTAT tonen: Force SYNC (Settings → Force SYNC Preview, daarna een Google "sync my devices").

## [2.4.0] - 2025-09-13
### Added
- FanSpeed trait ondersteuning voor climate devices wanneer `fan_modes` beschikbaar zijn (SYNC attributes: `availableFanSpeeds`, `reversible=false`).
- EXECUTE: SetFanSpeed (`action.devices.commands.SetFanSpeed`) mapping naar HA `climate.set_fan_mode`.
- QUERY: retourneert `currentFanSpeedSetting` indien fan_mode aanwezig.
- Uitgebreidere EXECUTE logging: elke device+command combinatie met compacte param samenvatting (on, bri, mode, temp, fan).
- Admin Settings: Device List Filters (per domein zichtbaar ja/nee, lokaal opgeslagen in browser) + reset knop.

### Changed
- EXECUTE log detail toont nu aantal groepen + totaal commands + compacte lijst (afgekapt tot ~600 chars).

### Notes
- Domain visibility filters beïnvloeden alleen weergave in admin UI, niet selectie/persistentie of SYNC exposure.
- FanSpeed verschijnt alleen bij climate entities met fan_modes attributen.

## [2.3.6] - 2025-09-13
## [2.3.7] - 2025-09-13
### Changed
- Selectie opslaan: bulk_update accepteert nu ook entities zonder actieve state zodat pending keuzes niet kwijtraken.
- Front-end toggle lock window (4s) voorkomt tussentijdse inversie door refresh.
- Directe refresh na succesvolle POST vermindert visueel verschil tussen lokale en serverstatus.
### Notes
- Lock window wordt na bevestigde server response verkort (800ms). Eventueel later vervangbaar door echte realtime push.

### Added
- Logging van SELECT (device selectie wijzigingen) in zelfde buffer.
### Changed
- Log timestamps gebaseerd op realtime (time.time) i.p.v. event loop time.
- Toggle frontend: pending selectie heeft absolute prioriteit tijdens refresh (geen tussenfase meer zichtbaar).
### Fixed
- Flicker na toggle (kortstondige inversie) verminderd door verwijderen van fallback merge.
### Notes
- SELECT log detail toont max 10 sample pairs; volledige diff kan later optioneel.

## [2.3.5] - 2025-09-13
### Fixed
- Admin page onbruikbaar door JavaScript syntax error (dubbele `});` in visibilitychange listener) hersteld.

## [2.3.4] - 2025-09-13
### Added
- Settings optie: Background auto updates toggle (devices + logs) met respect voor verborgen tabbladen (document.hidden).
- Logs UI: kolommen (#, datum, tijd, requestId, intent, detail) + requestId logging.
### Changed
- Devices refresh overschrijft selectie niet; optimistisch pending mechanisme.
### Fixed
- Toggle flikkeren door race met refresh opgelost via `_pendingSelections` merge.
- Ontbrekende climate entity nu zichtbaar door entity_registry fallback en inclusion zonder state.
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
