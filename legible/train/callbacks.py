"""Trainer callbacks, copied from project 06 (smallprint/train/qlora.py at commit
3adf4fad7de74585e58ec208ec7f51127232b4bb): `Callback`, `StepTimer` and `SaveToStore`,
unchanged. Defined without the trainer so this package imports without the GPU stack."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from legible.train.checkpoint import CheckpointStore


class Callback:
    """A trainer callback without the trainer: every hook it does not define does nothing.

    The trainer calls a dozen hooks on every callback. Defined here rather than taken from
    transformers so this module imports without the GPU stack. The timing runs of
    2026-09-22 stopped at step 0 on a callback that defined only the two hooks it used.
    """

    def __getattr__(self, name: str) -> Any:
        if name.startswith("on_"):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


class StepTimer(Callback):
    """Seconds per optimiser step, timed around the steps and nothing else.

    Not the trainer's `train_runtime`: that counts the evaluations and checkpoint saves in
    between, and on the 2B smoke run, 2026-09-22, it gave 84.7 seconds a step against about
    25 for the steps themselves, two four-minute evaluations spread over ten steps. The
    smoke run's figure is what every GPU-hour estimate is multiplied out from, so it has to
    be the steps. `on_step_begin` fires at the start of an optimiser step, gradient
    accumulation included, and `on_step_end` at its end, before any save or evaluation.
    A callback in the trainer's sense, defined here so the module imports without the GPU
    stack, and with the clock a parameter so it is tested without one.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        import time

        self.clock = clock or time.perf_counter
        self.started: float | None = None
        self.total = 0.0
        self.steps = 0

    def on_step_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.started = self.clock()

    def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        if self.started is not None:
            self.total += self.clock() - self.started
            self.steps += 1
            self.started = None

    @property
    def seconds_per_step(self) -> float | None:
        return self.total / self.steps if self.steps else None


class SaveToStore(Callback):
    """A trainer callback that uploads each checkpoint as it is written.

    Defined here rather than imported from transformers so that this module still imports
    without the GPU stack; the trainer only needs the methods it calls.
    """

    def __init__(self, store: CheckpointStore, out_dir: Path) -> None:
        self.store = store
        self.out_dir = out_dir

    def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        directory = self.out_dir / f"checkpoint-{int(state.global_step)}"
        if directory.is_dir():
            self.store.save(directory)
