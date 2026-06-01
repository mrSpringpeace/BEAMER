"""Výpočetní vlákno – neblokuje UI a hlásí průběh."""
from __future__ import annotations

import copy

from PySide6.QtCore import QThread, Signal

from ..solver import solve_beam
from ..analysis import reserves_along_beam


class ComputeWorker(QThread):
    progress = Signal(float)            # 0..1
    done = Signal(object, object)       # (SolverResult, list[ReserveResult])

    def __init__(self, state, n_stations=120):
        super().__init__()
        # snapshot stavu, aby editace UI během výpočtu nezpůsobila závod
        self.state = copy.deepcopy(state)
        self.n_stations = n_stations

    def run(self):
        self.progress.emit(0.05)
        result = solve_beam(self.state)
        self.progress.emit(0.35)
        if result.is_stable:
            reserves = reserves_along_beam(
                result, self.state, self.n_stations,
                progress=lambda f: self.progress.emit(0.35 + 0.6*f))
        else:
            reserves = []
        self.progress.emit(1.0)
        self.done.emit(result, reserves)
