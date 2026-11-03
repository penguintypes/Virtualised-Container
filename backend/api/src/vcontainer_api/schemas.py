from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VolumeMount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    target: str = Field(min_length=2, max_length=4095)


class PortMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_port: int = Field(ge=1024, le=65535)
    container_port: int = Field(ge=1, le=65535)


class ContainerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    image: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    command: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    hostname: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$",
    )
    memory_max: str | None = Field(
        default=None,
        pattern=r"^(?:max|[1-9][0-9]*[KMG]?)$",
    )
    pids_max: int | None = Field(default=None, ge=1, le=32768)
    cpu_quota: int | None = Field(default=None, ge=1000, le=1000000000)
    cpu_period: int | None = Field(default=None, ge=1000, le=1000000)
    network: Literal["bridge"] | None = None
    ip: IPv4Address | None = None
    volumes: list[VolumeMount] = Field(default_factory=list, max_length=16)
    ports: list[PortMapping] = Field(default_factory=list, max_length=16)
    environment: dict[str, str] = Field(default_factory=dict, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def accept_dashboard_fields(cls, value):
        if not isinstance(value, dict):
            return value

        data = dict(value)
        if "memory" in data and "memory_max" not in data:
            data["memory_max"] = data.pop("memory")
        if "pids" in data and "pids_max" not in data:
            data["pids_max"] = data.pop("pids")

        environment = data.pop("env", data.get("environment", {}))
        if isinstance(environment, list):
            parsed_environment = {}
            for item in environment:
                if not isinstance(item, str) or "=" not in item:
                    raise ValueError("Environment entries must use NAME=VALUE")
                name, entry_value = item.split("=", 1)
                parsed_environment[name] = entry_value
            data["environment"] = parsed_environment

        volumes = data.get("volumes")
        if isinstance(volumes, list) and any(isinstance(item, str) for item in volumes):
            parsed_volumes = []
            for item in volumes:
                if not isinstance(item, str) or ":" not in item:
                    raise ValueError("Volume entries must use NAME:/TARGET")
                name, target = item.split(":", 1)
                parsed_volumes.append({"name": name, "target": target})
            data["volumes"] = parsed_volumes

        ports = data.get("ports")
        if isinstance(ports, list) and any(isinstance(item, str) for item in ports):
            parsed_ports = []
            for item in ports:
                if not isinstance(item, str) or ":" not in item:
                    raise ValueError("Port entries must use HOST:CONTAINER")
                host_port, container_port = item.split(":", 1)
                parsed_ports.append(
                    {
                        "host_port": host_port,
                        "container_port": container_port,
                    }
                )
            data["ports"] = parsed_ports

        return data


class ImagePull(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
    reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]*$",
    )


class ResourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_max: str | None = Field(
        default=None,
        pattern=r"^(?:max|[1-9][0-9]*[KMG]?)$",
    )
    pids_max: int | None = Field(default=None, ge=1, le=32768)
    cpu_quota: int | None = Field(default=None, ge=1000, le=1000000000)
    cpu_period: int | None = Field(default=None, ge=1000, le=1000000)


class VolumeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")


class ComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yaml: str = Field(min_length=1, max_length=1_048_576)
