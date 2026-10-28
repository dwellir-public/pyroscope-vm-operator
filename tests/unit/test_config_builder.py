"""Exercise managed workload configuration independently of Juju."""

import pytest

from config_builder import S3StorageConfig, build_config, validate_package_version


def test_local_storage_and_ingestion_listener():
    config = build_config(data_dir="/var/lib/pyroscope")
    assert config["target"] == "all"
    assert config["server"]["http_listen_port"] == 4040
    assert config["server"]["grpc_listen_address"] == "127.0.0.1"
    assert config["storage"] == {
        "backend": "filesystem",
        "filesystem": {"dir": "/var/lib/pyroscope/blocks"},
    }
    assert config["pyroscopedb"]["data_path"] == "/var/lib/pyroscope/data"
    assert config["limits"]["compactor_blocks_retention_period"] == "14d"
    assert config["multitenancy_enabled"] is False


def test_persistent_paths_and_s3():
    s3 = S3StorageConfig.from_relation(
        {
            "bucket": "profiles",
            "endpoint": "https://s3.example:3900",
            "access-key": "ACCESS",
            "secret-key": "SECRET",
            "region": "test",
        }
    )
    config = build_config(data_dir="/mnt/profiles", s3=s3)
    assert config["storage"]["backend"] == "s3"
    assert config["storage"]["s3"]["endpoint"] == "s3.example:3900"
    assert config["storage"]["s3"]["insecure"] is False
    assert config["storage"]["s3"]["bucket_lookup_type"] == "path-style"
    assert config["compactor"]["data_dir"] == "/mnt/profiles/compactor"
    assert "SECRET" not in repr(s3)


@pytest.mark.parametrize(
    "details",
    [
        {},
        {"bucket": "b", "endpoint": "http://s3", "access-key": "a"},
        {"bucket": "b", "endpoint": "ftp://s3", "access-key": "a", "secret-key": "s"},
        {"bucket": "b", "endpoint": "http://user:pass@s3", "access-key": "a", "secret-key": "s"},
        {"bucket": "b", "endpoint": "http://s3/path", "access-key": "a", "secret-key": "s"},
        {
            "bucket": "b",
            "endpoint": "http://s3",
            "access-key": "a",
            "secret-key": "s",
            "path": "x",
        },
    ],
)
def test_invalid_s3_rejected_without_echoing_values(details):
    with pytest.raises(ValueError) as exc:
        S3StorageConfig.from_relation(details)
    assert "pass@" not in str(exc.value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"http_port": 0},
        {"http_port": 65536},
        {"http_port": 9095},
        {"log_level": "unexpected"},
        {"retention_period": "oops"},
        {"retention_period": "-1d"},
        {"data_dir": "relative"},
    ],
)
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        build_config(**{"data_dir": "/var/lib/pyroscope", **kwargs})


@pytest.mark.parametrize("version", ["2.0.0", "1.20.0", "", "1.21.0;echo secret"])
def test_package_pin_prevents_unsupported_architecture(version):
    with pytest.raises(ValueError):
        validate_package_version(version)


def test_package_pin_accepts_supported_version():
    assert validate_package_version("1.21.0") == "1.21.0"
