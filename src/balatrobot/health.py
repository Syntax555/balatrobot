"""Health check module using httpx."""

import httpx


def check_health(host: str, port: int, timeout: float = 5.0) -> bool:
    """Check API health via HTTP POST using JSON-RPC 2.0.

    Args:
        host: Hostname to connect to
        port: Port to connect to
        timeout: Request timeout in seconds

    Returns:
        True if API is healthy, False otherwise
    """
    url = f"http://{host}:{port}"
    payload = {
        "jsonrpc": "2.0",
        "method": "health",
        "params": {},
        "id": 1,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            data = response.json()

            # Check for successful JSON-RPC response
            if "result" in data and data["result"].get("status") == "ok":
                return True

            # Log error details
            if "error" in data:
                print(f"Health check error: {data['error']}")
            else:
                print(f"Unexpected health response: {data}")
            return False

    except httpx.ConnectError as e:
        print(f"Connection error: {e}")
    except httpx.TimeoutException:
        print("Health check timed out")
    except Exception as e:
        print(f"Health check failed: {e}")

    return False
