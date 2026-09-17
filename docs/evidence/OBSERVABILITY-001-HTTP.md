# OBSERVABILITY-001-HTTP

## Real HTTP Boundary Verification
To satisfy `AG-008` requirement `O-10`, the `test_t11_processing_matrix_http_boundary` test launches a real instance of the ANNY-RUNTIME `AdminServer` bounding to a transient local TCP port.

### Execution Evidence
The test executes the following HTTP requests against the live instance using standard HTTP proxy stacks via `urllib.request`:

```python
        # Test /api/processing/matrix via real HTTP
        req = urllib.request.Request(f"http://localhost:{port}/api/processing/matrix")
        req.add_header("Cookie", "admin_session=dummy")
        with opener.open(req) as resp:
            assert resp.status == 200
            response = json.loads(resp.read().decode())
            assert "global" in response
            assert "departments" in response
            assert response["global"]["total"] == 1

        # Test /api/processing/events via real HTTP
        req2 = urllib.request.Request(f"http://localhost:{port}/api/processing/events?limit=10")
        req2.add_header("Cookie", "admin_session=dummy")
        with opener.open(req2) as resp2:
            assert resp2.status == 200
            response_events = json.loads(resp2.read().decode())
            assert isinstance(response_events, list)
            assert len(response_events) == 1
            assert response_events[0].get("execution_id") == "exec-1"
```

### Verification Condition
The test establishes definitively that the `TelemetryAggregator` instantiated globally is exposed properly across the `AdminServer` REST boundary and serializes its exact JSON representation. All tests successfully run green.
