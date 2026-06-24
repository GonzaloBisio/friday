"""Tests para friday.collectors.cloudwatch — CloudWatchCollector con boto3 mockeado.

No pega a AWS: los clientes ECS y CloudWatch se inyectan como MagicMock.
"""

from unittest.mock import MagicMock

import pytest

from friday.collectors.cloudwatch import CloudWatchCollector

_SERVICES = {
    "clubs-service": {"ecs": "nexcourt-dev-clubs-service", "log_group": "/nexcourt-dev/clubs"},
    "kong":          {"ecs": "nexcourt-dev-kong",          "log_group": "/nexcourt-dev/kong"},
}


def _ecs_mock(services_payload):
    ecs = MagicMock()
    ecs.describe_services.return_value = {"services": services_payload}
    return ecs


def _cw_mock(results):
    cw = MagicMock()
    cw.get_metric_data.return_value = {"MetricDataResults": results}
    return cw


class TestStatusCollection:
    def test_service_up_when_running_meets_desired(self):
        ecs = _ecs_mock([
            {"serviceName": "nexcourt-dev-clubs-service", "runningCount": 1,
             "desiredCount": 1, "status": "ACTIVE"},
        ])
        col = CloudWatchCollector(
            cluster="c", services={"clubs-service": _SERVICES["clubs-service"]},
            ecs_client=ecs, cw_client=_cw_mock([]),
        )
        points = col.collect()
        status = next(p for p in points if p.name == "status")
        assert status.value == 1.0
        assert status.service == "clubs-service"
        assert status.tags["health"] == "UP"

    def test_service_down_when_running_below_desired(self):
        ecs = _ecs_mock([
            {"serviceName": "nexcourt-dev-clubs-service", "runningCount": 0,
             "desiredCount": 2, "status": "ACTIVE"},
        ])
        col = CloudWatchCollector(
            cluster="c", services={"clubs-service": _SERVICES["clubs-service"]},
            ecs_client=ecs, cw_client=_cw_mock([]),
        )
        status = next(p for p in col.collect() if p.name == "status")
        assert status.value == 0.0
        assert status.tags["health"] == "DOWN"

    def test_emits_task_counts(self):
        ecs = _ecs_mock([
            {"serviceName": "nexcourt-dev-clubs-service", "runningCount": 2,
             "desiredCount": 3, "status": "ACTIVE"},
        ])
        col = CloudWatchCollector(
            cluster="c", services={"clubs-service": _SERVICES["clubs-service"]},
            ecs_client=ecs, cw_client=_cw_mock([]),
        )
        points = {p.name: p.value for p in col.collect()}
        assert points["tasks_running"] == 2.0
        assert points["tasks_desired"] == 3.0


class TestUtilizationCollection:
    def test_maps_cpu_and_mem_to_services(self):
        # get_metric_data devuelve por Id; el id codifica índice del servicio.
        results = [
            {"Id": "q0_cpu_percent", "Values": [12.5]},
            {"Id": "q0_mem_percent", "Values": [44.0]},
        ]
        ecs = _ecs_mock([])
        col = CloudWatchCollector(
            cluster="c", services={"clubs-service": _SERVICES["clubs-service"]},
            ecs_client=ecs, cw_client=_cw_mock(results),
        )
        points = {p.name: p for p in col.collect()}
        assert points["cpu_percent"].value == 12.5
        assert points["cpu_percent"].service == "clubs-service"
        assert points["mem_percent"].value == 44.0
        assert points["mem_percent"].unit == "%"

    def test_skips_metrics_without_datapoints(self):
        results = [{"Id": "q0_cpu_percent", "Values": []}]
        col = CloudWatchCollector(
            cluster="c", services={"clubs-service": _SERVICES["clubs-service"]},
            ecs_client=_ecs_mock([]), cw_client=_cw_mock(results),
        )
        assert all(p.name != "cpu_percent" for p in col.collect())


class TestQueryBuilding:
    def test_builds_two_queries_per_service(self):
        col = CloudWatchCollector(cluster="c", services=_SERVICES,
                                  ecs_client=MagicMock(), cw_client=MagicMock())
        queries, meta = col._build_metric_queries()
        assert len(queries) == 4  # 2 servicios × (cpu + mem)
        assert len(meta) == 4
        dims = queries[0]["MetricStat"]["Metric"]["Dimensions"]
        assert {"Name": "ClusterName", "Value": "c"} in dims


class TestEmptyServices:
    def test_no_services_returns_empty(self):
        col = CloudWatchCollector(cluster="c", services={},
                                  ecs_client=MagicMock(), cw_client=MagicMock())
        assert col.collect() == []


class ExpiredTokenException(Exception):
    """Imita el error de token SSO vencido de botocore (nombre con la pista de auth)."""


class TestAuthDegradation:
    """Token AWS vencido: el collector NO debe spamear tracebacks. Pausa con
    cooldown, marca needs_login, y se cura solo o con reset_auth()."""

    def _col(self, ecs):
        return CloudWatchCollector(
            cluster="c", services={"clubs-service": _SERVICES["clubs-service"]},
            ecs_client=ecs, cw_client=MagicMock(),
        )

    def test_auth_error_returns_empty_and_flags_login(self):
        ecs = MagicMock()
        ecs.describe_services.side_effect = ExpiredTokenException("token expired, reauthenticate")
        col = self._col(ecs)
        assert col.collect() == []        # no propaga (base.run no logea traceback)
        assert col.needs_login is True

    def test_circuit_open_stops_hammering_aws(self):
        ecs = MagicMock()
        ecs.describe_services.side_effect = ExpiredTokenException("ExpiredToken")
        col = self._col(ecs)
        col.collect()
        col.collect()
        col.collect()
        # Solo el PRIMER intento pegó a AWS; el resto se salteó por el cooldown.
        assert ecs.describe_services.call_count == 1

    def test_reset_auth_forces_retry(self):
        ecs = MagicMock()
        ecs.describe_services.side_effect = ExpiredTokenException("ExpiredToken")
        col = self._col(ecs)
        col.collect()
        col.reset_auth()
        col.collect()
        assert ecs.describe_services.call_count == 2  # reintentó tras el reset

    def test_non_auth_error_propagates(self):
        ecs = MagicMock()
        ecs.describe_services.side_effect = ValueError("bug real")
        col = self._col(ecs)
        with pytest.raises(ValueError):
            col.collect()
        assert col.needs_login is False  # un bug no marca needs_login

    def test_recovers_when_token_back(self):
        ecs = MagicMock()
        ecs.describe_services.side_effect = ExpiredTokenException("ExpiredToken")
        col = self._col(ecs)
        col.collect()
        assert col.needs_login is True
        # Token vuelve: describe_services responde OK.
        ecs.describe_services.side_effect = None
        ecs.describe_services.return_value = {"services": [
            {"serviceName": "nexcourt-dev-clubs-service", "runningCount": 1,
             "desiredCount": 1, "status": "ACTIVE"},
        ]}
        col.reset_auth()
        points = col.collect()
        assert col.needs_login is False
        assert any(p.name == "status" and p.value == 1.0 for p in points)
