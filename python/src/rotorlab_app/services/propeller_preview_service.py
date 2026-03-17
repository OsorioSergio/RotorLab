from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from rotorlab_app.models.propeller import PropellerBuildRequestDTO, PropellerFeatureState
from rotorlab_app.services.propeller_preview_bridge import PropellerBuildBridge


class _BuildTaskSignals(QObject):
    finished = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)


class _BuildTask(QRunnable):
    def __init__(
        self,
        request_id: int,
        bridge: PropellerBuildBridge,
        request: PropellerBuildRequestDTO,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._bridge = bridge
        self._request = request
        self.signals = _BuildTaskSignals()

    def run(self) -> None:
        try:
            result = self._bridge.build_model(self._request)
        except Exception as exc:  # pragma: no cover - exercised in integration tests
            self.signals.failed.emit(self._request_id, str(exc))
            return
        self.signals.finished.emit(self._request_id, result)


@dataclass
class PendingBuildRequest:
    feature_state: PropellerFeatureState
    dirty_stages: list[str]


class PropellerBuildService(QObject):
    build_started = pyqtSignal(list)
    build_ready = pyqtSignal(object)
    build_failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bridge = PropellerBuildBridge()
        self._thread_pool = QThreadPool.globalInstance()
        self._debounce = QTimer(self)
        self._debounce.setInterval(180)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._submit_pending_request)
        self._pending_request: PendingBuildRequest | None = None
        self._active_request_id = 0

    @property
    def using_rust_backend(self) -> bool:
        return self._bridge.using_rust_backend

    @property
    def backend_error(self) -> str | None:
        return self._bridge.backend_error

    def request_build(
        self,
        feature_state: PropellerFeatureState,
        dirty_stages: list[str],
    ) -> None:
        self._pending_request = PendingBuildRequest(
            feature_state=feature_state.clone(),
            dirty_stages=list(dirty_stages),
        )
        self._debounce.start()

    def _submit_pending_request(self) -> None:
        pending = self._pending_request
        if pending is None:
            return

        self._active_request_id += 1
        request_id = self._active_request_id
        request = PropellerBuildRequestDTO(
            feature_state=pending.feature_state,
            dirty_stages=pending.dirty_stages,
        )
        self.build_started.emit(request.dirty_stages)

        task = _BuildTask(request_id, self._bridge, request)
        task.signals.finished.connect(self._handle_task_finished)
        task.signals.failed.connect(self._handle_task_failed)
        self._thread_pool.start(task)

    def _handle_task_finished(self, request_id: int, result) -> None:
        if request_id != self._active_request_id:
            return
        self.build_ready.emit(result)

    def _handle_task_failed(self, request_id: int, message: str) -> None:
        if request_id != self._active_request_id:
            return
        self.build_failed.emit(message)


PropellerPreviewService = PropellerBuildService
