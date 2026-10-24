"""事件驱动任务基类及任务执行状态管理。"""

from __future__ import annotations

import math
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from .event import Event
from .event_engine import EventEngine


class TaskMeta(ABC):
    """订阅事件并同步运行具体任务的抽象基类。

    Args:
        event_engine: 用于注册触发器和分发任务结束事件的事件引擎。
        triger: 非空且无重复的事件类型序列，采用完整事件类型精确匹配。
    """

    FINISHED_EVENT_TYPE: str = "task.execution.finished"

    def __init__(self, event_engine: EventEngine, triger: Sequence[str]) -> None:
        """验证任务触发器并向事件引擎注册本实例。

        Args:
            event_engine: 用于注册触发器和分发任务结束事件的事件引擎。
            triger: 非空且无重复的事件类型序列。

        Raises:
            TypeError: triger 不是事件类型序列或直接传入字符串时抛出。
            ValueError: triger 为空或包含重复事件类型时抛出。
            EventFormatError: triger 中含格式不合法的事件类型时抛出。
        """
        if isinstance(triger, str) or not isinstance(triger, Sequence):
            raise TypeError("triger must be a sequence of event type strings.")

        trigger_types = list(triger)
        if not trigger_types:
            raise ValueError("triger must contain at least one event type.")

        for event_type in trigger_types:
            Event.validate_event_type(event_type)
        if len(set(trigger_types)) != len(trigger_types):
            raise ValueError("triger event types must be unique.")

        self.event_engine = event_engine
        self.triger = trigger_types
        self._registered_triggers = tuple(trigger_types)
        self._progress = 0.0
        self._is_running = False
        self._is_closed = False
        self._state_lock = threading.Lock()

        for event_type in self._registered_triggers:
            self.event_engine.register(event_type, self._on_trigger)

    @property
    def progress(self) -> float:
        """返回当前运行进度，范围为 0 至 100。"""
        with self._state_lock:
            return self._progress

    def update_progress(self, value: float) -> None:
        """更新运行进度。

        Args:
            value: 进度值，必须是 0 至 100 之间的有限数值，且不得回退。

        Raises:
            TypeError: value 不是数值或为布尔值时抛出。
            ValueError: value 超出范围、不是有限数值或小于当前进度时抛出。
            RuntimeError: 任务当前未运行时抛出。
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("progress must be a number.")

        try:
            progress = float(value)
        except OverflowError as exc:
            raise ValueError("progress must be between 0 and 100.") from exc

        if not math.isfinite(progress) or not 0 <= progress <= 100:
            raise ValueError("progress must be a finite number between 0 and 100.")

        with self._state_lock:
            if not self._is_running:
                raise RuntimeError(
                    "progress can only be updated while the task is running."
                )
            if progress < self._progress:
                raise ValueError("progress cannot decrease during a task run.")
            self._progress = progress

    @abstractmethod
    def run(self, event: Event) -> None:
        """处理触发任务的事件。

        Args:
            event: 与本任务触发类型匹配的事件。
        """
        raise NotImplementedError

    def close(self) -> None:
        """取消本任务在事件引擎中的全部触发器注册。"""
        with self._state_lock:
            if self._is_closed:
                return
            self._is_closed = True

        for event_type in self._registered_triggers:
            self.event_engine.unregister(event_type, self._on_trigger)

    def _on_trigger(self, event: Event) -> None:
        """执行任务并在成功或失败后分发结束事件。

        Args:
            event: 触发本次任务运行的事件。

        Raises:
            RuntimeError: 本任务已有运行中的实例调用时抛出。
            Exception: 子类的 run() 失败时，在发出结束事件后继续抛出。
        """
        with self._state_lock:
            if self._is_closed:
                return
            if self._is_running:
                raise RuntimeError("this task instance is already running.")
            self._is_running = True
            self._progress = 0.0

        try:
            self.run(event)
        except Exception as run_error:
            with self._state_lock:
                self._is_running = False
                progress = self._progress
            try:
                self._emit_finished(event, "failed", progress)
            except Exception as finished_error:
                raise run_error from finished_error
            raise
        else:
            with self._state_lock:
                self._progress = 100.0
                self._is_running = False
                progress = self._progress
            self._emit_finished(event, "succeeded", progress)

    def _emit_finished(self, event: Event, status: str, progress: float) -> None:
        """通过 EventEngine 本地分发单次运行的结束事件。

        Args:
            event: 触发任务运行的原始事件。
            status: 运行结束状态，取值为 succeeded 或 failed。
            progress: 任务运行结束时的进度。
        """
        metadata: dict[str, Any] | None = None
        if event.trace_id is not None:
            metadata = {"trace_id": event.trace_id}

        self.event_engine.emit(
            self.FINISHED_EVENT_TYPE,
            {
                "task_name": type(self).__name__,
                "status": status,
                "progress": progress,
                "trigger_event_id": event.event_id,
                "trigger_event_type": event.event_type,
            },
            source="event_engine.task",
            metadata=metadata,
        )


__all__ = ["TaskMeta"]
