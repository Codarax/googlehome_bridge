# Operational Diagnostics - HA Google Home Bridge

This document legt uit hoe je de nieuwe metrics interpreteert en gebruikt voor performance troubleshooting.

Versies: metrics geïntroduceerd in 2.6.7; 2.6.8 & 2.6.9 hotfixes (init / guard); 2.6.10 alleen IDE import fallback – geen metric wijzigingen.

## Overzicht Endpoints & UI
- Admin UI tab "Metrics": toont latency percentielen (p50, p95, max) voor SYNC, QUERY en EXECUTE + event loop lag en per-device EXECUTE timing.
- Endpoint `/habridge/status?token=...`: JSON payload met dezelfde velden voor automatisering of externe monitoring.

## Latency Velden
JSON veld `latency` bevat sub-objecten:

```
latency: {
  sync:    { count, p50, p95, max },
  query:   { count, p50, p95, max },
  execute: { count, p50, p95, max },
  loopLagMs: { count, p50, p95, max }
}
```

Betekenis:
- `count`: aantal recente samples (max 100 voor intents, 120 voor loop lag).
- `p50`: mediaan van laatste samples (typische tijd).
- `p95`: worst-case normaal scenario; 95% is sneller dan deze waarde.
- `max`: hoogste gemeten sample in buffer.
- `loopLagMs`: gemeten event loop lag (idealiter < 20ms p95). Hoge waardes (>100ms p95) wijzen op blokkades (sync disk I/O, zware integraties, CPU spikes).

## SYNC
- Normaal: < 150ms p95, afhankelijk van aantal devices.
- Hoge waarden kunnen duiden op: zeer veel entiteiten, blokkades in area lookup of Home Assistant core druk.
- Hulpmiddel: bekijk `cacheAgeMs`. Een verse SYNC na invalidatie is duurder; hergebruik (cache hit) minimaliseert latency.

## QUERY
- Nieuwe optimalisatie bouwt alleen antwoord voor gevraagde devices. Een Google multi-device status check ("Is de lamp en thermostaat aan?") hoort < 120ms p95 te blijven.
- Stijgende p95: check of sensors/climate entiteiten traag states bijwerken of laden.

## EXECUTE
- Parallel service calls: totale EXECUTE tijd ~ max individuele call (niet som). p95 > 400ms structureel? Controleer per-device stats.

## Per-Device EXECUTE Timing
JSON veld `execDeviceStats` per stable ID:
```
"execDeviceStats": {
  "light_woonkamer": { "count": 6, "last": 45, "p50": 42, "p95": 80, "max": 81 },
  ...
}
```
Interpretatie:
- `last`: meest recente aanroep duur (ms).
- `p50`, `p95`, `max`: percentielen / maximum over de laatste ~20 aanroepen voor dat device.
- Gebruik p95 om outliers te zien; max toont singular spikes (mogelijk incidentele HA druk). 

Indicatoren:
- Eén device met p95 >> rest (bijv. 600ms) wijst op traag domein (Zigbee routing, wifi component, cloud integratie).
- Hoge max maar lage p95 => sporadische glitch, vaak te negeren.

## Event Loop Lag Troubleshooting
- p95 < 30ms: uitstekend.
- 30–80ms: licht verhoogd; mogelijk zware automations of logging bursts.
- 80–200ms: merkbaar; optimaliseer andere integraties / disable debug logging.
- >200ms: Google Assistant delays te verwachten. Check Supervisor system load, database I/O, langdurige sync services.

Aanpak bij hoge lag:
1. In HA: Profiler (Performance panel) gebruiken om blokkerende integraties te identificeren.
2. Database onderhoud: purge & vacuum (`recorder`) kan lag verlagen.
3. Verminder hoge-frequentie automations / template sensors.

## Workflow Voor Troubleshooting "Google denkt lang na"
1. Kijk Metrics tab tijdens een voice command.
2. Noteer EXECUTE totale tijd (log) en per-device p95/last.
3. Indien EXECUTE < 300ms maar Assistant toch traag -> externe factoren (netwerk, Google infra) of OAuth token refresh.
4. Indien event loop lag p95 > 150ms tegelijk → systeemdruk oorzaak.
5. Identificeer top trage device(s) via per-device tabel, test directe service call vanuit HA Developer Tools en vergelijk tijd.

## Automatiserings Integratie
Voor periodic scraping kun je een REST sensor maken:
```yaml
sensor:
  - platform: rest
    name: GH Bridge Status
    resource: "http://homeassistant.local:8123/habridge/status?token=JE_ADMIN_TOKEN"
    scan_interval: 60
    value_template: "{{ value_json.devices }}"
    json_attributes:
      - latency
      - execDeviceStats
```
Vervolgens templates maken om p95 latencies te monitoren.

## Wanneer Herstarten?
- Alleen als loop lag structureel > 300ms blijft na het pauzeren van intensieve integraties.
- Niet nodig voor het leegmaken van metrics; buffers schuiven automatisch.

## Beknopte Checklist
- Langzame respons? → Controleer: EXECUTE p95, loop lag p95.
- Eén lamp traag? → Per-device p95 hoog; optimaliseer netwerk (Zigbee / Wifi) of firmware.
- SYNC vaak duur? → Overactieve invalidaties (veel selectie/alias wijzigingen) of extreem veel devices (>400).

## Versiebeheer
Deze diagnostische functies toegevoegd in release 2.6.7 (uitgebreide metrics).

## Support
Open een issue met: excerpt van `/habridge/status`, aantal devices, relevante p95 waarden, en voorbeeld logregel van een EXECUTE.
