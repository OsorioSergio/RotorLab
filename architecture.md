# RotorLab Architecture

## 1. Purpose and Scope

This document defines the technical architecture of RotorLab as a desktop engineering platform with:

- a Python application shell and user interface using PyQt
- a Rust backend for workflow module logic and performance-critical compute
- in-process Python-to-Rust integration via PyO3 bindings built with maturin

RotorLab is workflow-centered. The workflow graph is the organizing structure of the project, and specialized environments are opened from that graph.

This architecture aligns with the UI structure in `rotorlab_ui_architecture_notes.md`:

- Top section: Global Controls, Environment Tabs, Context Toolbar
- Middle section: windowed workspace (Orchestrate, CAD, Simulation, Results)
- Bottom section: status feedback and console access

---

## 2. Architectural Narrative

RotorLab is implemented as a layered system:

1. UI Shell (PyQt)
2. Python Orchestration Layer
3. Rust Core Module Engine

### 2.1 Layer 1: UI Shell (PyQt)

The PyQt shell owns desktop UX and interaction flow:

- app lifecycle and main window
- top/middle/bottom shell layout
- environment tab management (fixed Orchestrate + dynamic tabs)
- context toolbar switching based on active environment
- module library and drag/drop interactions
- status bar and console/log viewer surfaces

### 2.2 Layer 2: Python Orchestration Layer

Python is the application coordinator:

- canonical in-memory project state for UI sessions
- project I/O and schema versioning for persisted files
- command routing from UI events to domain operations
- conversion between UI models and language-neutral DTO payloads
- background task dispatch for non-blocking Rust calls
- orchestration of environment state synchronization (tab state, selection state, run state)

### 2.3 Layer 3: Rust Core Module Engine

Rust is the deterministic compute and module runtime:

- workflow graph validation and execution logic
- module registry and module dispatch
- CAD/geometry processing through Truck
- stable, typed execution outputs for downstream modules
- performance-critical operations (geometry kernels, heavy validations, repeated compute)

---

## 3. Responsibility Split

### 3.1 Python Responsibilities

- App lifecycle and PyQt windowing
- Global/top-level command handling
- Environment tab creation/activation/closure rules
- UI-driven graph editing intent capture
- Persisted project ownership (`.rotorlab` JSON schema)
- User-facing status and error presentation
- Background worker management and cancellation signaling

### 3.2 Rust Responsibilities

- Canonical graph consistency checks
- Module execution semantics
- Deterministic validation and run diagnostics
- CAD kernel invocation and geometry artifact generation
- Efficient compute pipelines and memory-safe transformations

### 3.3 Ownership Boundary

- Python owns persisted schema and UI/session state.
- Rust owns execution semantics and compute-heavy module logic.
- Boundary communication uses explicit DTO payloads and result envelopes.

---

## 4. Runtime Topology (v1)

### 4.1 Process Model

- Single desktop process for v1.
- PyQt main thread runs UI event loop.
- Rust is loaded as Python extension module(s) with PyO3.

### 4.2 Concurrency Model

- UI thread never performs heavy compute directly.
- Python dispatches Rust calls through worker threads/tasks.
- Long operations report incremental status back to UI-safe channels.
- Cancellation is best-effort and cooperative per operation type.

### 4.3 PyO3 and maturin Integration

- Rust crate exports PyO3 entry points.
- maturin builds distributable Python wheels.
- Python imports compiled extension as a normal package dependency.

---

## 5. Core Workflow Primitives

These primitives are shared concepts across Python and Rust.

## 5.1 Domain Objects

- `Project`: root container with metadata, workflows, settings
- `WorkflowGraph`: directed graph of modules and connections
- `ModuleNode`: a node instance with type, config, and identity
- `Connection`: typed edge describing data/control flow between nodes
- `ExecutionContext`: runtime context (parameters, run options, environment)
- `Artifact`: typed output from modules (geometry, mesh, numeric table, plot-ready series)

### 5.2 Identity and Serialization Rules

- Every persisted entity has a stable unique ID (UUID recommended).
- Python persists canonical JSON schema (`.rotorlab`).
- Rust receives validated DTO payloads derived from persisted/current state.
- Rust does not write project files directly in v1.

---

## 6. Public Interfaces and Contracts

## 6.1 Python Service Interfaces

### `ProjectService`

- `new_project() -> ProjectDTO`
- `open_project(path) -> ProjectDTO`
- `save_project(path, project_dto) -> SaveResult`
- `export_project(path, options) -> ExportResult`

### `WorkflowService`

- `add_node(project_id, node_template) -> NodeDTO`
- `remove_node(project_id, node_id) -> OpResult`
- `connect_nodes(project_id, from_port, to_port) -> ConnectionDTO`
- `validate_graph(project_id) -> ExecutionResult`

### `ExecutionService`

- `run_workflow(project_id, execution_request) -> ExecutionResult`
- `stop_execution(run_id) -> OpResult`
- `rebuild_project(project_id) -> ExecutionResult`
- `refresh_dependencies(project_id) -> OpResult`

### `CadServiceBridge`

- `preview_geometry(node_id, config) -> ExecutionResult`
- `build_geometry(node_id, config) -> ExecutionResult`
- `query_geometry_metrics(artifact_id) -> ExecutionResult`

## 6.2 Rust Core Traits

### `Module`

- Defines module metadata, input/output contracts, and execute behavior.

### `ModuleRegistry`

- Resolves module type IDs to concrete module implementations.

### `GraphValidator`

- Performs structural and semantic graph validation with deterministic diagnostics.

### `GraphExecutor`

- Schedules and executes graph operations with artifact propagation.

## 6.3 Shared Data Contracts

- `ProjectDTO`
- `NodeDTO`
- `ConnectionDTO`
- `ExecutionRequest`
- `ExecutionResult`

DTOs are language-neutral schema objects to keep Python and Rust decoupled from UI-specific models.

## 6.4 Result Envelope Standard

All boundary operations return a standardized envelope:

- `ok: bool`
- `data: object | null`
- `error: ErrorDTO | null`
- `warnings: WarningDTO[]`
- `timing: TimingDTO`

This keeps UI behavior consistent for status bar updates, dialogs, and console details.

## 6.5 Binding Boundary Conventions

- Python-facing Rust functions use stable, explicit names (for example `validate_graph`, `execute_graph`, `cad_build_geometry`).
- Rust errors map into structured `ErrorDTO` with code, message, details.
- API compatibility is gated by an `api_version` handshake:
  - Python declares supported versions.
  - Rust returns implemented version.
  - Startup fails fast on incompatible major versions.

---

## 7. CAD Architecture (Truck in Rust)

## 7.1 Why CAD Lives in Rust

CAD and geometry kernels are compute-heavy and sensitive to numerical correctness. Rust plus Truck provides:

- high performance for geometry operations
- memory safety guarantees
- deterministic behavior and reliable error handling

## 7.2 CAD Request Flow

1. User configures a geometry node in PyQt UI.
2. Python validates UI-level input and builds CAD DTO payload.
3. Python worker invokes Rust CAD bridge function.
4. Rust maps DTO to module config and calls Truck kernel operations.
5. Rust produces geometry artifacts and metadata.
6. Python receives `ExecutionResult` and updates:
   - visualization/preview state
   - workflow artifact references
   - status bar and console entries

## 7.3 CAD Outputs

Rust returns derived outputs that can be consumed by UI and downstream modules, for example:

- tessellated preview buffers for viewport rendering
- geometric properties (span, chord, area, volume, centroid, bounding box)
- serialized intermediate references for later module execution
- structured diagnostics for invalid or degenerate geometry

---

## 8. UI Architecture Mapping

This section maps major UI concepts to architecture components.

### 8.1 Top Section

- Global Project Controls: Python command handlers via `ProjectService` and `ExecutionService`
- Environment Selection Row: Python tab manager with fixed Orchestrate anchor + dynamic context tabs
- Context Toolbar: environment-specific command sets routed through orchestration layer

### 8.2 Middle Section

- Windowed workspace model implemented in PyQt dock/floating window framework
- Orchestrate environment includes:
  - Module Selection window (Python-driven module catalog)
  - Canvas window (graph editing UI with drag/drop and connect interactions)

### 8.3 Bottom Section

- Status bar reflects operation state from orchestration events and Rust result envelopes
- Console/Logs view consumes structured logs and diagnostics from both layers

### 8.4 End-to-End Sequence (Reference Flow)

Module drag/drop -> graph update -> Rust validation -> UI status update:

1. User drags module from Module Selection into Canvas.
2. `WorkflowService.add_node` updates in-memory graph.
3. Python triggers `validate_graph` through Rust binding.
4. Rust `GraphValidator` returns `ExecutionResult` with warnings/errors/timing.
5. Python updates canvas node decorations and bottom status message.
6. Console captures details for traceability.

---

## 9. Cross-Cutting Concerns

### 9.1 Error Propagation

- Rust never returns opaque string-only failures across boundary.
- All failures map to structured error codes and human-readable messages.
- Python distinguishes:
  - user-correctable validation issues
  - runtime execution failures
  - internal/system failures

### 9.2 Logging and Diagnostics

- Python emits UI and orchestration logs.
- Rust emits compute/module logs with operation IDs.
- Shared correlation IDs allow joining events in console.
- Status bar shows concise state; console provides deep diagnostics.

### 9.3 Concurrency and Thread Safety

- UI updates occur only on UI thread.
- Background workers own blocking calls into Rust.
- Shared mutable state in Python is synchronized at orchestration boundary.
- Rust internals use thread-safe patterns where parallel execution is enabled.

### 9.4 Performance Expectations

- Interactive UI actions remain responsive during background execution.
- Graph validation should be low-latency for common edit operations.
- CAD build operations can be longer-running but must stream progress and final diagnostics.

---

## 10. Build, Packaging, and Repository Structure

## 10.1 Suggested Repository Layout

```text
RotorLab/
  python/
    rotorlab_app/
      ui/
      services/
      models/
      logging/
  rust/
    rotorlab_core/
      src/
      crates/
        graph_engine/
        cad_engine/
        module_runtime/
  rotorlab_ui_architecture_notes.md
  architecture.md
```

### 10.2 Python Packaging

- Python package contains PyQt app, services, DTO models, and orchestration code.
- Rust extension is consumed as pinned package dependency (local build or wheel artifact).

### 10.3 Rust Packaging

- Workspace with focused crates:
  - graph engine
  - CAD engine (Truck integration)
  - module runtime/registry
- One PyO3-facing crate exposes stable binding API.

### 10.4 maturin Build Integration

- Local development: maturin develop for editable extension install.
- CI build: maturin build producing wheel artifacts per platform.
- App packaging includes matching Python package and Rust extension wheel.

### 10.5 Version Compatibility Policy

- Python and Rust components share semantic versions with compatibility matrix.
- `api_version` handshake enforces runtime compatibility.
- Breaking boundary changes require major version bump on both sides.

---

## 11. Delivery Roadmap

### Phase 1: Shell + Orchestrate + Validation

- Build PyQt shell with three-row top section and bottom status bar.
- Implement Orchestrate module library + canvas graph editing.
- Integrate Rust graph validation through PyO3.

### Phase 2: CAD Module Execution

- Implement geometry module configuration UI.
- Execute CAD operations through Rust Truck-backed engine.
- Return preview geometry artifacts and metrics to UI.

### Phase 3: Simulation/Results + Diagnostics Expansion

- Add simulation and results environment tabs and context toolbars.
- Expand module execution pipeline and result artifact handling.
- Improve console diagnostics, run history, and operational observability.

---

## 12. Document Quality Checklist

This checklist is used to validate architecture completeness.

- Every major UI concept from `rotorlab_ui_architecture_notes.md` maps to a concrete architecture component.
- Python vs Rust ownership is explicit and non-overlapping.
- At least one end-to-end sequence is documented from UI action to Rust validation and back.
- CAD path explicitly references Truck and explains Rust ownership rationale.
- Interface and type names are consistent across all sections.

