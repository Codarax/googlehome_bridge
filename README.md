# Google Home Bridge (Home Assistant Integrated) v2.0.0

Deze repository levert een geïntegreerde Home Assistant custom component die Google Smart Home koppelt zonder aparte poort of reverse proxy. Het vervangt de eerdere 1.x add-on (Docker + Flask + React UI).

## Kernpunten
- Endpoints binnen HA domein: `/habridge/oauth`, `/habridge/token`, `/habridge/smarthome`, `/habridge/admin`.
- Config Flow (UI) voor client_id & client_secret.
- Automatische eerste device selectie voor directe SYNC.
- Lichtgewicht inline admin UI + iframe sidebar panel.

## Installatie (Korte Versie)
1. Kopieer `custom_components/habridge` naar je HA config map (of HACS custom repository).
2. Herstart HA.
3. Instellingen → Integraties → Voeg "HA Bridge" toe → vul Google OAuth gegevens.
4. Open zijbalk panel → controleer/selecteer entiteiten.
5. Configureer Google Cloud Console endpoints op jouw domein.

## Google Cloud URLs
| Doel | URL |
|------|-----|
| Authorization | `https://<domein>/habridge/oauth` |
| Token | `https://<domein>/habridge/token` |
| Fulfillment | `https://<domein>/habridge/smarthome` |
| Admin UI | `https://<domein>/habridge/admin` |

## Migratie
Zie `MIGRATION.md` voor upgrade vanaf add-on 1.x.

## Changelog
Zie `CHANGELOG.md`.

## Roadmap
- Extra traits (dimmer, color)
- Report State / Sync triggers
- Veiligheid: throttling / admin API key optioneel
- HACS listing

## Release Procedure (Maintainers)
1. Bump versie in `custom_components/habridge/manifest.json` (gedaan voor 2.0.0).
2. Update `CHANGELOG.md` + `MIGRATION.md` indien nodig.
3. Commit & push `main`.
4. Tag release:
   ```bash
   git tag v2.0.0
   git push origin v2.0.0
   ```
5. Maak GitHub Release met release notes (kopieer sectie 2.0.0 uit changelog).
6. Markeer oude add-on documentatie als deprecated (optioneel README sectie).

## Ondersteuning
Issues en PR's welkom. Gebruik GitHub Issues voor bug reports / feature requests.

---
Geïntegreerde eenvoud voor Google Smart Home binnen Home Assistant.
