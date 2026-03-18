use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::f64::consts::PI;
use std::sync::{Mutex, OnceLock};
use std::time::Instant;
use truck_geometry::prelude::{BSplineSurface, KnotVec, ParametricSurface, Point3};

const BACKEND_CONTRACT: &str = "rotorlab-propeller-build:2026-03-17.1";
const STAGE_ORDER: [&str; 8] = [
    "center_surface",
    "profile_configurator",
    "section_placement",
    "tip",
    "hub",
    "pattern",
    "blade_preview",
    "diagnostics",
];

#[derive(Debug, Clone, Deserialize)]
struct DistributionControlPoint {
    eta: f64,
    value: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct RadialDistribution {
    #[allow(dead_code)]
    key: String,
    #[allow(dead_code)]
    label: String,
    #[allow(dead_code)]
    unit: String,
    #[allow(dead_code)]
    stage: String,
    control_points: Vec<DistributionControlPoint>,
}

#[derive(Debug, Clone, Deserialize)]
struct GlobalParameters {
    radius: f64,
    pitch_reference_deg: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct ProfileDefinition {
    camber_family: String,
    thickness_family: String,
    trailing_edge_thickness: f64,
    leading_edge_bias: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct PreviewSettings {
    span_samples: usize,
    chord_samples: usize,
    section_eta: f64,
    tessellation_rows: usize,
    tessellation_cols: usize,
    #[allow(dead_code)]
    show_mesh: bool,
    #[allow(dead_code)]
    show_wireframe: bool,
    show_sections: bool,
}

#[derive(Debug, Clone, Deserialize)]
struct TipParameters {
    closure_bias: f64,
    roundness: f64,
    cap_depth_ratio: f64,
    cap_length_ratio: f64,
    tip_thickness_fade: f64,
    tip_camber_fade: f64,
    tip_rake_fade: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct HubParameters {
    hub_radius_ratio: f64,
    hub_length_ratio: f64,
    fore_profile_split: f64,
    aft_profile_split: f64,
    root_cutback_start: f64,
    root_le_blend_ratio: f64,
    root_te_blend_ratio: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct PatternParameters {
    num_blades: u32,
    start_angle_deg: f64,
    handedness: String,
    axis_convention: String,
}

#[derive(Debug, Clone, Deserialize)]
struct PropellerFeatureState {
    node_id: String,
    #[allow(dead_code)]
    display_name: String,
    #[allow(dead_code)]
    module_type: String,
    global_parameters: GlobalParameters,
    profile_definition: ProfileDefinition,
    preview_settings: PreviewSettings,
    tip_parameters: TipParameters,
    hub_parameters: HubParameters,
    pattern_parameters: PatternParameters,
    distributions: BTreeMap<String, RadialDistribution>,
}

#[derive(Debug, Clone, Deserialize)]
struct PropellerBuildRequestDto {
    feature_state: PropellerFeatureState,
    dirty_stages: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct PropellerDiagnosticDto {
    severity: String,
    stage: String,
    message: String,
}

#[derive(Debug, Clone, Default, Serialize)]
struct PropellerBuildMeshDto {
    vertices: Vec<[f64; 3]>,
    faces: Vec<[usize; 3]>,
    section_polylines: Vec<Vec<[f64; 3]>>,
}

#[derive(Debug, Clone, Serialize)]
struct PropellerModelMetadataDto {
    source: String,
    valid: bool,
    watertight: bool,
    blade_count: u32,
    component_count: usize,
    bounds_min: [f64; 3],
    bounds_max: [f64; 3],
    topology_status: Value,
}

#[derive(Debug, Clone, Serialize)]
struct PropellerBuildResponseDto {
    ok: bool,
    built_stages: Vec<String>,
    stage_timings_ms: BTreeMap<String, f64>,
    radial_series: BTreeMap<String, Vec<[f64; 2]>>,
    section_samples: BTreeMap<String, Vec<Vec<[f64; 2]>>>,
    placed_section_samples: BTreeMap<String, Vec<Vec<[f64; 3]>>>,
    preview_mesh: PropellerBuildMeshDto,
    diagnostics: Vec<PropellerDiagnosticDto>,
    model_metadata: PropellerModelMetadataDto,
}

#[derive(Debug, Clone)]
struct Station {
    eta: f64,
    radius: f64,
    rake: f64,
    skew: f64,
    chord: f64,
    beta: f64,
}

#[derive(Debug, Clone)]
struct PlacedSection {
    eta: f64,
    upper: Vec<[f64; 3]>,
    lower: Vec<[f64; 3]>,
    ring: Vec<[f64; 3]>,
}

#[derive(Debug, Clone, Default)]
struct CenterSurfaceArtifact {
    radial_series: BTreeMap<String, Vec<[f64; 2]>>,
    stations: Vec<Station>,
}

#[derive(Debug, Clone, Default)]
struct ProfileConfiguratorArtifact {
    radial_series: BTreeMap<String, Vec<[f64; 2]>>,
    section_samples: BTreeMap<String, Vec<Vec<[f64; 2]>>>,
    selected_eta: f64,
}

#[derive(Debug, Clone, Default)]
struct SectionPlacementArtifact {
    placed_sections: BTreeMap<String, Vec<Vec<[f64; 3]>>>,
    span_sections: Vec<PlacedSection>,
}

#[derive(Debug, Clone)]
struct TipArtifact {
    closure_rings: Vec<Vec<[f64; 3]>>,
    tip_surface: BSplineSurface<Point3>,
    apex: [f64; 3],
}

#[derive(Debug, Clone)]
struct HubArtifact {
    hub_rings: Vec<Vec<[f64; 3]>>,
    hub_surface: BSplineSurface<Point3>,
    fore_cap_surface: BSplineSurface<Point3>,
    aft_cap_surface: BSplineSurface<Point3>,
}

#[derive(Debug, Clone)]
struct PatternArtifact {
    blade_angles_rad: Vec<f64>,
}

#[derive(Debug, Clone, Default)]
struct MeshPart {
    vertices: Vec<[f64; 3]>,
    faces: Vec<[usize; 3]>,
}

#[derive(Debug, Clone)]
struct BuildMeshArtifact {
    mesh: PropellerBuildMeshDto,
    model_metadata: PropellerModelMetadataDto,
}

#[derive(Debug, Clone)]
struct CachedBuildArtifacts {
    center_surface: CenterSurfaceArtifact,
    profile_configurator: ProfileConfiguratorArtifact,
    section_placement: SectionPlacementArtifact,
    tip_artifact: TipArtifact,
    hub_artifact: HubArtifact,
    pattern_artifact: PatternArtifact,
    build_mesh: BuildMeshArtifact,
}

static BUILD_CACHE: OnceLock<Mutex<HashMap<String, CachedBuildArtifacts>>> = OnceLock::new();

fn build_cache() -> &'static Mutex<HashMap<String, CachedBuildArtifacts>> {
    BUILD_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn load_cached_artifacts(node_id: &str) -> Option<CachedBuildArtifacts> {
    let cache = build_cache().lock().ok()?;
    cache.get(node_id).cloned()
}

fn store_cached_artifacts(node_id: &str, artifacts: CachedBuildArtifacts) {
    if let Ok(mut cache) = build_cache().lock() {
        if cache.len() >= 24 && !cache.contains_key(node_id) {
            cache.clear();
        }
        cache.insert(node_id.to_string(), artifacts);
    }
}

#[pyfunction]
fn propeller_backend_contract() -> &'static str {
    BACKEND_CONTRACT
}

#[pyfunction]
fn propeller_build_model(payload: &str) -> PyResult<String> {
    let request: PropellerBuildRequestDto = serde_json::from_str(payload).map_err(|err| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Invalid propeller build payload: {err}"
        ))
    })?;
    let response = build_model_internal(&request).map_err(|message| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Propeller build failed: {message}"
        ))
    })?;
    serde_json::to_string(&response).map_err(|err| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Could not encode propeller build response: {err}"
        ))
    })
}

#[allow(dead_code)]
#[pyfunction]
fn propeller_backend_api_version() -> &'static str {
    "2.0.0"
}

#[allow(dead_code)]
#[pyfunction]
fn propeller_rebuild_preview(payload: &str) -> PyResult<String> {
    propeller_build_model(payload)
}

fn build_model_internal(
    request: &PropellerBuildRequestDto,
) -> Result<PropellerBuildResponseDto, String> {
    let dirty_stages: Vec<String> = request
        .dirty_stages
        .iter()
        .filter(|stage| stage_index(stage).is_some())
        .cloned()
        .collect();
    let dirty_stages = if dirty_stages.is_empty() {
        STAGE_ORDER
            .iter()
            .map(|stage| (*stage).to_string())
            .collect::<Vec<_>>()
    } else {
        dirty_stages
    };
    let start_index = dirty_stages
        .iter()
        .filter_map(|stage| stage_index(stage))
        .min()
        .unwrap_or(0);
    let state = &request.feature_state;
    let cached_artifacts = load_cached_artifacts(&state.node_id);
    let start_index = if start_index > 0 && cached_artifacts.is_none() {
        0
    } else {
        start_index
    };
    let mut timings = BTreeMap::new();

    let center_surface = if start_index > 0 {
        match cached_artifacts.as_ref() {
            Some(cache) => cache.center_surface.clone(),
            None => build_center_surface(state),
        }
    } else {
        let start = Instant::now();
        let artifact = build_center_surface(state);
        record_timing(&mut timings, start_index, 0, "center_surface", start);
        artifact
    };

    let profile_configurator = if start_index > 1 {
        match cached_artifacts.as_ref() {
            Some(cache) => cache.profile_configurator.clone(),
            None => build_profile_configurator(state),
        }
    } else {
        let start = Instant::now();
        let artifact = build_profile_configurator(state);
        record_timing(&mut timings, start_index, 1, "profile_configurator", start);
        artifact
    };

    let section_placement = if start_index > 2 {
        match cached_artifacts.as_ref() {
            Some(cache) => cache.section_placement.clone(),
            None => build_section_placement(state, &center_surface, &profile_configurator),
        }
    } else {
        let start = Instant::now();
        let artifact = build_section_placement(state, &center_surface, &profile_configurator);
        record_timing(&mut timings, start_index, 2, "section_placement", start);
        artifact
    };

    let tip_artifact = if start_index > 3 {
        match cached_artifacts.as_ref() {
            Some(cache) => cache.tip_artifact.clone(),
            None => build_tip_stage(state, &section_placement)?,
        }
    } else {
        let start = Instant::now();
        let artifact = build_tip_stage(state, &section_placement)?;
        record_timing(&mut timings, start_index, 3, "tip", start);
        artifact
    };

    let hub_artifact = if start_index > 4 {
        match cached_artifacts.as_ref() {
            Some(cache) => cache.hub_artifact.clone(),
            None => build_hub_stage(state)?,
        }
    } else {
        let start = Instant::now();
        let artifact = build_hub_stage(state)?;
        record_timing(&mut timings, start_index, 4, "hub", start);
        artifact
    };

    let pattern_artifact = if start_index > 5 {
        match cached_artifacts.as_ref() {
            Some(cache) => cache.pattern_artifact.clone(),
            None => build_pattern_stage(state),
        }
    } else {
        let start = Instant::now();
        let artifact = build_pattern_stage(state);
        record_timing(&mut timings, start_index, 5, "pattern", start);
        artifact
    };

    let build_mesh = if start_index > 6 {
        match cached_artifacts.as_ref() {
            Some(cache) => cache.build_mesh.clone(),
            None => build_preview_mesh(
                state,
                &section_placement,
                &tip_artifact,
                &hub_artifact,
                &pattern_artifact,
            )?,
        }
    } else {
        let start = Instant::now();
        let artifact = build_preview_mesh(
            state,
            &section_placement,
            &tip_artifact,
            &hub_artifact,
            &pattern_artifact,
        )?;
        record_timing(&mut timings, start_index, 6, "blade_preview", start);
        artifact
    };

    let start = Instant::now();
    let diagnostics = build_diagnostics(
        state,
        &center_surface,
        &section_placement,
        &tip_artifact,
        &hub_artifact,
        &build_mesh,
    );
    record_timing(&mut timings, start_index, 7, "diagnostics", start);

    let built_stages = STAGE_ORDER[start_index..]
        .iter()
        .map(|stage| (*stage).to_string())
        .collect::<Vec<_>>();
    let ok =
        !diagnostics.iter().any(|item| item.severity == "error") && build_mesh.model_metadata.valid;

    store_cached_artifacts(
        &state.node_id,
        CachedBuildArtifacts {
            center_surface: center_surface.clone(),
            profile_configurator: profile_configurator.clone(),
            section_placement: section_placement.clone(),
            tip_artifact: tip_artifact.clone(),
            hub_artifact: hub_artifact.clone(),
            pattern_artifact: pattern_artifact.clone(),
            build_mesh: build_mesh.clone(),
        },
    );

    Ok(PropellerBuildResponseDto {
        ok,
        built_stages,
        stage_timings_ms: timings,
        radial_series: merge_radial_series(
            &center_surface.radial_series,
            &profile_configurator.radial_series,
        ),
        section_samples: profile_configurator.section_samples,
        placed_section_samples: section_placement.placed_sections,
        preview_mesh: build_mesh.mesh,
        diagnostics,
        model_metadata: build_mesh.model_metadata,
    })
}

fn build_center_surface(state: &PropellerFeatureState) -> CenterSurfaceArtifact {
    let eta_hub = clamp(state.hub_parameters.hub_radius_ratio, 0.10, 0.45);
    let mut radial_series = BTreeMap::new();
    let sample_etas = (0..64).map(|index| index as f64 / 63.0).collect::<Vec<_>>();

    for key in ["pitch_pd", "rake", "skew", "chord"] {
        let samples = sample_etas
            .iter()
            .map(|eta| {
                let mapped_eta = clamp(eta_hub + eta * (1.0 - eta_hub), eta_hub, 1.0);
                [*eta, distribution_value(state, key, mapped_eta)]
            })
            .collect::<Vec<_>>();
        radial_series.insert(key.to_string(), samples);
    }

    CenterSurfaceArtifact {
        radial_series,
        stations: sample_center_stations(state, state.preview_settings.span_samples.max(10)),
    }
}

fn build_profile_configurator(state: &PropellerFeatureState) -> ProfileConfiguratorArtifact {
    let eta_hub = clamp(state.hub_parameters.hub_radius_ratio, 0.10, 0.45);
    let mut radial_series = BTreeMap::new();
    let sample_etas = (0..64).map(|index| index as f64 / 63.0).collect::<Vec<_>>();

    for key in ["camber", "thickness", "angle_of_attack"] {
        let samples = sample_etas
            .iter()
            .map(|eta| {
                let mapped_eta = clamp(eta_hub + eta * (1.0 - eta_hub), eta_hub, 1.0);
                [*eta, distribution_value(state, key, mapped_eta)]
            })
            .collect::<Vec<_>>();
        radial_series.insert(key.to_string(), samples);
    }

    let selected_eta = clamp(state.preview_settings.section_eta, eta_hub, 1.0);
    let section_curves = build_section_curves(
        state,
        selected_eta,
        state.preview_settings.chord_samples.max(24),
        1.0,
        1.0,
    );
    let mut section_samples = BTreeMap::new();
    section_samples.insert(format!("{selected_eta:.3}"), section_curves);

    ProfileConfiguratorArtifact {
        radial_series,
        section_samples,
        selected_eta,
    }
}

fn build_section_placement(
    state: &PropellerFeatureState,
    center_surface: &CenterSurfaceArtifact,
    profile_configurator: &ProfileConfiguratorArtifact,
) -> SectionPlacementArtifact {
    let mut placed_sections = BTreeMap::new();
    let selected_key = format!("{:.3}", profile_configurator.selected_eta);
    let mut selected_sections = Vec::<Vec<[f64; 3]>>::new();
    let mut span_sections = Vec::<PlacedSection>::new();

    for station in &center_surface.stations {
        let section_curves = build_section_curves(
            state,
            station.eta,
            state.preview_settings.chord_samples.max(24),
            1.0,
            1.0,
        );
        let upper = place_section_curve(state, station, &section_curves[0], station.eta);
        let lower = place_section_curve(state, station, &section_curves[1], station.eta);
        let ring = build_ring_from_surfaces(&upper, &lower);
        if selected_sections.is_empty()
            || (station.eta - profile_configurator.selected_eta).abs() <= 1e-6
        {
            selected_sections = vec![upper.clone(), lower.clone()];
        }
        span_sections.push(PlacedSection {
            eta: station.eta,
            upper,
            lower,
            ring,
        });
    }

    placed_sections.insert(selected_key, selected_sections);
    SectionPlacementArtifact {
        placed_sections,
        span_sections,
    }
}

fn build_tip_stage(
    state: &PropellerFeatureState,
    section_placement: &SectionPlacementArtifact,
) -> Result<TipArtifact, String> {
    let tip_base = section_placement
        .span_sections
        .last()
        .ok_or_else(|| "No span sections available for tip construction.".to_string())?;
    let base_ring = &tip_base.ring;
    let core_ring = &base_ring[..base_ring.len().saturating_sub(1)];
    let centroid = average_point3(core_ring);
    let radial_dir = normalize3([centroid[0], centroid[1], 0.0]);
    let axial_dir = [0.0, 0.0, 1.0];
    let diameter = state.global_parameters.radius * 2.0;
    let tip = &state.tip_parameters;

    let apex = add3(
        centroid,
        add3(
            scale3(
                radial_dir,
                diameter * tip.cap_depth_ratio * 0.18 * (0.6 + tip.roundness),
            ),
            scale3(
                axial_dir,
                diameter * tip.cap_length_ratio * (0.3 + tip.tip_rake_fade),
            ),
        ),
    );

    let mut closure_rings = Vec::new();
    closure_rings.push(base_ring.clone());

    let rows = 4usize;
    for index in 1..rows {
        let t = index as f64 / rows as f64;
        let shrink = (1.0 - t).powf(0.65 + tip.roundness * 1.35);
        let camber_shift = tip.tip_camber_fade * diameter * 0.004 * t * (1.0 - t);
        let thickness_shift = tip.tip_thickness_fade * diameter * 0.0025 * t;
        let closure_shift = scale3(
            add3(axial_dir, scale3(radial_dir, tip.closure_bias - 0.5)),
            diameter * tip.cap_length_ratio * t * 0.12,
        );
        let ring = core_ring
            .iter()
            .map(|point| {
                let mut next = blend3(centroid, *point, shrink);
                next = add3(next, closure_shift);
                add3(
                    next,
                    scale3(
                        radial_dir,
                        camber_shift + thickness_shift * radial_dir[0].abs(),
                    ),
                )
            })
            .collect::<Vec<_>>();
        closure_rings.push(close_ring(ring));
    }

    let final_ring = close_ring(vec![apex; core_ring.len()]);
    closure_rings.push(final_ring);

    let tip_surface = build_surface_from_rings(&closure_rings)?;
    Ok(TipArtifact {
        closure_rings,
        tip_surface,
        apex,
    })
}

fn build_hub_stage(state: &PropellerFeatureState) -> Result<HubArtifact, String> {
    let hub = &state.hub_parameters;
    let radius = state.global_parameters.radius * clamp(hub.hub_radius_ratio, 0.10, 0.45);
    let length = state.global_parameters.radius * 2.0 * clamp(hub.hub_length_ratio, 0.08, 0.70);
    let fore_share = clamp(hub.fore_profile_split, 0.05, 0.95);
    let aft_share = clamp(hub.aft_profile_split, 0.05, 0.95);
    let share_sum = fore_share + aft_share;
    let fore_len = length * (fore_share / share_sum);
    let aft_len = length * (aft_share / share_sum);
    let ring_points = state.preview_settings.tessellation_cols.max(48);
    let ring_count = 8usize;
    let end_radius = radius * 0.12;

    let mut hub_rings = Vec::new();
    for index in 0..ring_count {
        let t = index as f64 / (ring_count.saturating_sub(1).max(1) as f64);
        let z = -fore_len + t * (fore_len + aft_len);
        let profile = if t <= 0.5 {
            let local = t / 0.5;
            end_radius + (radius - end_radius) * local.sin().powf(0.9)
        } else {
            let local = (t - 0.5) / 0.5;
            end_radius + (radius - end_radius) * (1.0 - local).sin().powf(0.9)
        };
        hub_rings.push(circle_ring(profile.max(end_radius), z, ring_points));
    }

    let fore_center = [0.0, 0.0, -fore_len];
    let aft_center = [0.0, 0.0, aft_len];
    let fore_cap_surface = build_cap_surface(&hub_rings[0], fore_center)?;
    let aft_cap_surface = build_cap_surface(
        hub_rings
            .last()
            .ok_or_else(|| "Hub ring generation failed.".to_string())?,
        aft_center,
    )?;
    let hub_surface = build_surface_from_rings(&hub_rings)?;

    Ok(HubArtifact {
        hub_rings,
        hub_surface,
        fore_cap_surface,
        aft_cap_surface,
    })
}

fn build_pattern_stage(state: &PropellerFeatureState) -> PatternArtifact {
    let blade_count = state.pattern_parameters.num_blades.max(1) as usize;
    let handedness_sign = handedness_sign(&state.pattern_parameters);
    let start_angle = state.pattern_parameters.start_angle_deg.to_radians();
    let blade_angles_rad = (0..blade_count)
        .map(|index| {
            handedness_sign * (start_angle + (2.0 * PI * index as f64) / blade_count as f64)
        })
        .collect::<Vec<_>>();
    PatternArtifact { blade_angles_rad }
}

fn build_preview_mesh(
    state: &PropellerFeatureState,
    section_placement: &SectionPlacementArtifact,
    tip_artifact: &TipArtifact,
    hub_artifact: &HubArtifact,
    pattern_artifact: &PatternArtifact,
) -> Result<BuildMeshArtifact, String> {
    let section_rings = section_placement
        .span_sections
        .iter()
        .map(|section| section.ring.clone())
        .collect::<Vec<_>>();
    let blade_surface = build_surface_from_rings(&section_rings)?;
    let root_center = root_cap_center(state, &section_placement.span_sections[0]);
    let root_cap_surface =
        build_cap_surface(&section_placement.span_sections[0].ring, root_center)?;

    let rows = state.preview_settings.tessellation_rows.max(16);
    let cols = state.preview_settings.tessellation_cols.max(48);
    let blade_side_mesh = tessellate_surface(&blade_surface, rows, cols);
    let root_cap_mesh = tessellate_surface(&root_cap_surface, (rows / 3).max(6), cols);
    let tip_cap_mesh = tessellate_surface(&tip_artifact.tip_surface, (rows / 3).max(6), cols);
    let hub_side_mesh = tessellate_surface(&hub_artifact.hub_surface, (rows / 3).max(10), cols);
    let hub_fore_mesh = tessellate_surface(&hub_artifact.fore_cap_surface, 6, cols);
    let hub_aft_mesh = tessellate_surface(&hub_artifact.aft_cap_surface, 6, cols);

    let mut assembled_vertices = Vec::<[f64; 3]>::new();
    let mut assembled_faces = Vec::<[usize; 3]>::new();
    let mut section_polylines = Vec::<Vec<[f64; 3]>>::new();

    append_mesh(
        &mut assembled_vertices,
        &mut assembled_faces,
        &hub_side_mesh,
        0.0,
    );
    append_mesh(
        &mut assembled_vertices,
        &mut assembled_faces,
        &hub_fore_mesh,
        0.0,
    );
    append_mesh(
        &mut assembled_vertices,
        &mut assembled_faces,
        &hub_aft_mesh,
        0.0,
    );

    for angle in &pattern_artifact.blade_angles_rad {
        append_mesh(
            &mut assembled_vertices,
            &mut assembled_faces,
            &blade_side_mesh,
            *angle,
        );
        append_mesh(
            &mut assembled_vertices,
            &mut assembled_faces,
            &root_cap_mesh,
            *angle,
        );
        append_mesh(
            &mut assembled_vertices,
            &mut assembled_faces,
            &tip_cap_mesh,
            *angle,
        );
        if state.preview_settings.show_sections {
            for ring in &section_rings {
                section_polylines.push(rotate_polyline_z(ring, *angle));
            }
        }
    }

    let welded_mesh = weld_mesh(
        PropellerBuildMeshDto {
            vertices: assembled_vertices,
            faces: assembled_faces,
            section_polylines,
        },
        (state.global_parameters.radius * 1e-7).max(1e-4),
    );
    let (bounds_min, bounds_max) = mesh_bounds(&welded_mesh.vertices);
    let watertight = mesh_is_watertight(&welded_mesh);
    let component_count = pattern_artifact.blade_angles_rad.len() + 1;

    Ok(BuildMeshArtifact {
        mesh: welded_mesh,
        model_metadata: PropellerModelMetadataDto {
            source: "truck_tessellation".to_string(),
            valid: !bounds_min.iter().any(|value| value.is_nan()),
            watertight,
            blade_count: state.pattern_parameters.num_blades.max(1),
            component_count,
            bounds_min,
            bounds_max,
            topology_status: json!({
                "hub_closed": true,
                "blade_components_closed": watertight,
                "single_component": false,
                "axis_convention": state.pattern_parameters.axis_convention,
                "tip_apex": tip_artifact.apex,
                "hub_rings": hub_artifact.hub_rings.len(),
            }),
        },
    })
}

fn build_diagnostics(
    state: &PropellerFeatureState,
    center_surface: &CenterSurfaceArtifact,
    section_placement: &SectionPlacementArtifact,
    tip_artifact: &TipArtifact,
    _hub_artifact: &HubArtifact,
    build_mesh: &BuildMeshArtifact,
) -> Vec<PropellerDiagnosticDto> {
    let mut diagnostics = Vec::new();

    if state.pattern_parameters.num_blades < 2 {
        diagnostics.push(error("pattern", "At least two blades are required."));
    }
    if state.pattern_parameters.axis_convention.to_lowercase() != "z" {
        diagnostics.push(error(
            "pattern",
            "Only the z-axis shaft convention is supported by the Rust backend.",
        ));
    }
    if state.tip_parameters.cap_depth_ratio > 0.24 || state.tip_parameters.cap_length_ratio > 0.34 {
        diagnostics.push(warning(
            "tip",
            "Aggressive tip cap values may distort the Truck tip closure.",
        ));
    }
    if state.hub_parameters.root_le_blend_ratio + state.hub_parameters.root_te_blend_ratio > 0.30 {
        diagnostics.push(warning(
            "hub",
            "Large root blend ratios may cause root/hub overlap in downstream solid modeling.",
        ));
    }
    if estimate_pattern_collision(state, center_surface) {
        diagnostics.push(warning(
            "pattern",
            "Root chord spacing is tight for the current blade count and may cause patterned overlap.",
        ));
    }
    if build_mesh.mesh.vertices.is_empty() || build_mesh.mesh.faces.is_empty() {
        diagnostics.push(error(
            "blade_preview",
            "Truck tessellation did not produce a preview mesh.",
        ));
    }
    if !build_mesh.model_metadata.watertight {
        diagnostics.push(error(
            "blade_preview",
            "The assembled preview mesh is not watertight after tessellation.",
        ));
    }
    if center_surface
        .stations
        .iter()
        .map(|station| station.skew.abs())
        .max_by(|left, right| left.total_cmp(right))
        .unwrap_or(0.0)
        > 0.65
    {
        diagnostics.push(warning(
            "section_placement",
            "High skew may increase the risk of section self-intersection near the tip.",
        ));
    }
    diagnostics.push(info(
        "diagnostics",
        format!(
            "Built {} placed sections, {} closure rings, and {} preview faces.",
            section_placement.span_sections.len(),
            tip_artifact.closure_rings.len(),
            build_mesh.mesh.faces.len()
        ),
    ));
    diagnostics
}

fn sample_center_stations(state: &PropellerFeatureState, span_samples: usize) -> Vec<Station> {
    let eta_hub = clamp(state.hub_parameters.hub_radius_ratio, 0.10, 0.45);
    let diameter = state.global_parameters.radius * 2.0;
    let handedness = handedness_sign(&state.pattern_parameters);
    let mut stations = Vec::with_capacity(span_samples.max(2));

    for index in 0..span_samples.max(2) {
        let t = index as f64 / (span_samples.max(2).saturating_sub(1) as f64);
        let eta = eta_hub + (1.0 - eta_hub) * t;
        let radius = state.global_parameters.radius * eta;
        let pitch_pd = distribution_value(state, "pitch_pd", eta);
        let rake = distribution_value(state, "rake", eta);
        let skew = handedness * distribution_value(state, "skew", eta);
        let chord_ratio = distribution_value(state, "chord", eta);
        let pitch = pitch_pd * diameter;
        let beta = pitch.atan2(2.0 * PI * radius.max(1.0));
        stations.push(Station {
            eta,
            radius,
            rake,
            skew,
            chord: chord_ratio * diameter,
            beta,
        });
    }
    stations
}

fn build_section_curves(
    state: &PropellerFeatureState,
    eta: f64,
    chord_samples: usize,
    camber_scale: f64,
    thickness_scale: f64,
) -> Vec<Vec<[f64; 2]>> {
    let camber = distribution_value(state, "camber", eta) * camber_scale;
    let thickness = distribution_value(state, "thickness", eta) * thickness_scale;
    let te_thickness = state.profile_definition.trailing_edge_thickness;
    let count = chord_samples.max(8);
    let mut upper = Vec::with_capacity(count);
    let mut lower = Vec::with_capacity(count);

    for index in 0..count {
        let x = index as f64 / (count.saturating_sub(1).max(1) as f64);
        let x_profile = profile_x(state.profile_definition.leading_edge_bias, x);
        let camber_y = camber_curve(&state.profile_definition.camber_family, camber, x_profile);
        let camber_dy = camber_slope(&state.profile_definition.camber_family, camber, x_profile);
        let thickness_shape =
            thickness_curve(&state.profile_definition.thickness_family, x_profile);
        let thickness_y = (5.0 * thickness * thickness_shape
            + te_thickness * x_profile * x_profile)
            .max(te_thickness);
        let half_thickness = thickness_y * 0.5;
        let phi = camber_dy.atan();
        upper.push([
            x_profile - half_thickness * phi.sin(),
            camber_y + half_thickness * phi.cos(),
        ]);
        lower.push([
            x_profile + half_thickness * phi.sin(),
            camber_y - half_thickness * phi.cos(),
        ]);
    }
    vec![upper, lower]
}

fn place_section_curve(
    state: &PropellerFeatureState,
    station: &Station,
    section_curve: &[[f64; 2]],
    eta: f64,
) -> Vec<[f64; 3]> {
    let aoa_deg = distribution_value(state, "angle_of_attack", eta);
    let theta = station.skew;
    let beta_eff =
        station.beta + (aoa_deg + state.global_parameters.pitch_reference_deg).to_radians();
    let radial = [theta.cos(), theta.sin(), 0.0];
    let tangential = [-theta.sin(), theta.cos(), 0.0];
    let axial = [0.0, 0.0, 1.0];
    let chord_dir = normalize3(add3(
        scale3(tangential, beta_eff.cos()),
        scale3(axial, beta_eff.sin()),
    ));
    let thickness_dir = normalize3(cross3(radial, chord_dir));
    let origin = add3(
        scale3(radial, station.radius),
        scale3(axial, station.rake * state.global_parameters.radius * 2.0),
    );

    section_curve
        .iter()
        .map(|point| {
            let chordwise = scale3(chord_dir, station.chord * (point[0] - 0.45));
            let thickness = scale3(thickness_dir, station.chord * point[1]);
            add3(origin, add3(chordwise, thickness))
        })
        .collect::<Vec<_>>()
}

fn build_ring_from_surfaces(upper: &[[f64; 3]], lower: &[[f64; 3]]) -> Vec<[f64; 3]> {
    let mut ring = upper.to_vec();
    let mut lower_reversed = lower.to_vec();
    lower_reversed.reverse();
    ring.extend(lower_reversed);
    close_ring(ring)
}

fn build_surface_from_rings(rings: &[Vec<[f64; 3]>]) -> Result<BSplineSurface<Point3>, String> {
    if rings.len() < 2 {
        return Err("A Truck surface requires at least two rings.".to_string());
    }
    let cols = rings[0].len();
    if cols < 4 {
        return Err("A Truck surface requires at least four control points per ring.".to_string());
    }
    if rings.iter().any(|ring| ring.len() != cols) {
        return Err("All Truck surface rings must share the same point count.".to_string());
    }
    let rows = rings.len();
    let u_degree = 3usize.min(rows.saturating_sub(1));
    let v_degree = 3usize.min(cols.saturating_sub(1));
    let point_grid = rings
        .iter()
        .map(|ring| {
            ring.iter()
                .map(|point| Point3::new(point[0], point[1], point[2]))
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    let uknot = KnotVec::uniform_knot(u_degree, rows.saturating_sub(u_degree));
    let vknot = KnotVec::uniform_knot(v_degree, cols.saturating_sub(v_degree));
    BSplineSurface::try_new((uknot, vknot), point_grid)
        .map_err(|err| format!("Truck surface construction failed: {err}"))
}

fn build_cap_surface(
    base_ring: &[[f64; 3]],
    apex: [f64; 3],
) -> Result<BSplineSurface<Point3>, String> {
    let core_ring = &base_ring[..base_ring.len().saturating_sub(1)];
    let centroid = average_point3(core_ring);
    let mut rings = Vec::new();
    rings.push(base_ring.to_vec());
    for scale in [0.62, 0.28, 0.08] {
        let ring = core_ring
            .iter()
            .map(|point| blend3(apex, blend3(centroid, *point, scale), 0.85))
            .collect::<Vec<_>>();
        rings.push(close_ring(ring));
    }
    rings.push(close_ring(vec![apex; core_ring.len()]));
    build_surface_from_rings(&rings)
}

fn tessellate_surface(surface: &BSplineSurface<Point3>, rows: usize, cols: usize) -> MeshPart {
    let rows = rows.max(2);
    let cols = cols.max(3);
    let mut vertices = Vec::with_capacity(rows * cols);
    let mut faces = Vec::with_capacity((rows - 1) * (cols - 1) * 2);

    for row in 0..rows {
        let u = row as f64 / (rows.saturating_sub(1) as f64);
        for col in 0..cols {
            let v = col as f64 / (cols.saturating_sub(1) as f64);
            let point = surface.subs(u, v);
            vertices.push([point.x, point.y, point.z]);
        }
    }

    for row in 0..rows - 1 {
        let row_offset = row * cols;
        let next_offset = (row + 1) * cols;
        for col in 0..cols - 1 {
            let a = row_offset + col;
            let b = row_offset + col + 1;
            let c = next_offset + col;
            let d = next_offset + col + 1;
            faces.push([a, c, b]);
            faces.push([b, c, d]);
        }
    }

    MeshPart { vertices, faces }
}

fn append_mesh(
    target_vertices: &mut Vec<[f64; 3]>,
    target_faces: &mut Vec<[usize; 3]>,
    mesh: &MeshPart,
    angle: f64,
) {
    let offset = target_vertices.len();
    target_vertices.extend(
        mesh.vertices
            .iter()
            .map(|vertex| rotate_point_z(*vertex, angle)),
    );
    target_faces.extend(
        mesh.faces
            .iter()
            .map(|face| [face[0] + offset, face[1] + offset, face[2] + offset]),
    );
}

fn weld_mesh(mesh: PropellerBuildMeshDto, epsilon: f64) -> PropellerBuildMeshDto {
    let mut welded_vertices = Vec::<[f64; 3]>::new();
    let mut welded_faces = Vec::<[usize; 3]>::new();
    let mut vertex_map = HashMap::<(i64, i64, i64), usize>::new();
    let mut remap = Vec::<usize>::with_capacity(mesh.vertices.len());

    for vertex in &mesh.vertices {
        let key = (
            (vertex[0] / epsilon).round() as i64,
            (vertex[1] / epsilon).round() as i64,
            (vertex[2] / epsilon).round() as i64,
        );
        let index = if let Some(existing) = vertex_map.get(&key) {
            *existing
        } else {
            let next = welded_vertices.len();
            welded_vertices.push(*vertex);
            vertex_map.insert(key, next);
            next
        };
        remap.push(index);
    }

    for face in &mesh.faces {
        let remapped = [remap[face[0]], remap[face[1]], remap[face[2]]];
        if remapped[0] != remapped[1] && remapped[1] != remapped[2] && remapped[0] != remapped[2] {
            welded_faces.push(remapped);
        }
    }

    PropellerBuildMeshDto {
        vertices: welded_vertices,
        faces: welded_faces,
        section_polylines: mesh.section_polylines,
    }
}

fn mesh_is_watertight(mesh: &PropellerBuildMeshDto) -> bool {
    if mesh.faces.is_empty() {
        return false;
    }
    let mut edge_counts = HashMap::<(usize, usize), usize>::new();
    for face in &mesh.faces {
        for edge in [(face[0], face[1]), (face[1], face[2]), (face[2], face[0])] {
            let key = if edge.0 <= edge.1 {
                (edge.0, edge.1)
            } else {
                (edge.1, edge.0)
            };
            *edge_counts.entry(key).or_insert(0) += 1;
        }
    }
    edge_counts.values().all(|count| *count == 2)
}

fn mesh_bounds(vertices: &[[f64; 3]]) -> ([f64; 3], [f64; 3]) {
    if vertices.is_empty() {
        return ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]);
    }
    let mut min = vertices[0];
    let mut max = vertices[0];
    for vertex in vertices {
        for axis in 0..3 {
            min[axis] = min[axis].min(vertex[axis]);
            max[axis] = max[axis].max(vertex[axis]);
        }
    }
    (min, max)
}

fn profile_x(leading_edge_bias: f64, x: f64) -> f64 {
    let bias = clamp(leading_edge_bias, -0.35, 0.35);
    if bias >= 0.0 {
        x.powf(1.0 + bias * 1.8)
    } else {
        1.0 - (1.0 - x).powf(1.0 + bias.abs() * 1.8)
    }
}

fn camber_curve(family: &str, camber: f64, x: f64) -> f64 {
    match family {
        "parabolic" => camber * 4.0 * x * (1.0 - x),
        "elliptic" => camber * (1.0 - (2.0 * x - 1.0).powi(2)).max(0.0).sqrt(),
        _ => camber * (PI * x).sin(),
    }
}

fn camber_slope(family: &str, camber: f64, x: f64) -> f64 {
    match family {
        "parabolic" => camber * 4.0 * (1.0 - 2.0 * x),
        "elliptic" => {
            let inner = (1.0 - (2.0 * x - 1.0).powi(2)).max(1e-6);
            camber * (-(4.0 * x - 2.0) / inner.sqrt())
        }
        _ => camber * PI * (PI * x).cos(),
    }
}

fn thickness_curve(family: &str, x: f64) -> f64 {
    match family {
        "ogive" => (PI * x).sin().powf(0.85),
        "elliptic" => (1.0 - (2.0 * x - 1.0).powi(2)).max(0.0).sqrt(),
        _ => {
            0.2969 * x.max(1e-6).sqrt() - 0.1260 * x - 0.3516 * x * x + 0.2843 * x * x * x
                - 0.1015 * x * x * x * x
        }
    }
}

fn root_cap_center(state: &PropellerFeatureState, root_section: &PlacedSection) -> [f64; 3] {
    let hub = &state.hub_parameters;
    let centroid = average_point3(&root_section.ring[..root_section.ring.len().saturating_sub(1)]);
    let radial = normalize3([centroid[0], centroid[1], 0.0]);
    let axial = [0.0, 0.0, 1.0];
    add3(
        centroid,
        add3(
            scale3(
                radial,
                -state.global_parameters.radius * hub.root_cutback_start * 0.22,
            ),
            scale3(
                axial,
                state.global_parameters.radius
                    * (hub.root_le_blend_ratio - hub.root_te_blend_ratio)
                    * 0.4,
            ),
        ),
    )
}

fn estimate_pattern_collision(
    state: &PropellerFeatureState,
    center_surface: &CenterSurfaceArtifact,
) -> bool {
    let blade_count = state.pattern_parameters.num_blades.max(1) as f64;
    let root_station = match center_surface.stations.first() {
        Some(station) => station,
        None => return false,
    };
    let arc_space = 2.0 * PI * root_station.radius.max(1.0) / blade_count;
    root_station.chord > arc_space * 0.88
}

fn distribution_value(state: &PropellerFeatureState, key: &str, eta: f64) -> f64 {
    state
        .distributions
        .get(key)
        .map(|distribution| evaluate_distribution(&distribution.control_points, eta))
        .unwrap_or(0.0)
}

fn evaluate_distribution(control_points: &[DistributionControlPoint], eta: f64) -> f64 {
    if control_points.is_empty() {
        return 0.0;
    }
    let mut pairs = control_points
        .iter()
        .map(|point| [point.eta, point.value])
        .collect::<Vec<_>>();
    pairs.sort_by(|left, right| left[0].total_cmp(&right[0]));
    if pairs.len() == 1 {
        return pairs[0][1];
    }
    let clamped_eta = clamp(eta, pairs[0][0], pairs[pairs.len() - 1][0]);
    catmull_rom(&pairs, clamped_eta)
}

fn catmull_rom(points: &[[f64; 2]], x: f64) -> f64 {
    if points.is_empty() {
        return 0.0;
    }
    if points.len() == 1 {
        return points[0][1];
    }
    if x <= points[0][0] {
        return points[0][1];
    }
    if x >= points[points.len() - 1][0] {
        return points[points.len() - 1][1];
    }

    let mut segment_index = 0usize;
    for index in 0..points.len() - 1 {
        if points[index][0] <= x && x <= points[index + 1][0] {
            segment_index = index;
            break;
        }
    }

    let p0 = points[segment_index.saturating_sub(1)];
    let p1 = points[segment_index];
    let p2 = points[segment_index + 1];
    let p3 = points[(segment_index + 2).min(points.len() - 1)];
    let span = p2[0] - p1[0];
    if span <= 1e-9 {
        return p1[1];
    }

    let t = (x - p1[0]) / span;
    let a0 = -0.5 * p0[1] + 1.5 * p1[1] - 1.5 * p2[1] + 0.5 * p3[1];
    let a1 = p0[1] - 2.5 * p1[1] + 2.0 * p2[1] - 0.5 * p3[1];
    let a2 = -0.5 * p0[1] + 0.5 * p2[1];
    let a3 = p1[1];
    ((a0 * t + a1) * t + a2) * t + a3
}

fn circle_ring(radius: f64, z: f64, point_count: usize) -> Vec<[f64; 3]> {
    let count = point_count.max(12);
    let mut ring = Vec::with_capacity(count + 1);
    for index in 0..count {
        let angle = 2.0 * PI * index as f64 / count as f64;
        ring.push([radius * angle.cos(), radius * angle.sin(), z]);
    }
    close_ring(ring)
}

fn close_ring(mut ring: Vec<[f64; 3]>) -> Vec<[f64; 3]> {
    if let Some(first) = ring.first().copied() {
        ring.push(first);
    }
    ring
}

fn rotate_point_z(point: [f64; 3], angle: f64) -> [f64; 3] {
    let cos_angle = angle.cos();
    let sin_angle = angle.sin();
    [
        point[0] * cos_angle - point[1] * sin_angle,
        point[0] * sin_angle + point[1] * cos_angle,
        point[2],
    ]
}

fn rotate_polyline_z(points: &[[f64; 3]], angle: f64) -> Vec<[f64; 3]> {
    points
        .iter()
        .map(|point| rotate_point_z(*point, angle))
        .collect::<Vec<_>>()
}

fn merge_radial_series(
    left: &BTreeMap<String, Vec<[f64; 2]>>,
    right: &BTreeMap<String, Vec<[f64; 2]>>,
) -> BTreeMap<String, Vec<[f64; 2]>> {
    let mut merged = left.clone();
    for (key, value) in right {
        merged.insert(key.clone(), value.clone());
    }
    merged
}

fn record_timing(
    timings: &mut BTreeMap<String, f64>,
    start_index: usize,
    stage_index: usize,
    stage_name: &str,
    start: Instant,
) {
    if stage_index >= start_index {
        timings.insert(stage_name.to_string(), elapsed_ms(start));
    }
}

fn elapsed_ms(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1000.0
}

fn stage_index(stage: &str) -> Option<usize> {
    STAGE_ORDER.iter().position(|item| *item == stage)
}

fn handedness_sign(pattern: &PatternParameters) -> f64 {
    if pattern.handedness.eq_ignore_ascii_case("left") {
        -1.0
    } else {
        1.0
    }
}

fn clamp(value: f64, minimum: f64, maximum: f64) -> f64 {
    value.max(minimum).min(maximum)
}

fn add3(left: [f64; 3], right: [f64; 3]) -> [f64; 3] {
    [left[0] + right[0], left[1] + right[1], left[2] + right[2]]
}

fn scale3(vector: [f64; 3], factor: f64) -> [f64; 3] {
    [vector[0] * factor, vector[1] * factor, vector[2] * factor]
}

fn cross3(left: [f64; 3], right: [f64; 3]) -> [f64; 3] {
    [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]
}

fn normalize3(vector: [f64; 3]) -> [f64; 3] {
    let norm = (vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2]).sqrt();
    if norm <= 1e-9 {
        [0.0, 0.0, 1.0]
    } else {
        [vector[0] / norm, vector[1] / norm, vector[2] / norm]
    }
}

fn average_point3(points: &[[f64; 3]]) -> [f64; 3] {
    if points.is_empty() {
        return [0.0, 0.0, 0.0];
    }
    let sum = points
        .iter()
        .fold([0.0, 0.0, 0.0], |acc, point| add3(acc, *point));
    scale3(sum, 1.0 / points.len() as f64)
}

fn blend3(left: [f64; 3], right: [f64; 3], factor: f64) -> [f64; 3] {
    add3(scale3(left, 1.0 - factor), scale3(right, factor))
}

fn error(stage: &str, message: impl Into<String>) -> PropellerDiagnosticDto {
    PropellerDiagnosticDto {
        severity: "error".to_string(),
        stage: stage.to_string(),
        message: message.into(),
    }
}

fn warning(stage: &str, message: impl Into<String>) -> PropellerDiagnosticDto {
    PropellerDiagnosticDto {
        severity: "warning".to_string(),
        stage: stage.to_string(),
        message: message.into(),
    }
}

fn info(stage: &str, message: impl Into<String>) -> PropellerDiagnosticDto {
    PropellerDiagnosticDto {
        severity: "info".to_string(),
        stage: stage.to_string(),
        message: message.into(),
    }
}

#[pymodule]
fn rotorlab_propeller_preview(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(propeller_backend_contract, module)?)?;
    module.add_function(wrap_pyfunction!(propeller_build_model, module)?)?;
    module.add_function(wrap_pyfunction!(propeller_backend_api_version, module)?)?;
    module.add_function(wrap_pyfunction!(propeller_rebuild_preview, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reset_build_cache() {
        build_cache().lock().expect("cache lock").clear();
    }

    #[test]
    fn default_build_returns_truck_tessellated_mesh() {
        reset_build_cache();
        let request = PropellerBuildRequestDto {
            feature_state: default_feature_state("test-node-a"),
            dirty_stages: vec![],
        };
        let result = build_model_internal(&request).expect("build should succeed");
        assert!(result.ok);
        assert_eq!(
            result.built_stages,
            STAGE_ORDER
                .iter()
                .map(|stage| (*stage).to_string())
                .collect::<Vec<_>>()
        );
        assert!(!result.preview_mesh.vertices.is_empty());
        assert!(!result.preview_mesh.faces.is_empty());
        assert_eq!(result.model_metadata.source, "truck_tessellation");
        assert_eq!(result.model_metadata.blade_count, 4);
        assert!(result.model_metadata.component_count >= 5);
    }

    #[test]
    fn dirty_stage_without_cache_falls_back_to_full_rebuild() {
        reset_build_cache();
        let request = PropellerBuildRequestDto {
            feature_state: default_feature_state("test-node-b"),
            dirty_stages: vec!["hub".to_string()],
        };
        let result = build_model_internal(&request).expect("build should succeed");
        assert_eq!(
            result.built_stages,
            STAGE_ORDER
                .iter()
                .map(|stage| (*stage).to_string())
                .collect::<Vec<_>>()
        );
    }

    #[test]
    fn dirty_stage_response_marks_only_downstream_stages_after_cache_warmup() {
        reset_build_cache();
        let state = default_feature_state("test-node-cache");
        build_model_internal(&PropellerBuildRequestDto {
            feature_state: state.clone(),
            dirty_stages: vec![],
        })
        .expect("warm build should succeed");
        let result = build_model_internal(&PropellerBuildRequestDto {
            feature_state: state,
            dirty_stages: vec!["hub".to_string()],
        })
        .expect("cached build should succeed");
        assert_eq!(
            result.built_stages,
            vec![
                "hub".to_string(),
                "pattern".to_string(),
                "blade_preview".to_string(),
                "diagnostics".to_string()
            ]
        );
    }

    #[test]
    fn invalid_axis_reports_error() {
        reset_build_cache();
        let mut state = default_feature_state("test-node-c");
        state.pattern_parameters.axis_convention = "x".to_string();
        let result = build_model_internal(&PropellerBuildRequestDto {
            feature_state: state,
            dirty_stages: vec![],
        })
        .expect("build should still complete");

        assert!(!result.ok);
        assert!(result
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.stage == "pattern" && diagnostic.severity == "error"));
    }

    fn default_feature_state(node_id: &str) -> PropellerFeatureState {
        let mut distributions = BTreeMap::new();
        distributions.insert(
            "pitch_pd".to_string(),
            radial_distribution(
                "pitch_pd",
                "Pitch P/D",
                "ratio",
                "center_surface",
                vec![[0.22, 0.92], [0.55, 1.02], [0.82, 1.04], [1.0, 0.98]],
            ),
        );
        distributions.insert(
            "rake".to_string(),
            radial_distribution(
                "rake",
                "Rake",
                "D",
                "center_surface",
                vec![[0.22, 0.0], [0.60, 0.03], [0.82, 0.08], [1.0, 0.12]],
            ),
        );
        distributions.insert(
            "skew".to_string(),
            radial_distribution(
                "skew",
                "Skew",
                "rad",
                "center_surface",
                vec![[0.22, 0.0], [0.55, 0.12], [0.82, 0.22], [1.0, 0.30]],
            ),
        );
        distributions.insert(
            "chord".to_string(),
            radial_distribution(
                "chord",
                "Chord / D",
                "ratio",
                "center_surface",
                vec![[0.22, 0.18], [0.45, 0.32], [0.72, 0.24], [1.0, 0.10]],
            ),
        );
        distributions.insert(
            "camber".to_string(),
            radial_distribution(
                "camber",
                "Camber",
                "ratio",
                "profile_configurator",
                vec![[0.22, 0.055], [0.60, 0.035], [1.0, 0.010]],
            ),
        );
        distributions.insert(
            "thickness".to_string(),
            radial_distribution(
                "thickness",
                "Thickness",
                "ratio",
                "profile_configurator",
                vec![[0.22, 0.18], [0.60, 0.12], [1.0, 0.06]],
            ),
        );
        distributions.insert(
            "angle_of_attack".to_string(),
            radial_distribution(
                "angle_of_attack",
                "AoA Correction",
                "deg",
                "profile_configurator",
                vec![[0.22, 0.0], [0.70, 1.8], [1.0, -0.4]],
            ),
        );

        PropellerFeatureState {
            node_id: node_id.to_string(),
            display_name: "Propeller".to_string(),
            module_type: "geometry.propeller_parametric_builder".to_string(),
            global_parameters: GlobalParameters {
                radius: 2500.0,
                pitch_reference_deg: 0.0,
            },
            profile_definition: ProfileDefinition {
                camber_family: "modified_naca".to_string(),
                thickness_family: "naca66_like".to_string(),
                trailing_edge_thickness: 0.006,
                leading_edge_bias: 0.0,
            },
            preview_settings: PreviewSettings {
                span_samples: 18,
                chord_samples: 36,
                section_eta: 0.7,
                tessellation_rows: 40,
                tessellation_cols: 72,
                show_mesh: true,
                show_wireframe: true,
                show_sections: true,
            },
            tip_parameters: TipParameters {
                closure_bias: 0.36,
                roundness: 0.62,
                cap_depth_ratio: 0.08,
                cap_length_ratio: 0.14,
                tip_thickness_fade: 0.78,
                tip_camber_fade: 0.64,
                tip_rake_fade: 0.24,
            },
            hub_parameters: HubParameters {
                hub_radius_ratio: 0.22,
                hub_length_ratio: 0.34,
                fore_profile_split: 0.42,
                aft_profile_split: 0.58,
                root_cutback_start: 0.18,
                root_le_blend_ratio: 0.08,
                root_te_blend_ratio: 0.06,
            },
            pattern_parameters: PatternParameters {
                num_blades: 4,
                start_angle_deg: 0.0,
                handedness: "right".to_string(),
                axis_convention: "z".to_string(),
            },
            distributions,
        }
    }

    fn radial_distribution(
        key: &str,
        label: &str,
        unit: &str,
        stage: &str,
        points: Vec<[f64; 2]>,
    ) -> RadialDistribution {
        RadialDistribution {
            key: key.to_string(),
            label: label.to_string(),
            unit: unit.to_string(),
            stage: stage.to_string(),
            control_points: points
                .into_iter()
                .map(|item| DistributionControlPoint {
                    eta: item[0],
                    value: item[1],
                })
                .collect::<Vec<_>>(),
        }
    }
}
