"""TimeAgent 独立线程计时器。"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from basic_utils.logging import get_logger


logger = get_logger(__name__)


class TimeAgentTimer:
    """按配置间隔在线程中重复调用回调的计时器。"""

    def __init__(
        self,
        callback: Callable[[], None],
        interval_seconds: float = 60,
        *,
        name: str,
    ) -> None:
        """创建尚未启动的计时器。

        Args:
            callback: 每次计时到期时执行的无参回调。
            interval_seconds: 每次回调后的等待秒数，必须大于零。
            name: 计时器线程名称，用于日志与诊断。

        Raises:
            TypeError: 回调不可调用，或间隔类型无效时抛出。
            ValueError: 计时器名称为空或间隔不为有限正数时抛出。
        """
        if not callable(callback):
            raise TypeError("callback must be callable.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string.")

        self._validate_interval(interval_seconds)
        self.callback = callback
        self.name = name.strip()
        self.interval_seconds = float(interval_seconds)
        self.is_running = False
        self._condition = threading.Condition()
        self._interval_revision = 0
        self._thread: threading.Thread | None = None

    @staticmethod
    def _validate_interval(interval_seconds: float) -> None:
        if isinstance(interval_seconds, bool) or not isinstance(
            interval_seconds,
            (int, float),
        ):
            raise TypeError("interval_seconds must be a number of seconds.")
        try:
            is_finite = math.isfinite(interval_seconds)
        except OverflowError as error:
            raise ValueError(
                "interval_seconds must be a finite positive number."
            ) from error
        if not is_finite or interval_seconds <= 0:
            raise ValueError("interval_seconds must be a finite positive number.")

    def set_interval(self, interval_seconds: float) -> None:
        """设置计时器间隔；运行中修改时从此刻重新计算下一次触发时间。

        对外 API：间隔单位为秒，必须为有限正数。

        Args:
            interval_seconds: 每次回调后的等待秒数。

        Raises:
            TypeError: 间隔不是数字时抛出。
            ValueError: 间隔不是有限正数时抛出。
        """
        self._validate_interval(interval_seconds)
        with self._condition:
            self.interval_seconds = float(interval_seconds)
            self._interval_revision += 1
            self._condition.notify_all()

    def start(self) -> None:
        """启动计时器线程；首次回调在完整间隔后执行。

        对外 API：计时器已运行时重复调用不会创建额外线程。

        Raises:
            RuntimeError: 前一次停止操作尚未等待线程退出时抛出。
        """
        with self._condition:
            if self.is_running:
                return
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError(
                    f"Timer {self.name!r} is still stopping."
                )
            self.is_running = True
            self._thread = threading.Thread(
                target=self._run,
                name=self.name,
                daemon=True,
            )
            try:
                self._thread.start()
            except Exception:
                self.is_running = False
                self._thread = None
                raise

    def stop(self) -> None:
        """停止计时器并等待当前回调及线程结束。

        对外 API：计时器未运行时不执行操作。线程退出前不会再开始新的回调。
        """
        with self._condition:
            self.is_running = False
            self._condition.notify_all()
            thread = self._thread

        if thread is not None and thread is not threading.current_thread():
            thread.join()

        with self._condition:
            if self._thread is thread and (
                thread is None or not thread.is_alive()
            ):
                self._thread = None

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    if not self.is_running:
                        return

                    revision = self._interval_revision
                    deadline = time.monotonic() + self.interval_seconds
                    while self.is_running:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        self._condition.wait(remaining)
                        if revision != self._interval_revision:
                            break

                    if not self.is_running:
                        return
                    if revision != self._interval_revision:
                        continue

                try:
                    self.callback()
                except Exception:
                    logger.exception(
                        f"Timer callback failed for {self.name!r}; "
                        "the timer will continue."
                    )
        finally:
            with self._condition:
                self.is_running = False
                self._thread = None
                self._condition.notify_all()
