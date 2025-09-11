# Google Home Bridge Add-on for Home Assistant

Deze add-on draait een OAuth + Google Smart Home fulfillment server als container binnen Home Assistant.

## Features
- OAuth 2.0 Authorization Code + Refresh Tokens
- Google Smart Home intents: SYNC / QUERY / EXECUTE / DISCONNECT
- Admin UI: basis selectie van apparaten (`/admin`)
- Health endpoint voor supervisor watchdog
- Configurabel via add-on opties & environment vars

## Installatie (lokaal)
1. Kopieer de map `addon/` naar je Home Assistant host onder `/addons/googlehome_bridge`.
2. In Home Assistant: Instellingen -> Add-ons -> Add-on store -> Drie puntjes -> Repositories -> (eigen repo toevoegen) of gebruik de "Load local add-ons" functie.
3. Ververs, open de add-on en klik Install.
4. Pas opties aan (Client ID/Secret etc.).
5. Start de add-on. Controleer Logboek voor "Starting OAuth server".

## Poorten & Bereikbaarheid
- Container luistert op `0.0.0.0:5000`.
- Admin UI: `http://<home_assistant_host>:5000/admin`
- Health: `http://<home_assistant_host>:5000/health`

## Add-on Opties -> Environment Mapping
| Optie | Env Var | Doel |
|-------|---------|------|
| client_id | CLIENT_ID | OAuth client id voor Google / test |
| client_secret | CLIENT_SECRET | OAuth secret |
| debug | DEBUG | Extra logging |
| expose_sensors | EXPOSE_SENSORS | Schakel generieke sensor export in |
| expose_temperature | EXPOSE_TEMPERATURE | Temperatuursensoren |
| expose_humidity | EXPOSE_HUMIDITY | Vochtigheid |
| expose_power | EXPOSE_POWER | Vermogen |
| expose_generic | EXPOSE_GENERIC | Waarde sensoren |

## Belangrijke Environment Vars
- `HA_URL`: standaard `http://supervisor/core` (interne core API). Je kunt ook de externe basis URL zetten.
- `HA_TOKEN`: Gebruik een Long-Lived Access Token of Supervisor token. (Let op beveiliging.)
- `PORT`: Standaard 5000.

## Bestanden / Persistente Data
- Tokens (`tokens.json`) en devices (`devices.json`) kunnen in toekomstige versie naar `/config` of `/share` worden gemapt.

## Endpoints Overzicht
| Methode | Pad | Beschrijving |
|---------|-----|--------------|
| GET | /oauth | OAuth authorize endpoint (code uitgifte) |
| POST | /token | Token exchange (code->access, refresh->access) |
| POST | /smarthome | Google intents (SYNC/QUERY/EXECUTE/DISCONNECT) |
| GET | /health | Health check (status info) |
| GET | /admin | Admin web UI (rudimentair) |
| GET | /admin/devices | Lijst HA entities / export status |
| POST | /admin/login | (Basic) admin login |
| POST | /admin/logout | Uitloggen |
| POST | /admin/devices/select | Selecteer welke devices geëxporteerd worden |

## Google Smart Home Koppelen (Samenvatting)
1. Maak een nieuw Google Cloud project, activeer Smart Home API.
2. Maak een OAuth client (Web app). Redirect URI: `https://<jouw domein>/oauth` (of via tunneling / reverse proxy naar deze add-on).
3. Fulfillment URL in Google Console: `https://<jouw domein>/smarthome`.
4. OAuth endpoints instellen:
   - Authorization URL: `https://<jouw domein>/oauth`
   - Token URL: `https://<jouw domein>/token`
5. Deploy een reverse proxy (NGINX / Caddy) met HTTPS (Let’s Encrypt) die verkeer naar Home Assistant host poort 5000 doorstuurt.
6. Test SYNC via Google Home app na account linking.

## Reverse Proxy Voorbeeld (Caddy)
```
bridge.example.com {
    encode gzip
    reverse_proxy 192.168.1.10:5000
}
```

## Logging
Wordt naar stdout geschreven; in Add-on log viewer zichtbaar. Zet `debug` op true voor extra details.

## Watchdog
Supervisor pingt `GET /health`. Status "healthy" => OK. Anders restart afhankelijk van policy.

## Toekomstige Verbeteringen (Suggesties)
- Ingress support (UI binnen HA paneel)
- Persistentie devices/tokens naar `/config` map
- Auth hardening admin UI
- Rate limiting & verbeterde error codes

## Disclaimer
Niet officieel geassocieerd met Google of Home Assistant. Gebruik op eigen risico.
