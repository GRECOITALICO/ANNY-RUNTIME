# ANNY Runtime — Reconstruction Master 001

Status: P0 / CANONICAL RECONSTRUCTION DOCUMENT
Owner: ANNY Runtime
Authority: ANNY / DTO
Purpose: permitir reconstruir el Runtime desde cero, incluso después de pérdida de contexto conversacional o agotamiento de tokens.

## 1. Regla fundamental

La conversación NO es estado durable. El repositorio Git y sus artefactos verificables son la fuente de continuidad.

Una reconstrucción correcta debe:

1. leer este documento;
2. ejecutar el bootstrap desde la fuente actual;
3. verificar identidad, tenant, Fabric y autoridad;
4. descubrir el estado canónico y la misión actual;
5. inspeccionar el ledger de hitos y evidencia;
6. verificar el commit/branch remoto observado;
7. continuar únicamente desde el último hito `VERIFIED` o `CERTIFIED`.

Nunca se debe continuar desde memoria conversacional, supuestos, caché de UI o un workspace no reconciliado.

## 2. Arquitectura canónica

```text
ANNY (Cloud DTO / L0)
        |
        v
ANNY Runtime Protocol
        |
        v
ANNY Runtime (local)
        |
        +--> Identity
        +--> Enrollment / Binding
        +--> Three-Plane Bootstrap
        +--> Control Center / Admin API
        +--> Continuity / Event Ledger
        +--> Execution Pipeline
        +--> Evidence / Receipts / Audit
        +--> Recovery / Generation Fence
        +--> Fabric Adapter
        +--> Update / Sync subsystem
        |
        v
ANNY-owned execution paths
        |
        v
OS (Linux / WSL2 target)
```

El README vigente describe el Runtime como gateway físico local de ejecución, residente en la máquina, acotado por Tenant/Workspace y agnóstico del proveedor de modelo. fileciteturn112file0

## 3. Modelo de planos

El Runtime trabaja con tres superficies reconciliadas:

- Runtime plane: identidad local, proceso, versión, salud, generación.
- Control/Cloud plane: ANNY, misión, tarea, autoridad, contratos y estado canónico.
- Fabric/Repository plane: GitHub/Fabric, repositorios, commits, evidencia, provenance y políticas.

La regla es `evidence-first`: ninguna superficie puede declarar estado superior a la evidencia disponible.

## 4. Bootstrap canónico

El bootstrap determinista actual está compuesto por estas fases:

### A-D

- identidad y reachability local;
- conectividad y binding GitHub/org;
- reachability/state/node@HEAD/provenance de Fabric;
- trust token, tenant binding y admission.

### E-K

- E: Policy Snapshot;
- F: Cross-Plane Reconciliation;
- G: Inventory Discovery;
- H: Critical Access Verification;
- I: Contracts Discovery;
- J: Delegation Context;
- K: Continuity Coherence.

El hito `ANNY-BOOTSTRAP-DETERMINISTIC-001` elevó el bootstrap a 12 fases y 25 gates obligatorios y reportó 42 tests passing en el commit `a9771d11e3bf49fb1170a8a1140fc9887ac6e97a`. Ese commit es un ancla histórica importante, no una sustitución del estado HEAD actual.

## 5. Estado actual conocido antes de esta documentación

HEAD funcional reciente observado en `main`:

- `f1043b322bf33b88587e2a68131e658e774e6688` — contrato P0 de SYNC;
- `64f1336061c1d44c4bec53c68fce36546be07ca9` — Control Center live + bootstrap asíncrono;
- `a9771d11e3bf49fb1170a8a1140fc9887ac6e97a` — bootstrap determinista de 12 fases/25 gates.

El Control Center actual expone estado live y `VERIFY NOW`, pero las rutas administrativas observadas no contienen todavía una ruta canónica `/api/sync`. fileciteturn113file0

## 6. Hitos de reconstrucción

Cada hito debe registrarse con:

```yaml
milestone_id:
status: PLANNED | IN_PROGRESS | VERIFIED | CERTIFIED | BLOCKED
commit_sha:
branch:
mission_id:
task_id:
objective:
changes:
tests:
evidence_refs:
known_gaps:
next_action:
reconstruction_entrypoint:
```

La regla de recuperación es:

```text
último VERIFIED/CERTIFIED
        -> leer evidencia
        -> verificar commit remoto
        -> comprobar tests asociados
        -> reconstruir estado
        -> continuar en NEXT_ACTION
```

## 7. Hitos canónicos conocidos

### M-001 — Three Plane Bootstrap

Status: IMPLEMENTED

Commit: `5d133811670612341f3e2f5c43e9250bd7bbd7f6`

Resultado: gates explícitos para runtime reachability, health, binding, admission y Fabric node at remote HEAD.

### M-001-R1.1 — Dynamic Fabric

Status: IMPLEMENTED

Commit: `7de69a49d713eafe4d17d16d3c2c2bcad2fe0d1b`

Resultado: eliminación de hardcodes del Fabric y unificación en `GitHubFabricAdapter`.

### M-002-R2-PHYSICAL — Operational Continuity

Status: IMPLEMENTED

Commit: `0d1e37164a827d7adcc0f4c3defdaf55a13ff3`

Resultado: engine de continuidad de dos fases, `PREPARE_MUTATION` / `FINALIZE_MUTATION`, commit de dos fases y reconciliación de estados huérfanos.

### ANNY-BOOTSTRAP-DETERMINISTIC-001

Status: IMPLEMENTED

Commit: `a9771d11e3bf49fb1170a8a1140fc9887ac6e97a`

Resultado: 12 fases de bootstrap, 25 gates obligatorios, inventario, verificación de acceso crítico, contratos, delegación y coherencia de continuidad.

### ANNY-LOCALHOST-ACCESS-001

Status: IMPLEMENTED

Commit: `64f1336061c1d44c4bec53c68fce36546be07ca9`

Resultado: Control Center local live, startup asíncrono, polling de `/api/status`, verificación bajo demanda y paneles operativos.

### SYNC-CONTROL-001

Status: CONTRACT_DEFINED / IMPLEMENTATION_PENDING

Commit documental: `f1043b322bf33b88587e2a68131e658e774e6688`

Resultado: contrato P0 de SYNC definido. La semántica es `SYNC != VERIFY != STAGE != ACTIVATE` y exige una operación durable con trace/evidence.

## 8. Gaps abiertos que NO deben declararse como terminados

- End-to-end Sync real.
- UpdateManager real: actualmente sus operaciones principales siguen siendo stubs. fileciteturn114file0
- Rollback verificado de una actualización real.
- Evidencia durable completa de cada sync/update.
- Separación observable y verificable entre Sync, Stage y Activate.
- Observabilidad/reanudación completa de streams en todo el recorrido.
- Certificación de plataformas fuera de los límites realmente probados.

## 9. Contrato de verdad

Estados permitidos:

- `FACT`: demostrado por fuente durable y verificable.
- `HYPOTHESIS`: propuesta todavía no demostrada.
- `UNKNOWN`: no existe evidencia suficiente.
- `UNVERIFIED`: existe afirmación o implementación, pero no fue validada en la ejecución actual.

Nunca convertir `UNKNOWN` en `PASS` por inferencia.

## 10. Procedimiento exacto después de pérdida de tokens/contexto

```text
A. Localizar GRECOITALICO/ANNY-RUNTIME.
B. Obtener HEAD remoto real de la rama objetivo.
C. Leer docs/RECONSTRUCTION-MASTER-001.md.
D. Leer README.md.
E. Leer docs/* de bootstrap, continuidad, contratos, recovery y sync.
F. Ejecutar/inspeccionar el bootstrap determinista.
G. Comparar runtime HEAD, Fabric node@HEAD y estado canónico.
H. Leer el último milestone `VERIFIED` o `CERTIFIED`.
I. Leer `NEXT_ACTION` y blockers asociados.
J. Verificar tests/evidence antes de ejecutar mutaciones.
K. Continuar solamente desde el `next_action` durable.
L. Registrar un nuevo milestone al finalizar cada unidad verificable.
```

## 11. Regla de commit

Cada cambio relevante debe producir una marca durable:

```text
implementation -> tests -> evidence -> milestone -> commit
```

No cerrar un hito sólo porque el código "parece" terminado.

## 12. Regla de no pérdida

Ninguna sesión debe depender de texto que exista únicamente en ChatGPT. Toda información necesaria para continuar debe terminar en:

- código;
- documentación;
- estado durable;
- evidencia;
- tests;
- milestone ledger;
- next action.

## 13. Entry point único de reconstrucción

El comando conversacional conceptual es:

```text
inicia bootstrap como ANNY
```

El Runtime debe ser capaz de traducir esa intención a reconstrucción determinista basada en evidencia, no a un recuerdo de sesión.

## 14. Hito actual

`RECONSTRUCTION-MASTER-001` consolida la documentación base necesaria para recuperar el diseño y el último estado conocido de ANNY Runtime sin depender del contexto conversacional.

Después de este documento, cualquier desarrollo debe actualizar el ledger de hitos y la evidencia correspondiente.
