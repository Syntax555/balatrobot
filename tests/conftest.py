"""Shared test configuration for BalatroBot tests."""

import asyncio
import os
import random
import time

import pytest

from balatrobot.config import Config
from balatrobot.health import check_health
from balatrobot.manager import InstanceManager


def pytest_configure(config):
    """Start Balatro instances before workers spawn.

    This runs in the main process only. Workers inherit the BALATROBOT_PORTS
    environment variable to know which ports to connect to.
    """
    # Only run in main process (not in xdist workers)
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id is not None:
        return

    # Determine number of instances needed from -n flag
    numprocesses = getattr(config.option, "numprocesses", None)
    parallel = numprocesses if numprocesses and numprocesses > 0 else 1

    # Generate random ports to avoid TIME_WAIT conflicts
    port_range_start = 12346
    port_range_end = 23456
    ports = random.sample(range(port_range_start, port_range_end), parallel)

    # Store ports in env var for workers to read
    os.environ["BALATROBOT_PORTS"] = ",".join(str(p) for p in ports)

    # Store config for use in pytest_unconfigure
    config._balatro_ports = ports
    config._balatro_parallel = parallel

    # Create base config from environment
    base_config = Config.from_env()

    # Create manager and start instances
    manager = InstanceManager(base_config)
    config._balatro_manager = manager

    async def start_all():
        tasks = []
        for port in ports:
            tasks.append(manager.start(port))

        await asyncio.gather(*tasks)

        # Wait for all instances to be healthy
        timeout = 45.0
        start_time = time.time()
        while time.time() - start_time < timeout:
            all_healthy = True
            for port in ports:
                if not check_health("127.0.0.1", port):
                    all_healthy = False
                    break
            if all_healthy:
                print(f"All {parallel} Balatro instance(s) healthy on ports: {ports}")
                return
            await asyncio.sleep(1.0)

        raise RuntimeError(
            f"Balatro instances failed to become healthy within {timeout}s"
        )

    try:
        asyncio.run(start_all())
    except Exception as e:
        # Clean up any instances that did start
        asyncio.run(manager.stop_all())
        raise pytest.UsageError(f"Could not start Balatro instances: {e}") from e


def pytest_unconfigure(config):
    """Stop Balatro instances after tests complete."""
    manager = getattr(config, "_balatro_manager", None)
    if manager is not None:
        try:
            asyncio.run(manager.stop_all())
        except Exception as e:
            print(f"Error stopping Balatro instances: {e}")


@pytest.fixture(scope="session")
def port(worker_id):
    """Get assigned port for this worker from env var."""
    ports_str = os.environ.get("BALATROBOT_PORTS", "12346")
    ports = [int(p) for p in ports_str.split(",")]

    if worker_id == "master":
        return ports[0]

    worker_num = int(worker_id.replace("gw", ""))
    return ports[worker_num]


@pytest.fixture(scope="session")
async def balatro_server(request, port, worker_id):
    """Wait for pre-started Balatro instance to be healthy."""
    # Check if we should connect to Balatro (only if integration tests are not deselected)
    marker_expr = request.config.getoption("markexpr", "")
    if marker_expr and "not integration" in marker_expr:
        yield None
        return

    # Check if any integration tests are actually collected
    if not any("integration" in item.keywords for item in request.session.items):
        yield None
        return

    # Wait for instance to be healthy (should already be running from pytest_configure)
    start_time = time.time()
    timeout = 10.0  # Shorter timeout since instance should already be running
    while time.time() - start_time < timeout:
        if check_health("127.0.0.1", port):
            print(f"[{worker_id}] Connected to Balatro on port {port}")
            yield None  # No manager to yield, instances managed globally
            return
        await asyncio.sleep(0.5)

    pytest.fail(f"Balatro instance on port {port} not responding")
