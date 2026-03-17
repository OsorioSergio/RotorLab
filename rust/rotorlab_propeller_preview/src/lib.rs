use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeMap;

#[derive(Debug, Deserialize)]
struct PropellerPreviewRequestDto {
    feature_state: Value,
    dirty_stages: Vec<String>,
}

#[derive(Debug, Serialize)]
struct PropellerDiagnosticDto {
    severity: String,
    stage: String,
    message: String,
}

#[derive(Debug, Serialize)]
struct PropellerPreviewResponseDto {
    ok: bool,
    built_stages: Vec<String>,
    stage_timings_ms: BTreeMap<String, f64>,
    radial_series: BTreeMap<String, Vec<[f64; 2]>>,
    section_samples: BTreeMap<String, Vec<Vec<[f64; 2]>>>,
    placed_section_samples: BTreeMap<String, Vec<Vec<[f64; 3]>>>,
    mesh: Value,
    diagnostics: Vec<PropellerDiagnosticDto>,
}

#[pyfunction]
fn propeller_rebuild_preview(payload: &str) -> PyResult<String> {
    let request: PropellerPreviewRequestDto = serde_json::from_str(payload).map_err(|err| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
            "Invalid propeller preview payload: {err}"
        ))
    })?;

    let response = PropellerPreviewResponseDto {
        ok: false,
        built_stages: request.dirty_stages,
        stage_timings_ms: BTreeMap::new(),
        radial_series: BTreeMap::new(),
        section_samples: BTreeMap::new(),
        placed_section_samples: BTreeMap::new(),
        mesh: json!({
            "vertices": [],
            "faces": [],
            "section_polylines": []
        }),
        diagnostics: vec![PropellerDiagnosticDto {
            severity: "error".to_string(),
            stage: "diagnostics".to_string(),
            message: "Rust preview backend scaffold is present, but geometry evaluation is not implemented yet. The Python fallback backend should be used until the Rust toolchain is available and this crate is completed.".to_string(),
        }],
    };

    serde_json::to_string(&response).map_err(|err| {
        PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
            "Could not encode propeller preview response: {err}"
        ))
    })
}

#[pymodule]
fn rotorlab_propeller_preview(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(propeller_rebuild_preview, module)?)?;
    Ok(())
}
