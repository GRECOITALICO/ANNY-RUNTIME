"""Minimal SSE (Server-Sent Events) endpoint for real-time telemetry."""

import json
import time
from http.server import BaseHTTPRequestHandler
from runtime.telemetry.collector import TelemetryCollector

def handle_telemetry_stream(handler: BaseHTTPRequestHandler, telemetry_collector: TelemetryCollector):
    """Streams telemetry events as Server-Sent Events."""
    if not telemetry_collector:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(b"TelemetryCollector not configured")
        return

    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('Connection', 'keep-alive')
    handler.end_headers()

    # Flush headers
    try:
        handler.wfile.flush()
    except Exception:
        return

    # Send initial recent events
    recent_events = telemetry_collector.get_live()
    try:
        for env in recent_events:
            handler.wfile.write(f"data: {json.dumps(env.to_dict())}\n\n".encode('utf-8'))
        handler.wfile.flush()
    except Exception:
        return

    # Since we are using standard HTTP server which blocks on handles, we need to poll
    # the collector for new events and write them. 
    # For a naive SSE implementation, we'll keep track of the last seen event_id.
    
    seen_ids = {env.event_id for env in recent_events}
    
    while True:
        try:
            time.sleep(1.0)
            current_events = telemetry_collector.get_live()
            for env in current_events:
                if env.event_id not in seen_ids:
                    handler.wfile.write(f"data: {json.dumps(env.to_dict())}\n\n".encode('utf-8'))
                    seen_ids.add(env.event_id)
            handler.wfile.flush()
        except Exception:
            # Client disconnected
            break
