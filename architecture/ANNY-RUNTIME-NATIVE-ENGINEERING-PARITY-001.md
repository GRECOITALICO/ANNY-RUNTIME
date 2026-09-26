# ANNY Runtime — Native Engineering Parity Program 001

## Purpose

ANNY-RUNTIME must become the native engineering environment from which ANNY can perform the work that is currently delegated to temporary external coding agents.

The target is functional parity with the useful engineering substrate normally exercised by coding-agent harnesses, not superficial product decoration.

External coding agents such as Codex and Antigravity are construction instruments only. They are not part of the final ANNY product architecture.

## Reference capability class

The useful engineering substrate to reproduce consists of:
- isolated workspace/repository access;
- deterministic file inspection and editing;
- terminal/command execution;
- test, lint and type-check execution;
- Git status/diff/branch/commit and mutation evidence;
- GitHub repository/API operations, including pull requests and related workflow inspection;
- process lifecycle and local service diagnostics;
- evidence, provenance, receipts and checkpoints;
- governed authorization, execution context and replay protection;
- local/remote model execution under explicit policy;
- orchestration of simple and complex engineering tasks;
- optional worker delegation after ANNY-first proof;
- a native IDE/workspace interaction surface.

OpenAI documents Codex as capable of reading/editing files, executing commands and tests, lint/type checks, repository work, PR workflows and isolated workspaces. This document treats those as a reference class, not as an instruction to copy provider-specific implementation details.

## Design rule

Every capability must follow:

DEFINED
-> IMPLEMENTED
-> TESTED
-> RUNTIME_EXECUTED
-> ANNY_FIRST_USE_VERIFIED
-> EVIDENCE
-> CERTIFIED

Local source/tests alone do not establish Runtime execution or certification.

## Priority ladder

### P0-A — Execution substrate
1. Execution Context
2. Workspace lifecycle and ownership
3. Shell/command execution
4. Process lifecycle
5. Cancellation/timeout/limits
6. stdout/stderr/result capture
7. deterministic evidence emission
8. result validation
9. replay/idempotency
10. failure containment

Acceptance:
ANNY can safely execute a bounded deterministic command inside a governed workspace.

### P0-B — Repository engineering
11. repository.inspect
12. repository.search
13. repository.read
14. repository.diff
15. repository.create
16. repository.edit
17. repository.patch
18. repository.delete
19. git status/log/diff
20. git branch
21. git add/commit
22. source snapshot verification
23. clean/dirty workspace verification

Acceptance:
ANNY can inspect, modify, validate and checkpoint a local repository without external coding-agent help.

### P0-C — Verification toolchain
24. test runner
25. focused test selection
26. full test suite
27. linter
28. formatter
29. type checker
30. static analysis
31. compile/build
32. artifact metadata/hash
33. test-result/evidence correlation

Acceptance:
ANNY can execute the complete local verification loop through Runtime.

### P0-D — GitHub engineering plane
34. authenticated identity
35. repository metadata
36. branch/ref reads
37. commit reads/writes
38. file reads/writes where authorized
39. pull request create/read/update
40. issue create/read/update
41. PR reviews/comments
42. workflow/run inspection
43. CI dispatch where authorized
44. compare commits
45. release/tag inspection
46. protected mutation gates

Rule:
GitHub operations are not equivalent to Repository Fabric authority. Runtime remains a governed client/worker.

### P0-E — Local developer environment
47. package/dependency inspection
48. environment/version inspection
49. interpreter/runtime selection
50. virtualenv/package installation policy
51. executable discovery
52. port/listener diagnostics
53. service/systemd diagnostics
54. logs/journal inspection
55. temporary artifact management

Acceptance:
ANNY can diagnose and prepare the local development environment without a second agent.

### P0-F — Evidence and governance
56. canonical execution receipt
57. durable evidence persistence
58. source/provenance tuple
59. request->execution->result correlation
60. checkpoint generation
61. continuity reconstruction
62. authorization decision capture
63. failure classification
64. audit trail
65. secret-redaction boundary

Acceptance:
Every material Runtime action is reproducible and auditable.

### P0-G — Harness and ANNY self-use
66. Harness request contract
67. fail-closed dispatcher
68. execution-context binding
69. workspace binding
70. source-snapshot binding
71. executor/worker binding
72. result validation
73. receipt/evidence handoff
74. ANNY result consumption
75. checkpoint after completion

Acceptance:
ANNY can select and execute repository.inspect through the native Harness without Codex/Antigravity.

### P1-A — Native IDE
76. workspace browser
77. file tree/search
78. editor/read/write/patch
79. diff view
80. task/execution console
81. test output
82. diagnostics
83. execution trace
84. source/provenance view
85. evidence/receipt view
86. Git status/diff/commit controls
87. PR review surface
88. Runtime attachment/state panel

Rule:
IDE is a product surface over Runtime capabilities; it is not a second execution authority.

### P1-B — Complex engineering
89. multi-step planning
90. inspect->edit->validate composite tasks
91. diagnose->patch->test
92. refactor workflows
93. migration workflows
94. hardening workflows
95. build/test/retest loops
96. artifact generation
97. rollback/recovery orchestration
98. bounded long-running tasks

Acceptance:
ANNY can perform complex engineering tasks natively after Level-1 proof.

### P1-C — Intelligence and workers
99. deterministic executor selection
100. local model executor
101. model artifact provenance
102. model capability binding
103. worker lifecycle
104. optional delegated worker interface
105. delegation receipts
106. delegation authorization
107. worker failure fallback to native Runtime

Rule:
Delegation is optional. Native Runtime execution is the fallback.

## Existing-state reconciliation

Already present, but not yet proven as a complete product capability:
- ExecutionContext;
- WorkspaceManager;
- EphemeralWorkspaceManager;
- ShellExecutor;
- ProcessManager;
- GitService;
- CapabilityGate;
- CapabilityRegistry;
- ExecutionManager;
- WorkerManager;
- DeterministicExecutor;
- MCP Gateway/ToolRegistry;
- RuntimeDoctor;
- SyncService;
- GitHub read-only client;
- Orchestrator;
- local model/Qwen path;
- evidence/continuity components;
- Harness contract work and executable dispatcher work from Batch023.

Known gaps/risks:
- ShellExecutor and GitService use interfaces that are not consistently aligned with the current ProcessManager/Workspace APIs.
- GitHubClient is read-only; GitHub engineering write operations are not yet a native Runtime capability set.
- Runtime has no native IDE module.
- Browser automation is not present as a Runtime module.
- Update service is not a coherent current module.
- RuntimeDoctor contains placeholder PASS claims for identity, enrollment, session, capabilities, tools, workspace and updater; these must not become live truth.
- Some Runtime/MCP repository tools are remote-GitHub oriented rather than checked-out-workspace oriented.
- Harness source-snapshot verification, durable cross-plane receipt handoff and ANNY result consumption remain incomplete.

## Batch order

### BATCH 024
Repair and unify the execution substrate:
- canonical ExecutionContext adapter;
- canonical WorkspaceManager adapter;
- ShellExecutor contract alignment;
- ProcessManager contract alignment;
- deterministic command execution;
- bounded stdout/stderr;
- timeout/cancel;
- result/evidence hooks;
- negative security tests.

### BATCH 025
Complete repository engineering:
- inspect/search/read/diff/edit/patch/create/delete;
- canonical local Git operations;
- source snapshot capture;
- dirty-tree controls;
- mutation receipts.

### BATCH 026
Complete verification toolchain:
- test/lint/type-check/build adapters;
- deterministic command result envelope;
- evidence correlation.

### BATCH 027
Complete governed GitHub engineering client:
- read/write refs;
- PR/issue/review operations;
- CI inspection/dispatch;
- protected mutation gates;
- explicit distinction between GitHub and Repository Fabric.

### BATCH 028
Complete environment/process operations and service diagnostics.

### BATCH 029
Complete Harness execution path and ANNY-first repository.inspect.

### BATCH 030
Build Native IDE over the same Runtime capability boundary.

### BATCH 031+
Complex engineering workflows, local models, worker delegation and native fallback.

## Exit condition for external-agent retirement

Antigravity must no longer be required for any ANNY product task.

Codex may remain temporarily available as an external construction instrument while Runtime capabilities are proven. It must not remain a structural dependency.

Final target:
ANNY selects capability
-> Runtime Harness
-> Execution Context
-> Runtime tools/executors
-> evidence
-> ANNY consumes result
-> checkpoint
-> optional delegation only after ANNY-first proof.

## Safety invariants

activation=false
production=false
authority_expansion=false
destructive_mutation=false
historical_overwrite=false
azure_mutation=false
routing_authorization=false
deployment_authorized=false
merge_authorized=false
KIRA_P2=SEPARATE_AND_UNTOUCHED
T12=SEPARATE_BLOCKER


## Open-source acceleration boundary

ANNY Runtime may use mature open-source infrastructure for commodity engineering layers when the license and security review permit it.

The reuse decision belongs below the ANNY governance boundary:

ANNY policy -> ExecutionContext -> capability -> Runtime adapter -> component -> validation -> evidence.

Open-source reuse is an implementation accelerator, not an authority source and not a substitute for ANNY's own continuity, policy, evidence or Repository Fabric semantics.

The durable policy is:
architecture/ANNY-RUNTIME-OPEN-SOURCE-REUSE-AND-PROVENANCE-POLICY-001.md
