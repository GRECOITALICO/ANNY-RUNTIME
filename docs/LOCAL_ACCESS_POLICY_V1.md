# Local access policy v1

## Audit evidence (2026-10-27)

The Codex process ran as `anny` (uid 1000).  The active task policy exposed an
unrestricted filesystem sandbox and no approval gate; Linux reported no
effective ambient capabilities.  This is not a grant to Runtime: Runtime has
only the roots explicitly named in `github_inbox_local_roots`.

The audit used only directory metadata and effective access checks.  It did not
list, read, create, edit, delete, or transmit personal documents or secrets.

| Directory | Metadata/access check | Read/list | Write/create | Delete | Execute |
| --- | --- | --- | --- | --- | --- |
| `/home/anny/Workspace/CONRRAD-CORE` | VERIFIED: owner `anny`, mode 775, r/w/x | VERIFIED by effective permission | VERIFIED by effective permission | UNKNOWN: deliberately not exercised | VERIFIED for a process launched by Codex; Runtime does not expose command execution |
| `/home/anny/.codex/visualizations/2026/10/27/01a17e9b-d93d-7ed1-89d5-90290d39813d` | VERIFIED: owner `anny`, mode 775, r/w/x | VERIFIED by effective permission | VERIFIED by effective permission | UNKNOWN: deliberately not exercised | VERIFIED for a process launched by Codex; not exposed to Runtime |
| `/home/anny/Workspace/ANNY-RUNTIME-local-control-center` | VERIFIED: owner `anny`, mode 775, r/w/x | VERIFIED by effective permission | VERIFIED by effective permission | UNKNOWN: deliberately not exercised | VERIFIED for a process launched by Codex; not exposed to Runtime |
| `/home/anny/Descargas` | VERIFIED: owner `anny`, mode 755, r/w/x | VERIFIED by effective permission | VERIFIED by effective permission | UNKNOWN: deliberately not exercised | UNKNOWN for Runtime |
| `/home/anny/Documentos` | VERIFIED: owner `anny`, mode 755, r/w/x | VERIFIED by effective permission | VERIFIED by effective permission | UNKNOWN: deliberately not exercised | UNKNOWN for Runtime |
| `/home/anny/Escritorio` | VERIFIED: owner `anny`, mode 755, r/w/x | VERIFIED by effective permission | VERIFIED by effective permission | UNKNOWN: deliberately not exercised | UNKNOWN for Runtime |
| `/home/anny` | VERIFIED: owner `anny`, mode 700, r/w/x | VERIFIED by effective permission | VERIFIED by effective permission | UNKNOWN: deliberately not exercised | UNKNOWN for Runtime; never authorize this broad parent as a Runtime root |

`VERIFIED` above means an effective access check, not that file contents were
read or that a destructive operation was performed.  Directories outside this
inventory, other users' homes, system paths, credential stores, and the
contents of personal roots are `UNKNOWN` or `DENIED` by the Runtime policy.

The current Control Center service remains on port 8646 from this checkout. It
was not restarted.  The 7891 service and the Podman service on 8644 were not
started, restarted, or modified.

## Runtime model

`github_inbox_local_roots` is an explicit mapping.  An absent mapping grants
nothing and prevents worker activation.  Each root grants only the listed
operations; permissions do not imply one another.

```yaml
github_inbox_local_roots:
  anny-runtime-worktree:
    path: /home/anny/Workspace/ANNY-RUNTIME-local-control-center
    operations: [list, read, inspect, hash]
```

The example is documentation only; it was not written to the active service
configuration and does not activate the worker.  The policy has bounded host
methods for `write`, `create`, `move`, and `delete` so a future governed
executor can apply an independently approved operation.  They are not GitHub
inbox capabilities in v1; `execute` has no host implementation.  No shell
command capability is registered.

Every request identifies a configured root id and relative path.  The policy:

- rejects absolute paths, empty components, `.`/`..` traversal, symlinks, and
  non-regular files for file reads;
- opens each path component relative to an already-open root descriptor with
  `O_NOFOLLOW`, rather than trusting string-prefix checks;
- limits list results, text reads, hashes, output size, and execution time;
- blocks conventional credential locations and secret/key file names before
  they can be published to GitHub; and
- returns a normalized authorization failure, which the inbox publishes as
  `BLOCKED` rather than a successful result.

The Capability Registry remains the selector authority.  The only new inbox
capabilities are `filesystem.local.list`, `filesystem.local.read_text`,
`filesystem.local.inspect`, and `filesystem.local.hash`; all are deterministic
and read-only.  The private inbox remains the only remote write target.

## Remaining gap

Codex can perform approved local edits and invoke tools in its own environment;
Runtime v1 deliberately cannot do either from a GitHub request.  Therefore
this is not full capability equivalence.  The minimum safe next step is an
independent review of a specific write operation and root, followed by a new
registered governed-write capability with an approval/evidence contract.  Do
not solve that gap by mounting a home directory, a host socket, or a shell into
the runner.
