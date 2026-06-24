import json
from unittest.mock import Mock

from YSimulator.YClient.client import SimulationClient


def test_hourly_summary_logs_even_when_no_actions():
    client_cls = SimulationClient.__ray_metadata__.modified_class
    client = client_cls.__new__(client_cls)
    client.action_logger = Mock()
    client.hourly_actions = []

    client_cls._log_hourly_summary(client, day=2, slot=7)

    assert client.action_logger.info.call_count == 1
    payload = json.loads(client.action_logger.info.call_args.args[0])
    assert payload["summary_type"] == "hourly"
    assert payload["day"] == 2
    assert payload["slot"] == 7
    assert payload["total_actions"] == 0
    assert payload["successful_actions"] == 0
    assert payload["total_execution_time_seconds"] == 0
    assert payload["average_execution_time_seconds"] == 0
    assert payload["actions_by_method"] == {}
    assert client.hourly_actions == []


def test_daily_summary_logs_even_when_no_actions():
    client_cls = SimulationClient.__ray_metadata__.modified_class
    client = client_cls.__new__(client_cls)
    client.action_logger = Mock()
    client.daily_actions = []

    client_cls._log_daily_summary(client, day=4)

    assert client.action_logger.info.call_count == 1
    payload = json.loads(client.action_logger.info.call_args.args[0])
    assert payload["summary_type"] == "daily"
    assert payload["day"] == 4
    assert payload["total_actions"] == 0
    assert payload["successful_actions"] == 0
    assert payload["total_execution_time_seconds"] == 0
    assert payload["average_execution_time_seconds"] == 0
    assert payload["actions_by_method"] == {}
    assert client.daily_actions == []
