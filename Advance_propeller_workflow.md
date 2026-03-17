# Advanced Propeller Workflow

## Purpose

This document explains how to implement a CAESES-like advanced propeller parametrization workflow inside a program whose frontend is built with **Python + Qt** and whose backend uses **Rust** for computation and **Truck** as the CAD kernel. The goal is to give Codex a concrete implementation target: a feature that behaves like the CAESES advanced propeller workflow, but fits your architecture and remains extensible for unconventional blades such as highly skewed and tip-rake propellers.

The CAESES workflow is fundamentally a **layered geometric parametrization pipeline**:

1. Define radial distributions that describe the blade reference surface.
2. Define a reusable 2D section generator from camberline and thickness laws.
3. Apply spanwise distributions to morph the section along the radius.
4. Loft or skin the evolving sections into a blade surface.
5. Close the tip and blend the blade into the hub.
6. Scale and pattern the blade into a watertight propeller solid.
7. Optionally derive a CFD flow domain around it.

That separation is the most important architectural lesson from CAESES. The software should not treat the propeller as “one giant function.” It should treat it as a graph of reusable geometric operators.

---

## 1. Design Philosophy

A robust propeller parametrization system should satisfy five goals:

- **Geometric clarity**: each parameter must affect a physically meaningful part of the blade.
- **Smoothness**: radial laws and section morphing must produce differentiable geometry.
- **Local control**: changing one design variable should not destabilize the entire blade.
- **Backend authority**: final geometry must be generated in Rust/Truck, not inferred from the UI.
- **Incremental recomputation**: small parameter edits should recompute only affected stages.

The workflow should therefore be modeled as a **directed acyclic graph of geometry stages**, where each stage consumes parameters and outputs typed geometric objects.

---

## 2. High-Level Feature Architecture

## 2.1 Main split of responsibilities

### Python + Qt frontend
The frontend should own:

- parameter editing widgets
- radial distribution editors
- preview orchestration
- scene tree / workflow navigation
- selection and inspector UI
- persistence of project/session state
- user commands such as “rebuild blade”, “freeze distribution”, “export STEP”, or “generate domain”

### Rust backend
The backend should own:

- parameter validation
- B-spline and interpolation evaluation
- section generation mathematics
- reference surface construction
- section placement and transforms
- lofting / skinning / surface creation
- tip closure and hub-blade blending
- final B-rep generation
- mesh-ready topology extraction
- STEP/IGES/native export

### Truck CAD kernel
Truck should be used for:

- curves and surfaces
- topological entities
- face / edge / shell / solid construction
- trimming and sewing
- boolean operations where needed
- fillet or blend approximations if implemented via native or custom operators

The frontend should **never** become the source of geometric truth. It sends parameters and requests. Rust rebuilds and returns geometry artifacts or renderable tessellation.

---

## 2.2 Recommended module decomposition

A clean backend module layout could be:

```text
backend/
  core/
    units.rs
    types.rs
    errors.rs
  param/
    parameter.rs
    expression.rs
    design_variable.rs
    dependency_graph.rs
  math/
    bspline.rs
    interpolation.rs
    transforms.rs
    arc_length.rs
  propeller/
    model.rs
    distributions.rs
    center_surface.rs
    profile_definition.rs
    profile_configurator.rs
    blade_sections.rs
    blade_surface.rs
    tip_surface.rs
    hub.rs
    fillet.rs
    solid.rs
    pattern.rs
    domain.rs
  cad/
    truck_bridge.rs
    tessellation.rs
    export.rs
  api/
    commands.rs
    events.rs
    dto.rs
```

And on the Qt side:

```text
frontend/
  ui/
    workflow_panel.py
    parameter_panel.py
    distribution_editor.py
    section_preview.py
    viewport.py
  models/
    propeller_state.py
    command_queue.py
    scene_tree_model.py
  services/
    rust_client.py
    serializer.py
    undo_redo.py
```

---

## 3. Workflow Stages and Their Mathematics

## 3.1 Stage A: Center Surface / Reference Blade Surface

In the CAESES tutorial, the center surface is driven by radial distributions for:

- pitch
- rake
- skew
- chord
- hub radius and tip radius bounds

These functions are defined along the normalized radial coordinate

\[
\eta = \frac{r}{R}, \qquad \eta \in [\eta_{hub}, 1]
\]

where:
- \(r\) is local radius,
- \(R\) is propeller radius,
- \(\eta_{hub}\) is the nondimensional hub cutoff.

The center surface is not yet the true blade thickness surface. It is a **placement surface** or **mean/reference surface** that tells you where each section lives in 3D.

### Core radial distributions

Define these functions:

\[
P_D(\eta) = \text{pitch-to-diameter ratio}
\]
\[
\rho(\eta) = \text{rake law}
\]
\[
\sigma(\eta) = \text{skew law}
\]
\[
c(\eta) = \text{normalized chord law}
\]

Then dimensional chord is:

\[
C(r) = c(\eta) D
\]

where \(D = 2R\).

### Pitch angle relation

For a helical reference line, local pitch angle \(\beta\) is related to geometric pitch \(P\) by:

\[
\tan\beta(r) = \frac{P(r)}{2\pi r}
\]

If pitch is given as \(P/D\), then:

\[
P(r) = P_D(\eta) D
\]

and therefore

\[
\beta(r) = \arctan\left(\frac{P_D(\eta) D}{2\pi r}\right)
\]

This is one of the central equations of the workflow. The local section orientation should be constructed from this angle, optionally combined with an angle-of-attack correction distribution later.

### Rake and skew interpretation

- **Rake** is an axial displacement of the blade section reference location.
- **Skew** is an azimuthal shift of the section, often interpreted as a circumferential displacement that changes the section’s angular position as a function of radius.

A practical implementation is to define a section reference point at each radius:

\[
\mathbf{x}_{ref}(r) =
\begin{bmatrix}
 x(r) \\
 y(r) \\
 z(r)
\end{bmatrix}
\]

with the shaft axis taken as \(z\). Then for a section centerline point:

- radial placement comes from \(r\),
- axial shift comes from rake \(\rho(r)\),
- azimuthal shift comes from skew \(\sigma(r)\).

One useful parameterization is:

\[
\theta(r) = \theta_0 + \theta_{skew}(r)
\]

where \(\theta_{skew}\) is obtained from the skew function. Then

\[
\mathbf{x}_{ref}(r) =
\begin{bmatrix}
 r\cos\theta(r) \\
 r\sin\theta(r) \\
 \rho(r)
\end{bmatrix}
\]

Depending on your internal frame convention, you may place rake in \(x\) and revolve around \(z\), but the idea is the same: skew changes circumferential phase, rake changes axial offset.

### Why B-splines are the correct representation

CAESES uses low-order B-spline curves for distributions because they provide:

- smoothness,
- local control,
- stable editing through a small number of points,
- interpolation or approximation behavior depending on implementation.

You should model each radial law as a cubic B-spline or equivalent smooth curve over \(\eta\). The UI should expose control points or constrained design variables, but the backend should evaluate the spline.

---

## 3.2 Stage B: Profile Configurator / Section Generator

The section generator produces a 2D profile from:

- a camberline definition
- a thickness distribution
- optional leading edge and trailing edge modifications

The CAESES tutorial uses a NACA 66 modified section with \(a = 0.8\), built from separate camberline and thickness laws. Architecturally, the crucial idea is not the specific NACA family, but the decomposition:

\[
\text{profile} = \text{camberline} + \text{thickness law}
\]

### Generic mathematical form

Let \(x \in [0,1]\) be the normalized chord coordinate.

Define:

\[
\mathbf{c}(x) = [x, y_c(x)]
\]

as the camberline in 2D.

Let the thickness distribution be

\[
t(x) \ge 0
\]

which is usually a full thickness, so half-thickness is

\[
h(x) = \frac{t(x)}{2}
\]

If the camberline tangent angle is

\[
\phi(x) = \arctan\left(\frac{dy_c}{dx}\right)
\]

then upper and lower surfaces are:

\[
\mathbf{u}(x) =
\begin{bmatrix}
 x - h(x)\sin\phi(x) \\
 y_c(x) + h(x)\cos\phi(x)
\end{bmatrix}
\]

\[
\mathbf{l}(x) =
\begin{bmatrix}
 x + h(x)\sin\phi(x) \\
 y_c(x) - h(x)\cos\phi(x)
\end{bmatrix}
\]

This is the standard “offset normal to camberline” construction and should be your default section-generation method.

### Spanwise morphing parameters

At each radius, the profile definition is modified by spanwise parameters such as:

- maximum camber
- maximum thickness
- trailing-edge thickness
- angle of attack correction

This means your section profile is not a single static airfoil, but a **family of sections**:

\[
S(x; r) = f\big(x, m(r), t_{max}(r), t_{TE}(r), \alpha(r), \ldots\big)
\]

where \(m(r)\), \(t_{max}(r)\), \(t_{TE}(r)\), and \(\alpha(r)\) are radial distributions.

### Leading edge and trailing edge control

The tutorial highlights modification of:

- leading edge trim / radius / ellipse mode
- trailing edge thickness

This should be implemented as a post-process over the raw thickness distribution.

For example:

1. Start with baseline thickness law \(t_0(x)\).
2. Apply an LE modification function \(g_{LE}(x)\) near \(x=0\).
3. Apply a TE modification function \(g_{TE}(x)\) near \(x=1\).

Then:

\[
t(x) = t_0(x) + g_{LE}(x) + g_{TE}(x)
\]

with support localized near the edge regions.

A robust implementation uses smooth blending windows, for example compact cubic ramps, rather than hard piecewise breaks.

---

## 3.3 Stage C: Spanwise Section Placement

Once you have a 2D section and a radial reference frame, you must place each section in 3D.

At each radial sample \(r_i\), create a local orthonormal frame:

\[
\{\mathbf{e}_c, \mathbf{e}_t, \mathbf{e}_n\}
\]

where typically:

- \(\mathbf{e}_c\): chordwise direction
- \(\mathbf{e}_t\): thickness direction
- \(\mathbf{e}_n\): spanwise or surface-normal-compatible direction

A practical construction is:

1. Define a spanwise direction along the reference surface.
2. Define the local circumferential/tangential direction around the shaft.
3. Rotate by the local pitch angle \(\beta(r)\) plus optional \(\alpha(r)\).

### Section transform

If \(\mathbf{p}_{2d}(x) = [x_{sec}, y_{sec}]\) is a 2D section point, then its 3D mapping can be written as:

\[
\mathbf{p}_{3d}(x,r) = \mathbf{x}_{ref}(r) + C(r)\,x_{sec}\,\mathbf{e}_c(r) + C(r)\,y_{sec}\,\mathbf{e}_t(r)
\]

where the section is scaled by local chord \(C(r)\).

If a local AoA correction \(\alpha(r)\) is present, then the chord basis is additionally rotated:

\[
\beta_{eff}(r) = \beta(r) + \alpha(r)
\]

This is conceptually what CAESES is doing when it uses an angle-of-attack radial distribution on top of the pitch-driven blade orientation.

### Important architectural note

Do not directly loft from UI control points. Always generate **sampled section curves** in Rust, each with a known frame and metadata. The blade surface stage should consume typed `SectionCurve3D` objects.

---

## 3.4 Stage D: Blade Surface Generation

After placing multiple sections from hub radius to near-tip radius, generate the blade surface by lofting or skinning.

Mathematically, if the section family is sampled at radii \(r_i\), then the blade surface is an approximation of:

\[
\mathbf{S}(u,v)
\]

where:
- \(u\) is chordwise parameter,
- \(v\) is spanwise parameter.

The easiest robust strategy is:

1. Sample \(N_v\) span stations.
2. At each station, build a closed or open section spline in 3D.
3. Loft them with consistent parameterization.

### Parameter consistency requirement

Every spanwise section must use the same chordwise parameter convention, for example:

- start at trailing edge suction side,
- go through leading edge,
- return on pressure side,
- end at trailing edge pressure side.

Without consistent section orientation and knoting, the loft can twist or self-intersect.

### Tip gap idea from CAESES

CAESES reserves part of the spanwise domain for tip closure by using a span parameter domain like:

\[
v \in [0, 1 - \text{tipGap}]
\]

This is an excellent pattern. In your implementation, do not force the blade main loft to collapse exactly at the tip. Leave a small residual domain for a dedicated tip patch.

That reduces singular behavior and gives you better control over tip thickness and closure shape.

---

## 3.5 Stage E: Tip Surface / Closure

A propeller blade tip should be treated as a dedicated geometric entity, not as an afterthought.

The tip closure consumes:

- the terminal blade section,
- a maximum tip length or closure extent,
- the local thickness and camber information,
- the final spanwise tangent directions.

### Mathematical view

The tip is a patch connecting the pressure and suction sides around the final section. In abstract terms, it is a boundary interpolation problem between edge curves:

\[
\partial \Omega_{tip} = \{\gamma_1, \gamma_2, \gamma_3, \gamma_4\}
\]

You can implement this as:

- a Coons patch,
- a Gordon surface,
- a ruled/blended patch,
- or a custom skinned cap.

For first implementation, a ruled or Coons-like patch is enough, as long as:

- the boundary is watertight,
- tangency is acceptable,
- curvature remains well behaved.

### Recommendation for v1

Use a dedicated `TipBuilder` that:

1. extracts terminal pressure and suction edge curves,
2. creates a rounded closure spine,
3. builds a patch from those boundaries,
4. sews it to the blade main loft.

---

## 3.6 Stage F: Hub, Closed Blade, and Fillet

Once the blade surface and tip are built, create a closed blade shell or solid and connect it to a hub.

### Hub scaling logic

CAESES scales the hub relative to blade radius. This is the correct modeling choice because the hub must remain proportionally valid under radius changes.

If

\[
R = \text{blade radius}
\]

then hub dimensions should be expressed as:

\[
L_{hub} = k_L R, \qquad R_{hub} = k_H R
\]

where \(k_L\) and \(k_H\) are dimensionless parameters.

### Blade-hub intersection

Create a “closed blade” by intersecting or trimming the blade against the hub region. This can be done by:

- converting blade faces to a B-rep shell,
- intersecting against a slightly reduced hub helper solid,
- trimming overlapping regions,
- sewing everything back to a valid shell/solid.

### Fillet logic

The CAESES tutorial uses a rule of thumb where root fillet radii are proportional to root thickness. That is a very good engineering rule.

If root thickness is \(t_{root}\), define for example:

\[
r_{LE} = \frac{t_{root}}{10}
\]
\[
r_{PS} = \frac{2}{3}t_{root}
\]
\[
r_{SS} = \frac{1}{3}t_{root}
\]
\[
r_{TE} = \frac{t_{TE}}{2}
\]

The exact side naming depends on your pressure/suction convention, but the principle is:

- fillet size follows section thickness,
- larger fillet on the thicker side,
- LE and TE get dedicated radii.

In software, this means the fillet stage should read geometric measurements from already-built sections or the blade root profile rather than asking the user to manually enter all radii.

---

## 3.7 Stage G: Full Propeller Solid by Patterning

Once a single blade is valid and blended into the hub, generate the full propeller by circular patterning.

For number of blades \(N\), each blade instance uses rotation:

\[
\theta_k = \frac{2\pi k}{N}, \qquad k = 0,1,\ldots,N-1
\]

Apply rotation around the shaft axis to the closed blade body and union the result with the hub.

The pattern stage must preserve topological validity. If Truck boolean union is expensive or fragile, a staged shell merge followed by solidification may be more stable.

---

## 3.8 Stage H: Flow Domain

The flow domain should be a separate workflow branch, not mixed into blade geometry generation.

Define domain dimensions relative to blade radius, for example:

\[
R_{dom} = 4R
\]
\[
z_{start} = -5R
\]
\[
z_{end} = 10R
\]

This matches the CAESES design pattern of dimensionless domain settings tied to blade radius. The same pattern should be used in your program.

For one-blade periodic analysis, include an angular sector:

\[
\Delta\theta = \frac{2\pi}{N}
\]

and clip the domain accordingly.

---

## 4. Parameter Model

A propeller feature like this should expose three classes of parameters.

## 4.1 Global parameters

Examples:

- propeller radius \(R\)
- diameter \(D = 2R\)
- number of blades \(N\)
- hub scale factors
- units

## 4.2 Radial distribution parameters

Examples:

- pitchDelta
- rake2Pos
- rakeTip
- skewTip
- chordMax
- camber root control
- max-thickness control
- trailing-edge thickness
- angle-of-attack tip correction

These should be stored as either:

- direct control point values of a spline,
- or higher-level design variables that drive constrained control points.

## 4.3 Section-definition parameters

Examples:

- camberline family type
- thickness family type
- NACA coefficients or custom profile data
- LE trim mode
- LE radius mode
- TE thickness behavior

---

## 5. Recommended Data Model

A good boundary between Qt and Rust is a serializable schema. JSON is enough for commands and state interchange.

Example:

```json
{
  "project_units": "mm",
  "propeller": {
    "radius": 2500.0,
    "num_blades": 3,
    "hub_radius_ratio": 0.2,
    "distributions": {
      "pitch_pd": {
        "type": "bspline",
        "degree": 3,
        "control_points": [[0.2, 0.9], [0.7, 1.05], [1.0, 1.0]]
      },
      "rake": {
        "type": "bspline",
        "degree": 3,
        "control_points": [[0.2, 0.0], [0.7, 0.03], [0.85, 0.08], [1.0, 0.1]]
      },
      "skew": {
        "type": "bspline",
        "degree": 3,
        "control_points": [[0.2, 0.0], [0.7, 0.1], [1.0, 0.2]]
      },
      "chord": {
        "type": "bspline",
        "degree": 3,
        "control_points": [[0.2, 0.2], [0.5, 0.65], [0.8, 0.45], [1.0, 0.1]]
      }
    },
    "profile_definition": {
      "camberline": {"family": "naca_a_modified", "a": 0.8},
      "thickness": {"family": "naca66"},
      "leading_edge": {"mode": "ellipse", "trim": 0.0},
      "trailing_edge": {"thickness": 0.0075}
    },
    "profile_parameters": {
      "camber": {"type": "bspline", "control_points": [[0.2, 0.03], [0.6, 0.01], [1.0, 0.0]]},
      "max_thickness": {"type": "bspline", "control_points": [[0.2, 0.2], [0.6, 0.1], [1.0, 0.05]]},
      "angle_of_attack": {"type": "bspline", "control_points": [[0.2, 0.0], [0.6, 0.0], [1.0, 0.0]], "scale_deg": 10.0}
    }
  }
}
```

The backend should deserialize this into typed structs and build an internal dependency graph.

---

## 6. Communication Between Frontend and Backend

## 6.1 Recommended IPC model

Because the frontend is Python/Qt and the backend is Rust, you need a stable communication boundary. There are four reasonable approaches:

1. **Python bindings to Rust** via PyO3/maturin
2. **Local RPC** via gRPC, Cap’n Proto, or MessagePack-RPC
3. **Process-based command protocol** via JSON over stdio
4. **Embedded Rust dynamic library** loaded from Python

For this kind of CAD application, the most practical initial choice is usually:

- **PyO3 bindings** if you want tight synchronous calls and simpler deployment,
- or **JSON-RPC over stdio/socket** if you want stronger isolation and crash containment.

### Recommended choice for your case

Since you are building a desktop engineering tool with Qt and a geometry-heavy backend, I recommend:

- **Rust backend as a long-lived worker process**
- **structured JSON commands/events**
- **binary mesh payloads or memory-mapped buffers** for heavy geometry previews

This gives you:

- crash isolation from the UI
- easier debugging
- versioned command protocol
- simpler future support for remote compute or batch mode

---

## 6.2 Command/event protocol

The frontend should send commands such as:

```json
{ "cmd": "create_propeller_feature", "feature_id": "prop_01" }
```

```json
{ "cmd": "set_parameter", "feature_id": "prop_01", "path": "distributions.pitch_pd.cp[1].y", "value": 1.05 }
```

```json
{ "cmd": "rebuild_stage", "feature_id": "prop_01", "stage": "blade_surface" }
```

```json
{ "cmd": "export_step", "feature_id": "prop_01", "path": "C:/tmp/prop.step" }
```

The backend should respond with events like:

```json
{ "event": "parameter_updated", "feature_id": "prop_01" }
```

```json
{ "event": "stage_built", "feature_id": "prop_01", "stage": "center_surface", "artifact_id": "surf_12" }
```

```json
{ "event": "preview_mesh_ready", "feature_id": "prop_01", "artifact_id": "mesh_77" }
```

```json
{ "event": "error", "feature_id": "prop_01", "message": "Loft failed: inconsistent section orientation" }
```

---

## 6.3 Incremental rebuild strategy

The frontend should not request a full rebuild after every keystroke unless the model is tiny. Instead:

- parameter edit updates backend state,
- dependency graph marks affected stages dirty,
- preview debounce triggers staged rebuild,
- final export forces full precise rebuild.

### Dependency logic example

If the user changes `skewTip`, then recompute:

- skew distribution
- center surface frames
- placed sections
- blade loft
- tip patch
- final blade shell
- patterned propeller preview

But you do **not** need to recompute:

- baseline profile family definition,
- unrelated CFD domain settings,
- unchanged hub dimensions unless dependency exists.

This dependency graph is one of the most important engineering pieces of the feature.

---

## 6.4 Preview vs exact geometry

The backend should support two geometry modes:

### Fast preview mode
Used during interactive edits.

- fewer span stations
- fewer profile samples
- approximate tessellation
- cheap or deferred fillet rebuild
- optional skipping of full boolean union

### Exact build mode
Used for export, analysis, or final save.

- denser sampling or exact curve evaluation
- precise Truck surfaces/B-reps
- full tip/hub closure
- exact patterning and sewing
- STEP export

This separation is essential for UI responsiveness.

---

## 7. Internal Rust Object Model

A good internal typed model might look like this:

```rust
struct PropellerModel {
    units: Units,
    global: GlobalParameters,
    center_surface: CenterSurfaceConfig,
    profile_definition: ProfileDefinition,
    profile_parameters: ProfileParameterSet,
    hub: HubConfig,
    solid: SolidConfig,
    domain: Option<DomainConfig>,
}

struct GlobalParameters {
    radius: f64,
    diameter: f64,
    num_blades: u32,
    radius_hub: f64,
}

struct RadialDistribution {
    spline: BSpline1D,
    domain: (f64, f64),
}

struct SectionFrame {
    origin: Point3,
    e_chord: Vec3,
    e_thickness: Vec3,
    e_span: Vec3,
}

struct SectionCurve3D {
    radius: f64,
    frame: SectionFrame,
    curve_upper: Curve3,
    curve_lower: Curve3,
    trailing_edge_gap: f64,
}
```

Then the build pipeline becomes:

```text
PropellerModel
  -> evaluate radial distributions
  -> build center/reference frames
  -> generate section family
  -> place section curves in 3D
  -> loft blade surface
  -> build tip patch
  -> close to blade shell/solid
  -> merge with hub
  -> circular pattern
  -> tessellate/export
```

---

## 8. Qt UI Design for This Feature

To mimic the CAESES spirit, the UI should reflect the workflow stages directly.

## 8.1 Suggested panel structure

### Workflow tree
- Center Surface
- Profile Configurator
- Blade Surface
- Tip Surface
- Propeller Solid
- Flow Domain

### Inspector panel
For the selected stage:
- parameter table
- spline editor
- toggles for design variable vs fixed parameter
- validation warnings

### Viewport
- center/reference curves
- radial plots
- section preview at chosen radius
- 3D blade preview
- final solid preview

### Plot dock
For radial distributions:
- pitch
- rake
- skew
- chord
- camber
- thickness
- AoA

This is important: do not hide the radial functions. CAESES makes them explicit because they are the real heart of the parametrization.

---

## 8.2 Editing interaction model

A good UX pattern is:

1. user selects a distribution,
2. Qt shows control points and physical meaning,
3. user drags a point or edits a design variable,
4. frontend sends parameter delta,
5. backend rebuilds affected stages,
6. frontend refreshes plot + 3D preview.

For section debugging, let the user scrub a radial slider \(\eta\) and inspect the exact 2D section at that radius.

That is one of the best debugging tools for this workflow.

---

## 9. Numerical and Geometric Risks

Codex should be aware of the main failure modes.

## 9.1 Loft twisting
Caused by inconsistent section orientation or parameterization.

Mitigation:
- enforce common section start point and winding,
- align frames consistently,
- validate section normals between stations.

## 9.2 Self-intersections near root or tip
Caused by high skew, high rake, extreme pitch, or oversized chord.

Mitigation:
- geometric validation checks after section placement,
- min-distance tests between adjacent sections,
- parameter guard rails.

## 9.3 Degenerate trailing edge
Caused by thickness law collapsing too sharply.

Mitigation:
- minimum TE thickness,
- edge smoothing windows,
- explicit TE mode.

## 9.4 Fillet failure
Caused by invalid blade-hub intersection topology.

Mitigation:
- fallback build without fillet in preview mode,
- helper offset hub,
- staged trim before blend.

## 9.5 Slow rebuilds
Caused by rebuilding solid booleans during every drag.

Mitigation:
- preview mode,
- debounce parameter edits,
- stage-level dirty tracking.

---

## 10. Recommended Build Order for the Feature

Codex should implement the feature in this order.

### Phase 1: Parametric math core
- radial spline evaluation
- profile generator from camberline + thickness
- local pitch angle computation
- section placement in 3D

### Phase 2: Surface generation
- blade section sampling
- main blade loft
- section preview tools

### Phase 3: Closure geometry
- tip patch
- hub primitive
- root trimming / merge

### Phase 4: Solid and patterning
- closed blade body
- circular blade array
- final propeller solid

### Phase 5: UI polish
- workflow tree
- spline editing widgets
- radial plot dock
- per-stage visibility and diagnostics

### Phase 6: CFD support
- flow domain generation
- periodic sector option
- export hooks

---

## 11. Minimal Viable Version

A strong first version does **not** need to replicate every CAESES detail.

Version 1 should include:

- cubic spline radial distributions for pitch, rake, skew, chord
- profile generation from camber + thickness
- spanwise camber and thickness variation
- optional AoA correction
- blade loft
- tip patch
- simple hub
- blade patterning
- mesh preview

Version 1 can postpone:

- sophisticated variable fillet
- advanced edge modes
- full CFD domain wizard
- optimization hooks
- imported profile libraries

---

## 12. Final Recommended Architectural Principle

The propeller workflow should be implemented as a **feature graph**, not as a monolithic propeller object.

That means:

- each stage is a typed node,
- each node has explicit inputs and outputs,
- the frontend edits parameters and stage settings,
- the backend resolves dependencies and rebuilds nodes,
- Truck only receives validated geometric construction requests.

This is the closest conceptual equivalent to the CAESES workflow, and it is the right design for a professional CAD/engineering application.

---

## 13. Practical Summary for Codex

Codex should think of this feature as the composition of three engines:

### 1. Parametrization engine
Evaluates design variables, expressions, and radial B-splines.

### 2. Geometry engine
Builds section curves, transforms them into 3D, lofts surfaces, closes the tip, merges with the hub, and patterns blades.

### 3. Application engine
Synchronizes Qt widgets, state tree, preview meshes, undo/redo, persistence, and backend commands.

The most important mathematical backbone is:

- \(\eta = r/R\) for spanwise normalization,
- \(P(r) = (P/D)(\eta) D\),
- \(\beta(r) = \arctan(P(r)/(2\pi r))\),
- section construction from camberline normals,
- 3D placement through local section frames,
- lofting of consistent section families,
- scaling all dimensional geometry from radius and diameter.

If this structure is respected, the feature will not only reproduce the CAESES workflow conceptually, but also remain maintainable as you later add:

- imported airfoil families,
- BEMT coupling,
- optimization,
- acoustic or CFD workflows,
- unconventional propeller topologies.

---

## Source Basis

This document is based on the CAESES **Advanced Propeller Workflow** tutorial, especially its staged workflow for center surface distributions, profile configuration via camberline and thickness laws, blade surface generation, tip closure, propeller solid creation, and flow domain setup. CAESES explicitly structures the model around radial distributions for pitch, rake, skew, and chord; profile-parameter distributions such as camber, maximum thickness, trailing-edge thickness, and angle of attack; dedicated tip-surface generation; root blending into the hub; and flow-domain dimensions scaled to blade radius. citeturn346804view0turn197193view0
