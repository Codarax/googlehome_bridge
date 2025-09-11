"""Small Home Assistant stub server for local/offline testing.

Run this alongside the main server to simulate HA responses at
`http://localhost:8123/api/...`.

Usage:
  python ha_stub.py

Set env var HA_STUB_PORT to change port.
"""
from flask import Flask, jsonify, request
import os
import threading

app = Flask(__name__)

ENTITIES = [
    {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Keuken Licht", "device_class": None}},
    {"entity_id": "switch.coffee", "state": "on", "attributes": {"friendly_name": "Koffiezetter"}},
    {"entity_id": "switch.woonkamer_lamp", "state": "off", "attributes": {"friendly_name": "Woonkamer Lamp"}},
    {"entity_id": "sensor.temperature_outside", "state": "18.5", "attributes": {"friendly_name": "Buiten Temp", "device_class": "temperature"}},
    {"entity_id": "climate.living_room", "state": "heat", "attributes": {"friendly_name": "Woonkamer", "temperature": 21, "fan_modes": ["low","medium","high"]}}
]

@app.route('/api/states', methods=['GET'])
def states():
    return jsonify(ENTITIES)

@app.route('/api/states/<path:entity_id>', methods=['GET'])
def state(entity_id):
    # entity_id comes as e.g. 'light.kitchen'
    for e in ENTITIES:
        if e['entity_id'] == entity_id:
            return jsonify(e)
    return jsonify({}), 404

@app.route('/api/services/<domain>/<service>', methods=['POST'])
def service(domain, service):
    data = request.get_json() or {}
    # simple simulation: flip on/off for lights and switches
    entity_id = data.get('entity_id')
    if entity_id:
        for e in ENTITIES:
            if e['entity_id'] == entity_id:
                if service in ('turn_on','turn_off'):
                    e['state'] = 'on' if service == 'turn_on' else 'off'
                if service == 'set_temperature':
                    # accept 'temperature' in payload
                    t = data.get('temperature')
                    if t is not None:
                        e.setdefault('attributes', {})['temperature'] = t
                return jsonify({'result': 'success'})
    return jsonify({'result': 'ok'})

def run():
    port = int(os.getenv('HA_STUB_PORT', '8123'))
    app.run(host='127.0.0.1', port=port)

if __name__ == '__main__':
    run()
