use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::f64::consts::PI;
use std::sync::{Mutex, OnceLock};
use std::time::Instant;
use truck_geometry::prelude::{BSplineSurface, KnotVec, ParametricSurface, Point3};

const STAGE_ORDER: [&str; 5] = [
    "center_surface",
    "profile_configurator",
    "section_placement",
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
    num_blades: u32,
    hub_radius_ratio: f64,
    pitch_reference_deg: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct ProfileDefinition {
    #[allow(dead_code)]
    camber_family: String,
    #[allow(dead_code)]
    thickness_family: String,
    trailing_edge_thickness: f64,
    #[allow(dead_code)]
    leading_edge_bias: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct PreviewSettings {
    span_samples: usize,
    chord_samples: usize,
    section_eta: f64,
    #[allow(dead_code)]
    show_mesh: bool,
    #[allow(dead_code)]
    show_wireframe: bool,
    show_sections: bool,
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
    distributions: BTreeMap<String, RadialDistribution>,
}

#[derive(Debug, Clone, Deserialize)]
struct PropellerPreviewRequestDto {
    feature_state: PropellerFeatureState,
    dirty_stages: Vec<String>,
    #[serde(default = "default_build_mode")]
    build_mode: String,
    #[serde(default)]
    #[allow(dead_code)]
    requested_artifacts: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
struct PropellerDiagnosticDto {
    severity: String,
    stage: String,
    message: String,
}

#[derive(Debug, Clone, Default, Serialize)]
struct PropellerPreviewMeshDto {
    vertices: Vec<[f64; 3]>,
    faces: Vec<[usize; 3]>,
    section_polylines: Vec<Vec<[f64; 3]>>,
}

#[derive(Debug, Clone, Serialize)]
struct PropellerPreviewResponseDto {
    ok: bool,
    built_stages: Vec<String>,
    stage_timings_ms: BTreeMap<String, f64>,
    radial_series: BTreeMap<String, Vec<[f64; 2]>>,
    section_samples: BTreeMap<String, Vec<Vec<[f64; 2]>>>,
    placed_section_samples: BTreeMap<String, Vec<Vec<[f64; 3]>>>,
    mesh: PropellerPreviewMeshDto,
    diagnostics: Vec<PropellerDiagnosticDto>,
    exact_artifacts: Value,
}

#[derive(Debug, Clone)]
struct Station {
    eta: f64,
    radius: f64,
    #[allow(dead_code)]
    pitch_pd: f64,
    rake: f64,
    skew: f64,
    chord: f64,
    beta: f64,
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
    span_sections: Vec<Vec<[f64; 3]>>,
}

#[derive(Debug, Clone, Default)]
struct BladePreviewArtifact {
    mesh: PropellerPreviewMeshDto,
}

#[derive(Debug, Clone)]
struct ExactBladeSurfaceArtifact {
    u_degree: usize,
    v_degree: usize,
    control_points_u: usize,
    control_points_v: usize,
    sample_points_u: usize,
    sample_points_v: usize,
    estimated_area: f64,
    bounds_min: [f64; 3],
    bounds_max: [f64; 3],
}

#[derive(Debug, Clone)]
struct ExactTipSurfaceArtifact {
    u_degree: usize,
    v_degree: usize,
    control_points_u: usize,
    control_points_v: usize,
    sample_points_u: usize,
    sample_points_v: usize,
    estimated_area: f64,
    bounds_min: [f64; 3],
    bounds_max: [f64; 3],
    tip_radius: f64,
}

#[derive(Debug, Default)]
struct NodeCache {
    center_surface: Option<CenterSurfaceArtifact>,
    profile_configurator: Option<ProfileConfiguratorArtifact>,
    section_placement: Option<SectionPlacementArtifact>,
    blade_preview: Option<BladePreviewArtifact>,
    diagnostics: Option<Vec<PropellerDiagnosticDto>>,
}

fn preview_cache() -> &'static Mutex<HashMap<String, NodeCache>> {
    static CACHE: OnceLock<Mutex<HashMap<String, NodeCache>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

#[pyfunction]
fn propeller_backend_api_version() -> &'static str {
    "1.0.0"
}

#[pyfunction]
fn propeller_rebuild_preview(payload: &str) -> PyResult<String> {
    let request: PropellerPreviewRequestDto = serde_json::from_str(payload).map_err(|err| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Invalid propeller preview payload: {err}"
        ))
    })?;
    let response = rebuild_preview_internal(&request)?;
    serde_json::to_string(&response).map_err(|err| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Could not encode propeller preview response: {err}"
        ))
    })
}

fn rebuild_preview_internal(
    request: &PropellerPreviewRequestDto,
) -> PyResult<PropellerPreviewResponseDto> {
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
            .collect()
    } else {
        dirty_stages
    };
    let start_index = dirty_stages
        .iter()
        .filter_map(|stage| stage_index(stage))
        .min()
        .unwrap_or(0);
    let mut timings = BTreeMap::new();

    let key = if request.feature_state.node_id.trim().is_empty() {
        "__default__".to_string()
    } else {
        request.feature_state.node_id.clone()
    };
    let mut cache_map = preview_cache().lock().map_err(|err| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Could not lock propeller preview cache: {err}"
        ))
    })?;
    let cache = cache_map.entry(key).or_default();
    let state = &request.feature_state;

    if start_index <= 0 || cache.center_surface.is_none() {
        let start = Instant::now();
        cache.center_surface = Some(build_center_surface(state));
        timings.insert("center_surface".to_string(), elapsed_ms(start));
    }
    let center_surface = cache.center_surface.clone().unwrap_or_default();

    if start_index <= 1 || cache.profile_configurator.is_none() {
        let start = Instant::now();
        cache.profile_configurator = Some(build_profile_configurator(state));
        timings.insert("profile_configurator".to_string(), elapsed_ms(start));
    }
    let profile_configurator = cache.profile_configurator.clone().unwrap_or_default();

    if start_index <= 2 || cache.section_placement.is_none() {
        let start = Instant::now();
        cache.section_placement = Some(build_section_placement(
            state,
            &center_surface,
            &profile_configurator,
        ));
        timings.insert("section_placement".to_string(), elapsed_ms(start));
    }
    let section_placement = cache.section_placement.clone().unwrap_or_default();

    if start_index <= 3 || cache.blade_preview.is_none() {
        let start = Instant::now();
        cache.blade_preview = Some(build_blade_preview(state, &section_placement));
        timings.insert("blade_preview".to_string(), elapsed_ms(start));
    }
    let blade_preview = cache.blade_preview.clone().unwrap_or_default();

    if start_index <= 4 || cache.diagnostics.is_none() {
        let start = Instant::now();
        cache.diagnostics = Some(build_diagnostics(
            state,
            &center_surface,
            &section_placement,
            &blade_preview,
        ));
        timings.insert("diagnostics".to_string(), elapsed_ms(start));
    }
    let diagnostics = cache.diagnostics.clone().unwrap_or_default();
    let exact_artifacts = if request.build_mode.eq_ignore_ascii_case("exact") {
        build_exact_artifacts(&request.feature_state, &blade_preview.mesh)
    } else {
        json!({})
    };

    let built_stages: Vec<String> = STAGE_ORDER[start_index..]
        .iter()
        .map(|stage| (*stage).to_string())
        .collect();
    Ok(PropellerPreviewResponseDto {
        ok: !diagnostics.iter().any(|item| item.severity == "error"),
        built_stages,
        stage_timings_ms: timings,
        radial_series: merge_radial_series(
            &center_surface.radial_series,
            &profile_configurator.radial_series,
        ),
        section_samples: profile_configurator.section_samples,
        placed_section_samples: section_placement.placed_sections,
        mesh: blade_preview.mesh,
        diagnostics,
        exact_artifacts,
    })
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

fn stage_index(stage: &str) -> Option<usize> {
    STAGE_ORDER.iter().position(|item| *item == stage)
}

fn elapsed_ms(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1000.0
}

fn default_build_mode() -> String {
    "preview".to_string()
}

fn build_center_surface(state: &PropellerFeatureState) -> CenterSurfaceArtifact {
    let eta_hub = clamp(state.global_parameters.hub_radius_ratio, 0.0, 1.0);
    let mut radial_series = BTreeMap::new();
    let sample_etas: Vec<f64> = (0..64).map(|index| index as f64 / 63.0).collect();

    for key in ["pitch_pd", "rake", "skew", "chord"] {
        let samples = sample_etas
            .iter()
            .map(|eta| {
                let mapped_eta = clamp(eta_hub + eta * (1.0 - eta_hub), eta_hub, 1.0);
                [*eta, distribution_value(state, key, mapped_eta)]
            })
            .collect();
        radial_series.insert(key.to_string(), samples);
    }

    let stations = sample_center_stations(state, state.preview_settings.span_samples.max(2));

    CenterSurfaceArtifact {
        radial_series,
        stations,
    }
}

fn sample_center_stations(state: &PropellerFeatureState, span_samples: usize) -> Vec<Station> {
    let eta_hub = clamp(state.global_parameters.hub_radius_ratio, 0.0, 1.0);
    let diameter = state.global_parameters.radius * 2.0;
    let span_samples = span_samples.max(2);
    let mut stations = Vec::with_capacity(span_samples);

    for index in 0..span_samples {
        let t = index as f64 / (span_samples.saturating_sub(1).max(1) as f64);
        let eta = eta_hub + (1.0 - eta_hub) * t;
        let radius = state.global_parameters.radius * eta;
        let pitch_pd = distribution_value(state, "pitch_pd", eta);
        let rake = distribution_value(state, "rake", eta);
        let skew = distribution_value(state, "skew", eta);
        let chord_ratio = distribution_value(state, "chord", eta);
        let pitch = pitch_pd * diameter;
        let beta = pitch.atan2(2.0 * PI * radius.max(1.0));
        stations.push(Station {
            eta,
            radius,
            pitch_pd,
            rake,
            skew,
            chord: chord_ratio * diameter,
            beta,
        });
    }
    stations
}

fn build_exact_artifacts(state: &PropellerFeatureState, mesh: &PropellerPreviewMeshDto) -> Value {
    let (bounds_min, bounds_max) = mesh_bounds(&mesh.vertices);
    match build_truck_blade_surface(state) {
        Ok(surface) => match build_truck_tip_surface(state) {
            Ok(tip_surface) => json!({
                "mode": "exact",
                "exact_stages_built": ["blade_surface", "tip"],
                "pending_exact_stages": ["hub", "pattern"],
                "blade_count": state.global_parameters.num_blades,
                "vertex_count": mesh.vertices.len(),
                "face_count": mesh.faces.len(),
                "bounds_min": bounds_min,
                "bounds_max": bounds_max,
                "blade_surface": {
                    "engine": "truck-geometry",
                    "u_degree": surface.u_degree,
                    "v_degree": surface.v_degree,
                    "control_points_u": surface.control_points_u,
                    "control_points_v": surface.control_points_v,
                    "sample_points_u": surface.sample_points_u,
                    "sample_points_v": surface.sample_points_v,
                    "estimated_area": surface.estimated_area,
                    "bounds_min": surface.bounds_min,
                    "bounds_max": surface.bounds_max,
                },
                "tip_surface": {
                    "engine": "truck-geometry",
                    "u_degree": tip_surface.u_degree,
                    "v_degree": tip_surface.v_degree,
                    "control_points_u": tip_surface.control_points_u,
                    "control_points_v": tip_surface.control_points_v,
                    "sample_points_u": tip_surface.sample_points_u,
                    "sample_points_v": tip_surface.sample_points_v,
                    "estimated_area": tip_surface.estimated_area,
                    "bounds_min": tip_surface.bounds_min,
                    "bounds_max": tip_surface.bounds_max,
                    "tip_radius": tip_surface.tip_radius,
                },
                "message": "Truck blade-surface and tip stages completed. Hub/pattern exact stages are still pending."
            }),
            Err(tip_error) => json!({
                "mode": "exact",
                "exact_stages_built": ["blade_surface"],
                "pending_exact_stages": ["tip", "hub", "pattern"],
                "blade_count": state.global_parameters.num_blades,
                "vertex_count": mesh.vertices.len(),
                "face_count": mesh.faces.len(),
                "bounds_min": bounds_min,
                "bounds_max": bounds_max,
                "blade_surface": {
                    "engine": "truck-geometry",
                    "u_degree": surface.u_degree,
                    "v_degree": surface.v_degree,
                    "control_points_u": surface.control_points_u,
                    "control_points_v": surface.control_points_v,
                    "sample_points_u": surface.sample_points_u,
                    "sample_points_v": surface.sample_points_v,
                    "estimated_area": surface.estimated_area,
                    "bounds_min": surface.bounds_min,
                    "bounds_max": surface.bounds_max,
                },
                "tip_error": tip_error,
                "message": "Truck blade-surface stage completed, but tip stage failed. Hub/pattern exact stages remain pending."
            }),
        },
        Err(message) => json!({
            "mode": "exact",
            "exact_stages_built": [],
            "pending_exact_stages": ["blade_surface", "tip", "hub", "pattern"],
            "blade_count": state.global_parameters.num_blades,
            "vertex_count": mesh.vertices.len(),
            "face_count": mesh.faces.len(),
            "bounds_min": bounds_min,
            "bounds_max": bounds_max,
            "error": message,
            "message": "Exact blade-surface stage failed. Falling back to preview-derived metadata."
        }),
    }
}

fn build_truck_blade_surface(
    state: &PropellerFeatureState,
) -> Result<ExactBladeSurfaceArtifact, String> {
    let span_samples = (state.preview_settings.span_samples.saturating_mul(2)).max(24);
    let chord_samples = (state.preview_settings.chord_samples.saturating_mul(2)).max(64);
    let stations = sample_center_stations(state, span_samples);
    if stations.len() < 4 {
        return Err("Not enough span stations for exact blade surface.".to_string());
    }

    let mut section_envelopes: Vec<Vec<[f64; 3]>> = Vec::with_capacity(stations.len());
    for station in &stations {
        let section = build_section_curves(state, station.eta, chord_samples);
        let upper = place_section_curve(state, station, &section[0], station.eta);
        let lower = place_section_curve(state, station, &section[1], station.eta);
        let mut envelope = upper;
        let mut lower_reversed = lower;
        lower_reversed.reverse();
        envelope.extend(lower_reversed);
        section_envelopes.push(envelope);
    }
    if section_envelopes[0].len() < 4 {
        return Err("Not enough section points for exact blade surface.".to_string());
    }

    let control_points_u = section_envelopes.len();
    let control_points_v = section_envelopes[0].len();
    let u_degree = 3usize.min(control_points_u.saturating_sub(1));
    let v_degree = 3usize.min(control_points_v.saturating_sub(1));
    if u_degree == 0 || v_degree == 0 {
        return Err("Invalid B-spline degree for exact blade surface.".to_string());
    }

    let point_grid: Vec<Vec<Point3>> = section_envelopes
        .iter()
        .map(|section| {
            section
                .iter()
                .map(|point| Point3::new(point[0], point[1], point[2]))
                .collect()
        })
        .collect();
    let uknot = KnotVec::uniform_knot(u_degree, control_points_u.saturating_sub(u_degree));
    let vknot = KnotVec::uniform_knot(v_degree, control_points_v.saturating_sub(v_degree));
    let surface = BSplineSurface::try_new((uknot, vknot), point_grid)
        .map_err(|err| format!("Truck B-spline surface construction failed: {err}"))?;

    let sample_points_u = (span_samples.saturating_mul(2)).max(32);
    let sample_points_v = (chord_samples / 2).max(32);
    let sampled = sample_surface_points(&surface, sample_points_u, sample_points_v);
    let estimated_area = estimate_surface_area(&sampled, sample_points_u, sample_points_v);
    let (bounds_min, bounds_max) = mesh_bounds(&sampled);

    Ok(ExactBladeSurfaceArtifact {
        u_degree,
        v_degree,
        control_points_u,
        control_points_v,
        sample_points_u,
        sample_points_v,
        estimated_area,
        bounds_min,
        bounds_max,
    })
}

fn build_truck_tip_surface(
    state: &PropellerFeatureState,
) -> Result<ExactTipSurfaceArtifact, String> {
    let span_samples = (state.preview_settings.span_samples.saturating_mul(2)).max(24);
    let chord_samples = (state.preview_settings.chord_samples.saturating_mul(2)).max(64);
    let stations = sample_center_stations(state, span_samples);
    let tip_station = stations
        .last()
        .ok_or_else(|| "Could not evaluate tip station for exact tip stage.".to_string())?;
    let section = build_section_curves(state, tip_station.eta, chord_samples);
    if section.len() < 2 {
        return Err("Tip stage requires both upper and lower section curves.".to_string());
    }

    let upper = place_section_curve(state, tip_station, &section[0], tip_station.eta);
    let lower = place_section_curve(state, tip_station, &section[1], tip_station.eta);
    let mut tip_envelope = upper;
    let mut lower_reversed = lower;
    lower_reversed.reverse();
    tip_envelope.extend(lower_reversed);
    if tip_envelope.len() < 4 {
        return Err("Not enough section points for exact tip stage.".to_string());
    }

    let tip_center = average_point3(&tip_envelope);
    let tip_radius = tip_envelope
        .iter()
        .map(|point| norm3(sub3(*point, tip_center)))
        .fold(0.0, f64::max);
    let blend_factors = [1.0, 0.70, 0.35, 0.0];
    let point_grid: Vec<Vec<Point3>> = blend_factors
        .iter()
        .map(|factor| {
            tip_envelope
                .iter()
                .map(|point| {
                    let blended = blend3(tip_center, *point, *factor);
                    Point3::new(blended[0], blended[1], blended[2])
                })
                .collect()
        })
        .collect();

    let control_points_u = point_grid.len();
    let control_points_v = point_grid[0].len();
    let u_degree = 3usize.min(control_points_u.saturating_sub(1));
    let v_degree = 3usize.min(control_points_v.saturating_sub(1));
    if u_degree == 0 || v_degree == 0 {
        return Err("Invalid B-spline degree for exact tip stage.".to_string());
    }

    let uknot = KnotVec::uniform_knot(u_degree, control_points_u.saturating_sub(u_degree));
    let vknot = KnotVec::uniform_knot(v_degree, control_points_v.saturating_sub(v_degree));
    let surface = BSplineSurface::try_new((uknot, vknot), point_grid)
        .map_err(|err| format!("Truck B-spline tip-surface construction failed: {err}"))?;

    let sample_points_u = 40usize;
    let sample_points_v = (chord_samples / 2).max(32);
    let sampled = sample_surface_points(&surface, sample_points_u, sample_points_v);
    let estimated_area = estimate_surface_area(&sampled, sample_points_u, sample_points_v);
    let (bounds_min, bounds_max) = mesh_bounds(&sampled);

    Ok(ExactTipSurfaceArtifact {
        u_degree,
        v_degree,
        control_points_u,
        control_points_v,
        sample_points_u,
        sample_points_v,
        estimated_area,
        bounds_min,
        bounds_max,
        tip_radius,
    })
}

fn sample_surface_points(
    surface: &BSplineSurface<Point3>,
    sample_points_u: usize,
    sample_points_v: usize,
) -> Vec<[f64; 3]> {
    let u_start = surface.uknot_vec().first().copied().unwrap_or(0.0);
    let u_end = surface.uknot_vec().last().copied().unwrap_or(1.0);
    let v_start = surface.vknot_vec().first().copied().unwrap_or(0.0);
    let v_end = surface.vknot_vec().last().copied().unwrap_or(1.0);

    let mut sampled = Vec::with_capacity(sample_points_u.saturating_mul(sample_points_v));
    for ui in 0..sample_points_u {
        let u = u_start
            + (u_end - u_start) * (ui as f64) / (sample_points_u.saturating_sub(1).max(1) as f64);
        for vi in 0..sample_points_v {
            let v = v_start
                + (v_end - v_start) * (vi as f64)
                    / (sample_points_v.saturating_sub(1).max(1) as f64);
            let point = surface.subs(u, v);
            sampled.push([point.x, point.y, point.z]);
        }
    }
    sampled
}

fn estimate_surface_area(points: &[[f64; 3]], rows: usize, cols: usize) -> f64 {
    if rows < 2 || cols < 2 {
        return 0.0;
    }
    let mut area = 0.0;
    for row in 0..rows.saturating_sub(1) {
        for col in 0..cols.saturating_sub(1) {
            let a = points[row * cols + col];
            let b = points[row * cols + col + 1];
            let c = points[(row + 1) * cols + col];
            let d = points[(row + 1) * cols + col + 1];
            area += 0.5 * norm3(cross3(sub3(b, a), sub3(c, a)));
            area += 0.5 * norm3(cross3(sub3(d, b), sub3(c, b)));
        }
    }
    area
}

fn mesh_bounds(vertices: &[[f64; 3]]) -> ([f64; 3], [f64; 3]) {
    if vertices.is_empty() {
        return ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]);
    }

    let mut min = vertices[0];
    let mut max = vertices[0];
    for vertex in vertices.iter().skip(1) {
        for index in 0..3 {
            if vertex[index] < min[index] {
                min[index] = vertex[index];
            }
            if vertex[index] > max[index] {
                max[index] = vertex[index];
            }
        }
    }
    (min, max)
}

fn build_profile_configurator(state: &PropellerFeatureState) -> ProfileConfiguratorArtifact {
    let eta_hub = clamp(state.global_parameters.hub_radius_ratio, 0.0, 1.0);
    let sample_etas: Vec<f64> = (0..64).map(|index| index as f64 / 63.0).collect();
    let mut radial_series = BTreeMap::new();

    for key in ["camber", "thickness", "angle_of_attack"] {
        let samples = sample_etas
            .iter()
            .map(|eta| {
                let mapped_eta = clamp(eta_hub + eta * (1.0 - eta_hub), eta_hub, 1.0);
                [*eta, distribution_value(state, key, mapped_eta)]
            })
            .collect();
        radial_series.insert(key.to_string(), samples);
    }

    let section_eta = clamp(state.preview_settings.section_eta, eta_hub, 1.0);
    let section_key = format!("{section_eta:.3}");
    let section_curves =
        build_section_curves(state, section_eta, state.preview_settings.chord_samples);

    let mut section_samples = BTreeMap::new();
    section_samples.insert(section_key, section_curves);

    ProfileConfiguratorArtifact {
        radial_series,
        section_samples,
        selected_eta: section_eta,
    }
}

fn build_section_placement(
    state: &PropellerFeatureState,
    center_surface: &CenterSurfaceArtifact,
    profile_config: &ProfileConfiguratorArtifact,
) -> SectionPlacementArtifact {
    let selected_eta = profile_config.selected_eta;
    let selected_key = format!("{selected_eta:.3}");
    let chord_samples = state.preview_settings.chord_samples;
    let mut span_sections: Vec<Vec<[f64; 3]>> = Vec::new();
    let mut selected_sections: Vec<Vec<[f64; 3]>> = Vec::new();

    for station in &center_surface.stations {
        let section = build_section_curves(state, station.eta, chord_samples);
        let upper_3d = place_section_curve(state, station, &section[0], station.eta);
        let lower_3d = place_section_curve(state, station, &section[1], station.eta);
        let mut envelope = upper_3d.clone();
        let mut lower_reversed = lower_3d.clone();
        lower_reversed.reverse();
        envelope.extend(lower_reversed);
        span_sections.push(envelope);
        if (station.eta - selected_eta).abs() < 1e-6 || selected_sections.is_empty() {
            selected_sections = vec![upper_3d, lower_3d];
        }
    }

    let mut placed_sections = BTreeMap::new();
    placed_sections.insert(selected_key, selected_sections);

    SectionPlacementArtifact {
        placed_sections,
        span_sections,
    }
}

fn build_blade_preview(
    state: &PropellerFeatureState,
    section_placement: &SectionPlacementArtifact,
) -> BladePreviewArtifact {
    let mut section_polylines = section_placement.span_sections.clone();
    if section_polylines.is_empty() {
        return BladePreviewArtifact {
            mesh: PropellerPreviewMeshDto::default(),
        };
    }
    let num_points = section_polylines[0].len();
    if num_points < 2 {
        return BladePreviewArtifact {
            mesh: PropellerPreviewMeshDto::default(),
        };
    }

    let mut vertices: Vec<[f64; 3]> = Vec::new();
    let mut faces: Vec<[usize; 3]> = Vec::new();
    for polyline in &section_polylines {
        vertices.extend(polyline.iter().copied());
    }

    for section_index in 0..section_polylines.len().saturating_sub(1) {
        let row_offset = section_index * num_points;
        let next_offset = (section_index + 1) * num_points;
        for point_index in 0..num_points.saturating_sub(1) {
            let a = row_offset + point_index;
            let b = row_offset + point_index + 1;
            let c = next_offset + point_index;
            let d = next_offset + point_index + 1;
            faces.push([a, c, b]);
            faces.push([b, c, d]);
        }
    }

    let blade_count = state.global_parameters.num_blades.max(1) as usize;
    if blade_count > 1 {
        let base_vertices = vertices.clone();
        let base_faces = faces.clone();
        let base_polylines = section_polylines.clone();
        for blade_index in 1..blade_count {
            let angle = (2.0 * PI * blade_index as f64) / blade_count as f64;
            let cos_angle = angle.cos();
            let sin_angle = angle.sin();
            let blade_offset = vertices.len();
            let rotated_vertices: Vec<[f64; 3]> = base_vertices
                .iter()
                .map(|vertex| {
                    [
                        vertex[0] * cos_angle - vertex[1] * sin_angle,
                        vertex[0] * sin_angle + vertex[1] * cos_angle,
                        vertex[2],
                    ]
                })
                .collect();
            vertices.extend(rotated_vertices);
            faces.extend(base_faces.iter().map(|face| {
                [
                    face[0] + blade_offset,
                    face[1] + blade_offset,
                    face[2] + blade_offset,
                ]
            }));
            for polyline in &base_polylines {
                section_polylines.push(
                    polyline
                        .iter()
                        .map(|point| {
                            [
                                point[0] * cos_angle - point[1] * sin_angle,
                                point[0] * sin_angle + point[1] * cos_angle,
                                point[2],
                            ]
                        })
                        .collect(),
                );
            }
        }
    }

    BladePreviewArtifact {
        mesh: PropellerPreviewMeshDto {
            vertices,
            faces,
            section_polylines: if state.preview_settings.show_sections {
                section_polylines
            } else {
                Vec::new()
            },
        },
    }
}

fn build_diagnostics(
    state: &PropellerFeatureState,
    center_surface: &CenterSurfaceArtifact,
    section_placement: &SectionPlacementArtifact,
    blade_preview: &BladePreviewArtifact,
) -> Vec<PropellerDiagnosticDto> {
    let mut diagnostics = Vec::new();
    if state.global_parameters.hub_radius_ratio >= 0.5 {
        diagnostics.push(PropellerDiagnosticDto {
            severity: "warning".to_string(),
            stage: "center_surface".to_string(),
            message: "Hub radius ratio is high and may compress the active blade span.".to_string(),
        });
    }
    if state.global_parameters.num_blades < 2 {
        diagnostics.push(PropellerDiagnosticDto {
            severity: "error".to_string(),
            stage: "blade_preview".to_string(),
            message: "At least two blades are required for a valid propeller preview.".to_string(),
        });
    }
    if blade_preview.mesh.vertices.len() < 10 {
        diagnostics.push(PropellerDiagnosticDto {
            severity: "error".to_string(),
            stage: "blade_preview".to_string(),
            message: "Preview mesh could not be generated from the current section data."
                .to_string(),
        });
    }
    if let Some(max_skew) = center_surface
        .stations
        .iter()
        .map(|station| station.skew.abs())
        .max_by(|left, right| left.total_cmp(right))
    {
        if max_skew > 0.5 {
            diagnostics.push(PropellerDiagnosticDto {
                severity: "warning".to_string(),
                stage: "section_placement".to_string(),
                message:
                    "High skew may cause self-intersection near the tip in later exact geometry stages."
                        .to_string(),
            });
        }
    }
    diagnostics.push(PropellerDiagnosticDto {
        severity: "info".to_string(),
        stage: "diagnostics".to_string(),
        message: format!(
            "Built {} spanwise section envelopes.",
            section_placement.span_sections.len()
        ),
    });
    diagnostics
}

fn build_section_curves(
    state: &PropellerFeatureState,
    eta: f64,
    chord_samples: usize,
) -> Vec<Vec<[f64; 2]>> {
    let camber = distribution_value(state, "camber", eta);
    let thickness = distribution_value(state, "thickness", eta);
    let te_thickness = state.profile_definition.trailing_edge_thickness;
    let count = chord_samples.max(2);
    let mut upper = Vec::with_capacity(count);
    let mut lower = Vec::with_capacity(count);

    for index in 0..count {
        let x = index as f64 / (count.saturating_sub(1).max(1) as f64);
        let camber_y = camber * (PI * x).sin();
        let camber_dy = camber * PI * (PI * x).cos();
        let thickness_shape = 0.2969 * x.max(1e-6).sqrt() - 0.1260 * x - 0.3516 * x * x
            + 0.2843 * x * x * x
            - 0.1015 * x * x * x * x;
        let thickness_y =
            (5.0 * thickness * thickness_shape + te_thickness * x * x).max(te_thickness);
        let half_thickness = thickness_y * 0.5;
        let phi = camber_dy.atan();
        upper.push([
            x - half_thickness * phi.sin(),
            camber_y + half_thickness * phi.cos(),
        ]);
        lower.push([
            x + half_thickness * phi.sin(),
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
        .collect()
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
    let mut pairs: Vec<[f64; 2]> = control_points
        .iter()
        .map(|point| [point.eta, point.value])
        .collect();
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

fn clamp(value: f64, minimum: f64, maximum: f64) -> f64 {
    value.max(minimum).min(maximum)
}

fn add3(left: [f64; 3], right: [f64; 3]) -> [f64; 3] {
    [left[0] + right[0], left[1] + right[1], left[2] + right[2]]
}

fn sub3(left: [f64; 3], right: [f64; 3]) -> [f64; 3] {
    [left[0] - right[0], left[1] - right[1], left[2] - right[2]]
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

fn norm3(vector: [f64; 3]) -> f64 {
    (vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2]).sqrt()
}

#[pymodule]
fn rotorlab_propeller_preview(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(propeller_backend_api_version, module)?)?;
    module.add_function(wrap_pyfunction!(propeller_rebuild_preview, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_mesh_for_default_preview_request() {
        let request = PropellerPreviewRequestDto {
            feature_state: default_feature_state("test-node-a"),
            dirty_stages: vec![],
            build_mode: "preview".to_string(),
            requested_artifacts: vec![],
        };
        let result = rebuild_preview_internal(&request).expect("preview rebuild should succeed");
        assert!(result.ok);
        assert_eq!(
            result.built_stages,
            STAGE_ORDER
                .iter()
                .map(|s| s.to_string())
                .collect::<Vec<_>>()
        );
        assert!(result.mesh.vertices.len() > 100);
        assert!(result.mesh.faces.len() > 100);
        assert!(result.radial_series.contains_key("pitch_pd"));
        assert!(result.radial_series.contains_key("camber"));
        assert_eq!(result.exact_artifacts, json!({}));
    }

    #[test]
    fn dirty_stage_rebuild_marks_downstream_stages() {
        let request = PropellerPreviewRequestDto {
            feature_state: default_feature_state("test-node-b"),
            dirty_stages: vec!["section_placement".to_string()],
            build_mode: "preview".to_string(),
            requested_artifacts: vec![],
        };
        let result = rebuild_preview_internal(&request).expect("preview rebuild should succeed");
        assert_eq!(
            result.built_stages,
            vec![
                "section_placement".to_string(),
                "blade_preview".to_string(),
                "diagnostics".to_string()
            ]
        );
    }

    #[test]
    fn exact_mode_populates_exact_artifacts() {
        let request = PropellerPreviewRequestDto {
            feature_state: default_feature_state("test-node-c"),
            dirty_stages: vec![],
            build_mode: "exact".to_string(),
            requested_artifacts: vec!["exact_artifacts".to_string()],
        };
        let result = rebuild_preview_internal(&request).expect("preview rebuild should succeed");
        let exact_artifacts = result
            .exact_artifacts
            .as_object()
            .expect("exact artifacts should be an object");
        assert_eq!(exact_artifacts.get("mode"), Some(&json!("exact")));
        assert_eq!(
            exact_artifacts.get("exact_stages_built"),
            Some(&json!(["blade_surface", "tip"]))
        );
        assert_eq!(
            exact_artifacts.get("pending_exact_stages"),
            Some(&json!(["hub", "pattern"]))
        );
        assert_eq!(exact_artifacts.get("blade_count"), Some(&json!(4)));
        assert!(exact_artifacts.get("vertex_count").is_some());
        assert!(exact_artifacts.get("face_count").is_some());
        assert!(exact_artifacts.get("bounds_min").is_some());
        assert!(exact_artifacts.get("bounds_max").is_some());
        assert!(exact_artifacts.get("blade_surface").is_some());
        assert!(exact_artifacts.get("tip_surface").is_some());
        assert!(exact_artifacts
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .contains("Truck blade-surface and tip stages completed"));
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
                num_blades: 4,
                hub_radius_ratio: 0.22,
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
                show_mesh: true,
                show_wireframe: true,
                show_sections: true,
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
                .collect(),
        }
    }
}
