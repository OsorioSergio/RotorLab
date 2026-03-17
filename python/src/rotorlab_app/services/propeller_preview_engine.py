from __future__ import annotations

import math
import time
from typing import Any

from rotorlab_app.models.propeller import (
    PropellerDiagnosticDTO,
    PropellerPreviewMesh,
    PropellerPreviewRequestDTO,
    PropellerPreviewResult,
    STAGE_ORDER,
)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm <= 1e-9:
        return (0.0, 0.0, 1.0)
    return tuple(component / norm for component in vector)


def _cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(
    vector: tuple[float, float, float],
    factor: float,
) -> tuple[float, float, float]:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _catmull_rom(points: list[tuple[float, float]], x: float) -> float:
    if not points:
        return 0.0
    if len(points) == 1:
        return points[0][1]

    ordered = sorted(points, key=lambda item: item[0])
    if x <= ordered[0][0]:
        return ordered[0][1]
    if x >= ordered[-1][0]:
        return ordered[-1][1]

    segment_index = 0
    for index in range(len(ordered) - 1):
        if ordered[index][0] <= x <= ordered[index + 1][0]:
            segment_index = index
            break

    p0 = ordered[max(segment_index - 1, 0)]
    p1 = ordered[segment_index]
    p2 = ordered[segment_index + 1]
    p3 = ordered[min(segment_index + 2, len(ordered) - 1)]

    span = p2[0] - p1[0]
    if span <= 1e-9:
        return p1[1]

    t = (x - p1[0]) / span
    a0 = -0.5 * p0[1] + 1.5 * p1[1] - 1.5 * p2[1] + 0.5 * p3[1]
    a1 = p0[1] - 2.5 * p1[1] + 2.0 * p2[1] - 0.5 * p3[1]
    a2 = -0.5 * p0[1] + 0.5 * p2[1]
    a3 = p1[1]
    return ((a0 * t + a1) * t + a2) * t + a3


class PythonPropellerPreviewBackend:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def rebuild_preview(self, request: PropellerPreviewRequestDTO) -> PropellerPreviewResult:
        state = request.feature_state
        dirty_stages = [stage for stage in request.dirty_stages if stage in STAGE_ORDER] or list(STAGE_ORDER)
        start_index = min(STAGE_ORDER.index(stage) for stage in dirty_stages)
        timings: dict[str, float] = {}

        if start_index <= 0 or "center_surface" not in self._cache:
            start = time.perf_counter()
            self._cache["center_surface"] = self._build_center_surface(state)
            timings["center_surface"] = (time.perf_counter() - start) * 1000.0

        center_surface = self._cache["center_surface"]
        if start_index <= 1 or "profile_configurator" not in self._cache:
            start = time.perf_counter()
            self._cache["profile_configurator"] = self._build_profile_configurator(state, center_surface)
            timings["profile_configurator"] = (time.perf_counter() - start) * 1000.0

        profile_config = self._cache["profile_configurator"]
        if start_index <= 2 or "section_placement" not in self._cache:
            start = time.perf_counter()
            self._cache["section_placement"] = self._build_section_placement(
                state,
                center_surface,
                profile_config,
            )
            timings["section_placement"] = (time.perf_counter() - start) * 1000.0

        section_placement = self._cache["section_placement"]
        if start_index <= 3 or "blade_preview" not in self._cache:
            start = time.perf_counter()
            self._cache["blade_preview"] = self._build_blade_preview(
                state,
                section_placement,
            )
            timings["blade_preview"] = (time.perf_counter() - start) * 1000.0

        blade_preview = self._cache["blade_preview"]
        if start_index <= 4 or "diagnostics" not in self._cache:
            start = time.perf_counter()
            self._cache["diagnostics"] = self._build_diagnostics(
                state,
                center_surface,
                section_placement,
                blade_preview,
            )
            timings["diagnostics"] = (time.perf_counter() - start) * 1000.0

        diagnostics = self._cache["diagnostics"]
        built_stages = list(STAGE_ORDER[start_index:])

        return PropellerPreviewResult(
            ok=not any(item.severity == "error" for item in diagnostics),
            built_stages=built_stages,
            stage_timings_ms=timings,
            radial_series=center_surface["radial_series"] | profile_config["radial_series"],
            section_samples=profile_config["section_samples"],
            placed_section_samples=section_placement["placed_sections"],
            mesh=blade_preview["mesh"],
            diagnostics=diagnostics,
        )

    def _build_center_surface(self, state) -> dict[str, Any]:
        distributions = state.distributions
        radial_series: dict[str, list[tuple[float, float]]] = {}
        sample_etas = [index / 63.0 for index in range(64)]
        eta_hub = state.global_parameters.hub_radius_ratio
        diameter = state.global_parameters.radius * 2.0
        stations = []

        for key in ("pitch_pd", "rake", "skew", "chord"):
            distribution = distributions[key]
            radial_series[key] = [
                (eta, self._evaluate_distribution(distribution.control_points, _clamp(eta_hub + eta * (1.0 - eta_hub), eta_hub, 1.0)))
                for eta in sample_etas
            ]

        for index in range(state.preview_settings.span_samples):
            t = index / max(1, state.preview_settings.span_samples - 1)
            eta = eta_hub + (1.0 - eta_hub) * t
            radius = state.global_parameters.radius * eta
            pitch_pd = self._evaluate_distribution(distributions["pitch_pd"].control_points, eta)
            rake = self._evaluate_distribution(distributions["rake"].control_points, eta)
            skew = self._evaluate_distribution(distributions["skew"].control_points, eta)
            chord_ratio = self._evaluate_distribution(distributions["chord"].control_points, eta)
            pitch = pitch_pd * diameter
            beta = math.atan2(pitch, 2.0 * math.pi * max(radius, 1.0))
            stations.append(
                {
                    "eta": eta,
                    "radius": radius,
                    "pitch_pd": pitch_pd,
                    "rake": rake,
                    "skew": skew,
                    "chord": chord_ratio * diameter,
                    "beta": beta,
                }
            )

        return {"radial_series": radial_series, "stations": stations}

    def _build_profile_configurator(self, state, center_surface: dict[str, Any]) -> dict[str, Any]:
        radial_series: dict[str, list[tuple[float, float]]] = {}
        sample_etas = [index / 63.0 for index in range(64)]
        eta_hub = state.global_parameters.hub_radius_ratio
        for key in ("camber", "thickness", "angle_of_attack"):
            distribution = state.distributions[key]
            radial_series[key] = [
                (eta, self._evaluate_distribution(distribution.control_points, _clamp(eta_hub + eta * (1.0 - eta_hub), eta_hub, 1.0)))
                for eta in sample_etas
            ]

        section_eta = _clamp(
            state.preview_settings.section_eta,
            eta_hub,
            1.0,
        )
        section_curves = self._build_section_curves(
            state,
            section_eta,
            chord_samples=state.preview_settings.chord_samples,
        )
        return {
            "radial_series": radial_series,
            "section_samples": {f"{section_eta:.3f}": section_curves},
            "selected_eta": section_eta,
        }

    def _build_section_placement(self, state, center_surface: dict[str, Any], profile_config: dict[str, Any]) -> dict[str, Any]:
        placed_sections: dict[str, list[list[tuple[float, float, float]]]] = {}
        selected_eta = profile_config["selected_eta"]
        selected_key = f"{selected_eta:.3f}"
        selected_sections: list[list[tuple[float, float, float]]] = []
        span_sections: list[list[tuple[float, float, float]]] = []

        for station in center_surface["stations"]:
            eta = station["eta"]
            upper_2d, lower_2d = self._build_section_curves(
                state,
                eta,
                chord_samples=state.preview_settings.chord_samples,
            )
            upper_3d = self._place_section_curve(state, station, upper_2d, eta)
            lower_3d = self._place_section_curve(state, station, lower_2d, eta)
            span_sections.append(upper_3d + list(reversed(lower_3d)))
            if abs(eta - selected_eta) < 1e-6 or selected_key not in placed_sections:
                selected_sections = [upper_3d, lower_3d]

        placed_sections[selected_key] = selected_sections
        return {
            "placed_sections": placed_sections,
            "span_sections": span_sections,
        }

    def _build_blade_preview(self, state, section_placement: dict[str, Any]) -> dict[str, Any]:
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        section_polylines = section_placement["span_sections"]

        if not section_polylines:
            return {"mesh": PropellerPreviewMesh()}

        num_points = len(section_polylines[0])
        for polyline in section_polylines:
            vertices.extend(polyline)

        for section_index in range(len(section_polylines) - 1):
            row_offset = section_index * num_points
            next_offset = (section_index + 1) * num_points
            for point_index in range(num_points - 1):
                a = row_offset + point_index
                b = row_offset + point_index + 1
                c = next_offset + point_index
                d = next_offset + point_index + 1
                faces.append((a, c, b))
                faces.append((b, c, d))

        if state.global_parameters.num_blades > 1:
            base_vertices = list(vertices)
            base_faces = list(faces)
            base_polylines = list(section_polylines)
            blade_count = state.global_parameters.num_blades
            for blade_index in range(1, blade_count):
                angle = (2.0 * math.pi * blade_index) / blade_count
                cos_angle = math.cos(angle)
                sin_angle = math.sin(angle)
                blade_offset = len(vertices)
                rotated_vertices = [
                    (
                        vertex[0] * cos_angle - vertex[1] * sin_angle,
                        vertex[0] * sin_angle + vertex[1] * cos_angle,
                        vertex[2],
                    )
                    for vertex in base_vertices
                ]
                vertices.extend(rotated_vertices)
                faces.extend(
                    (
                        face[0] + blade_offset,
                        face[1] + blade_offset,
                        face[2] + blade_offset,
                    )
                    for face in base_faces
                )
                for polyline in base_polylines:
                    section_polylines.append(
                        [
                            (
                                point[0] * cos_angle - point[1] * sin_angle,
                                point[0] * sin_angle + point[1] * cos_angle,
                                point[2],
                            )
                            for point in polyline
                        ]
                    )

        return {
            "mesh": PropellerPreviewMesh(
                vertices=vertices,
                faces=faces,
                section_polylines=section_polylines if state.preview_settings.show_sections else [],
            )
        }

    def _build_diagnostics(
        self,
        state,
        center_surface: dict[str, Any],
        section_placement: dict[str, Any],
        blade_preview: dict[str, Any],
    ) -> list[PropellerDiagnosticDTO]:
        diagnostics: list[PropellerDiagnosticDTO] = []
        if state.global_parameters.hub_radius_ratio >= 0.5:
            diagnostics.append(
                PropellerDiagnosticDTO(
                    severity="warning",
                    stage="center_surface",
                    message="Hub radius ratio is high and may compress the active blade span.",
                )
            )
        if state.global_parameters.num_blades < 2:
            diagnostics.append(
                PropellerDiagnosticDTO(
                    severity="error",
                    stage="blade_preview",
                    message="At least two blades are required for a valid propeller preview.",
                )
            )
        if len(blade_preview["mesh"].vertices) < 10:
            diagnostics.append(
                PropellerDiagnosticDTO(
                    severity="error",
                    stage="blade_preview",
                    message="Preview mesh could not be generated from the current section data.",
                )
            )
        max_skew = max(abs(station["skew"]) for station in center_surface["stations"])
        if max_skew > 0.5:
            diagnostics.append(
                PropellerDiagnosticDTO(
                    severity="warning",
                    stage="section_placement",
                    message="High skew may cause self-intersection near the tip in later exact geometry stages.",
                )
            )
        diagnostics.append(
            PropellerDiagnosticDTO(
                severity="info",
                stage="diagnostics",
                message=f"Built {len(section_placement['span_sections'])} spanwise section envelopes.",
            )
        )
        return diagnostics

    def _evaluate_distribution(self, control_points, eta: float) -> float:
        pairs = [(point.eta, point.value) for point in control_points]
        return _catmull_rom(pairs, _clamp(eta, pairs[0][0], pairs[-1][0]))

    def _build_section_curves(self, state, eta: float, chord_samples: int) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        camber = self._evaluate_distribution(state.distributions["camber"].control_points, eta)
        thickness = self._evaluate_distribution(state.distributions["thickness"].control_points, eta)
        te_thickness = state.profile_definition.trailing_edge_thickness
        upper: list[tuple[float, float]] = []
        lower: list[tuple[float, float]] = []

        for index in range(chord_samples):
            x = index / max(1, chord_samples - 1)
            camber_y = camber * math.sin(math.pi * x)
            camber_dy = camber * math.pi * math.cos(math.pi * x)
            thickness_shape = (
                0.2969 * math.sqrt(max(x, 1e-6))
                - 0.1260 * x
                - 0.3516 * x * x
                + 0.2843 * x * x * x
                - 0.1015 * x * x * x * x
            )
            thickness_y = max(te_thickness, 5.0 * thickness * thickness_shape + te_thickness * x * x)
            half_thickness = thickness_y * 0.5
            phi = math.atan(camber_dy)
            upper.append(
                (
                    x - half_thickness * math.sin(phi),
                    camber_y + half_thickness * math.cos(phi),
                )
            )
            lower.append(
                (
                    x + half_thickness * math.sin(phi),
                    camber_y - half_thickness * math.cos(phi),
                )
            )

        return upper, lower

    def _place_section_curve(
        self,
        state,
        station: dict[str, float],
        section_curve: list[tuple[float, float]],
        eta: float,
    ) -> list[tuple[float, float, float]]:
        aoa_deg = self._evaluate_distribution(
            state.distributions["angle_of_attack"].control_points,
            eta,
        )
        theta = station["skew"]
        beta_eff = station["beta"] + math.radians(aoa_deg + state.global_parameters.pitch_reference_deg)
        radial = (math.cos(theta), math.sin(theta), 0.0)
        tangential = (-math.sin(theta), math.cos(theta), 0.0)
        axial = (0.0, 0.0, 1.0)
        chord_dir = _normalize(_add(_scale(tangential, math.cos(beta_eff)), _scale(axial, math.sin(beta_eff))))
        thickness_dir = _normalize(_cross(radial, chord_dir))
        origin = _add(
            _scale(radial, station["radius"]),
            _scale(axial, station["rake"] * state.global_parameters.radius * 2.0),
        )

        points_3d: list[tuple[float, float, float]] = []
        for x_sec, y_sec in section_curve:
            chordwise = _scale(chord_dir, station["chord"] * (x_sec - 0.45))
            thickness = _scale(thickness_dir, station["chord"] * y_sec)
            points_3d.append(_add(origin, _add(chordwise, thickness)))
        return points_3d

