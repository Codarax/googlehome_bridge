import requests
from server import HAClient


def test_get_entities_handles_connection_error(monkeypatch):
	client = HAClient()

	def raise_conn(*args, **kwargs):
		raise requests.exceptions.ConnectionError("unable to connect")

	monkeypatch.setattr(client.session, 'get', raise_conn)

	# On connection error the method should return an empty list
	assert client.get_entities() == []


def test_get_entity_state_handles_connection_error(monkeypatch):
	client = HAClient()

	def raise_conn(*args, **kwargs):
		raise requests.exceptions.ConnectionError("unable to connect")

	monkeypatch.setattr(client.session, 'get', raise_conn)

	# On connection error the method should return None
	assert client.get_entity_state('light.test_entity') is None


def test_call_service_handles_connection_error(monkeypatch):
	client = HAClient()

	def raise_conn(*args, **kwargs):
		raise requests.exceptions.ConnectionError("unable to connect")

	monkeypatch.setattr(client.session, 'post', raise_conn)

	# On connection error the method should return None
	assert client.call_service('light', 'turn_on', 'light.test_entity') is None

