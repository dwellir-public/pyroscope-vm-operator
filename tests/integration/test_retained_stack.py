"""Exercise a local charm artifact in the explicitly selected retained reference model.

These tests never create or destroy models and never remove applications or storage.
The Pyroscope application and integrations remain available after the run.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import struct
import time
import uuid
from pathlib import Path

import jubilant
import pytest

MODEL = "localhost-localhost:admin/machine-observability-v3-reference"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """Reuse only the explicit reference model and preserve before/after status evidence."""
    model = os.environ.get("JUJU_TEST_MODEL")
    if not model:
        pytest.skip("Set JUJU_TEST_MODEL to the retained localhost-localhost reference model")
    if model != MODEL:
        pytest.fail(f"This suite only permits the retained test model {MODEL}")
    artifact = Path(os.environ.get("CHARM_PATH", ""))
    if not artifact.is_file() or artifact.suffix != ".charm":
        pytest.fail("CHARM_PATH must point to a built local .charm artifact")
    juju = jubilant.Juju(model=model, cli_binary=os.environ.get("JUJU_BIN"), wait_timeout=900)
    evidence = tmp_path_factory.mktemp("retained-stack-status")
    before = json.loads(juju.cli("status", "--format", "json"))
    (evidence / "before.json").write_text(json.dumps(before, indent=2))
    app = os.environ.get("PYROSCOPE_APP", "pyroscope-vm")
    existing = before.get("applications", {}).get(app)
    if existing:
        if existing.get("charm-name") != "pyroscope-vm":
            pytest.fail("Refusing to refresh an application using another charm")
        juju.refresh(app, path=artifact.resolve())
    else:
        juju.deploy(artifact.resolve(), app=app, base="ubuntu@24.04")
    juju.wait(lambda status: jubilant.all_active(status, app))
    integrate_existing(juju, app, before)
    juju.wait(lambda status: jubilant.all_active(status, app))
    collector = os.environ.get("COLLECTOR_APP")
    if collector:
        juju.wait(lambda status: jubilant.all_active(status, app, collector))
    unit = next(iter(juju.status().get_units(app)))
    try:
        yield juju, app, unit
    finally:
        after = json.loads(juju.cli("status", "--format", "json"))
        (evidence / "after.json").write_text(json.dumps(after, indent=2))
        assert set(before.get("applications", {})) <= set(after.get("applications", {}))


def integrate_existing(juju: jubilant.Juju, app: str, before: dict) -> None:
    """Add only missing integrations to explicitly named existing collector and Grafana apps."""
    for variable, endpoint in [
        ("COLLECTOR_APP", "send-profiles"),
        ("GRAFANA_APP", "grafana-source"),
    ]:
        remote = os.environ.get(variable)
        if not remote:
            continue
        if remote not in before.get("applications", {}):
            pytest.fail(f"{variable} must identify an already deployed application")
        provider_endpoint = "profiling" if variable == "COLLECTOR_APP" else "grafana-source"
        current = json.loads(juju.cli("status", "--format", "json"))
        related = any(
            relation.get("related-application") == remote
            for relation in current.get("applications", {})
            .get(app, {})
            .get("relations", {})
            .get(provider_endpoint, [])
        )
        if not related:
            juju.integrate(f"{remote}:{endpoint}", f"{app}:{provider_endpoint}")


def remote_json(juju, unit: str, path: str, body: dict) -> dict:
    """Send a local backend API request from its unit without exposing ports externally."""
    code = (
        "import json,urllib.request; "
        f"body=json.dumps({body!r}).encode(); "
        f'req=urllib.request.Request("http://127.0.0.1:4040{path}",data=body,'
        'headers={"Content-Type":"application/json"}); '
        "print(urllib.request.urlopen(req,timeout=15).read().decode())"
    )
    return json.loads(juju.exec("python3", "-c", code, unit=unit).stdout)


def varint(value: int) -> bytes:
    """Encode a protobuf unsigned integer for the small synthetic pprof fixture."""
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def field(number: int, value: int | bytes) -> bytes:
    """Encode an integer or length-delimited protobuf field without extra dependencies."""
    if isinstance(value, bytes):
        return varint(number * 8 + 2) + varint(len(value)) + value
    return varint(number * 8) + varint(value)


def cpu_profile() -> bytes:
    """Build one valid pprof CPU sample with a named function and current timestamp."""
    profile = field(1, field(1, 1) + field(2, 2))
    profile += field(2, field(1, varint(1)) + field(2, varint(10000000)))
    profile += field(4, field(1, 1) + field(4, field(1, 1) + field(2, 1)))
    profile += field(5, field(1, 1) + field(2, 3) + field(4, 4))
    for value in (b"", b"cpu", b"nanoseconds", b"pyroscope_vm_smoke", b"smoke.py"):
        profile += field(6, value)
    profile += field(9, time.time_ns()) + field(10, 1000000000)
    profile += field(11, field(1, 1) + field(2, 2)) + field(12, 10000000)
    return gzip.compress(profile)


def wait_for_service(juju, unit: str, service: str) -> None:
    """Require a fresh service label to appear after actual profile ingestion."""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = remote_json(
            juju,
            unit,
            "/querier.v1.QuerierService/LabelValues",
            {
                "name": "service_name",
                "start": int((time.time() - 120) * 1000),
                "end": int((time.time() + 10) * 1000),
            },
        )
        if service in result.get("names", []):
            return
        time.sleep(2)
    pytest.fail("Newly ingested profiling service was not queryable within 60 seconds")


def assert_profile_stack(juju, unit: str, service: str, function: str | None) -> None:
    """Require nonzero stack samples rather than treating indexed labels as full ingestion."""
    window = {"start": int((time.time() - 120) * 1000), "end": int((time.time() + 10) * 1000)}
    types = remote_json(juju, unit, "/querier.v1.QuerierService/ProfileTypes", window)
    for profile_type in types.get("profileTypes", []):
        if profile_type.get("sampleType") != "cpu":
            continue
        result = remote_json(
            juju,
            unit,
            "/querier.v1.QuerierService/SelectMergeStacktraces",
            {
                **window,
                "profileTypeID": profile_type["ID"],
                "labelSelector": "{service_name=" + json.dumps(service) + "}",
            },
        )
        graph = result.get("flamegraph", {})
        if int(graph.get("total", 0)) > 0 and (
            function in graph.get("names", []) if function else len(graph.get("names", [])) > 1
        ):
            return
    pytest.fail("Ingested service has no matching nonzero CPU stack samples")


def test_native_profile_ingestion_and_query(stack):
    juju, _, unit = stack
    service = "pyroscope-vm-smoke-" + uuid.uuid4().hex
    payload = base64.b64encode(cpu_profile()).decode()
    code = (
        "import base64,time,urllib.request; "
        f"body=base64.b64decode({payload!r}); "
        f'url="http://127.0.0.1:4040/ingest?name={service}&format=pprof&from="'
        '+str(int(time.time())-1)+"&until="+str(int(time.time())); '
        "req=urllib.request.Request(url,data=body,"
        'headers={"Content-Type":"application/octet-stream"}); '
        "print(urllib.request.urlopen(req,timeout=15).status)"
    )
    assert juju.exec("python3", "-c", code, unit=unit).stdout.strip() == "200"
    wait_for_service(juju, unit, service)
    assert_profile_stack(juju, unit, service, "pyroscope_vm_smoke")


def otlp_cpu_profile(service: str) -> bytes:
    """Build a current OTLP v0.3.0 dictionary profile for Pyroscope 1.21.0.

    Field numbers follow opentelemetry-proto v1.10.0 profiles/v1development and
    collector/profiles/v1development. Dictionary index zero is a sentinel.
    """
    dictionary = field(1, b"") + field(1, field(2, 4096) + field(4, 4))
    dictionary += field(2, b"")
    dictionary += field(2, field(1, 1) + field(2, 1) + field(3, field(1, 1) + field(2, 1)))
    dictionary += field(3, b"") + field(3, field(1, 3) + field(3, 4)) + field(4, b"")
    for value in (b"", b"cpu", b"nanoseconds", b"smoke_function", b"smoke.py"):
        dictionary += field(5, value)
    dictionary += field(6, b"") + field(7, b"") + field(7, field(1, varint(1)))
    now = time.time_ns()
    sample = field(1, 1) + field(4, varint(10000000)) + field(5, struct.pack("<Q", now))
    sample_type = field(1, 1) + field(2, 2)
    profile = field(1, sample_type) + field(2, sample)
    profile += varint(3 * 8 + 1) + struct.pack("<Q", now - 1000000000)
    profile += field(4, 1000000000) + field(5, sample_type) + field(6, 10000000)
    profile += field(7, uuid.uuid4().bytes)
    resource = field(1, field(1, b"service.name") + field(2, field(1, service.encode())))
    return field(1, field(1, resource) + field(2, field(2, profile))) + field(2, dictionary)


def test_otlp_profiles_through_selected_collector(stack):
    juju, _, backend_unit = stack
    collector = os.environ.get("COLLECTOR_APP")
    fixture = os.environ.get("OTLP_PROFILE_FIXTURE")
    service = os.environ.get("OTLP_PROFILE_SERVICE", "pyroscope-otlp-smoke-" + uuid.uuid4().hex)
    test_unit = os.environ.get("TEST_COLLECTOR_UNIT")
    if not collector and not test_unit:
        pytest.skip("Set COLLECTOR_APP or TEST_COLLECTOR_UNIT for OTLP collector testing")
    if fixture and not os.environ.get("OTLP_PROFILE_SERVICE"):
        pytest.fail("A custom OTLP fixture requires OTLP_PROFILE_SERVICE")
    # Fixture must match the deployed collector and Pyroscope v1development protocol revision.
    # A stale fixture must not pass based on profiles from an earlier test run.
    previous = remote_json(
        juju,
        backend_unit,
        "/querier.v1.QuerierService/LabelValues",
        {
            "name": "service_name",
            "start": int((time.time() - 120) * 1000),
            "end": int((time.time() + 10) * 1000),
        },
    )
    assert service not in previous.get("names", []), "Fixture service must be unique per run"
    body = Path(fixture).read_bytes() if fixture else otlp_cpu_profile(service)
    payload = base64.b64encode(body).decode()
    port = int(os.environ.get("COLLECTOR_OTLP_HTTP_PORT", "4318"))
    if not 1 <= port <= 65535:
        pytest.fail("COLLECTOR_OTLP_HTTP_PORT must be a valid port")
    unit = test_unit or next(iter(juju.status().get_units(collector)))
    code = (
        "import base64,urllib.request; "
        f"body=base64.b64decode({payload!r}); "
        f'req=urllib.request.Request("http://127.0.0.1:{port}/v1development/profiles",data=body,'
        'headers={"Content-Type":"application/x-protobuf"}); '
        "print(urllib.request.urlopen(req,timeout=15).status)"
    )
    assert juju.exec("python3", "-c", code, unit=unit).stdout.strip() == "200"
    wait_for_service(juju, backend_unit, service)
    assert_profile_stack(juju, backend_unit, service, None if fixture else "smoke_function")
