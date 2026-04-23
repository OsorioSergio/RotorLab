from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ADVANCED_PROPELLER_MODULE_TYPE = "geometry.propeller_parametric_builder"
ACTIVE_PROPELLER_STAGES: tuple[str, ...] = (
    "center_surface",
    "profile_configurator",
    "section_placement",
    "tip",
    "hub",
    "pattern",
    "blade_preview",
    "diagnostics",
)
DEFERRED_PROPELLER_STAGES: tuple[str, ...] = ("flow_domain",)
STAGE_LABELS: dict[str, str] = {
    "center_surface": "Center Surface",
    "profile_configurator": "Profile Configurator",
    "section_placement": "Section Placement",
    "tip": "Tip Surface",
    "hub": "Hub Cylinder",
    "pattern": "Pattern",
    "blade_preview": "Blade Preview",
    "diagnostics": "Diagnostics",
    "flow_domain": "Flow Domain",
}
STAGE_ORDER: tuple[str, ...] = ACTIVE_PROPELLER_STAGES


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass
class DistributionControlPoint:
    eta: float
    value: float

    def to_dict(self) -> dict[str, float]:
        return {"eta": self.eta, "value": self.value}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DistributionControlPoint:
        return cls(
            eta=float(payload.get("eta", 0.0)),
            value=float(payload.get("value", 0.0)),
        )


@dataclass
class RadialDistribution:
    key: str
    label: str
    unit: str
    stage: str
    control_points: list[DistributionControlPoint]

    def clone(self) -> RadialDistribution:
        return RadialDistribution.from_dict(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "stage": self.stage,
            "control_points": [point.to_dict() for point in self.control_points],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RadialDistribution:
        raw_points = payload.get("control_points", [])
        control_points = [
            DistributionControlPoint.from_dict(point)
            for point in raw_points
            if isinstance(point, dict)
        ]
        return cls(
            key=str(payload.get("key", "")),
            label=str(payload.get("label", "")),
            unit=str(payload.get("unit", "")),
            stage=str(payload.get("stage", "center_surface")),
            control_points=control_points,
        )


@dataclass
class GlobalParameters:
    radius: float = 2500.0
    pitch_reference_deg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "radius": self.radius,
            "pitch_reference_deg": self.pitch_reference_deg,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GlobalParameters:
        return cls(
            radius=float(payload.get("radius", 2500.0)),
            pitch_reference_deg=float(payload.get("pitch_reference_deg", 0.0)),
        )


@dataclass
class ProfileDefinition:
    camber_family: str = "modified_naca"
    thickness_family: str = "naca66_like"
    trailing_edge_thickness: float = 0.006
    leading_edge_bias: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "camber_family": self.camber_family,
            "thickness_family": self.thickness_family,
            "trailing_edge_thickness": self.trailing_edge_thickness,
            "leading_edge_bias": self.leading_edge_bias,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProfileDefinition:
        return cls(
            camber_family=str(payload.get("camber_family", "modified_naca")),
            thickness_family=str(payload.get("thickness_family", "naca66_like")),
            trailing_edge_thickness=float(payload.get("trailing_edge_thickness", 0.006)),
            leading_edge_bias=float(payload.get("leading_edge_bias", 0.0)),
        )


@dataclass
class PreviewSettings:
    span_samples: int = 18
    chord_samples: int = 36
    section_eta: float = 0.7
    tessellation_rows: int = 64
    tessellation_cols: int = 120
    show_mesh: bool = True
    show_wireframe: bool = False
    show_sections: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_samples": self.span_samples,
            "chord_samples": self.chord_samples,
            "section_eta": self.section_eta,
            "tessellation_rows": self.tessellation_rows,
            "tessellation_cols": self.tessellation_cols,
            "show_mesh": self.show_mesh,
            "show_wireframe": self.show_wireframe,
            "show_sections": self.show_sections,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PreviewSettings:
        return cls(
            span_samples=int(payload.get("span_samples", 18)),
            chord_samples=int(payload.get("chord_samples", 36)),
            section_eta=float(payload.get("section_eta", 0.7)),
            tessellation_rows=int(payload.get("tessellation_rows", 64)),
            tessellation_cols=int(payload.get("tessellation_cols", 120)),
            show_mesh=bool(payload.get("show_mesh", True)),
            show_wireframe=bool(payload.get("show_wireframe", False)),
            show_sections=bool(payload.get("show_sections", False)),
        )


@dataclass
class TipParameters:
    closure_bias: float = 0.36
    roundness: float = 0.62
    cap_depth_ratio: float = 0.08
    cap_length_ratio: float = 0.14
    tip_thickness_fade: float = 0.78
    tip_camber_fade: float = 0.64
    tip_rake_fade: float = 0.24

    def to_dict(self) -> dict[str, Any]:
        return {
            "closure_bias": self.closure_bias,
            "roundness": self.roundness,
            "cap_depth_ratio": self.cap_depth_ratio,
            "cap_length_ratio": self.cap_length_ratio,
            "tip_thickness_fade": self.tip_thickness_fade,
            "tip_camber_fade": self.tip_camber_fade,
            "tip_rake_fade": self.tip_rake_fade,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TipParameters:
        return cls(
            closure_bias=float(payload.get("closure_bias", 0.36)),
            roundness=float(payload.get("roundness", 0.62)),
            cap_depth_ratio=float(payload.get("cap_depth_ratio", 0.08)),
            cap_length_ratio=float(payload.get("cap_length_ratio", 0.14)),
            tip_thickness_fade=float(payload.get("tip_thickness_fade", 0.78)),
            tip_camber_fade=float(payload.get("tip_camber_fade", 0.64)),
            tip_rake_fade=float(payload.get("tip_rake_fade", 0.24)),
        )


@dataclass
class HubParameters:
    hub_radius_ratio: float = 0.22
    hub_length_ratio: float = 0.34
    fore_profile_split: float = 0.42
    aft_profile_split: float = 0.58
    root_cutback_start: float = 0.18
    root_le_blend_ratio: float = 0.08
    root_te_blend_ratio: float = 0.06

    def to_dict(self) -> dict[str, Any]:
        return {
            "hub_radius_ratio": self.hub_radius_ratio,
            "hub_length_ratio": self.hub_length_ratio,
            "fore_profile_split": self.fore_profile_split,
            "aft_profile_split": self.aft_profile_split,
            "root_cutback_start": self.root_cutback_start,
            "root_le_blend_ratio": self.root_le_blend_ratio,
            "root_te_blend_ratio": self.root_te_blend_ratio,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HubParameters:
        return cls(
            hub_radius_ratio=float(payload.get("hub_radius_ratio", 0.22)),
            hub_length_ratio=float(payload.get("hub_length_ratio", 0.34)),
            fore_profile_split=float(payload.get("fore_profile_split", 0.42)),
            aft_profile_split=float(payload.get("aft_profile_split", 0.58)),
            root_cutback_start=float(payload.get("root_cutback_start", 0.18)),
            root_le_blend_ratio=float(payload.get("root_le_blend_ratio", 0.08)),
            root_te_blend_ratio=float(payload.get("root_te_blend_ratio", 0.06)),
        )


@dataclass
class PatternParameters:
    num_blades: int = 4
    start_angle_deg: float = 0.0
    handedness: str = "right"
    axis_convention: str = "z"

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_blades": self.num_blades,
            "start_angle_deg": self.start_angle_deg,
            "handedness": self.handedness,
            "axis_convention": self.axis_convention,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PatternParameters:
        handedness = str(payload.get("handedness", "right")).lower()
        axis_convention = str(payload.get("axis_convention", "z")).lower()
        return cls(
            num_blades=int(payload.get("num_blades", 4)),
            start_angle_deg=float(payload.get("start_angle_deg", 0.0)),
            handedness=handedness if handedness in {"right", "left"} else "right",
            axis_convention=axis_convention if axis_convention in {"z"} else "z",
        )


@dataclass
class PropellerFeatureState:
    node_id: str
    display_name: str
    module_type: str = ADVANCED_PROPELLER_MODULE_TYPE
    global_parameters: GlobalParameters = field(default_factory=GlobalParameters)
    profile_definition: ProfileDefinition = field(default_factory=ProfileDefinition)
    preview_settings: PreviewSettings = field(default_factory=PreviewSettings)
    tip_parameters: TipParameters = field(default_factory=TipParameters)
    hub_parameters: HubParameters = field(default_factory=HubParameters)
    pattern_parameters: PatternParameters = field(default_factory=PatternParameters)
    distributions: dict[str, RadialDistribution] = field(default_factory=dict)
    dirty_stages: list[str] = field(default_factory=lambda: list(STAGE_ORDER))

    def mark_dirty_from_stage(self, stage: str) -> None:
        if stage not in STAGE_ORDER:
            return
        start_index = STAGE_ORDER.index(stage)
        downstream = STAGE_ORDER[start_index:]
        existing = set(self.dirty_stages)
        self.dirty_stages = [
            stage_name
            for stage_name in STAGE_ORDER
            if stage_name in existing or stage_name in downstream
        ]

    def mark_clean(self, built_stages: list[str]) -> None:
        built = set(built_stages)
        self.dirty_stages = [stage for stage in self.dirty_stages if stage not in built]

    def clone(self) -> PropellerFeatureState:
        return PropellerFeatureState.from_dict(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "module_type": self.module_type,
            "global_parameters": self.global_parameters.to_dict(),
            "profile_definition": self.profile_definition.to_dict(),
            "preview_settings": self.preview_settings.to_dict(),
            "tip_parameters": self.tip_parameters.to_dict(),
            "hub_parameters": self.hub_parameters.to_dict(),
            "pattern_parameters": self.pattern_parameters.to_dict(),
            "distributions": {
                key: distribution.to_dict()
                for key, distribution in self.distributions.items()
            },
            "dirty_stages": list(self.dirty_stages),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerFeatureState:
        distributions_payload = payload.get("distributions", {})
        distributions = {
            str(key): RadialDistribution.from_dict(value)
            for key, value in distributions_payload.items()
            if isinstance(value, dict)
        }
        return cls(
            node_id=str(payload.get("node_id", "")),
            display_name=str(payload.get("display_name", "Propeller")),
            module_type=str(payload.get("module_type", ADVANCED_PROPELLER_MODULE_TYPE)),
            global_parameters=GlobalParameters.from_dict(
                payload.get("global_parameters", {})
                if isinstance(payload.get("global_parameters", {}), dict)
                else {}
            ),
            profile_definition=ProfileDefinition.from_dict(
                payload.get("profile_definition", {})
                if isinstance(payload.get("profile_definition", {}), dict)
                else {}
            ),
            preview_settings=PreviewSettings.from_dict(
                payload.get("preview_settings", {})
                if isinstance(payload.get("preview_settings", {}), dict)
                else {}
            ),
            tip_parameters=TipParameters.from_dict(
                payload.get("tip_parameters", {})
                if isinstance(payload.get("tip_parameters", {}), dict)
                else {}
            ),
            hub_parameters=HubParameters.from_dict(
                payload.get("hub_parameters", {})
                if isinstance(payload.get("hub_parameters", {}), dict)
                else {}
            ),
            pattern_parameters=PatternParameters.from_dict(
                payload.get("pattern_parameters", {})
                if isinstance(payload.get("pattern_parameters", {}), dict)
                else {}
            ),
            distributions=distributions or default_distributions(),
            dirty_stages=[
                stage
                for stage in payload.get("dirty_stages", list(STAGE_ORDER))
                if isinstance(stage, str) and stage in STAGE_ORDER
            ]
            or list(STAGE_ORDER),
        )


@dataclass
class PropellerBuildRequestDTO:
    feature_state: PropellerFeatureState
    dirty_stages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_state": self.feature_state.to_dict(),
            "dirty_stages": list(self.dirty_stages),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerBuildRequestDTO:
        state_payload = payload.get("feature_state", {})
        return cls(
            feature_state=PropellerFeatureState.from_dict(
                state_payload if isinstance(state_payload, dict) else {}
            ),
            dirty_stages=[
                stage
                for stage in payload.get("dirty_stages", list(STAGE_ORDER))
                if isinstance(stage, str) and stage in STAGE_ORDER
            ]
            or list(STAGE_ORDER),
        )


@dataclass
class PropellerBuildMesh:
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    section_polylines: list[list[tuple[float, float, float]]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertices": [list(vertex) for vertex in self.vertices],
            "faces": [list(face) for face in self.faces],
            "section_polylines": [
                [list(point) for point in polyline]
                for polyline in self.section_polylines
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerBuildMesh:
        def _triple(values: Any) -> tuple[float, float, float] | None:
            if not isinstance(values, (list, tuple)) or len(values) != 3:
                return None
            return (float(values[0]), float(values[1]), float(values[2]))

        vertices = [_triple(vertex) for vertex in payload.get("vertices", [])]
        faces = [_triple(face) for face in payload.get("faces", [])]
        section_polylines: list[list[tuple[float, float, float]]] = []
        for polyline in payload.get("section_polylines", []):
            if not isinstance(polyline, list):
                continue
            points = [_triple(point) for point in polyline]
            section_polylines.append([point for point in points if point is not None])
        return cls(
            vertices=[vertex for vertex in vertices if vertex is not None],
            faces=[
                (int(face[0]), int(face[1]), int(face[2]))
                for face in faces
                if face is not None
            ],
            section_polylines=section_polylines,
        )


@dataclass
class PropellerDiagnosticDTO:
    severity: str
    stage: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "stage": self.stage,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerDiagnosticDTO:
        return cls(
            severity=str(payload.get("severity", "info")),
            stage=str(payload.get("stage", "diagnostics")),
            message=str(payload.get("message", "")),
        )


@dataclass
class PropellerModelMetadata:
    source: str = "truck_tessellation"
    valid: bool = False
    watertight: bool = False
    blade_count: int = 0
    component_count: int = 0
    bounds_min: list[float] = field(default_factory=list)
    bounds_max: list[float] = field(default_factory=list)
    topology_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "valid": self.valid,
            "watertight": self.watertight,
            "blade_count": self.blade_count,
            "component_count": self.component_count,
            "bounds_min": list(self.bounds_min),
            "bounds_max": list(self.bounds_max),
            "topology_status": dict(self.topology_status),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerModelMetadata:
        return cls(
            source=str(payload.get("source", "truck_tessellation")),
            valid=bool(payload.get("valid", False)),
            watertight=bool(payload.get("watertight", False)),
            blade_count=int(payload.get("blade_count", 0)),
            component_count=int(payload.get("component_count", 0)),
            bounds_min=[
                float(value)
                for value in payload.get("bounds_min", [])
                if isinstance(value, (int, float))
            ],
            bounds_max=[
                float(value)
                for value in payload.get("bounds_max", [])
                if isinstance(value, (int, float))
            ],
            topology_status=dict(payload.get("topology_status", {}))
            if isinstance(payload.get("topology_status", {}), dict)
            else {},
        )


@dataclass
class PropellerBuildResult:
    ok: bool
    built_stages: list[str]
    stage_timings_ms: dict[str, float]
    radial_series: dict[str, list[tuple[float, float]]]
    section_samples: dict[str, list[list[tuple[float, float]]]]
    placed_section_samples: dict[str, list[list[tuple[float, float, float]]]]
    preview_mesh: PropellerBuildMesh
    diagnostics: list[PropellerDiagnosticDTO]
    model_metadata: PropellerModelMetadata = field(default_factory=PropellerModelMetadata)

    @property
    def mesh(self) -> PropellerBuildMesh:
        return self.preview_mesh

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "built_stages": list(self.built_stages),
            "stage_timings_ms": dict(self.stage_timings_ms),
            "radial_series": {
                key: [list(point) for point in samples]
                for key, samples in self.radial_series.items()
            },
            "section_samples": {
                key: [[list(point) for point in curve] for curve in curves]
                for key, curves in self.section_samples.items()
            },
            "placed_section_samples": {
                key: [[list(point) for point in curve] for curve in curves]
                for key, curves in self.placed_section_samples.items()
            },
            "preview_mesh": self.preview_mesh.to_dict(),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "model_metadata": self.model_metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerBuildResult:
        return cls(
            ok=bool(payload.get("ok", False)),
            built_stages=[
                stage for stage in payload.get("built_stages", []) if isinstance(stage, str)
            ],
            stage_timings_ms={
                str(key): float(value)
                for key, value in payload.get("stage_timings_ms", {}).items()
            },
            radial_series={
                str(key): [
                    (float(point[0]), float(point[1]))
                    for point in samples
                    if isinstance(point, (list, tuple)) and len(point) == 2
                ]
                for key, samples in payload.get("radial_series", {}).items()
                if isinstance(samples, list)
            },
            section_samples={
                str(key): [
                    [
                        (float(point[0]), float(point[1]))
                        for point in curve
                        if isinstance(point, (list, tuple)) and len(point) == 2
                    ]
                    for curve in curves
                    if isinstance(curve, list)
                ]
                for key, curves in payload.get("section_samples", {}).items()
                if isinstance(curves, list)
            },
            placed_section_samples={
                str(key): [
                    [
                        (float(point[0]), float(point[1]), float(point[2]))
                        for point in curve
                        if isinstance(point, (list, tuple)) and len(point) == 3
                    ]
                    for curve in curves
                    if isinstance(curve, list)
                ]
                for key, curves in payload.get("placed_section_samples", {}).items()
                if isinstance(curves, list)
            },
            preview_mesh=PropellerBuildMesh.from_dict(
                payload.get("preview_mesh", {})
                if isinstance(payload.get("preview_mesh", {}), dict)
                else {}
            ),
            diagnostics=[
                PropellerDiagnosticDTO.from_dict(item)
                for item in payload.get("diagnostics", [])
                if isinstance(item, dict)
            ],
            model_metadata=PropellerModelMetadata.from_dict(
                payload.get("model_metadata", {})
                if isinstance(payload.get("model_metadata", {}), dict)
                else {}
            ),
        )


@dataclass
class PropellerEnvironmentSession:
    feature_state: PropellerFeatureState
    last_result: PropellerBuildResult | None = None
    active_stage: str = ACTIVE_PROPELLER_STAGES[0]


def default_distributions() -> dict[str, RadialDistribution]:
    hub_eta = 0.22
    return {
        distribution.key: distribution
        for distribution in (
            RadialDistribution(
                key="pitch_pd",
                label="Pitch P/D",
                unit="ratio",
                stage="center_surface",
                control_points=[
                    DistributionControlPoint(hub_eta, 0.92),
                    DistributionControlPoint(0.55, 1.02),
                    DistributionControlPoint(0.82, 1.04),
                    DistributionControlPoint(1.0, 0.98),
                ],
            ),
            RadialDistribution(
                key="rake",
                label="Rake",
                unit="D",
                stage="center_surface",
                control_points=[
                    DistributionControlPoint(hub_eta, 0.00),
                    DistributionControlPoint(0.60, 0.03),
                    DistributionControlPoint(0.82, 0.08),
                    DistributionControlPoint(1.0, 0.12),
                ],
            ),
            RadialDistribution(
                key="skew",
                label="Skew",
                unit="rad",
                stage="center_surface",
                control_points=[
                    DistributionControlPoint(hub_eta, 0.00),
                    DistributionControlPoint(0.55, 0.12),
                    DistributionControlPoint(0.82, 0.22),
                    DistributionControlPoint(1.0, 0.30),
                ],
            ),
            RadialDistribution(
                key="chord",
                label="Chord / D",
                unit="ratio",
                stage="center_surface",
                control_points=[
                    DistributionControlPoint(hub_eta, 0.18),
                    DistributionControlPoint(0.45, 0.32),
                    DistributionControlPoint(0.72, 0.24),
                    DistributionControlPoint(1.0, 0.10),
                ],
            ),
            RadialDistribution(
                key="camber",
                label="Camber",
                unit="ratio",
                stage="profile_configurator",
                control_points=[
                    DistributionControlPoint(hub_eta, 0.055),
                    DistributionControlPoint(0.60, 0.035),
                    DistributionControlPoint(1.0, 0.010),
                ],
            ),
            RadialDistribution(
                key="thickness",
                label="Thickness",
                unit="ratio",
                stage="profile_configurator",
                control_points=[
                    DistributionControlPoint(hub_eta, 0.18),
                    DistributionControlPoint(0.60, 0.12),
                    DistributionControlPoint(1.0, 0.06),
                ],
            ),
            RadialDistribution(
                key="angle_of_attack",
                label="AoA Correction",
                unit="deg",
                stage="profile_configurator",
                control_points=[
                    DistributionControlPoint(hub_eta, 0.0),
                    DistributionControlPoint(0.70, 1.8),
                    DistributionControlPoint(1.0, -0.4),
                ],
            ),
        )
    }


def create_default_propeller_feature_state(
    node_id: str,
    display_name: str,
) -> PropellerFeatureState:
    return PropellerFeatureState(
        node_id=node_id,
        display_name=display_name,
        hub_parameters=HubParameters(hub_radius_ratio=0.22),
        preview_settings=PreviewSettings(
            section_eta=_clamp(0.7, 0.22, 1.0),
        ),
        distributions=default_distributions(),
        dirty_stages=list(STAGE_ORDER),
    )


PropellerPreviewMesh = PropellerBuildMesh
PropellerPreviewRequestDTO = PropellerBuildRequestDTO
PropellerPreviewResult = PropellerBuildResult
