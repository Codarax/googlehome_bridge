# Command handler module for Google Home EXECUTE requests
import time
import threading
from collections import defaultdict
from ha_client import ha_client, get_fan_mode_mapping
from config import (
    DEBUG, GH_TO_HA_MODE, MAX_RETRY_ATTEMPTS, RETRY_DELAY,
    COMMAND_SETTLE_DELAY
)

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

            # Clear processed commands
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

        # Execute command with retry
        result = self._execute_with_retry(
            ha_client.call_service,
            domain,
            'turn_on' if on else 'turn_off',
            entity_id
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        # Verify command execution
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
            if DEBUG:
                print(f"WARNING: {entity_id} command sent but device shows {actual_state} instead of {expected_state}")
            # Still report success but with actual state
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"on": actual_state == 'on', "online": True}}

    def _handle_fan_speed(self, entity_id, fan_speed):
        """Handle FanSpeed command."""
        # Parse speed name
        if fan_speed.startswith('speed_'):
            gh_fan = fan_speed[6:]  # Remove 'speed_' prefix
        else:
            gh_fan = fan_speed.lower()

        # Get fan mode mapping
        fan_mapping = get_fan_mode_mapping(entity_id, ha_client)
        ha_fan = fan_mapping.get(gh_fan, 'auto')

        if DEBUG:
            print(f"DEBUG: Fan speed request - GH: {fan_speed}, Parsed: {gh_fan}, HA: {ha_fan}, Available: {list(fan_mapping.keys())}")

        # Execute command with retry
        result = self._execute_with_retry(
            ha_client.call_service,
            'climate',
            'set_fan_mode',
            entity_id,
            fan_mode=ha_fan
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        # Verify command execution
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
                print(f"WARNING: Fan speed command sent but device shows {actual_fan_mode} instead of {ha_fan}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"currentFanSpeedSetting": f"speed_{actual_fan_mode.lower()}", "online": True}}

    def _handle_temperature_setpoint(self, entity_id, temperature):
        """Handle ThermostatTemperatureSetpoint command."""
        if DEBUG:
            print(f"DEBUG: Temperature setpoint command for {entity_id} - requested: {temperature}°C")

        # Execute command with retry
        result = self._execute_with_retry(
            ha_client.call_service,
            'climate',
            'set_temperature',
            entity_id,
            temperature=temperature
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        # Verify command execution
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
                print(f"WARNING: {entity_id} temperature command sent but device shows {actual_temp}°C instead of {temperature}°C")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatTemperatureSetpoint": actual_temp, "online": True}}

    def _handle_thermostat_mode(self, entity_id, thermostat_mode):
        """Handle ThermostatSetMode command."""
        gh_mode = thermostat_mode.lower()
        ha_mode = GH_TO_HA_MODE.get(gh_mode, 'auto')

        if DEBUG:
            print(f"DEBUG: Thermostat mode command for {entity_id} - requested: {gh_mode}, HA mode: {ha_mode}")

        # Execute command with retry
        result = self._execute_with_retry(
            ha_client.call_service,
            'climate',
            'set_hvac_mode',
            entity_id,
            hvac_mode=ha_mode
        )

        if result is None:
            return {"ids": [entity_id], "status": "ERROR", "errorCode": "deviceOffline"}

        # Verify command execution
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
                print(f"WARNING: {entity_id} mode command sent but device shows {actual_mode} instead of {ha_mode}")
            return {"ids": [entity_id], "status": "SUCCESS", "states": {"thermostatMode": actual_mode, "online": True}}

    def execute_commands(self, commands):
        """Execute a list of commands with proper queuing and error handling."""
        all_results = []

        # Group commands by device to prevent race conditions
        device_commands = defaultdict(list)

        for command in commands:
            for device in command['devices']:
                entity_id = device['id']
                for execution in command['execution']:
                    device_commands[entity_id].append(execution)

        # Process commands per device
        for entity_id, executions in device_commands.items():
            device_results = []

            for execution in executions:
                command_name = execution['command']

                try:
                    if command_name == 'action.devices.commands.OnOff':
                        result = self._handle_on_off(entity_id, execution['params']['on'])
                        device_results.append(result)

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

# Global command handler instance
command_handler = CommandHandler()
