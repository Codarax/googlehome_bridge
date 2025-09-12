# HA Bridge (Inline Google Home Smart Home Bridge)

Deze integratie levert directe endpoints binnen dezelfde Home Assistant instance:

| Functie | Endpoint |
|--------|----------|
| OAuth authorize | `/habridge/oauth` |
| OAuth token | `/habridge/token` |
| Smart Home fulfillment | `/habridge/smarthome` |
| Health check | `/habridge/health` |
| Admin UI (iframe/panel) | `/habridge/admin` |
| Devices JSON API | `/habridge/devices` |

## Doel
Eenvoudige Google Home (Google Smart Home) bridge zonder aparte poort, reverse proxy of extra Nginx. Alles draait binnen HA en gebruikt hetzelfde publieke DuckDNS domein + certificaat.

## Installatie
1. Plaats de map `custom_components/habridge` in je Home Assistant config directory (of gebruik HACS custom repository).
2. Herstart Home Assistant.
3. Ga naar Instellingen → Integraties → "+" → zoek "HA Bridge" → vul in:
  - Client ID (Google Cloud OAuth client)
  - Client Secret
  - Expose Domains (lijst; standaard `switch`, `light`)
4. Na afronden verschijnt het zijbalk panel "HA Bridge" voor device selectie.
5. Opties wijzigen? Ga naar de integratie → "Opties".

## Google Cloud Console / Action Linking
Gebruik exact deze externe HTTPS URLs (vervang je domein):
- Authorization URL: `https://<jouw_domein>/habridge/oauth`
- Token URL: `https://<jouw_domein>/habridge/token`
- Fulfillment URL (Smart Home): `https://<jouw_domein>/habridge/smarthome`
- Redirect URI in client configuratie: dezelfde Authorization URL

## Device Selectie
Het systeem selecteert automatisch een eerste batch (max 50) bij eerste start wanneer geen selectie bestaat. Je kunt dit beheerden via het panel (checkboxen) dat `POST /habridge/devices` aanroept.

## Tokens & Persistentie
- Tokens: `.storage/habridge_tokens`
- Device selectie: `.storage/habridge_devices`

## Beveiliging
- Publieke endpoints (`/habridge/oauth`, `/habridge/token`, `/habridge/smarthome`, `/habridge/health`) hebben geen HA-auth nodig (vereist door Google). Zorg dat jouw domein HTTPS gebruikt.
- Admin & devices endpoints vereisen HA login.
- (Uitbreidbaar) Admin API key ondersteuning kan later worden toegevoegd als extra beveiligingslaag.

## Troubleshooting
| Probleem | Indicatie | Oplossing |
|----------|-----------|-----------|
| Geen apparaten bij SYNC | Lege lijst | Controleer selectie in panel, entiteiten domains allowed |
| redirect_uri_mismatch | OAuth error | Controleer letterlijke URL + https |
| 401 bij token | grant_type fout | Gebruik `authorization_code` of `refresh_token` |
| Geen panel zichtbaar | Cache of panel niet geregistreerd | Browser hard refresh, check logs |

## Roadmap / Uitbreiding
- Config Flow (UI) i.p.v. YAML.
- Meerdere trait types (Brightness, Color, etc.).
- Admin API key / rate limiting.
- WebSocket reportState (optioneel).

## Verwijderen
1. Verwijder de integratie via Instellingen → Integraties.
2. Verwijder map `custom_components/habridge`.
3. Herstart HA.

---
Made for simplified deployment in a single Home Assistant environment.
