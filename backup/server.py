from flask import Flask, request, jsonify, redirect
import jwt, time, secrets, requests, os, json

app = Flask(__name__)

# ---------------- CONFIG ----------------
# Haal omgevingsvariabelen op, met standaardwaarden voor testen.
CLIENT_ID = os.getenv("CLIENT_ID", "Yew6FCGaG5ALIfNaZzWBZXBBLkaOnP8e")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "HtHL5dDmYqtMpHWduEdHjkA0nOVJByNg")
HA_URL = os.getenv("HA_URL", "https://homeassistant.codarax.nl")
HA_TOKEN = os.getenv("HA_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIyNDBjZTc2NTZjMmQ0OGNkODVhYTc3ZGNlOWYwMWJmMyIsImlhdCI6MTc1NjM3NTAyMSwiZXhwIjoyMDcxNzM1MDIxfQ.n3kxMZOu9iz7oz2U85lhZRUfcVpGX0sC1dGL-uAlfIU")

# Token configuratie
TOKENS_FILE = os.getenv("TOKENS_FILE", "tokens.json")
USE_FILE_STORAGE = os.getenv("USE_FILE_STORAGE", "true").lower() == "true"

ACCESS_TOKEN_LIFETIME = 3600    # 1 uur
AUTH_CODE_LIFETIME = 600        # 10 min
REFRESH_TOKEN_LIFETIME = 86400 * 30  # 30 dagen

# ---------------- Storage ----------------
# Dictionaries om tokens en autorisatiecodes in op te slaan.
auth_codes = {}
access_tokens = {}
refresh_tokens = {}

def _now():
    """Haalt de huidige tijd in seconden op."""
    return int(time.time())

def cleanup_expired_tokens():
    """Ruimt verlopen tokens op."""
    current_time = _now()

    # Ruim verlopen auth codes op
    expired_codes = [code for code, data in auth_codes.items()
                    if data.get("expires_at", 0) < current_time]
    for code in expired_codes:
        del auth_codes[code]

    # Ruim verlopen access tokens op
    expired_tokens = [token for token, data in access_tokens.items()
                     if data.get("expires_at", 0) < current_time]
    for token in expired_tokens:
        del access_tokens[token]

    # Ruim verlopen refresh tokens op
    expired_refresh = [token for token, data in refresh_tokens.items()
                      if data.get("expires_at", 0) < current_time]
    for token in expired_refresh:
        del refresh_tokens[token]

def load_tokens():
    """Laadt de tokens uit het bestand."""
    global auth_codes, access_tokens, refresh_tokens

    if not USE_FILE_STORAGE:
        print("INFO: Using in-memory token storage")
        return

    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, "r") as f:
                data = json.load(f)
                auth_codes = data.get("auth_codes", {})
                access_tokens = data.get("access_tokens", {})
                refresh_tokens = data.get("refresh_tokens", {})

            # Ruim verlopen tokens op bij het laden
            cleanup_expired_tokens()
            print(f"INFO: Loaded tokens from {TOKENS_FILE}")
        else:
            auth_codes, access_tokens, refresh_tokens = {}, {}, {}
            print(f"INFO: No token file found, starting fresh")
    except Exception as e:
        print(f"ERROR: Failed to load tokens: {e}")
        auth_codes, access_tokens, refresh_tokens = {}, {}, {}

def save_tokens():
    """Slaat de tokens op in het bestand."""
    if not USE_FILE_STORAGE:
        return

    try:
        # Ruim verlopen tokens op voordat we opslaan
        cleanup_expired_tokens()

        data = {
            "auth_codes": auth_codes,
            "access_tokens": access_tokens,
            "refresh_tokens": refresh_tokens
        }

        with open(TOKENS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        print(f"INFO: Saved {len(access_tokens)} access tokens, {len(refresh_tokens)} refresh tokens")
    except Exception as e:
        print(f"ERROR: Failed to save tokens: {e}")

def persist_tokens():
    """Alias voor save_tokens()."""
    save_tokens()

def generate_jwt_access_token(client_id, lifetime=ACCESS_TOKEN_LIFETIME):
    """Genereert een nieuwe JWT access token."""
    payload = {
        "client_id": client_id,
        "iat": _now(),
        "exp": _now() + lifetime,
        "type": "access"
    }
    token = jwt.encode(payload, CLIENT_SECRET, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token

def generate_refresh_token(client_id, lifetime=REFRESH_TOKEN_LIFETIME):
    """Genereert een nieuwe refresh token."""
    payload = {
        "client_id": client_id,
        "iat": _now(),
        "exp": _now() + lifetime,
        "type": "refresh"
    }
    token = jwt.encode(payload, CLIENT_SECRET, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token

# ---------------- Home Assistant ----------------
def get_homeassistant_entities():
    """Haalt alle entiteiten op uit Home Assistant."""
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.get(f"{HA_URL}/api/states", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print("Fout bij ophalen van entiteiten:", e)
        return []

# ---------------- Device mapping ----------------
def generate_sync_devices():
    """Genereert de lijst van apparaten voor de SYNC-respons."""
    entities = get_homeassistant_entities()
    devices = []
    for entity in entities:
        entity_id = entity.get('entity_id')
        attributes = entity.get('attributes',{})
        friendly_name = attributes.get('friendly_name',entity_id)
        device_class = attributes.get('device_class','')

        # Belangrijke wijziging: willReportState is nu overal True.
        # Dit is essentieel voor Google om de status te kunnen opvragen.

        # SWITCH / LIGHT
        if entity_id.startswith('light.') or entity_id.startswith('switch.'):
            devices.append({
                'id': entity_id,
                'type':'action.devices.types.SWITCH',
                'traits':['action.devices.traits.OnOff'],
                'name':{'name':friendly_name},
                'willReportState':True
            })
        # CLIMATE
        elif entity_id.startswith('climate.'):
            devices.append({
                'id': entity_id,
                'type':'action.devices.types.AC_UNIT',
                'traits':['action.devices.traits.OnOff','action.devices.traits.TemperatureSetting'],
                'name':{'name':friendly_name},
                'willReportState':True,
                'attributes':{
                    'availableThermostatModes':'off,heat,cool,auto,fan-only,dry',
                    'thermostatTemperatureUnit':attributes.get('unit_of_measurement','C'),
                    'availableThermostatFanModes':'auto,low,medium,high'
                }
            })
        # BINARY SENSOR (DOOR / OPENING)
        elif entity_id.startswith('binary_sensor.') and device_class in ('door','opening'):
            devices.append({
                'id': entity_id,
                'type':'action.devices.types.SENSOR',
                'traits':['action.devices.traits.OpenClose'],
                'name':{'name':friendly_name},
                'willReportState':True
            })
        # SENSORS
        elif entity_id.startswith('sensor.'):
            if device_class in ('temperature','temperature_sensor') or 'temperature' in entity_id:
                devices.append({
                    'id': entity_id,
                    'type':'action.devices.types.SENSOR',
                    'traits':['action.devices.traits.TemperatureSetting'], # Correcte trait voor QUERY
                    'name':{'name':friendly_name},
                    'willReportState':True
                })
            # Luchtvochtigheid (humidity) logica is verwijderd zoals gevraagd.
            elif device_class in ('power','energy') or any(x in entity_id for x in ('power','energy','solar','generation')):
                devices.append({
                    'id': entity_id,
                    'type':'action.devices.types.SENSOR',
                    'traits':['action.devices.traits.SensorState'],
                    'name':{'name':friendly_name},
                    'willReportState':True
                })
    return devices

# ---------------- Mapping GH → HA ----------------
GH_TO_HA_FAN = {'auto':'auto','low':'low','medium':'medium','high':'high'}
GH_TO_HA_MODE = {'off':'off','heat':'heat','cool':'cool','auto':'auto','fan-only':'fan-only','dry':'dry'}

# ---------------- OAuth ----------------
@app.route('/oauth')
def oauth():
    client_id = request.args.get('client_id')
    redirect_uri = request.args.get('redirect_uri')
    state = request.args.get('state')
    if client_id != CLIENT_ID: return "Invalid client_id",400
    code = secrets.token_urlsafe(24)
    auth_codes[code] = {"client_id": client_id, "scope": request.args.get('scope'), "expires_at": _now()+AUTH_CODE_LIFETIME}
    persist_tokens()
    return redirect(f"{redirect_uri}?code={code}&state={state}")

@app.route('/token', methods=['POST'])
def token():
    grant_type = request.form.get('grant_type')
    client_id = request.form.get('client_id')
    client_secret = request.form.get('client_secret')

    print(f"DEBUG: Token request - grant_type: {grant_type}, client_id: {client_id}")

    if client_id != CLIENT_ID or client_secret != CLIENT_SECRET:
        print(f"ERROR: Invalid client credentials")
        return jsonify({"error": "invalid_client"}), 400

    if grant_type == 'authorization_code':
        code = request.form.get('code')
        if not code or code not in auth_codes:
            print(f"ERROR: Invalid or missing authorization code: {code}")
            return jsonify({"error": "invalid_grant"}), 400

        code_data = auth_codes.pop(code)
        if _now() > code_data.get('expires_at', 0):
            print(f"ERROR: Authorization code expired")
            return jsonify({"error": "invalid_grant", "error_description": "authorization code expired"}), 400

        # Genereer tokens
        access_token = generate_jwt_access_token(client_id)
        refresh_token = generate_refresh_token(client_id)

        # Sla tokens op
        access_tokens[access_token] = {
            "client_id": client_id,
            "expires_at": _now() + ACCESS_TOKEN_LIFETIME
        }
        refresh_tokens[refresh_token] = {
            "client_id": client_id,
            "expires_at": _now() + REFRESH_TOKEN_LIFETIME
        }

        persist_tokens()
        print(f"SUCCESS: Generated access token for client {client_id}")
        return jsonify({
            "token_type": "Bearer",
            "access_token": access_token,
            "expires_in": ACCESS_TOKEN_LIFETIME,
            "refresh_token": refresh_token
        })

    elif grant_type == 'refresh_token':
        refresh_token = request.form.get('refresh_token')
        if not refresh_token or refresh_token not in refresh_tokens:
            print(f"ERROR: Invalid refresh token: {refresh_token}")
            return jsonify({"error": "invalid_grant"}), 400

        # Genereer nieuwe access token
        new_access_token = generate_jwt_access_token(client_id)
        access_tokens[new_access_token] = {
            "client_id": client_id,
            "expires_at": _now() + ACCESS_TOKEN_LIFETIME
        }

        persist_tokens()
        print(f"SUCCESS: Refreshed access token for client {client_id}")
        return jsonify({
            "token_type": "Bearer",
            "access_token": new_access_token,
            "expires_in": ACCESS_TOKEN_LIFETIME
        })

    else:
        print(f"ERROR: Unsupported grant type: {grant_type}")
        return jsonify({"error": "unsupported_grant_type"}), 400

# ---------------- Smarthome ----------------
@app.route('/smarthome',methods=['POST'])
def smarthome():
    def _validate_bearer_token():
        auth_header = request.headers.get('Authorization','')
        if not auth_header.startswith('Bearer '):
            return None,(False,jsonify({"error":"missing token"}),401)
        token = auth_header.split()[1]
        if token not in access_tokens:
            return None,(False,jsonify({"error":"invalid token"}),401)
        try:
            payload = jwt.decode(token,CLIENT_SECRET,algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None,(False,jsonify({"error":"token_expired"}),401)
        except Exception:
            return None,(False,jsonify({"error":"invalid_token"}),401)
        return payload,(True,None,None)

    payload,(ok,err,status) = _validate_bearer_token()
    if not ok:
        print(f"ERROR: Token validation failed: {err}")
        return err, status

    intent_request = request.json
    intent = intent_request['inputs'][0]['intent']

    print(f"DEBUG: Processing intent: {intent}")

    # ---------------- SYNC ----------------
    if intent == 'action.devices.SYNC':
        devices = generate_sync_devices()
        print(f"DEBUG: SYNC returning {len(devices)} devices")
        if devices:
            print(f"DEBUG: First device: {devices[0]}")
        return jsonify({"requestId": intent_request.get('requestId'), "payload": {"agentUserId": "user_ha", "devices": devices}})

    # ---------------- QUERY ----------------
    elif intent=='action.devices.QUERY':
        devices={}
        for device in intent_request['inputs'][0]['payload']['devices']:
            entity_id = device['id']
            try:
                resp = requests.get(f"{HA_URL}/api/states/{entity_id}",
                                     headers={"Authorization":f"Bearer {HA_TOKEN}","Content-Type":"application/json"},timeout=8)
                resp.raise_for_status()
                state = resp.json()
            except Exception:
                devices[entity_id]={"online":False}
                continue

            device_info = {"online": True}
            
            # Climate
            if entity_id.startswith('climate.'):
                hvac_state = state['state']
                fan_mode = state['attributes'].get('fan_mode','auto')
                device_info.update({
                    "thermostatMode": hvac_state,
                    "thermostatTemperatureSetpoint": state['attributes'].get('temperature'),
                    "thermostatFanMode": fan_mode
                })
            # Light / Switch
            elif entity_id.startswith('light.') or entity_id.startswith('switch.'):
                device_info.update({"on": state['state'] == 'on'})

            # Binary sensor (door/opening)
            elif entity_id.startswith('binary_sensor.'):
                device_info.update({"openPercent": 100 if state['state'] == 'on' else 0})
            
            # Sensor
            elif entity_id.startswith('sensor.'):
                try:
                    val_float = float(state['state'])
                    device_class = state['attributes'].get('device_class', '')

                    # Aanpassing: gebruik de juiste attributen voor specifieke sensortypen.
                    if 'temperature' in entity_id or 'temperature' in device_class:
                        device_info.update({"thermostatTemperatureAmbient": val_float})
                    else: # Overige sensors
                        # Aanpassing: 'sensorState' vereist een array van objecten.
                        device_info.update({"sensorState": [{"name": "value", "value": val_float}]})
                except (ValueError, TypeError):
                    device_info = {"online": False}
            
            devices[entity_id] = device_info

        return jsonify({"requestId":intent_request.get('requestId'),"payload":{"devices":devices}})

    # ---------------- EXECUTE ----------------
    elif intent=='action.devices.EXECUTE':
        commands=intent_request['inputs'][0]['payload']['commands']
        results=[]
        for command in commands:
            for device in command['devices']:
                entity_id=device['id']
                for execution in command['execution']:
                    if execution['command']=='action.devices.commands.SetFanSpeed':
                        gh_fan = execution['params']['fanSpeed'].lower()
                        ha_fan = GH_TO_HA_FAN.get(gh_fan,'auto')
                        requests.post(f"{HA_URL}/api/services/climate/set_fan_mode",
                                    headers={"Authorization":f"Bearer {HA_TOKEN}","Content-Type":"application/json"},
                                    json={"entity_id": entity_id,"fan_mode":ha_fan})
                        results.append({"ids":[entity_id],"status":"SUCCESS","states":{"thermostatFanMode":ha_fan,"online":True}})
                    elif execution['command']=='action.devices.commands.OnOff':
                        on=execution['params']['on']
                        domain=entity_id.split('.')[0]
                        requests.post(f"{HA_URL}/api/services/{domain}/turn_{'on' if on else 'off'}",
                                    headers={"Authorization":f"Bearer {HA_TOKEN}","Content-Type":"application/json"},
                                    json={"entity_id": entity_id})
                        results.append({"ids":[entity_id],"status":"SUCCESS","states":{"on":on,"online":True}})
                    elif execution['command']=='action.devices.commands.ThermostatTemperatureSetpoint':
                        temp=execution['params']['thermostatTemperatureSetpoint']
                        requests.post(f"{HA_URL}/api/services/climate/set_temperature",
                                    headers={"Authorization":f"Bearer {HA_TOKEN}","Content-Type":"application/json"},
                                    json={"entity_id": entity_id,"temperature":temp})
                        results.append({"ids":[entity_id],"status":"SUCCESS","states":{"thermostatTemperatureSetpoint":temp,"online":True}})
                    elif execution['command']=='action.devices.commands.ThermostatSetMode':
                        gh_mode=execution['params']['thermostatMode'].lower()
                        ha_mode=GH_TO_HA_MODE.get(gh_mode,'auto')
                        requests.post(f"{HA_URL}/api/services/climate/set_hvac_mode",
                                    headers={"Authorization":f"Bearer {HA_TOKEN}","Content-Type":"application/json"},
                                    json={"entity_id": entity_id,"hvac_mode":ha_mode})
                        results.append({"ids":[entity_id],"status":"SUCCESS","states":{"thermostatMode":ha_mode,"online":True}})
        return jsonify({"requestId":intent_request.get('requestId'),"payload":{"commands":results}})

    else:
        return jsonify({"error":"unsupported intent"}),400

# ---------------- Initialization ----------------
load_tokens()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint voor monitoring."""
    try:
        # Test Home Assistant connectie
        ha_response = requests.get(f"{HA_URL}/api/states",
                                 headers={"Authorization": f"Bearer {HA_TOKEN}"},
                                 timeout=5)
        ha_status = ha_response.status_code == 200

        return jsonify({
            "status": "healthy",
            "home_assistant": "connected" if ha_status else "disconnected",
            "tokens": {
                "auth_codes": len(auth_codes),
                "access_tokens": len(access_tokens),
                "refresh_tokens": len(refresh_tokens)
            },
            "storage": "file" if USE_FILE_STORAGE else "memory"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    print("INFO: Starting OAuth server...")
    print(f"INFO: Client ID: {CLIENT_ID}")
    print(f"INFO: Home Assistant URL: {HA_URL}")
    print(f"INFO: Token storage: {'file' if USE_FILE_STORAGE else 'memory'}")
    app.run(host='0.0.0.0', port=3001, debug=False)
