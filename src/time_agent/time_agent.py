from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from basic_utils.logging import get_logger
from event_engine.event import Event
from event_engine.event_bus import EventBus, InMemoryEventBus

from .time_core import TimeCore
from .time_engine import TimeEngine
from .time_event import TimeEvent
from .time_timer import TimeAgentTimer


logger = get_logger(__name__)


class TimeAgent:
    """时间事件的创建、通知与事件总线发布协调器。

    对外 API：调用方可通过该类创建或发送时间事件、注册本地订阅者、
    查询当前 UTC 时间及服务状态。
    """

    TIMEPOINT_EVENT_TYPE: str = "time.cycle.timepoint"
    TIMER_COUNT: int = 10
    TIMER_EVENT_EXPIRATION_SECONDS: int = 60

    def __init__(
        self,
        timezone_name: str = "UTC",
        *,
        event_bus: EventBus | None = None,
    ) -> None:
        """初始化时间代理及其时间引擎和事件总线。

        对外 API：创建 TimeAgent 实例时调用。

        Args:
            timezone_name: TimeCore 和 TimeEngine 使用的时区名称，默认为 UTC。
            event_bus: 用于发布事件的 EventBus；未提供时创建进程内存事件总线。
        """
        self.time_core = TimeCore(timezone_name)
        self.time_engine = TimeEngine(timezone_name)
        self.bus = (
            event_bus
            if event_bus is not None
            else InMemoryEventBus(stream_name="time")
        )
        self.subscribers: List[Callable[[TimeEvent], None]] = []
        self.events: List[TimeEvent] = []
        self.timers = [
            TimeAgentTimer(
                self._publish_timer_event,
                name=f"time-agent-timer-{timer_number:02d}",
            )
            for timer_number in range(1, self.TIMER_COUNT + 1)
        ]

    def subscribe(self, callback: Callable[[TimeEvent], None]) -> None:
        """注册一个接收本地 TimeEvent 通知的回调函数。

        对外 API：事件通过 emit() 发出时，已注册的回调会依次收到该事件。

        Args:
            callback: 接收一个 TimeEvent、返回 None 的回调函数。
        """
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[TimeEvent], None]) -> None:
        """取消注册本地事件回调。

        对外 API：若回调当前已注册，则移除一次；未注册时不执行操作。

        Args:
            callback: 要取消注册的回调函数。
        """
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def emit(self, event: TimeEvent) -> None:
        """保存并向当前所有本地订阅者同步发送时间事件。

        对外 API：此方法只负责本地回调通知，不会写入 EventBus Stream。
        若某个回调抛出异常，异常会向调用方传播，后续回调不会继续执行。

        Args:
            event: 要保存并发送的时间事件。
        """
        self.events.append(event)
        for callback in list(self.subscribers):
            callback(event)

    def create_event(
        self,
        *,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "time_agent",
        occurs_at: Optional[datetime] = None,
        recurring: bool = False,
        cron: Optional[str] = None,
        timezone: str = "UTC",
    ) -> TimeEvent:
        """根据给定属性创建时间事件，但不保存或发送该事件。

        对外 API：适用于需要先组装事件、再自行决定何时发送的场景。

        Args:
            event_type: 事件类型名称。
            payload: 事件业务数据；省略或传入空值时使用空字典。
            source: 事件来源标识，默认为 ``time_agent``。
            occurs_at: 事件发生时间；未提供时使用当前 UTC 时间。
            recurring: 标记该事件是否属于重复事件，默认为 False。
            cron: 可选的 cron 表达式，用于描述重复时间规则。
            timezone: 事件时间规则使用的时区名称，默认为 UTC。

        Returns:
            创建完成但尚未发送的 TimeEvent。
        """
        event = TimeEvent(
            event_type=event_type,
            payload=payload or {},
            source=source,
            timestamp=occurs_at or self.time_engine.now_utc(),
            occurs_at=occurs_at or self.time_engine.now_utc(),
            recurring=recurring,
            cron=cron,
            timezone=timezone,
        )
        return event

    def schedule(self, *, event_type: str, payload: Optional[Dict[str, Any]] = None, source: str = "time_agent", occurs_at: datetime, recurring: bool = False, cron: Optional[str] = None, timezone: str = "UTC") -> TimeEvent:
        """创建时间事件，并立即通过本地回调机制发送。

        对外 API：该方法会调用 create_event() 创建事件，再调用 emit() 保存并
        通知订阅者；它不会将事件发布到 EventBus Stream，也不会等待 occurs_at
        到达后再触发。

        Args:
            event_type: 事件类型名称。
            payload: 事件业务数据；未提供时使用空字典。
            source: 事件来源标识，默认为 ``time_agent``。
            occurs_at: 事件的发生时间。
            recurring: 标记该事件是否属于重复事件，默认为 False。
            cron: 可选的 cron 表达式，用于描述重复时间规则。
            timezone: 事件时间规则使用的时区名称，默认为 UTC。

        Returns:
            已保存并通知本地订阅者的 TimeEvent。
        """
        event = self.create_event(
            event_type=event_type,
            payload=payload,
            source=source,
            occurs_at=occurs_at,
            recurring=recurring,
            cron=cron,
            timezone=timezone,
        )
        self.emit(event)
        return event

    def now(self) -> datetime:
        """获取 TimeEngine 提供的当前 UTC 时间。

        对外 API：返回带时区信息的 UTC datetime，不受构造时的本地时区设置影响。

        Returns:
            当前 UTC 时间。
        """
        return self.time_engine.now_utc()

    def publish_timepoint(self, expiration_seconds: int = 60) -> str | bytes:
        """将当前 UTC 时间点事件写入配置的 EventBus Stream。

        对外 API：发布 ``time.cycle.timepoint`` 事件，事件数据的 ``timepoint``
        字段为当前 UTC 时间的 ISO 8601 字符串，并在 ``expiration_seconds``
        秒后过期。使用 EventBus 的 Stream 发布接口；不会触发本地 subscribe()
        回调。

        Args:
            expiration_seconds: 事件有效时长，单位为秒，必须是非负整数，默认为 60。

        Returns:
            EventBus 返回的 Stream 条目 ID。
        """
        event = Event.create(
            self.TIMEPOINT_EVENT_TYPE,
            source="time_agent",
            event_data={"timepoint": self.now().isoformat()},
            expires_in_seconds=expiration_seconds,
        )
        return self.bus.publish_stream(event)

    def set_timer_interval(
        self,
        timer_index: int,
        interval_seconds: float,
    ) -> None:
        """设置指定计时器的运行间隔。

        对外 API：``timer_index`` 从 0 开始，范围为 0 至 9；运行中的计时器
        会从设置时刻重新计算下一次触发时间。

        Args:
            timer_index: 计时器索引，0 对应第一个计时器。
            interval_seconds: 每次回调后的等待秒数，必须为有限正数。

        Raises:
            IndexError: 索引不属于当前计时器范围时抛出。
            TypeError: 索引或间隔类型无效时抛出。
            ValueError: 间隔不是有限正数时抛出。
        """
        self._get_timer(timer_index).set_interval(interval_seconds)

    def start_timer(self, timer_index: int) -> None:
        """启动指定计时器。

        对外 API：计时器启动后先等待其完整间隔，再首次发布事件。

        Args:
            timer_index: 计时器索引，0 对应第一个计时器。

        Raises:
            IndexError: 索引不属于当前计时器范围时抛出。
            TypeError: 索引不是整数时抛出。
        """
        self._get_timer(timer_index).start()

    def stop_timer(self, timer_index: int) -> None:
        """停止指定计时器并等待其线程退出。

        对外 API：计时器未运行时不执行操作。

        Args:
            timer_index: 计时器索引，0 对应第一个计时器。

        Raises:
            IndexError: 索引不属于当前计时器范围时抛出。
            TypeError: 索引不是整数时抛出。
        """
        self._get_timer(timer_index).stop()

    def stop_timers(self) -> None:
        """停止所有计时器并等待其工作线程退出。

        对外 API：服务关闭时应在关闭 EventBus 前调用。
        """
        for timer in self.timers:
            timer.stop()

    def _get_timer(self, timer_index: int) -> TimeAgentTimer:
        """按从零开始的索引获取计时器。"""
        if isinstance(timer_index, bool) or not isinstance(timer_index, int):
            raise TypeError("timer_index must be an integer.")
        if not 0 <= timer_index < len(self.timers):
            raise IndexError(
                f"timer_index must be between 0 and {len(self.timers) - 1}."
            )
        return self.timers[timer_index]

    def _publish_timer_event(self) -> None:
        """创建当前 UTC 分钟对应的时间事件并写入 EventBus Stream。"""
        current_time = self.now()
        event_type = (
            f"time.timepoint.{current_time:%H}h{current_time:%M}m"
        )
        event = Event.create(
            event_type,
            source="time_agent",
            event_data={"timepoint": current_time.isoformat()},
            expires_in_seconds=self.TIMER_EVENT_EXPIRATION_SECONDS,
        )
        stream_entry_id = self.bus.publish_stream(event)
        logger.info(
            f"Published timer event {event_type!r} to Stream "
            f"{self.bus.stream_name!r} with ID {stream_entry_id}."
        )

    def status(self) -> Dict[str, Any]:
        """返回 TimeAgent 当前的基本运行状态。

        对外 API：用于监控或诊断当前时区、UTC 时间、本地事件数量和订阅者数量。

        Returns:
            包含 ``timezone``、``now``、``event_count`` 和 ``subscriber_count``
            字段的状态字典；其中 ``now`` 为 ISO 8601 UTC 时间字符串，
            ``running_timer_count`` 为正在运行的计时器数量。
        """
        return {
            "timezone": self.time_engine.timezone_name,
            "now": self.now().isoformat(),
            "event_count": len(self.events),
            "subscriber_count": len(self.subscribers),
            "running_timer_count": sum(
                timer.is_running for timer in self.timers
            ),
        }
