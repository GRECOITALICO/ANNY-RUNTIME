from typing import Dict, Any, List
from datetime import datetime, timezone
import dateutil.parser
from collections import defaultdict

from runtime.telemetry.collector import TelemetryCollector
from runtime.telemetry.telemetry import TelemetryEnvelope, RoutingClass

class TelemetryAggregator:
    def __init__(self, collector: TelemetryCollector):
        self.collector = collector

    def get_matrix(self, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Calculate the processing matrix dimensions based on real telemetry.
        """
        filters = filters or {}
        events = self.collector.query(filters, limit=10000) # Assuming an upper bound for aggregation

        # Keep track of latest execution per department
        departments: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total": 0,
            "deterministic": 0,
            "local_model": 0,
            "frontier_model": 0,
            "unknown": 0,
            "success": 0,
            "failed": 0,
            "timeout": 0,
            "blocked": 0,
            "latest_execution": None,
            "durations": [],
            "average_duration": 0.0
        })

        global_stats = {
            "total": 0,
            "deterministic": 0,
            "local_model": 0,
            "frontier_model": 0,
            "unknown": 0,
            "success": 0,
            "failed": 0,
            "timeout": 0,
            "blocked": 0,
            "latest_execution": None,
            "durations": [],
            "average_duration": 0.0
        }
        
        execution_states: Dict[str, Dict[str, Any]] = {}
        # Collector query returns newest-first by insertion. Sort chronologically by timestamp
        # to ensure terminal states (SUCCEEDED) are not overwritten by earlier states (QUEUED).
        def safe_timestamp(e):
            return e.timestamp or ""
        for event in sorted(events, key=safe_timestamp):
            if not event.execution_id:
                continue
                
            if event.execution_id not in execution_states:
                execution_states[event.execution_id] = {
                    "department_id": event.department_id or "UNKNOWN",
                    "routing_class": event.routing_class or "UNKNOWN",
                    "status": "UNKNOWN",
                    "duration_ms": None,
                    "timestamp": event.timestamp
                }
            
            state = execution_states[event.execution_id]
            # Update values if present in newer events
            if event.department_id:
                state["department_id"] = event.department_id
            if event.routing_class:
                state["routing_class"] = event.routing_class
            if event.status:
                state["status"] = event.status
            if event.duration_ms is not None:
                state["duration_ms"] = event.duration_ms
            
            # Keep track of latest timestamp
            try:
                ev_time = dateutil.parser.isoparse(event.timestamp)
                st_time = dateutil.parser.isoparse(state["timestamp"])
                if ev_time > st_time:
                    state["timestamp"] = event.timestamp
            except:
                pass

        # Now compute matrix
        for ex_id, state in execution_states.items():
            dept = state["department_id"]
            rc = state["routing_class"]
            status = state["status"]
            
            # Global
            global_stats["total"] += 1
            if rc == "DETERMINISTIC": global_stats["deterministic"] += 1
            elif rc == "LOCAL_MODEL": global_stats["local_model"] += 1
            elif rc == "FRONTIER_MODEL": global_stats["frontier_model"] += 1
            else: global_stats["unknown"] += 1
            
            if status == "SUCCEEDED": global_stats["success"] += 1
            elif status == "FAILED": global_stats["failed"] += 1
            elif status == "TIMED_OUT": global_stats["timeout"] += 1
            elif status in ("BLOCKED", "LIMIT_EXCEEDED"): global_stats["blocked"] += 1
            
            if state["duration_ms"] is not None:
                global_stats["durations"].append(state["duration_ms"])
                
            if not global_stats["latest_execution"] or state["timestamp"] > global_stats["latest_execution"]:
                global_stats["latest_execution"] = state["timestamp"]

            # Department
            departments[dept]["total"] += 1
            if rc == "DETERMINISTIC": departments[dept]["deterministic"] += 1
            elif rc == "LOCAL_MODEL": departments[dept]["local_model"] += 1
            elif rc == "FRONTIER_MODEL": departments[dept]["frontier_model"] += 1
            else: departments[dept]["unknown"] += 1
            
            if status == "SUCCEEDED": departments[dept]["success"] += 1
            elif status == "FAILED": departments[dept]["failed"] += 1
            elif status == "TIMED_OUT": departments[dept]["timeout"] += 1
            elif status in ("BLOCKED", "LIMIT_EXCEEDED"): departments[dept]["blocked"] += 1
            
            if state["duration_ms"] is not None:
                departments[dept]["durations"].append(state["duration_ms"])
                
            if not departments[dept]["latest_execution"] or state["timestamp"] > departments[dept]["latest_execution"]:
                departments[dept]["latest_execution"] = state["timestamp"]

        # Calculate averages
        if global_stats["durations"]:
            global_stats["average_duration"] = sum(global_stats["durations"]) / len(global_stats["durations"])
        del global_stats["durations"]
        
        for dept, stats in departments.items():
            if stats["durations"]:
                stats["average_duration"] = sum(stats["durations"]) / len(stats["durations"])
            del stats["durations"]

        return {
            "global": global_stats,
            "departments": dict(departments)
        }

    def get_events(self, filters: Dict[str, Any] = None, limit: int = 100) -> List[Dict[str, Any]]:
        filters = filters or {}
        events = self.collector.query(filters, limit=limit)
        return [e.to_dict() for e in events]
