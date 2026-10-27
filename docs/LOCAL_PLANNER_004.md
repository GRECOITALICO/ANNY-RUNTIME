# Local Planner 004

## Scope

`runtime.planning.local_planner` is a non-authorizing boundary between a local
model provider and the native task dispatcher. It can propose a plan, but it
cannot grant permissions, register capabilities, run shell commands, or call
the executor directly without independent validation.

The only currently admitted target capability is the provisional local fixture
capability `experimental.local.repository_change.v1`. The native dispatcher
continues to enforce its closed command registry, workspace boundaries,
preimage hashes, Podman isolation, and durable evidence.

## Reproducible local discovery

Run the following from the Runtime checkout. It does not start a service,
download a model, install packages, or contact a remote provider:

```bash
PYTHONPATH=. python cli/main.py local-planner-status
```

The result is sanitized and persisted at the Runtime data directory as
`native-executions/planning/local-model-discovery.json`. It contains client,
loopback, model-list and timestamp facts only; it does not persist environment
variables, credentials, prompts, or network configuration.

## Observed development-machine result

On the checked machine, the Ollama client reported version `0.32.5`, but its
loopback endpoint at `127.0.0.1:11434` was unavailable, the system service was
inactive, and no local model list could be verified. The resulting state is
`LOCAL_RUNTIME_WITHOUT_MODEL`.

Therefore no local-model inference was executed for this task. In particular,
the existing native executions retain `PLANNER=STRUCTURED_AUTHORIZED_PLAN` and
`NO_MODEL_AVAILABLE_OR_USED` provenance.

## If a model becomes available

`LocalPlanner` accepts a provider only after an explicit inference probe yields
`LOCAL_MODEL_READY` with `inference_status=VERIFIED`. A model listed by
discovery remains `LOCAL_MODEL_UNVERIFIED`. Provider output must be JSON containing a task
specification. `LocalPlanValidator` validates that data independently under
the existing dispatcher contract, attaches hashed provider evidence, and only
then permits `LocalPlanningOrchestrator` to invoke the same native executor.

Malformed output, provider errors, timeouts, unknown capabilities, remote
requests, unknown commands, path escapes, and any permission expansion return
denial/blocking results without a task workspace or runner execution.
