from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ADVANCED_PROPELLER_MODULE_TYPE = "geometry.propeller_parametric_builder"
ACTIVE_PROPELLER_STAGES: tuple[str, ...] = (
    "center_surface",
    "profile_configurator",
    "section_placement",
    "blade_preview",
    "diagnostics",
)
DEFERRED_PROPELLER_STAGES: tuple[str, ...] = (
    "tip",
    "hub",
    "pattern",
    "flow_domain",
)
STAGE_LABELS: dict[str, str] = {
    "center_surface": "Center Surface",
    "profile_configurator": "Profile Configurator",
    "section_placement": "Section Placement",
    "blade_preview": "Blade Preview",
    "diagnostics": "Diagnostics",
    "tip": "Tip Surface",
    "hub": "Hub Blend",
    "pattern": "Pattern",
    "flow_domain": "Flow Domain",
}
STAGE_ORDER: tuple[str, ...] = ACTIVE_PROPELLER_STAGES


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
    num_blades: int = 4
    hub_radius_ratio: float = 0.22
    pitch_reference_deg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "radius": self.radius,
            "num_blades": self.num_blades,
            "hub_radius_ratio": self.hub_radius_ratio,
            "pitch_reference_deg": self.pitch_reference_deg,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GlobalParameters:
        return cls(
            radius=float(payload.get("radius", 2500.0)),
            num_blades=int(payload.get("num_blades", 4)),
            hub_radius_ratio=float(payload.get("hub_radius_ratio", 0.22)),
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
    show_mesh: bool = True
    show_wireframe: bool = True
    show_sections: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_samples": self.span_samples,
            "chord_samples": self.chord_samples,
            "section_eta": self.section_eta,
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
            show_mesh=bool(payload.get("show_mesh", True)),
            show_wireframe=bool(payload.get("show_wireframe", True)),
            show_sections=bool(payload.get("show_sections", True)),
        )


@dataclass
class PropellerFeatureState:
    node_id: str
    display_name: str
    module_type: str = ADVANCED_PROPELLER_MODULE_TYPE
    global_parameters: GlobalParameters = field(default_factory=GlobalParameters)
    profile_definition: ProfileDefinition = field(default_factory=ProfileDefinition)
    preview_settings: PreviewSettings = field(default_factory=PreviewSettings)
    distributions: dict[str, RadialDistribution] = field(default_factory=dict)
    dirty_stages: list[str] = field(default_factory=lambda: list(STAGE_ORDER))

    def mark_dirty_from_stage(self, stage: str) -> None:
        if stage not in STAGE_ORDER:
            return
        start_index = STAGE_ORDER.index(stage)
        downstream = list(STAGE_ORDER[start_index:])
        self.dirty_stages = [stage_name for stage_name in STAGE_ORDER if stage_name in set(self.dirty_stages + downstream)]

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
            distributions=distributions or default_distributions(),
            dirty_stages=[
                stage
                for stage in payload.get("dirty_stages", list(STAGE_ORDER))
                if isinstance(stage, str) and stage in STAGE_ORDER
            ]
            or list(STAGE_ORDER),
        )


@dataclass
class PropellerPreviewRequestDTO:
    feature_state: PropellerFeatureState
    dirty_stages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_state": self.feature_state.to_dict(),
            "dirty_stages": list(self.dirty_stages),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerPreviewRequestDTO:
        state_payload = payload.get("feature_state", {})
        return cls(
            feature_state=PropellerFeatureState.from_dict(
                state_payload if isinstance(state_payload, dict) else {}
            ),
            dirty_stages=[
                stage
                for stage in payload.get("dirty_stages", list(STAGE_ORDER))
                if isinstance(stage, str)
            ],
        )


@dataclass
class PropellerPreviewMesh:
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
    def from_dict(cls, payload: dict[str, Any]) -> PropellerPreviewMesh:
        def _triple(values: Any) -> tuple[float, float, float] | None:
            if not isinstance(values, (list, tuple)) or len(values) != 3:
                return None
            return (float(values[0]), float(values[1]), float(values[2]))

        vertices = [_triple(vertex) for vertex in payload.get("vertices", [])]
        faces = [_triple(face) for face in payload.get("faces", [])]
        section_polylines = []
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
class PropellerPreviewResult:
    ok: bool
    built_stages: list[str]
    stage_timings_ms: dict[str, float]
    radial_series: dict[str, list[tuple[float, float]]]
    section_samples: dict[str, list[list[tuple[float, float]]]]
    placed_section_samples: dict[str, list[list[tuple[float, float, float]]]]
    mesh: PropellerPreviewMesh
    diagnostics: list[PropellerDiagnosticDTO]

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
                key: [
                    [list(point) for point in curve]
                    for curve in curves
                ]
                for key, curves in self.section_samples.items()
            },
            "placed_section_samples": {
                key: [
                    [list(point) for point in curve]
                    for curve in curves
                ]
                for key, curves in self.placed_section_samples.items()
            },
            "mesh": self.mesh.to_dict(),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PropellerPreviewResult:
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
            mesh=PropellerPreviewMesh.from_dict(
                payload.get("mesh", {})
                if isinstance(payload.get("mesh", {}), dict)
                else {}
            ),
            diagnostics=[
                PropellerDiagnosticDTO.from_dict(item)
                for item in payload.get("diagnostics", [])
                if isinstance(item, dict)
            ],
        )


@dataclass
class PropellerEnvironmentSession:
    feature_state: PropellerFeatureState
    last_result: PropellerPreviewResult | None = None
    active_stage: str = ACTIVE_PROPELLER_STAGES[0]


def default_distributions() -> dict[str, RadialDistribution]:
    return {
        distribution.key: distribution
        for distribution in (
            RadialDistribution(
                key="pitch_pd",
                label="Pitch P/D",
                unit="ratio",
                stage="center_surface",
                control_points=[
                    DistributionControlPoint(0.22, 0.92),
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
                    DistributionControlPoint(0.22, 0.00),
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
                    DistributionControlPoint(0.22, 0.00),
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
                    DistributionControlPoint(0.22, 0.18),
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
                    DistributionControlPoint(0.22, 0.055),
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
                    DistributionControlPoint(0.22, 0.18),
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
                    DistributionControlPoint(0.22, 0.0),
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
        distributions=default_distributions(),
        dirty_stages=list(STAGE_ORDER),
    )
