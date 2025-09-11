# Single-file OAuth server for Google Home HAVoice integration
# Consolidated version of all modules for easier deployment

from flask import Flask, request, jsonify, redirect
import jwt, time, secrets, requests, os, json
import threading
from collections import defaultdict

# ==================== CONFIGURATION ====================

# OAuth Configuration (NO hardcoded secrets – must be provided via environment)
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
HA_URL = os.getenv("HA_URL", "http://supervisor/core")
HA_TOKEN = os.getenv("HA_TOKEN")

# Home Assistant add-on loads /data/options.json later; so only warn now
if not CLIENT_ID or not CLIENT_SECRET:
    print("INFO: CLIENT_ID/CLIENT_SECRET not yet set at import time; will attempt later load.")
if not HA_TOKEN:
    print("WARNING: HA_TOKEN not set – Home Assistant API calls will fail until provided.")

# Feature flags
EXPOSE_SENSORS = os.getenv("EXPOSE_SENSORS", "false").lower() == "true"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
EXPOSE_TEMPERATURE = os.getenv("EXPOSE_TEMPERATURE", "true").lower() == "true"
EXPOSE_HUMIDITY = os.getenv("EXPOSE_HUMIDITY", "true").lower() == "true"
EXPOSE_POWER = os.getenv("EXPOSE_POWER", "false").lower() == "true"
EXPOSE_GENERIC = os.getenv("EXPOSE_GENERIC", "false").lower() == "true"
STRICT_VERIFICATION = os.getenv("STRICT_VERIFICATION", "false").lower() == "true"  # When true, mismatched states return an ERROR instead of SUCCESS

# Limits and timeouts
MAX_DEVICES = int(os.getenv("MAX_DEVICES", "50"))
TOKENS_FILE = os.getenv("TOKENS_FILE", "tokens.json")
USE_FILE_STORAGE = os.getenv("USE_FILE_STORAGE", "true").lower() == "true"
DEVICES_FILE = os.getenv("DEVICES_FILE", "devices.json")
DEVICES_LOCK = threading.Lock()

# Token lifetimes
ACCESS_TOKEN_LIFETIME = 3600    # 1 hour
AUTH_CODE_LIFETIME = 600        # 10 minutes
REFRESH_TOKEN_LIFETIME = 86400 * 30  # 30 days
SAVE_THROTTLE_SECONDS = 5

# Home Assistant settings
HA_REQUEST_TIMEOUT = 8
HA_VERIFY_SSL = False
COMMAND_VERIFICATION_DELAY = 0.5
COMMAND_SETTLE_DELAY = 1.0
MAX_RETRY_ATTEMPTS = 2
RETRY_DELAY = 1.0
FAN_MODE_CACHE_TIMEOUT = 300

# Mode mappings
GH_TO_HA_MODE = {
    'off': 'off', 'heat': 'heat', 'cool': 'cool', 'auto': 'auto',
    'fan-only': 'fan-only', 'dry': 'dry'
}

# ==================== HOME ASSISTANT CLIENT ====================

class HAClient:
    """Client for Home Assistant API communication."""

    def __init__(self):
        # Read HA connection settings at runtime so tests can monkeypatch env vars
        self.ha_url = os.getenv('HA_URL', HA_URL)
        self.ha_token = os.getenv('HA_TOKEN', HA_TOKEN)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json"
        })

    def get_entities(self):
        """Fetch all entities from Home Assistant."""
        try:
            response = self.session.get(
                f"{self.ha_url}/api/states",
                timeout=HA_REQUEST_TIMEOUT,
                verify=HA_VERIFY_SSL
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if DEBUG:
                print(f"ERROR: Failed to fetch HA entities: {e}")
            return []

    def get_entity_state(self, entity_id):
        """Get state of a specific entity."""
        try:
            response = self.session.get(
                f"{self.ha_url}/api/states/{entity_id}",
                timeout=HA_REQUEST_TIMEOUT,
                verify=HA_VERIFY_SSL
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if DEBUG:
                print(f"ERROR: Failed to get entity state for {entity_id}: {e}")
            return None

    def call_service(self, domain, service, entity_id, **kwargs):
        """Call a Home Assistant service."""
        try:
            data = {"entity_id": entity_id}
            data.update(kwargs)

            response = self.session.post(
                f"{self.ha_url}/api/services/{domain}/{service}",
                json=data,
                timeout=HA_REQUEST_TIMEOUT,
                verify=HA_VERIFY_SSL
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if DEBUG:
                print(f"ERROR: Failed to call service {domain}/{service} for {entity_id}: {e}")
            return None

    def verify_command(self, entity_id, expected_state=None, expected_attrs=None, delay=COMMAND_VERIFICATION_DELAY):
        """Verify that a command was executed successfully."""
        if delay:
            time.sleep(delay)

        entity = self.get_entity_state(entity_id)
        if not entity:
            return False, None

        success = True
        actual_state = entity.get('state')
        actual_attrs = entity.get('attributes', {})

        if expected_state and actual_state != expected_state:
            if DEBUG:
                print(f"WARNING: State verification failed for {entity_id} - expected: {expected_state}, actual: {actual_state}")
            success = False

        if expected_attrs:
            for attr, expected_value in expected_attrs.items():
                actual_value = actual_attrs.get(attr)
                if attr == 'temperature' and expected_value is not None:
                    if abs(actual_value - expected_value) >= 0.1:
                        if DEBUG:
                            print(f"WARNING: Temperature verification failed for {entity_id} - expected: {expected_value}, actual: {actual_value}")
                        success = False
                elif actual_value != expected_value:
                    if DEBUG:
                        print(f"WARNING: Attribute verification failed for {entity_id}.{attr} - expected: {expected_value}, actual: {actual_value}")
                    success = False

        return success, entity


def load_device_selections():
    """Load device selection map from DEVICES_FILE."""
    try:
        if not os.path.exists(DEVICES_FILE):
            return {}
        with open(DEVICES_FILE, 'r') as f:
            return json.load(f) or {}
    except Exception as e:
        if DEBUG:
            print(f"WARNING: Failed to load device selections: {e}")
        return {}


def save_device_selections(selections):
    """Persist device selection map atomically."""
    try:
        with DEVICES_LOCK:
            tmp = DEVICES_FILE + ".tmp"
            with open(tmp, 'w') as f:
                json.dump(selections, f, indent=2)
            os.replace(tmp, DEVICES_FILE)
    except Exception as e:
        if DEBUG:
            print(f"ERROR: Failed to save device selections: {e}")


# Global HA client
ha_client = HAClient()


def prune_device_selections(current_entities=None):
    """Remove stale entries and entries explicitly set to False.

    - If current_entities is provided (list of entity objects), only keys
      present in that list are kept.
    - Entries with a falsy value (False/0/None) are removed to avoid
      clutter; default selection is treated as False unless present.
    Returns the pruned selections dict and a boolean indicating if any
    changes were made.
    """
    try:
        selections = load_device_selections()
        original_keys = set(selections.keys())

        # If we have a list of current entities, build a set of valid ids
        valid_ids = None
        if current_entities is not None:
            valid_ids = {e.get('entity_id') for e in current_entities if e.get('entity_id')}

        # Build new dict keeping only truthy selections and valid ids
        new_selections = {}
        for k, v in selections.items():
            if not v:
                # Skip explicit falsy values (user deselected)
                continue
            if valid_ids is not None and k not in valid_ids:
                # Skip entries that no longer exist in HA
                continue
            new_selections[k] = True

        changed = set(new_selections.keys()) != original_keys
        if changed:
            save_device_selections(new_selections)
        return new_selections, changed
    except Exception as e:
        if DEBUG:
            print(f"WARNING: prune_device_selections failed: {e}")
        return selections if 'selections' in locals() else {}, False

# Fan mode cache
fan_mode_cache = {}

def get_fan_mode_mapping(entity_id, ha_client):
    """Get available fan modes for a specific device."""
    current_time = int(time.time())

    if entity_id in fan_mode_cache:
        cached_time, mapping = fan_mode_cache[entity_id]
        if current_time - cached_time < FAN_MODE_CACHE_TIMEOUT:
            return mapping
        else:
            del fan_mode_cache[entity_id]

    try:
        entity = ha_client.get_entity_state(entity_id)
        if entity:
            fan_modes = entity.get('attributes', {}).get('fan_modes', [])

            if fan_modes:
                if DEBUG:
                    print(f"DEBUG: Found fan modes for {entity_id}: {fan_modes}")

                mapping = {}
                for mode in fan_modes:
                    mapping[mode.lower()] = mode
                    mapping[f"speed_{mode.lower()}"] = mode

                fan_mode_cache[entity_id] = (current_time, mapping)
                if DEBUG:
                    print(f"DEBUG: Cached fan mode mapping for {entity_id}: {mapping}")
                return mapping
            else:
                if DEBUG:
                    print(f"WARNING: No fan_modes found for {entity_id}")

    except Exception as e:
        if DEBUG:
            print(f"ERROR: Getting fan modes for {entity_id}: {e}")

    fallback_mapping = {
        'auto': 'auto', 'low': 'low', 'medium': 'medium', 'high': 'high',
        'speed_auto': 'auto', 'speed_low': 'low', 'speed_medium': 'medium', 'speed_high': 'high'
    }

    fan_mode_cache[entity_id] = (current_time, fallback_mapping)
    return fallback_mapping

# ==================== TOKEN MANAGER ====================

class TokenManager:
    """Manages OAuth tokens with file storage and cleanup."""

    def __init__(self):
        self.auth_codes = {}
        self.access_tokens = {}
        self.refresh_tokens = {}
        self.last_save_time = 0

        if USE_FILE_STORAGE:
            self.load_tokens()

    def _now(self):
        return int(time.time())

    def cleanup_expired_tokens(self):
        """Clean up expired tokens."""
        current_time = self._now()

        expired_codes = [code for code, data in self.auth_codes.items()
                        if data.get("expires_at", 0) < current_time]
        for code in expired_codes:
            del self.auth_codes[code]

        expired_tokens = [token for token, data in self.access_tokens.items()
                         if data.get("expires_at", 0) < current_time]
        for token in expired_tokens:
            del self.access_tokens[token]

        expired_refresh = [token for token, data in self.refresh_tokens.items()
                          if data.get("expires_at", 0) < current_time]
        for token in expired_refresh:
            del self.refresh_tokens[token]

    def load_tokens(self):
        """Load tokens from file with error handling."""
        if not USE_FILE_STORAGE:
            if DEBUG:
                print("INFO: Using in-memory token storage")
            return

        try:
            if os.path.exists(TOKENS_FILE):
                with open(TOKENS_FILE, "r") as f:
                    data = json.load(f)
                    self.auth_codes = data.get("auth_codes", {})
                    self.access_tokens = data.get("access_tokens", {})
                    self.refresh_tokens = data.get("refresh_tokens", {})

                self.cleanup_expired_tokens()
                if DEBUG:
                    print(f"INFO: Loaded tokens from {TOKENS_FILE}")
            else:
                self.auth_codes, self.access_tokens, self.refresh_tokens = {}, {}, {}
                if DEBUG:
                    print(f"INFO: No token file found, starting fresh")
        except Exception as e:
            if DEBUG:
                print(f"ERROR: Failed to load tokens: {e}")
            self.auth_codes, self.access_tokens, self.refresh_tokens = {}, {}, {}

    def save_tokens(self):
        """Save tokens to file with atomic writes."""
        if not USE_FILE_STORAGE:
            return

        try:
            self.cleanup_expired_tokens()

            data = {
                "auth_codes": self.auth_codes,
                "access_tokens": self.access_tokens,
                "refresh_tokens": self.refresh_tokens
            }

            temp_file = TOKENS_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            os.replace(temp_file, TOKENS_FILE)

            if DEBUG:
                print(f"INFO: Saved {len(self.access_tokens)} access tokens, {len(self.refresh_tokens)} refresh tokens")
        except Exception as e:
            if DEBUG:
                print(f"ERROR: Failed to save tokens: {e}")

    def persist_tokens(self):
        """Persist tokens with throttling."""
        current_time = self._now()
        if current_time - self.last_save_time >= SAVE_THROTTLE_SECONDS:
            self.save_tokens()
            self.last_save_time = current_time

    def generate_auth_code(self, client_id):
        """Generate a new authorization code."""
        code = secrets.token_urlsafe(32)
        expires_at = self._now() + AUTH_CODE_LIFETIME

        self.auth_codes[code] = {
            "client_id": client_id,
            "expires_at": expires_at
        }

        self.persist_tokens()
        return code

    def consume_auth_code(self, code):
        """Consume an authorization code (one-time use)."""
        if code not in self.auth_codes:
            return None

        code_data = self.auth_codes[code]
        if code_data.get("expires_at", 0) < self._now():
            del self.auth_codes[code]
            return None

        del self.auth_codes[code]
        self.persist_tokens()
        return code_data

    def generate_access_token(self, client_id):
        """Generate a new JWT access token."""
        payload = {
            "client_id": client_id,
            "iat": self._now(),
            "exp": self._now() + ACCESS_TOKEN_LIFETIME,
            "type": "access"
        }
        token = jwt.encode(payload, CLIENT_SECRET, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode('utf-8')

        self.access_tokens[token] = {
            "client_id": client_id,
            "expires_at": payload["exp"]
        }

        self.persist_tokens()
        return token

    def validate_access_token(self, token):
        """Validate an access token."""
        try:
            if token not in self.access_tokens:
                return None

            token_data = self.access_tokens[token]
            if token_data.get("expires_at", 0) < self._now():
                del self.access_tokens[token]
                return None

            payload = jwt.decode(token, CLIENT_SECRET, algorithms=["HS256"])
            return payload

        except jwt.ExpiredSignatureError:
            if token in self.access_tokens:
                del self.access_tokens[token]
            return None
        except jwt.InvalidTokenError:
            return None

    def generate_refresh_token(self, client_id):
        """Generate a new refresh token."""
        payload = {
            "client_id": client_id,
            "iat": self._now(),
            "exp": self._now() + REFRESH_TOKEN_LIFETIME,
            "type": "refresh"
        }
        token = jwt.encode(payload, CLIENT_SECRET, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode('utf-8')

        self.refresh_tokens[token] = {
            "client_id": client_id,
            "expires_at": payload["exp"]
        }

        self.persist_tokens()
        return token

    def validate_refresh_token(self, token):
        """Validate a refresh token."""
        try:
            if token not in self.refresh_tokens:
                return None

            token_data = self.refresh_tokens[token]
            if token_data.get("expires_at", 0) < self._now():
                del self.refresh_tokens[token]
                return None

            payload = jwt.decode(token, CLIENT_SECRET, algorithms=["HS256"])
            return payload

        except jwt.ExpiredSignatureError:
            if token in self.refresh_tokens:
                del self.refresh_tokens[token]
            return None
        except jwt.InvalidTokenError:
            return None

# Global token manager
token_manager = TokenManager()

# Simple in-memory admin sessions (token -> {expires_at: int})
admin_sessions = {}


# ==================== DEVICE MANAGER ====================

class DeviceManager:
    """Manages device discovery and mapping for Google Home."""

    def __init__(self):
        self.entities_cache = []
        self.cache_timestamp = 0
        self.cache_timeout = 60

    def _should_skip_entity(self, entity):
        """Check if entity should be skipped."""
        entity_id = entity.get('entity_id', '')
        attributes = entity.get('attributes', {})
        friendly_name = attributes.get('friendly_name', entity_id)
        device_class = attributes.get('device_class', '')
        state = entity.get('state', '')

        if state in ['unknown', 'unavailable', None]:
            return True

        if len(friendly_name) <= 3:
            return True

        if any(skip in entity_id.lower() for skip in ['last_', 'timestamp', 'date', 'time']):
            return True

        return False

    def _is_priority_entity(self, entity):
        """Check if entity is a priority device."""
        entity_id = entity.get('entity_id', '')

        return (
            entity_id.startswith('climate.') or
            (entity_id.startswith('light.') and 'bedroom' in entity_id.lower()) or
            (entity_id.startswith('switch.') and any(imp in entity_id.lower() for imp in ['main', 'living', 'kitchen'])) or
            (entity_id.startswith('binary_sensor.') and entity.get('attributes', {}).get('device_class') in ('door', 'opening') and
             any(imp in entity_id.lower() for imp in ['front', 'main', 'back']))
        )

    def _create_switch_device(self, entity):
        """Create Google Home device config for switch/light."""
        entity_id = entity.get('entity_id')
        attributes = entity.get('attributes', {})
        friendly_name = attributes.get('friendly_name', entity_id)
        is_light = entity_id.startswith('light.')
        gh_type = 'action.devices.types.LIGHT' if is_light else 'action.devices.types.SWITCH'
        traits = ['action.devices.traits.OnOff']
        # Add Brightness trait if HA entity exposes brightness (0-255) like standard lights
        if is_light and 'brightness' in attributes:
            traits.append('action.devices.traits.Brightness')
        device = {
            'id': entity_id,
            'type': gh_type,
            'traits': traits,
            'name': {'name': friendly_name},
            'willReportState': True
        }
        return device

    def _create_climate_device(self, entity):
        """Create Google Home device config for climate/airco."""
        entity_id = entity.get('entity_id')
        attributes = entity.get('attributes', {})
        friendly_name = attributes.get('friendly_name', entity_id)
        fan_modes = attributes.get('fan_modes', ['auto', 'low', 'medium', 'high'])

        speeds = []
        for mode in fan_modes:
            speed_name = f"speed_{mode.lower()}"
            speeds.append({
                'speed_name': speed_name,
                'speed_values': [{'speed_synonym': [mode], 'lang': 'en'}]
            })

        return {
            'id': entity_id,
            'type': 'action.devices.types.AC_UNIT',
            'traits': ['action.devices.traits.OnOff', 'action.devices.traits.TemperatureSetting', 'action.devices.traits.FanSpeed'],
            'name': {'name': friendly_name},
            'willReportState': True,
            'attributes': {
                'availableThermostatModes': 'off,heat,cool,auto,fan-only,dry',
                'thermostatTemperatureUnit': attributes.get('unit_of_measurement', 'C'),
                'availableFanSpeeds': {
                    'speeds': speeds,
                    'ordered': True
                },
                'reversible': False
            }
        }

    def _create_binary_sensor_device(self, entity):
        """Create Google Home device config for binary sensor."""
        entity_id = entity.get('entity_id')
        attributes = entity.get('attributes', {})
        friendly_name = attributes.get('friendly_name', entity_id)

        return {
            'id': entity_id,
            'type': 'action.devices.types.SENSOR',
            'traits': ['action.devices.traits.OpenClose'],
            'name': {'name': friendly_name},
            'willReportState': True
        }

    def _create_sensor_device(self, entity):
        """Create Google Home device config for sensor."""
        entity_id = entity.get('entity_id')
        attributes = entity.get('attributes', {})
        friendly_name = attributes.get('friendly_name', entity_id)
        device_class = attributes.get('device_class', '')
        state = entity.get('state', '')

        # Export battery sensors explicitly as a sensor with percentage unit
        if device_class in ('battery', 'battery_sensor') or 'battery' in entity_id.lower():
            return {
                'id': entity_id,
                'type': 'action.devices.types.SENSOR',
                'traits': ['action.devices.traits.SensorState'],
                'name': {'name': friendly_name},
                'willReportState': True,
                'attributes': {
                    'sensorStatesSupported': [{
                        'name': 'Battery',
                        'numericCapabilities': {
                            'rawValueUnit': 'PERCENTAGE'
                        }
                    }]
                }
            }

        if (EXPOSE_TEMPERATURE and
            (device_class in ('temperature', 'temperature_sensor') or
             'temperature' in entity_id.lower() or 'temp' in entity_id.lower())):
            return {
                'id': entity_id,
                'type': 'action.devices.types.SENSOR',
                'traits': ['action.devices.traits.SensorState'],
                'name': {'name': friendly_name},
                'willReportState': True,
                'attributes': {
                    'sensorStatesSupported': [{
                        'name': 'Temperature',
                        'numericCapabilities': {
                            'rawValueUnit': 'CELSIUS'
                        }
                    }]
                }
            }

        elif (EXPOSE_HUMIDITY and
              (device_class in ('humidity', 'humidity_sensor') or
               'humidity' in entity_id.lower() or 'vochtigheid' in entity_id.lower())):
            return {
                'id': entity_id,
                'type': 'action.devices.types.SENSOR',
                'traits': ['action.devices.traits.SensorState'],
                'name': {'name': friendly_name},
                'willReportState': True,
                'attributes': {
                    'sensorStatesSupported': [{
                        'name': 'Humidity',
                        'numericCapabilities': {
                            'rawValueUnit': 'PERCENTAGE'
                        }
                    }]
                }
            }

        elif (EXPOSE_POWER and
              (device_class in ('power', 'energy') or
               any(x in entity_id.lower() for x in ('power', 'energy', 'solar', 'generation', 'watt', 'kw', 'kwh')))):
            return {
                'id': entity_id,
                'type': 'action.devices.types.SENSOR',
                'traits': ['action.devices.traits.SensorState'],
                'name': {'name': friendly_name},
                'willReportState': True,
                'attributes': {
                    'sensorStatesSupported': [{
                        'name': 'Power',
                        'numericCapabilities': {
                            'rawValueUnit': 'WATTS'
                        }
                    }]
                }
            }

        elif (EXPOSE_GENERIC and state.replace('.', '').replace('-', '').isdigit()):
            return {
                'id': entity_id,
                'type': 'action.devices.types.SENSOR',
                'traits': ['action.devices.traits.SensorState'],
                'name': {'name': friendly_name},
                'willReportState': True,
                'attributes': {
                    'sensorStatesSupported': [{
                        'name': 'Value',
                        'numericCapabilities': {
                            'rawValueUnit': 'UNKNOWN'
                        }
                    }]
                }
            }

        return None

    def get_sync_devices(self):
        """Generate the list of devices for the SYNC response."""
        current_time = int(time.time())

        if current_time - self.cache_timestamp > self.cache_timeout:
            self.entities_cache = ha_client.get_entities()
            self.cache_timestamp = current_time

        entities = self.entities_cache
        devices = []

        priority_entities = []
        regular_entities = []

        # First pass: classify entities into priority and regular lists
        for entity in entities:
            if self._should_skip_entity(entity):
                continue

            if self._is_priority_entity(entity):
                priority_entities.append(entity)
            else:
                regular_entities.append(entity)

        all_entities = priority_entities + regular_entities

        # Load selections once per sync
        selections = load_device_selections()

        # Second pass: build devices list from the ordered entities
        for entity in all_entities:
            if len(devices) >= MAX_DEVICES:
                if DEBUG:
                    print(f"DEBUG: Reached MAX_DEVICES limit ({MAX_DEVICES}), stopping")
                break

            entity_id = entity.get('entity_id')

            # Only include the device if it's explicitly selected in DEVICES_FILE
            allowed = selections.get(entity_id, False)
            if not allowed:
                # skip devices that are not selected
                continue

            if entity_id.startswith('light.') or entity_id.startswith('switch.'):
                device = self._create_switch_device(entity)
                if device:
                    devices.append(device)

            elif entity_id.startswith('climate.'):
                device = self._create_climate_device(entity)
                if device:
                    devices.append(device)

            elif (entity_id.startswith('binary_sensor.') and
                  entity.get('attributes', {}).get('device_class') in ('door', 'opening')):
                device = self._create_binary_sensor_device(entity)
                if device:
                    devices.append(device)

            elif entity_id.startswith('sensor.'):
                device = self._create_sensor_device(entity)
                if device:
                    # Only include sensor devices if explicitly selected
                    if allowed:
                        devices.append(device)

        if DEBUG:
            print(f"DEBUG: Generated {len(devices)} devices (max {MAX_DEVICES})")
            device_types = {}
            for d in devices:
                t = d.get('type', 'unknown')
                device_types[t] = device_types.get(t, 0) + 1
            print(f"DEBUG: Device types: {device_types}")

        return devices


# (admin endpoints moved below after app is created)

# Global device manager
device_manager = DeviceManager()

# ==================== COMMAND HANDLER ====================

class CommandQueue:
    """Queue for managing commands per device to prevent race conditions."""

    def __init__(self):
        self.queues = defaultdict(list)
        self.locks = defaultdict(threading.Lock)
        self.results = {}

    def add_command(self, device_id, command_func, *args, **kwargs):
        """Add a command to the queue for a specific device."""
        with self.locks[device_id]:
            command_id = f"{device_id}_{int(time.time() * 1000)}"
            self.queues[device_id].append((command_id, command_func, args, kwargs))
            return command_id

    def process_queue(self, device_id):
        """Process all commands in the queue for a device."""
        with self.locks[device_id]:
            queue = self.queues[device_id]
            if not queue:
                return []

            results = []
            for command_id, command_func, args, kwargs in queue:
                try:
                    result = command_func(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    if DEBUG:
                        print(f"ERROR: Command {command_id} failed: {e}")
                    results.append({
                        "ids": [device_id],
                        "status": "ERROR",
                        "errorCode": "deviceOffline"
                    })

            self.queues[device_id] = []
            return results

class CommandHandler:
    """Handles Google Home EXECUTE commands with improved reliability."""

    def __init__(self):
        self.queue = CommandQueue()

    def _execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with retry logic."""
        for attempt in range(MAX_RETRY_ATTEMPTS + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < MAX_RETRY_ATTEMPTS:
                    if DEBUG:
                        print(f"WARNING: Attempt {attempt + 1} failed, retrying in {RETRY_DELAY}s: {e}")
                    time.sleep(RETRY_DELAY)
                else:
                    if DEBUG:
                        print(f"ERROR: All retry attempts failed: {e}")
                    raise e

    def _handle_on_off(self, entity_id, on):
        """Handle OnOff command."""
        domain = entity_id.split('.')[0]
        expected_state = 'on' if on else 'off'

        if DEBUG:
            print(f"DEBUG: OnOff command for {entity_id} - requested state: {on}")

        result = self._execute_with_retry(
            ha_client.call_service,
            domain,
            'turn_on' if on else 'turn_off',
            entity_id
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        success, entity = ha_client.verify_command(
            entity_id,
            expected_state=expected_state,
            delay=COMMAND_SETTLE_DELAY
        )

        if success:
            if DEBUG:
                print(f"SUCCESS: {entity_id} successfully turned {'on' if on else 'off'}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"on": on, "online": True}}
        else:
            actual_state = entity.get('state') if entity else 'unknown'
            # One extra verification attempt before deciding
            if DEBUG:
                print(f"DEBUG: Verification failed for {entity_id}, retrying once (strict={STRICT_VERIFICATION})")
            retry_success, retry_entity = ha_client.verify_command(
                entity_id,
                expected_state=expected_state,
                delay=COMMAND_VERIFICATION_DELAY
            )
            if retry_success:
                if DEBUG:
                    print(f"SUCCESS: {entity_id} matched expected state on second attempt")
                return {"ids": [entity_id], "status": "SUCCESS", "states": {"on": on, "online": True}}
            # Decide outcome based on strict flag
            if STRICT_VERIFICATION:
                if DEBUG:
                    print(f"ERROR: {entity_id} state mismatch (expected {expected_state}, got {actual_state}) -> reporting deviceNotResponding")
                return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceNotResponding"}
            if DEBUG:
                print(f"WARNING: {entity_id} command sent but device shows {actual_state} instead of {expected_state}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"on": actual_state == 'on', "online": True}}

    def _handle_fan_speed(self, entity_id, fan_speed):
        """Handle FanSpeed command."""
        if fan_speed.startswith('speed_'):
            gh_fan = fan_speed[6:]
        else:
            gh_fan = fan_speed.lower()

        fan_mapping = get_fan_mode_mapping(entity_id, ha_client)
        ha_fan = fan_mapping.get(gh_fan, 'auto')

        if DEBUG:
            print(f"DEBUG: Fan speed request - GH: {fan_speed}, Parsed: {gh_fan}, HA: {ha_fan}, Available: {list(fan_mapping.keys())}")

        result = self._execute_with_retry(
            ha_client.call_service,
            'climate',
            'set_fan_mode',
            entity_id,
            fan_mode=ha_fan
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        success, entity = ha_client.verify_command(
            entity_id,
            expected_attrs={'fan_mode': ha_fan},
            delay=COMMAND_SETTLE_DELAY
        )

        if success:
            if DEBUG:
                print(f"SUCCESS: Fan speed changed to {ha_fan}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"currentFanSpeedSetting": f"speed_{ha_fan.lower()}", "online": True}}
        else:
            actual_fan_mode = entity.get('attributes', {}).get('fan_mode') if entity else 'auto'
            if DEBUG:
                print(f"DEBUG: Fan speed verification failed for {entity_id}, retrying (strict={STRICT_VERIFICATION})")
            retry_success, retry_entity = ha_client.verify_command(
                entity_id,
                expected_attrs={'fan_mode': ha_fan},
                delay=COMMAND_VERIFICATION_DELAY
            )
            if retry_success:
                if DEBUG:
                    print(f"SUCCESS: Fan speed matched on second attempt for {entity_id}")
                return {"ids": [entity_id], "status": "SUCCESS", "states": {"currentFanSpeedSetting": f"speed_{ha_fan.lower()}", "online": True}}
            if STRICT_VERIFICATION:
                if DEBUG:
                    print(f"ERROR: Fan speed mismatch (expected {ha_fan}, got {actual_fan_mode}) -> reporting deviceNotResponding")
                return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceNotResponding"}
            if DEBUG:
                print(f"WARNING: Fan speed command sent but device shows {actual_fan_mode} instead of {ha_fan}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"currentFanSpeedSetting": f"speed_{actual_fan_mode.lower()}", "online": True}}

    def _handle_temperature_setpoint(self, entity_id, temperature):
        """Handle ThermostatTemperatureSetpoint command."""
        if DEBUG:
            print(f"DEBUG: Temperature setpoint command for {entity_id} - requested: {temperature}°C")

        result = self._execute_with_retry(
            ha_client.call_service,
            'climate',
            'set_temperature',
            entity_id,
            temperature=temperature
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        success, entity = ha_client.verify_command(
            entity_id,
            expected_attrs={'temperature': temperature},
            delay=COMMAND_SETTLE_DELAY
        )

        if success:
            if DEBUG:
                print(f"SUCCESS: {entity_id} temperature set to {temperature}°C")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatTemperatureSetpoint": temperature, "online": True}}
        else:
            actual_temp = entity.get('attributes', {}).get('temperature') if entity else temperature
            if DEBUG:
                print(f"DEBUG: Temperature verification failed for {entity_id}, retrying (strict={STRICT_VERIFICATION})")
            retry_success, retry_entity = ha_client.verify_command(
                entity_id,
                expected_attrs={'temperature': temperature},
                delay=COMMAND_VERIFICATION_DELAY
            )
            if retry_success:
                if DEBUG:
                    print(f"SUCCESS: Temperature matched on second attempt for {entity_id}")
                return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatTemperatureSetpoint": temperature, "online": True}}
            if STRICT_VERIFICATION:
                if DEBUG:
                    print(f"ERROR: Temperature mismatch (expected {temperature}, got {actual_temp}) -> reporting deviceNotResponding")
                return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceNotResponding"}
            if DEBUG:
                print(f"WARNING: {entity_id} temperature command sent but device shows {actual_temp}°C instead of {temperature}°C")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatTemperatureSetpoint": actual_temp, "online": True}}

    def _handle_thermostat_mode(self, entity_id, thermostat_mode):
        """Handle ThermostatSetMode command."""
        gh_mode = thermostat_mode.lower()
        ha_mode = GH_TO_HA_MODE.get(gh_mode, 'auto')

        if DEBUG:
            print(f"DEBUG: Thermostat mode command for {entity_id} - requested: {gh_mode}, HA mode: {ha_mode}")

        result = self._execute_with_retry(
            ha_client.call_service,
            'climate',
            'set_hvac_mode',
            entity_id,
            hvac_mode=ha_mode
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        success, entity = ha_client.verify_command(
            entity_id,
            expected_state=ha_mode,
            delay=COMMAND_SETTLE_DELAY
        )

        if success:
            if DEBUG:
                print(f"SUCCESS: {entity_id} mode set to {ha_mode}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatMode": ha_mode, "online": True}}
        else:
            actual_mode = entity.get('state') if entity else ha_mode
            if DEBUG:
                print(f"DEBUG: Mode verification failed for {entity_id}, retrying (strict={STRICT_VERIFICATION})")
            retry_success, retry_entity = ha_client.verify_command(
                entity_id,
                expected_state=ha_mode,
                delay=COMMAND_VERIFICATION_DELAY
            )
            if retry_success:
                if DEBUG:
                    print(f"SUCCESS: Mode matched on second attempt for {entity_id}")
                return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatMode": ha_mode, "online": True}}
            if STRICT_VERIFICATION:
                if DEBUG:
                    print(f"ERROR: Mode mismatch (expected {ha_mode}, got {actual_mode}) -> reporting deviceNotResponding")
                return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceNotResponding"}
            if DEBUG:
                print(f"WARNING: {entity_id} mode command sent but device shows {actual_mode} instead of {ha_mode}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatMode": actual_mode, "online": True}}

    def execute_commands(self, commands):
        """Execute a list of commands with proper queuing and error handling."""
        all_results = []

        device_commands = defaultdict(list)

        for command in commands:
            for device in command['devices']:
                entity_id = device['id']
                for execution in command['execution']:
                    device_commands[entity_id].append(execution)

        for entity_id, executions in device_commands.items():
            device_results = []

            for execution in executions:
                command_name = execution['command']

                try:
                    if command_name == 'action.devices.commands.OnOff':
                        result = self._handle_on_off(entity_id, execution['params']['on'])
                        device_results.append(result)
                    elif command_name == 'action.devices.commands.BrightnessAbsolute':
                        # Translate percentage (0-100) to HA brightness (0-255)
                        percent = execution['params'].get('brightness')
                        if percent is None:
                            device_results.append({"ids": [entity_id], "status": "ERROR", "errorCode": "protocolError"})
                        else:
                            ha_brightness = max(0, min(255, int(round(percent * 255 / 100))))
                            domain = entity_id.split('.')[0]
                            # call turn_on with brightness
                            if DEBUG:
                                print(f"DEBUG: Brightness command for {entity_id} -> {percent}% ({ha_brightness})")
                            result_call = self._execute_with_retry(
                                ha_client.call_service,
                                domain,
                                'turn_on',
                                entity_id,
                                brightness=ha_brightness
                            )
                            if result_call is None:
                                device_results.append({"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"})
                            else:
                                # verify by reading state; brightness mismatch only logs warning (optionally strict)
                                success, ent = ha_client.verify_command(entity_id, expected_state='on', delay=COMMAND_VERIFICATION_DELAY)
                                actual_brightness = None
                                if ent:
                                    actual_brightness = ent.get('attributes', {}).get('brightness')
                                if actual_brightness is not None:
                                    actual_percent = int(round(actual_brightness * 100 / 255))
                                else:
                                    actual_percent = percent
                                if STRICT_VERIFICATION and actual_brightness is not None:
                                    expected_ha = ha_brightness
                                    if abs(actual_brightness - expected_ha) > 5:  # tolerance
                                        device_results.append({"ids": [entity_id], "status": "ERROR", "errorCode": "deviceNotResponding"})
                                        continue
                                device_results.append({"ids": [entity_id], "status": "SUCCESS", "states": {"online": True, "on": True, "brightness": actual_percent}})

                    elif command_name == 'action.devices.commands.SetFanSpeed':
                        result = self._handle_fan_speed(entity_id, execution['params']['fanSpeed'])
                        device_results.append(result)

                    elif command_name == 'action.devices.commands.ThermostatTemperatureSetpoint':
                        result = self._handle_temperature_setpoint(entity_id, execution['params']['thermostatTemperatureSetpoint'])
                        device_results.append(result)

                    elif command_name == 'action.devices.commands.ThermostatSetMode':
                        result = self._handle_thermostat_mode(entity_id, execution['params']['thermostatMode'])
                        device_results.append(result)

                    else:
                        if DEBUG:
                            print(f"WARNING: Unsupported command {command_name} for {entity_id}")
                        device_results.append({
                            "ids": [entity_id],
                            "status": "ERROR",
                            "errorCode": "commandNotSupported"
                        })

                except Exception as e:
                    if DEBUG:
                        print(f"ERROR: Failed to execute {command_name} for {entity_id}: {e}")
                    device_results.append({
                        "ids": [entity_id],
                        "status": "ERROR",
                        "errorCode": "deviceOffline"
                    })

            all_results.extend(device_results)

        return all_results

# Global command handler
command_handler = CommandHandler()

# ==================== FLASK APPLICATION ====================

app = Flask(__name__)

# Admin API key (set in production). If set, admin endpoints require header X-ADMIN-KEY with this value.
ADMIN_API_KEY = os.getenv('ADMIN_API_KEY')
# If not provided via env, allow reading from a file (useful for simple deploys).
if not ADMIN_API_KEY:
    key_file = os.getenv('ADMIN_API_KEY_FILE', 'ADMIN_API_KEY')
    try:
        if os.path.exists(key_file):
            with open(key_file, 'r') as kf:
                ADMIN_API_KEY = kf.read().strip()
    except Exception:
        # keep ADMIN_API_KEY as None if reading fails
        ADMIN_API_KEY = None

def require_admin_key():
    """Return (ok, response) tuple. If ADMIN_API_KEY is set, validate the X-ADMIN-KEY header."""
    # If no admin key is configured, allow access (no auth)
    if not ADMIN_API_KEY:
        return True, None

    # 1) Check explicit header or query param
    header = request.headers.get('X-ADMIN-KEY') or request.args.get('admin_key')
    if header == ADMIN_API_KEY:
        return True, None

    # 2) Check cookie-based admin session
    session_token = request.cookies.get('ADMIN_SESSION')
    if session_token:
        sess = admin_sessions.get(session_token)
        if sess and sess.get('expires_at', 0) > int(time.time()):
            return True, None

    return False, (jsonify({'error': 'missing or invalid admin key or session'}), 401)

@app.route('/oauth')
def oauth():
    client_id = request.args.get('client_id')
    redirect_uri = request.args.get('redirect_uri')
    state = request.args.get('state')

    if client_id != CLIENT_ID:
        return "Invalid client_id", 400

    code = token_manager.generate_auth_code(client_id)
    return redirect(f"{redirect_uri}?code={code}&state={state}")


# ----- Admin endpoints for device selection UI -----
@app.route('/admin/devices', methods=['GET'])
def admin_devices():
    """Return list of HA entities with selection flag."""
    ok, resp = require_admin_key()
    if not ok:
        return resp
    entities = ha_client.get_entities()
    # Prune stale/false entries before returning device list so UI stays clean
    selections, changed = prune_device_selections(entities)
    if changed and DEBUG:
        print(f"DEBUG: Pruned device selections, saved updated {DEVICES_FILE}")

    devices = []
    for e in entities:
        eid = e.get('entity_id')
        if not eid:
            continue
        devices.append({
            'entity_id': eid,
            'friendly_name': e.get('attributes', {}).get('friendly_name', eid),
            'state': e.get('state'),
            'device_class': e.get('attributes', {}).get('device_class'),
            # Only mark allowed if explicitly present and truthy
            'allowed': bool(selections.get(eid, False))
        })
    return jsonify({'devices': devices})


@app.route('/admin/login', methods=['POST'])
def admin_login():
    # Expect JSON {"admin_key": "..."}
    data = request.get_json() or {}
    provided = data.get('admin_key') or request.headers.get('X-ADMIN-KEY')
    if not ADMIN_API_KEY:
        return jsonify({'error': 'admin disabled'}), 403
    if provided != ADMIN_API_KEY:
        return jsonify({'error': 'invalid key'}), 401

    # create short-lived session token
    token = secrets.token_urlsafe(24)
    admin_sessions[token] = {'expires_at': int(time.time()) + 3600}
    resp = jsonify({'ok': True})
    resp.set_cookie('ADMIN_SESSION', token, httponly=True, secure=False)
    return resp


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    token = request.cookies.get('ADMIN_SESSION')
    if token and token in admin_sessions:
        del admin_sessions[token]
    resp = jsonify({'ok': True})
    resp.set_cookie('ADMIN_SESSION', '', expires=0)
    return resp


@app.route('/admin/devices/select', methods=['POST'])
def admin_devices_select():
    """Set selection for devices. Accepts JSON: {"entity_id":"...","allowed":true} or a list of such objects."""
    ok, resp = require_admin_key()
    if not ok:
        return resp
    payload = request.get_json() or {}
    selections = load_device_selections()

    if isinstance(payload, dict) and 'entity_id' in payload:
        selections[payload['entity_id']] = bool(payload.get('allowed', False))
    elif isinstance(payload, list):
        for it in payload:
            if 'entity_id' in it:
                selections[it['entity_id']] = bool(it.get('allowed', False))
    else:
        return jsonify({'error': 'invalid payload'}), 400

    # Remove any keys that are explicitly False to avoid persisting deselections
    cleaned = {k: v for k, v in selections.items() if v}
    save_device_selections(cleaned)
    # Return the cleaned mapping so the UI sees only kept (truthy) selections
    return jsonify({'ok': True, 'selections': cleaned})


# Serve a tiny admin UI (single-file) at /admin
@app.route('/admin')
def admin_ui():
        html = '''
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>HA -> Google Home Selections</title>
            <style>
                body{font-family:Segoe UI,Arial;margin:20px}
                table{border-collapse:collapse;width:100%}
                th,td{border:1px solid #ddd;padding:8px}
                th{background:#f4f4f4}
            </style>
        </head>
        <body>
            <h1>Select devices for Google Home sync</h1>
            <div id="status"></div>
            <table id="devices">
                <thead><tr><th>Allow</th><th>Entity ID</th><th>Name</th><th>State</th></tr></thead>
                <tbody></tbody>
            </table>

            <script>
                async function load(){
                    const res = await fetch('/admin/devices');
                    const status = res.status
                    const statusEl = document.getElementById('status')
                    if (status === 401){
                        statusEl.innerText = 'Geen toestemming: voer de Admin API key in via de Admin knop rechtsboven.'
                        document.getElementById('devices').style.display = 'none'
                        return
                    }
                    const data = await res.json();
                    const tbody = document.querySelector('#devices tbody');
                    tbody.innerHTML = '';
                    data.devices.forEach(d=>{
                        const tr = document.createElement('tr');
                        const cb = document.createElement('input'); cb.type='checkbox'; cb.checked = !!d.allowed;
                        cb.addEventListener('change', async ()=>{
                            await fetch('/admin/devices/select', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({entity_id:d.entity_id, allowed:cb.checked})});
                            document.getElementById('status').innerText = 'Saved';
                            setTimeout(()=>document.getElementById('status').innerText='',1500);
                        });
                        const tdAllow = document.createElement('td'); tdAllow.appendChild(cb);
                        tr.appendChild(tdAllow);
                        tr.appendChild(Object.assign(document.createElement('td'), {innerText: d.entity_id}));
                        tr.appendChild(Object.assign(document.createElement('td'), {innerText: d.friendly_name}));
                        tr.appendChild(Object.assign(document.createElement('td'), {innerText: d.state}));
                        tbody.appendChild(tr);
                    });
                }
                load();
            </script>
        </body>
        </html>
        '''
        return html

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

        code_data = token_manager.consume_auth_code(code)
        if not code_data:
            print(f"ERROR: Invalid or expired authorization code: {code}")
            return jsonify({"error": "invalid_grant"}), 400

        access_token = token_manager.generate_access_token(client_id)
        refresh_token = token_manager.generate_refresh_token(client_id)

        print(f"SUCCESS: Generated access token for client {client_id}")
        return jsonify({
            "token_type": "Bearer",
            "access_token": access_token,
            "expires_in": ACCESS_TOKEN_LIFETIME,
            "refresh_token": refresh_token
        })

    elif grant_type == 'refresh_token':
        refresh_token = request.form.get('refresh_token')

        refresh_data = token_manager.validate_refresh_token(refresh_token)
        if not refresh_data:
            print(f"ERROR: Invalid refresh token: {refresh_token}")
            return jsonify({"error": "invalid_grant"}), 400

        new_access_token = token_manager.generate_access_token(client_id)

        print(f"SUCCESS: Refreshed access token for client {client_id}")
        return jsonify({
            "token_type": "Bearer",
            "access_token": new_access_token,
            "expires_in": ACCESS_TOKEN_LIFETIME
        })

    else:
        print(f"ERROR: Unsupported grant type: {grant_type}")
        return jsonify({"error": "unsupported_grant_type"}), 400

@app.route('/smarthome', methods=['POST'])
def smarthome():
    def _validate_bearer_token():
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None, (False, jsonify({"error": "missing token"}), 401)
        token = auth_header.split()[1]

        payload = token_manager.validate_access_token(token)
        if not payload:
            return None, (False, jsonify({"error": "invalid token"}), 401)

        return payload, (True, None, None)

    payload, (ok, err, status) = _validate_bearer_token()
    if not ok:
        print(f"ERROR: Token validation failed: {err}")
        return err, status

    intent_request = request.json
    intent = intent_request['inputs'][0]['intent']

    print(f"DEBUG: Processing intent: {intent}")

    if intent == 'action.devices.SYNC':
        devices = device_manager.get_sync_devices()
        print(f"DEBUG: SYNC returning {len(devices)} devices")
        if devices:
            print(f"DEBUG: First device: {devices[0]}")
        return jsonify({"requestId": intent_request.get('requestId'), "payload": {"agentUserId": "user_ha", "devices": devices}})

    elif intent == 'action.devices.QUERY':
        devices = {}
        for device in intent_request['inputs'][0]['payload']['devices']:
            entity_id = device['id']

            state = ha_client.get_entity_state(entity_id)
            if not state:
                if DEBUG:
                    print(f"DEBUG: Could not fetch state for {entity_id}")
                devices[entity_id] = {"online": False, "error": "unavailable"}
                continue

            device_info = {"online": True}

            if entity_id.startswith('climate.'):
                hvac_state = state['state']
                fan_mode = state['attributes'].get('fan_mode', 'auto')
                device_info.update({
                    "thermostatMode": hvac_state,
                    "thermostatTemperatureSetpoint": state['attributes'].get('temperature'),
                    "currentFanSpeedSetting": f"speed_{fan_mode.lower()}"
                })
            elif entity_id.startswith('light.') or entity_id.startswith('switch.'):
                device_info.update({"on": state['state'] == 'on'})
                if entity_id.startswith('light.'):
                    br = state.get('attributes', {}).get('brightness')
                    if br is not None:
                        device_info.update({"brightness": int(round(br * 100 / 255))})
            elif entity_id.startswith('binary_sensor.'):
                device_info.update({"openPercent": 100 if state['state'] == 'on' else 0})
            elif entity_id.startswith('sensor.'):
                try:
                    val_float = float(state['state'])
                    device_class = state['attributes'].get('device_class', '')
                    entity_name_lower = entity_id.lower();

                    if (device_class in ('temperature', 'temperature_sensor') or
                        'temperature' in entity_name_lower or 'temp' in entity_name_lower):
                        device_info.update({
                            "sensorState": {
                                "name": "Temperature",
                                "currentSensorState": val_float
                            }
                        })
                    elif (device_class in ('humidity', 'humidity_sensor') or
                          'humidity' in entity_name_lower or 'vochtigheid' in entity_name_lower):
                        device_info.update({
                            "sensorState": {
                                "name": "Humidity",
                                "currentSensorState": val_float
                            }
                        })
                    elif (device_class in ('power', 'energy') or
                          any(x in entity_name_lower for x in ('power', 'energy', 'solar', 'generation', 'watt', 'kw', 'kwh'))):
                        device_info.update({
                            "sensorState": {
                                "name": "Power",
                                "currentSensorState": val_float
                            }
                        })
                    else:
                        device_info.update({
                            "sensorState": {
                                "name": "Value",
                                "currentSensorState": val_float
                            }
                        })

                except (ValueError, TypeError):
                    device_info = {"online": False, "error": "invalid_state"}

            devices[entity_id] = device_info

        return jsonify({"requestId": intent_request.get('requestId'), "payload": {"devices": devices}})

    elif intent == 'action.devices.EXECUTE':
        commands = intent_request['inputs'][0]['payload']['commands']
        results = command_handler.execute_commands(commands)
        return jsonify({"requestId": intent_request.get('requestId'), "payload": {"commands": results}})

    else:
        return jsonify({"error": "unsupported intent"}), 400

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint voor monitoring."""
    try:
        entities = ha_client.get_entities()
        ha_status = entities is not None and len(entities) > 0

        total_entities = len(entities) if entities else 0
        sync_devices = device_manager.get_sync_devices()
        exported_devices = len(sync_devices)

        return jsonify({
            "status": "healthy",
            "home_assistant": "connected" if ha_status else "disconnected",
            "configuration": {
                "expose_sensors": EXPOSE_SENSORS,
                "expose_temperature": EXPOSE_TEMPERATURE,
                "expose_humidity": EXPOSE_HUMIDITY,
                "expose_power": EXPOSE_POWER,
                "expose_generic": EXPOSE_GENERIC,
                "max_devices": MAX_DEVICES,
                "debug": DEBUG,
                "sensor_filtering": "Only sensors listed in DEVICES_FILE are exported; sensors are matched by 'sensor.' prefix",
                "airco_fix": "FanSpeed trait properly configured for climate devices"
            },
            "devices": {
                "total_in_ha": total_entities,
                "exported_to_gh": exported_devices,
                "sensor_breakdown": {
                    "temperature": len([d for d in sync_devices if d.get('id', '').startswith('sensor.') and 'Temperature' in str(d.get('attributes', {}).get('sensorStatesSupported', []))]),
                    "humidity": len([d for d in sync_devices if d.get('id', '').startswith('sensor.') and 'Humidity' in str(d.get('attributes', {}).get('sensorStatesSupported', []))]),
                    "power": len([d for d in sync_devices if d.get('id', '').startswith('sensor.') and 'Power' in str(d.get('attributes', {}).get('sensorStatesSupported', []))]),
                    "generic": len([d for d in sync_devices if d.get('id', '').startswith('sensor.') and 'Value' in str(d.get('attributes', {}).get('sensorStatesSupported', []))])
                }
            },
            "tokens": {
                "auth_codes": len(token_manager.auth_codes),
                "access_tokens": len(token_manager.access_tokens),
                "refresh_tokens": len(token_manager.refresh_tokens)
            },
            "storage": "file" if USE_FILE_STORAGE else "memory",
            "last_save": token_manager.last_save_time
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    # Map Home Assistant add-on options (if mounted as JSON) -> env (future: could parse /data/options.json)
    options_path = "/data/options.json"
    try:
        if os.path.exists(options_path):
            with open(options_path, 'r', encoding='utf-8') as f:
                opts = json.load(f)
            # Only set if not already provided explicitly
            for k_map in [
                ("client_id", "CLIENT_ID"),
                ("client_secret", "CLIENT_SECRET"),
                ("ha_url", "HA_URL"),
                ("ha_token", "HA_TOKEN"),
                ("debug", "DEBUG"),
                ("expose_sensors", "EXPOSE_SENSORS"),
                ("expose_temperature", "EXPOSE_TEMPERATURE"),
                ("expose_humidity", "EXPOSE_HUMIDITY"),
                ("expose_power", "EXPOSE_POWER"),
                ("expose_generic", "EXPOSE_GENERIC")
            ]:
                src, dst = k_map
                if src in opts and not os.getenv(dst):
                    val = opts[src]
                    # convert bools to lowercase string
                    if isinstance(val, bool):
                        val = str(val).lower()
                    os.environ[dst] = str(val)
                    print(f"INFO: Loaded option {src} -> env {dst}")
    except Exception as e:
        print(f"WARNING: Failed to load options.json: {e}")
    # Refresh globals after potential load
    try:
        CLIENT_ID = os.getenv("CLIENT_ID")
        CLIENT_SECRET = os.getenv("CLIENT_SECRET")
        HA_URL = os.getenv("HA_URL", HA_URL)
        HA_TOKEN = os.getenv("HA_TOKEN", HA_TOKEN)
        if not CLIENT_ID or not CLIENT_SECRET:
            raise RuntimeError("Missing CLIENT_ID or CLIENT_SECRET after loading /data/options.json")
    except Exception as e:
        print(f"FATAL: Configuration error: {e}")
        raise
    # ...existing code...
