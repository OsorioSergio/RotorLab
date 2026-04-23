# Propeller Generation Parameter Report

This report documents the parameters used by the current RotorLab advanced propeller generator. It follows the implemented Python DTOs and the Rust/Truck backend, not the broader design target in `Advance_propeller_workflow.md`.

Primary sources:

- `python/src/rotorlab_app/models/propeller.py`: parameter DTOs, defaults, stages, distributions.
- `python/src/rotorlab_app/ui/advanced_propeller.py`: UI controls, ranges, and stage invalidation.
- `rust/rotorlab_propeller_preview/src/lib.rs`: authoritative geometry generation.

## Generation Pipeline

The backend rebuilds the propeller in this order:

1. `center_surface`: evaluates pitch, rake, skew, and chord distributions into span stations.
2. `profile_configurator`: evaluates camber, thickness, and angle-of-attack distributions and builds sampled 2D sections.
3. `section_placement`: places 2D sections into 3D using radius, pitch angle, skew, rake, chord, and angle-of-attack.
4. `tip`: builds a closing tip cap from the final blade section ring.
5. `hub`: builds the shaft hub surface and end caps.
6. `pattern`: computes blade rotation angles.
7. `blade_preview`: lofts/tessellates the blade, root cap, tip cap, and hub, patterns blades, welds mesh vertices, and computes metadata.
8. `diagnostics`: reports validation errors and warnings.

When a parameter changes, the UI marks its stage and every downstream stage dirty. For example, a hub edit rebuilds `hub`, `pattern`, `blade_preview`, and `diagnostics`; a center-surface edit rebuilds almost everything.

Current invalidation caveat: a few values are consumed by earlier Rust stages than the UI currently marks dirty. With a warm backend cache, these can reuse stale upstream artifacts unless a full rebuild happens. The main cases are `span_samples`, `section_eta`, `hub_radius_ratio`, `handedness`, and part of `tessellation_cols`. They are called out in the relevant sections below.

## Coordinate and Unit Conventions

- `eta` is normalized radius: `eta = r / R`.
- `R` is `global_parameters.radius`.
- `D` is propeller diameter: `D = 2R`.
- The shaft axis is currently the `z` axis.
- Rake is applied as axial `z` displacement.
- Skew is applied as azimuthal rotation around `z`.
- Many blade dimensions are nondimensional ratios that become dimensional by multiplying by `R` or `D`.
- Radial distributions are evaluated with Catmull-Rom interpolation after sorting control points by `eta`. Values outside the first/last control point are clamped to the endpoint values.

## Parameters Not Treated as Shape Controls

These fields exist in the DTO but do not directly define the propeller shape:

| Field | Purpose |
| --- | --- |
| `node_id` | Stable cache key for incremental Rust rebuild artifacts. |
| `display_name` | UI label. |
| `module_type` | Identifies the advanced propeller module. |
| `dirty_stages` | Rebuild scheduler input; controls recomputation, not geometry. |
| `show_mesh` | Viewport display toggle only. |
| `show_wireframe` | Viewport display toggle only. |

`show_sections` is mostly a visualization flag, but it does affect whether section polylines are included in the backend preview result.

## Radial Distribution Control Points

Every radial law is a `RadialDistribution` with editable `DistributionControlPoint` entries:

| Parameter | Default behavior | Affects |
| --- | --- | --- |
| `control_points[].eta` | Radial location of a distribution point. Defaults vary by distribution. | Where the distribution value is applied along the blade span. Points are sorted, interpolated with Catmull-Rom, and clamped outside the first/last point. |
| `control_points[].value` | Distribution value at that `eta`. Defaults vary by distribution. | Meaning depends on the distribution: pitch ratio, rake, skew, chord ratio, camber, thickness, or angle-of-attack. |

The editor allows adding/removing points and direct numeric edits. The current UI does not enforce per-distribution numeric bounds for these table values.

## Center Surface Parameters

The center-surface stage defines the reference blade stations. These stations decide where each section is placed and how large/oriented it is.

| Parameter | Default | UI range | Stage dirtied | What it does | Geometry affected |
| --- | ---: | --- | --- | --- | --- |
| `radius` | `2500.0` | `500.0` to `12000.0` | `center_surface` | Defines propeller radius `R`; diameter is `D = 2R`. | Scales almost the whole model: radial station positions, pitch length, chord length, rake displacement, hub radius/length, tip-cap distances, root-cap offsets, mesh weld tolerance, and final bounds. |
| `pitch_reference_deg` | `0.0` | `-12.0` to `12.0` | `section_placement` | Adds a global pitch-angle offset to every placed section: `beta_eff = beta + angle_of_attack + pitch_reference`. | Changes blade twist/section chord direction without changing center-surface station radii or distribution values. |
| `pitch_pd` distribution | `[0.22,0.92]`, `[0.55,1.02]`, `[0.82,1.04]`, `[1.0,0.98]` | table edit | `center_surface` | Pitch-to-diameter ratio `P/D`. Backend computes `P = pitch_pd * D` and `beta = atan2(P, 2*pi*r)`. | Local pitch angle/twist of every span station; indirectly changes the blade loft and final mesh. |
| `rake` distribution | `[0.22,0.00]`, `[0.60,0.03]`, `[0.82,0.08]`, `[1.0,0.12]` | table edit | `center_surface` | Axial offset in units of diameter. Placement uses `z = rake * D`. | Moves sections forward/aft along the shaft axis; changes blade side surface, tip base position, bounds, and visual rake. |
| `skew` distribution | `[0.22,0.00]`, `[0.55,0.12]`, `[0.82,0.22]`, `[1.0,0.30]` | table edit | `center_surface` | Azimuthal section shift in radians. Backend multiplies it by handedness. | Sweeps section centers around the shaft; changes radial/tangential placement frame, blade planform, and tip location. Diagnostics warn if max absolute skew is above `0.65`. |
| `chord` distribution | `[0.22,0.18]`, `[0.45,0.32]`, `[0.72,0.24]`, `[1.0,0.10]` | table edit | `center_surface` | Chord-to-diameter ratio. Backend computes `chord = chord_ratio * D`. | Section scale along the chord direction, blade planform width, root spacing, and patterned overlap risk. Diagnostics warn when root chord is too large for blade count. |

## Profile Configurator Parameters

The profile configurator builds 2D upper/lower section curves before they are placed in 3D.

| Parameter | Default | UI range/options | Stage dirtied | What it does | Geometry affected |
| --- | ---: | --- | --- | --- | --- |
| `camber_family` | `modified_naca` | `modified_naca`, `parabolic`, `elliptic` | `profile_configurator` | Selects the camberline equation. `modified_naca` uses a sine shape, `parabolic` uses `4*x*(1-x)`, and `elliptic` uses an elliptical arc-like shape. | Mean-line shape of the 2D section and the slope used to offset upper/lower surfaces. |
| `thickness_family` | `naca66_like` | `naca66_like`, `ogive`, `elliptic` | `profile_configurator` | Selects the thickness distribution equation. | Upper/lower surface separation along chord; changes nose/body fullness and section ring shape. |
| `trailing_edge_thickness` | `0.006` | `0.001` to `0.03` | `profile_configurator` | Adds trailing-edge thickness as `te_thickness * x^2` and also acts as the minimum thickness. | Opens/thickens the trailing edge and guarantees a nonzero section thickness. |
| `leading_edge_bias` | `0.0` | `-0.3` to `0.3` | `profile_configurator` | Warps normalized chord coordinate before camber/thickness evaluation. Positive values use `x^(1 + bias*1.8)`; negative values bias from the trailing side. | Shifts where camber/thickness features appear along the chord and changes the sampled 2D profile coordinates. |
| `camber` distribution | `[0.22,0.055]`, `[0.60,0.035]`, `[1.0,0.010]` | table edit | `profile_configurator` | Camber amplitude by radius. | Curvature of each 2D section, then the placed blade surface after section placement. |
| `thickness` distribution | `[0.22,0.18]`, `[0.60,0.12]`, `[1.0,0.06]` | table edit | `profile_configurator` | Thickness amplitude by radius. | Section thickness and blade volume/fullness from root to tip. |
| `angle_of_attack` distribution | `[0.22,0.0]`, `[0.70,1.8]`, `[1.0,-0.4]` | table edit | `profile_configurator` | Local angular correction in degrees. | Added to pitch angle during 3D placement; changes local section incidence/twist but not the 2D profile shape. |

The backend currently builds section curves with `camber_scale = 1.0` and `thickness_scale = 1.0`; tip fades are applied later in the tip closure stage rather than during profile creation.

## Section Placement and Preview Sampling Parameters

These parameters control how many sections and points are generated, and which section is shown in profile/placement previews.

| Parameter | Default | UI range | Stage dirtied | What it does | Geometry affected |
| --- | ---: | --- | --- | --- | --- |
| `span_samples` | `18` | `8` to `40` | `section_placement` | Number of radial stations/section rings from hub cutoff to tip. Backend uses at least `10`, and the station list is actually built in `center_surface`. | More samples create more blade loft control rings and smoother spanwise geometry; also changes face count indirectly. Current cache invalidation should ideally start at `center_surface`. |
| `chord_samples` | `36` | `12` to `64` | `section_placement` | Number of points sampled per upper or lower 2D curve. Backend uses at least `24`. It is used by both selected profile samples and spanwise placed sections. | Controls section-ring resolution; each blade section ring is built from upper + reversed lower + closing point. Affects blade surface control columns and section preview detail. |
| `section_eta` | `0.7` | `hub_radius_ratio` to `1.0` | `section_placement` | Chooses the radial station used for returned 2D/3D section samples in the UI. It is clamped to the hub radius, and the selected profile sample is created in `profile_configurator`. | Preview/sample output only in the current backend. The main blade mesh still uses all span stations generated from `span_samples`. Current cache invalidation should ideally refresh `profile_configurator`. |
| `tessellation_rows` | `64` | `12` to `120` | `blade_preview` | Number of samples along the surface row direction during tessellation. Blade uses this directly; root/tip/hub use fractions of it. | Mesh density, face count, smoothness, and render cost. Does not change the underlying blade station math. |
| `tessellation_cols` | `120` | `24` to `180` | `blade_preview` | Number of samples around/across surfaces during tessellation. Hub ring generation also uses at least `48` points from this value when the hub stage is rebuilt. | Mesh density and hub circumferential control resolution. Higher values make hub and tessellated surfaces smoother. Current cache invalidation updates tessellation but may reuse the previous hub surface. |
| `show_sections` | `false` | checkbox | `blade_preview` when enabled through rebuild path | Requests section polylines in the preview mesh result. | Adds per-blade section polylines for display; does not change preview mesh vertices/faces. |

## Tip Surface Parameters

The tip stage starts from the final placed blade ring, computes a centroid, radial direction, axial direction, closure rings, and a repeated-point apex ring. These rings are skinned into a Truck B-spline surface.

| Parameter | Default | UI range | Stage dirtied | What it does | Geometry affected |
| --- | ---: | --- | --- | --- | --- |
| `closure_bias` | `0.36` | `0.05` to `0.95` | `tip` | Biases intermediate closure rings using `radial_dir * (closure_bias - 0.5)` combined with axial shift. | Moves the closing cap path inward/outward relative to the blade tip and affects closure asymmetry. |
| `roundness` | `0.62` | `0.05` to `1.0` | `tip` | Changes apex radial offset and the shrink exponent for closure rings. | Controls how bulbous or tight the tip cap is. Larger values generally produce a rounder, more gradual closure. |
| `cap_depth_ratio` | `0.08` | `0.01` to `0.25` | `tip` | Scales radial apex offset by `D * cap_depth_ratio * 0.18 * (0.6 + roundness)`. | Outboard depth/protrusion of the tip cap. Diagnostics warn when this is above `0.24`. |
| `cap_length_ratio` | `0.14` | `0.01` to `0.35` | `tip` | Scales axial apex offset and intermediate closure-ring shift. | Axial length of the tip closure. Diagnostics warn when this is above `0.34`. |
| `tip_thickness_fade` | `0.78` | `0.10` to `1.0` | `tip` | Adds a small fade-driven radial shift to intermediate closure rings. | Influences how section thickness visually disappears into the tip cap. |
| `tip_camber_fade` | `0.64` | `0.10` to `1.0` | `tip` | Adds a mid-closure radial camber-like shift using `t * (1-t)`. | Shapes the curvature/swell of the tip closure between base ring and apex. |
| `tip_rake_fade` | `0.24` | `0.0` to `1.0` | `tip` | Adds to the axial apex offset factor: `D * cap_length_ratio * (0.3 + tip_rake_fade)`. | Pulls the tip apex farther along the shaft axis, changing tip rake and bounds. |

## Hub Blend Parameters

The hub stage generates a closed hub as circular rings plus fore/aft cap surfaces. Some root blend parameters are used later when the blade root cap is built.

| Parameter | Default | UI range | Stage dirtied | What it does | Geometry affected |
| --- | ---: | --- | --- | --- | --- |
| `hub_radius_ratio` | `0.22` | `0.10` to `0.45` | `hub` | Defines hub radius as `R * hub_radius_ratio`. It also defines the inner blade span cutoff `eta_hub`. | Hub radius, root station radius, start of radial distributions, section-eta minimum, root chord spacing, and all section stations. Although the UI dirties `hub`, this value also affects center-surface station generation. |
| `hub_length_ratio` | `0.34` | `0.08` to `0.70` | `hub` | Defines total hub axial length as `D * hub_length_ratio`. | Fore/aft hub extent, cap positions, mesh bounds, and hub visual proportions. |
| `fore_profile_split` | `0.42` | `0.05` to `0.90` | `hub` | Share of total hub length placed in the negative axial direction after normalizing with aft split. | Fore hub length and fore cap location. |
| `aft_profile_split` | `0.58` | `0.05` to `0.95` | `hub` | Share of total hub length placed in the positive axial direction after normalizing with fore split. | Aft hub length and aft cap location. |
| `root_cutback_start` | `0.18` | `0.01` to `0.60` | `hub` | Moves the blade root cap center radially inward by `R * root_cutback_start * 0.22`. | Root cap shape/blend into hub area; affects the blade root closure, not the circular hub body itself. |
| `root_le_blend_ratio` | `0.08` | `0.0` to `0.20` | `hub` | Contributes to root cap axial offset as `R * (root_le_blend_ratio - root_te_blend_ratio) * 0.4`. | Biases root cap center toward the leading-edge side in the current root-closure approximation. |
| `root_te_blend_ratio` | `0.06` | `0.0` to `0.20` | `hub` | Counterpart to `root_le_blend_ratio` in the same axial offset equation. | Biases root cap center toward the trailing-edge side. Diagnostics warn if LE + TE blend exceeds `0.30`. |

Important implementation note: `hub_radius_ratio` is both a hub parameter and a center-surface input. A robust invalidation rule should rebuild from `center_surface` when it changes, because it changes `eta_hub` and every span station.

## Pattern Parameters

The pattern stage computes blade rotation angles, then the preview stage appends one rotated blade mesh, root cap, and tip cap for each angle.

| Parameter | Default | UI range/options | Stage dirtied | What it does | Geometry affected |
| --- | ---: | --- | --- | --- | --- |
| `num_blades` | `4` | `2` to `8` | `pattern` | Number of blades to pattern. Backend also protects with `max(1)` and diagnostics error below `2`. | Number of repeated blade components, face count, metadata `blade_count`, `component_count`, and collision risk. |
| `start_angle_deg` | `0.0` | `-180.0` to `180.0` | `pattern` | Global phase angle for the first blade. | Rotates the entire blade pattern around the shaft axis. |
| `handedness` | `right` | `right`, `left` | `pattern` | `right` uses positive sign; `left` uses negative sign. The same sign also affects skew during station generation in `center_surface`. | Mirrors rotation direction and skew direction; changes blade sweep and pattern orientation. Current cache invalidation should ideally start at `center_surface` when handedness changes. |
| `axis_convention` | `z` | `z` only in UI | `pattern` | Declares shaft-axis convention. Current Rust backend only supports `z`. | No alternate geometry transform currently exists. Diagnostics error if a non-`z` value reaches Rust. |

## Diagnostics Affected by Parameters

The backend reports:

| Diagnostic trigger | Parameters involved | Stage |
| --- | --- | --- |
| Fewer than two blades | `num_blades` | `pattern` |
| Unsupported axis convention | `axis_convention` | `pattern` |
| Aggressive tip cap values | `cap_depth_ratio`, `cap_length_ratio` | `tip` |
| Large root blend ratios | `root_le_blend_ratio`, `root_te_blend_ratio` | `hub` |
| Tight root chord spacing | `num_blades`, `hub_radius_ratio`, `chord` distribution, `radius` | `pattern` |
| Empty preview mesh | any upstream geometry/resolution issue | `blade_preview` |
| Non-watertight assembled mesh | tip/root/hub/loft/tessellation parameters | `blade_preview` |
| High skew | `skew` distribution, `handedness` | `section_placement` |

## Practical Mental Model

- Use `radius`, `hub_radius_ratio`, `chord`, `pitch_pd`, `rake`, and `skew` to define the main blade planform and placement.
- Use profile parameters and the `camber`, `thickness`, and `angle_of_attack` distributions to define local section shape and incidence.
- Use `span_samples` and `chord_samples` to control the smoothness and detail of the blade construction inputs.
- Use tip parameters to tune the closure from the last section to the tip apex.
- Use hub parameters to tune the shaft body and blade-root cap approximation.
- Use pattern parameters to decide how many blades exist and how they are arranged around the shaft.
- Use tessellation parameters and display toggles to control preview fidelity and rendering cost.
