from __future__ import annotations

from rotorlab_app.models.propeller import PropellerBuildRequestDTO, PropellerBuildResult


class PythonPropellerPreviewBackend:
    def rebuild_preview(self, _request: PropellerBuildRequestDTO) -> PropellerBuildResult:
        raise RuntimeError(
            "The Python propeller geometry fallback has been removed. "
            "Use the Rust backend via maturin develop."
        )
