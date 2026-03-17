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

_RUST_API_MAJOR = "1."


def _rust_backend_compatible() -> bool:
    if _rust_backend is None:
        return False
    api_version_fn = getattr(_rust_backend, "propeller_backend_api_version", None)
    if not callable(api_version_fn):
        return False
    version = str(api_version_fn())
    return version.startswith(_RUST_API_MAJOR)


class PropellerPreviewBridge:
    def __init__(self) -> None:
        self._python_backend = PythonPropellerPreviewBackend()
        self._use_rust_backend = _rust_backend_compatible()

    @property
    def using_rust_backend(self) -> bool:
        return self._use_rust_backend

    def rebuild_preview(self, request: PropellerPreviewRequestDTO) -> PropellerPreviewResult:
        if self._use_rust_backend and _rust_backend is not None:
            payload = json.dumps(request.to_dict())
            response = _rust_backend.propeller_rebuild_preview(payload)
            return PropellerPreviewResult.from_dict(json.loads(response))
        return self._python_backend.rebuild_preview(request)
