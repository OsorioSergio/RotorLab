from __future__ import annotations

import json

from rotorlab_app.models.propeller import (
    PropellerPreviewRequestDTO,
    PropellerPreviewResult,
)
from rotorlab_app.services.propeller_preview_engine import PythonPropellerPreviewBackend

try:
    import rotorlab_propeller_preview as _rust_backend
except ImportError:  # pragma: no cover - exercised only when the Rust extension is available
    _rust_backend = None


class PropellerPreviewBridge:
    def __init__(self) -> None:
        self._python_backend = PythonPropellerPreviewBackend()

    @property
    def using_rust_backend(self) -> bool:
        return _rust_backend is not None

    def rebuild_preview(self, request: PropellerPreviewRequestDTO) -> PropellerPreviewResult:
        if _rust_backend is not None:
            payload = json.dumps(request.to_dict())
            response = _rust_backend.propeller_rebuild_preview(payload)
            return PropellerPreviewResult.from_dict(json.loads(response))
        return self._python_backend.rebuild_preview(request)
