from __future__ import annotations

import json

from rotorlab_app.models.propeller import (
    PropellerBuildRequestDTO,
    PropellerBuildResult,
)

try:
    import rotorlab_propeller_preview as _rust_backend
except ImportError:  # pragma: no cover - exercised in backend-missing tests
    _rust_backend = None


EXPECTED_BACKEND_CONTRACT = "rotorlab-propeller-build:2026-03-17.1"


def _backend_error() -> str | None:
    if _rust_backend is None:
        return (
            "Rust backend is not installed. Run the repo maturin develop flow before using "
            "the advanced propeller workspace."
        )

    contract_fn = getattr(_rust_backend, "propeller_backend_contract", None)
    build_fn = getattr(_rust_backend, "propeller_build_model", None)
    if not callable(contract_fn) or not callable(build_fn):
        return "Rust backend is missing the authoritative propeller build entry points."

    contract = str(contract_fn())
    if contract != EXPECTED_BACKEND_CONTRACT:
        return (
            "Rust backend contract mismatch. "
            f"Expected {EXPECTED_BACKEND_CONTRACT}, got {contract}."
        )
    return None


class PropellerBuildBridge:
    def __init__(self) -> None:
        self._backend_error = _backend_error()

    @property
    def using_rust_backend(self) -> bool:
        return self._backend_error is None

    @property
    def backend_error(self) -> str | None:
        return self._backend_error

    def build_model(self, request: PropellerBuildRequestDTO) -> PropellerBuildResult:
        if self._backend_error is not None or _rust_backend is None:
            raise RuntimeError(self._backend_error or "Rust backend unavailable.")

        payload = json.dumps(request.to_dict())
        response = _rust_backend.propeller_build_model(payload)
        return PropellerBuildResult.from_dict(json.loads(response))

    def rebuild_preview(self, request: PropellerBuildRequestDTO) -> PropellerBuildResult:
        return self.build_model(request)


PropellerPreviewBridge = PropellerBuildBridge
