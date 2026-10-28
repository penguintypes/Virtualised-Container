from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
