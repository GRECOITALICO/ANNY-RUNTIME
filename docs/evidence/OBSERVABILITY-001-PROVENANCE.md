# OBSERVABILITY-001-PROVENANCE

## Real Task Provenance Flow
The test `test_t08_full_provenance_chain_to_matrix` validates the following lifecycle of a Task across the boundary:

1. **Manager Submission (`submit_task`)**: An incoming `Task` instance is validated against the Capability definition and a unique `execution_id` is assigned inside the `ExecutionContext`.
2. **Task Creation (`task.created`)**: The manager creates and emits a `TelemetryEnvelope` establishing the trace context and assigning `department_id` and `routing_class`.
3. **Task Routing (`task.routed`)**: The manager issues a routing decision to a `Worker` environment.
4. **Worker Execution (`execution.finished`)**: The worker operates on the task and ultimately fires a terminal state (`SUCCEEDED`, `FAILED`, etc.).
5. **Aggregation Processing (`get_matrix()`)**: The `TelemetryAggregator` queries the `TelemetryCollector` and folds these chronologically (respecting timezones) into an execution matrix state where:
   - `matrix["global"]["total"] == 1`
   - `matrix["global"]["latest_execution"]` maps to the terminal chronologically evaluated UTC timestamp.
   - `matrix["departments"]["DEPT-1"]["total"] == 1`

## Outcome Verification
The test ensures that `aggregator.get_matrix()` flawlessly reflects the complete end-to-end trace context propagated through the runtime layers without metadata loss or improper double counting. This satisfies `AG-008` requirement `O-09`.
