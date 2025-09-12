# Changelog

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
