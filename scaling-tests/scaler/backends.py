"""
Pluggable backends for the scaler. The scaler policy is identical regardless of
where the replicas live — only the I/O for read/write of replica count differs.

Implementations:
  - DockerComposeBackend: shells out to `docker compose scale`. Used for the
    laptop smoke test.
  - NomadBackend: POST /v1/job/{id}/scale. Used in `nomad agent -dev` and in
    the production Voltus cluster.
  - MockBackend: in-process counter. Used in unit tests.
"""
import os
import subprocess
from abc import ABC, abstractmethod
from typing import Optional

import requests


class Backend(ABC):
    @abstractmethod
    def get_count(self) -> int: ...

    @abstractmethod
    def set_count(self, n: int) -> None: ...


class MockBackend(Backend):
    def __init__(self, initial: int = 1):
        self._n = initial

    def get_count(self) -> int:
        return self._n

    def set_count(self, n: int) -> None:
        self._n = n


class DockerComposeBackend(Backend):
    def __init__(self, compose_file: str, service: str):
        self.compose_file = compose_file
        self.service = service

    def get_count(self) -> int:
        out = subprocess.check_output(
            ["docker", "compose", "-f", self.compose_file, "ps", "-q", self.service],
            text=True,
        )
        return len([line for line in out.splitlines() if line.strip()])

    def set_count(self, n: int) -> None:
        subprocess.check_call(
            ["docker", "compose", "-f", self.compose_file,
             "up", "-d", "--scale", f"{self.service}={n}", "--no-recreate", self.service]
        )


class NomadBackend(Backend):
    """
    Talks to Nomad's HTTP API. Works against `nomad agent -dev` and the
    production cluster identically — only NOMAD_ADDR / NOMAD_TOKEN differ.
    """
    def __init__(self, job_id: str, addr: Optional[str] = None, token: Optional[str] = None):
        self.job_id = job_id
        self.addr = (addr or os.environ.get("NOMAD_ADDR", "http://127.0.0.1:4646")).rstrip("/")
        self.token = token or os.environ.get("NOMAD_TOKEN")

    def _headers(self):
        return {"X-Nomad-Token": self.token} if self.token else {}

    def get_count(self) -> int:
        r = requests.get(f"{self.addr}/v1/job/{self.job_id}", headers=self._headers(), timeout=5)
        r.raise_for_status()
        spec = r.json()
        groups = spec.get("TaskGroups", [])
        return sum(int(g.get("Count", 0)) for g in groups) if groups else 0

    def set_count(self, n: int) -> None:
        for group_name in self._group_names():
            r = requests.post(
                f"{self.addr}/v1/job/{self.job_id}/scale",
                headers=self._headers(),
                json={"Count": n, "Target": {"Group": group_name},
                      "Message": f"scaler set count={n}"},
                timeout=10,
            )
            r.raise_for_status()

    def _group_names(self):
        r = requests.get(f"{self.addr}/v1/job/{self.job_id}", headers=self._headers(), timeout=5)
        r.raise_for_status()
        return [g["Name"] for g in r.json().get("TaskGroups", [])]


def from_env() -> Backend:
    kind = os.environ.get("SCALER_BACKEND", "mock").lower()
    if kind == "docker":
        return DockerComposeBackend(
            compose_file=os.environ["SCALER_COMPOSE_FILE"],
            service=os.environ.get("SCALER_SERVICE", "fake-julia"),
        )
    if kind == "nomad":
        return NomadBackend(job_id=os.environ.get("SCALER_JOB_ID", "fake-julia"))
    return MockBackend()
