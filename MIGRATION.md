# Migratie van Add-on (<=1.x) naar Geïntegreerde Component (2.0.0)

## Overzicht
Versie 2.0.0 vervangt de oude Docker add-on (poort 5000) door een directe Home Assistant custom component met paden onder `/habridge/*`. Geen aparte containerpoort of reverse proxy configuratie meer nodig.

## Wat Verandert
| Onderdeel | Oud (Add-on) | Nieuw (2.0.0) |
|-----------|--------------|---------------|
| Endpoint base | `http(s)://<domein>:5000/` | `https://<domein>/habridge/` |
| Admin UI | React build | Inline HTML (/habridge/admin) |
| Config | Add-on opties / YAML | UI Config Flow |
| Tokens opslag | /data/tokens.json | `.storage/habridge_tokens` |
| Device selectie | /data/devices.json | `.storage/habridge_devices` |

## Stappen Migratie
1. Noteer huidige Google Action instellingen (client_id, client_secret, URLs).
2. Stop de oude add-on (Supervisor → Add-ons → stop).
3. Verwijder (optioneel) de add-on of markeer hem als disabled.
4. Kopieer map `custom_components/habridge` naar je Home Assistant config (of HACS toevoegen als custom repo).
5. Herstart Home Assistant.
6. Ga naar Instellingen → Integraties → Voeg "HA Bridge" toe en vul client_id & client_secret (zelfde als voorheen).
7. Check of `https://<domein>/habridge/oauth` toegankelijk is (geen 404).
8. Open zijbalk panel "HA Bridge" en controleer device selectie (past automatisch eerste batch toe). Pas selectie aan indien nodig.
9. Test Google SYNC ("Hey Google, sync my devices").
10. Als alles werkt kun je oude bestandsresten opruimen (tokens.json/devices.json in add-on data niet meer nodig).

## Herconfiguratie Google (alleen indien endpoints veranderd)
Update in Google Cloud Console / Smart Home registratie:
- Authorization URL: `https://<domein>/habridge/oauth`
- Token URL: `https://<domein>/habridge/token`
- Fulfillment URL: `https://<domein>/habridge/smarthome`

Redirect URI = Authorization URL.

## Probleemoplossing
| Issue | Oorzaak | Oplossing |
|-------|---------|-----------|
| 404 op /habridge/oauth | Component niet geladen | Controleer logs, herstart HA |
| Lege SYNC | Geen selectie / domains mismatch | Panel selectie aanpassen / expose domains via Opties |
| Invalid client | Verkeerde client_id | Controleer configuratie in integratie opties |
| Token refresh faalt | Oude refresh token | Nieuwe token flow uitvoeren |

## Rollback
Je kunt terug naar 1.x door de add-on opnieuw te activeren en de component map te verwijderen. (Niet aanbevolen; 2.0.0 is superset.)

## Toekomst
- Meer traits (brightness, color)
- Report State
- Extra security (rate limiting)

---
Succesvolle migratie gewenst!
