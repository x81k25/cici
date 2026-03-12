"""Shared fixtures for GPU diagnostic tests."""

import subprocess
import json
import pytest


def nvidia_smi_query(*fields):
    """Run nvidia-smi query and return parsed CSV rows."""
    cmd = [
        "nvidia-smi",
        f"--query-gpu={','.join(fields)}",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    rows = []
    for line in result.stdout.strip().splitlines():
        rows.append([v.strip() for v in line.split(",")])
    return rows


@pytest.fixture(scope="session")
def gpu_inventory():
    """Return list of dicts describing each GPU."""
    fields = ["index", "name", "uuid", "memory.total", "compute_cap"]
    rows = nvidia_smi_query(*fields)
    gpus = []
    for row in rows:
        gpus.append({
            "index": int(row[0]),
            "name": row[1],
            "uuid": row[2],
            "memory_total_mib": int(row[3]),
            "compute_cap": row[4],
        })
    return gpus


@pytest.fixture(scope="session")
def rtx3060(gpu_inventory):
    """Return RTX 3060 info or skip."""
    for gpu in gpu_inventory:
        if "3060" in gpu["name"]:
            return gpu
    pytest.skip("RTX 3060 not found")


@pytest.fixture(scope="session")
def gtx960(gpu_inventory):
    """Return GTX 960 info or skip."""
    for gpu in gpu_inventory:
        if "960" in gpu["name"]:
            return gpu
    pytest.skip("GTX 960 not found")
