from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from rotorlab_app.models.propeller import PropellerFeatureState, PropellerPreviewRequestDTO
from rotorlab_app.services.propeller_preview_bridge import PropellerPreviewBridge


class _PreviewTaskSignals(QObject):
    finished = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)


class _PreviewTask(QRunnable):
    def __init__(
        self,
        request_id: int,
        bridge: PropellerPreviewBridge,
        request: PropellerPreviewRequestDTO,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._bridge = bridge
        self._request = request
        self.signals = _PreviewTaskSignals()

    def run(self) -> None:
        try:
            result = self._bridge.rebuild_preview(self._request)
        except Exception as exc:  # pragma: no cover - guarded by tests via happy-path behavior
            self.signals.failed.emit(self._request_id, str(exc))
            return
        self.signals.finished.emit(self._request_id, result)


@dataclass
class PendingPreviewRequest:
    feature_state: PropellerFeatureState
    dirty_stages: list[str]


class PropellerPreviewService(QObject):
    preview_started = pyqtSignal(list)
    preview_ready = pyqtSignal(object)
    preview_failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bridge = PropellerPreviewBridge()
        self._thread_pool = QThreadPool.globalInstance()
        self._debounce = QTimer(self)
        self._debounce.setInterval(180)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._submit_pending_request)
        self._pending_request: PendingPreviewRequest | None = None
        self._active_request_id = 0

    @property
    def using_rust_backend(self) -> bool:
        return self._bridge.using_rust_backend

    def request_preview(
        self,
        feature_state: PropellerFeatureState,
        dirty_stages: list[str],
    ) -> None:
        self._pending_request = PendingPreviewRequest(
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
        request = PropellerPreviewRequestDTO(
            feature_state=pending.feature_state,
            dirty_stages=pending.dirty_stages,
        )
        self.preview_started.emit(request.dirty_stages)

        task = _PreviewTask(request_id, self._bridge, request)
        task.signals.finished.connect(self._handle_task_finished)
        task.signals.failed.connect(self._handle_task_failed)
        self._thread_pool.start(task)

    def _handle_task_finished(self, request_id: int, result) -> None:
        if request_id != self._active_request_id:
            return
        self.preview_ready.emit(result)

    def _handle_task_failed(self, request_id: int, message: str) -> None:
        if request_id != self._active_request_id:
            return
        self.preview_failed.emit(message)
