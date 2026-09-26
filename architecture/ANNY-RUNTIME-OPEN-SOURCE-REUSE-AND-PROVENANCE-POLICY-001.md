# ANNY Runtime — Open Source Reuse and Provenance Policy 001

## Purpose

ANNY Runtime may reuse mature open-source components when they solve a required engineering problem reliably and when their licenses are compatible with ANNY's distribution model.

The objective is not to reproduce entire third-party projects. The objective is to acquire only the minimum implementation needed behind ANNY-owned interfaces, policies and evidence boundaries.

## Core rule

For every candidate component:

1. Identify the exact problem and the smallest required capability.
2. Evaluate the source license and redistribution obligations.
3. Decide between direct dependency, isolated adapter, selective source reuse, or independent reimplementation from documented behavior.
4. Preserve all legally required license, copyright, attribution and NOTICE material.
5. Record provenance and version information in ANNY's internal dependency/provenance inventory.
6. Keep the ANNY product architecture independent of the third party's names, APIs and control model where practical.
7. Do not copy code merely to hide its origin or bypass license obligations.

## Product naming rule

ANNY product UX, capability names and functional architecture should use ANNY-owned terminology rather than third-party project names.

This does not override legal obligations. If a license requires attribution, notices or redistribution terms, ANNY must satisfy those obligations in the appropriate legal/notice surface.

## Selection classes

### CLASS-A — Compatible direct dependency

A mature library is used as a dependency through a narrow ANNY adapter.

### CLASS-B — Isolated implementation reuse

Only the required source component is incorporated, with its required notices and license obligations retained.

### CLASS-C — Behavioral reimplementation

ANNY implements the required behavior independently after studying the problem, published interfaces, standards and publicly documented behavior.

### CLASS-D — Reject

Reject when license terms, provenance, security posture, maintenance risk, architectural coupling or distribution constraints are incompatible.

## Security rule

Open-source reuse never bypasses ANNY authorization.

Every reused component must remain behind canonical ANNY boundaries where applicable:

- ExecutionContext
- CapabilityGate / capability policy
- Workspace authority
- secret boundary
- network policy
- evidence/receipt
- continuity/checkpoint

A mature library does not become an authority source merely because Runtime uses it.

## Engineering rule

Reuse should concentrate on mechanical or commodity layers such as parsing, process utilities, protocol clients, browser transport, data structures or other bounded infrastructure.

ANNY-specific value should remain in ANNY-owned:

- authority model
- capability semantics
- policy
- orchestration
- continuity
- provenance
- evidence
- Repository Fabric boundary
- Control Center semantics
- ANNY-first execution

## Current repository observation

ANNY-RUNTIME currently declares third-party Python dependencies in requirements.txt and has a repository-level LICENSE using Apache License 2.0.

This document does not assert the license of every transitive dependency. Each dependency and any future source-reuse candidate requires explicit license verification before redistribution decisions are finalized.

## Required durable record

Every newly adopted source component must be recorded with:

- component identifier
- version or commit
- source location
- license
- reuse class
- files/modules affected
- whether source was copied, adapted or independently reimplemented
- required notices
- security review status
- removal/replacement strategy

## Forbidden patterns

- Copying an entire project when a small component is sufficient.
- Removing copyright/license notices required by the source license.
- Rebranding copied code to conceal provenance.
- Introducing a third-party component as a second authority or execution router.
- Treating dependency presence as proof of Runtime capability certification.

## Decision

Selective open-source reuse is approved as an engineering strategy for Runtime-native parity, subject to license, security, provenance and ANNY architecture controls.
