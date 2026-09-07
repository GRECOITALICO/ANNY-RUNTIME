# Provenance Audit

This document classifies the origin of the components distributed within the ANNY-RUNTIME public repository.

## Provenance Classification

All code in this repository falls under one of the following provenance categories:

| Component | Provenance | License/Origin | Notes |
| :--- | :--- | :--- | :--- |
| `runtime/` | **ORIGINAL** | Apache-2.0 | Core runtime execution engine and identity management developed entirely in-house for ANNY. |
| `cli/` | **ORIGINAL** | Apache-2.0 | Command-line interface developed in-house. |
| `contracts/` | **ORIGINAL** | Apache-2.0 | Protocol definitions and capability structures. |
| `adapters/` | **ORIGINAL** | Apache-2.0 | Implementation of the Fabric protocol adapter. |
| `packaging/` | **ORIGINAL** | Apache-2.0 | Systemd unit configurations. |
| `scripts/install.sh` | **ORIGINAL** | Apache-2.0 | Native bash installer. |
| `scripts/physical-cert-helper.sh` | **ORIGINAL** | Apache-2.0 | Append-only evidence collector for physical certification. |

## Third-Party Dependencies
The runtime explicitly utilizes standard Python libraries via `requirements.txt`.
See [THIRD-PARTY-COMPONENTS.md](THIRD-PARTY-COMPONENTS.md) for the exhaustive dependency manifest. No autonomous external frameworks (e.g., Docker, Kubernetes, standalone orchestrators) are bundled or required.

## Blocking Policy
Any component categorized as `UNKNOWN` is strictly forbidden from entering the public distributable tree. As of the `v0.2.0` distribution, there are **no** `UNKNOWN` components. All components have been verified as `ORIGINAL`.
