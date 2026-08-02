"""
Event - 事件模型定义
统一事件格式，用于EventEngine异步消息分发
"""
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Optional, Dict
from datetime import datetime
import uuid


class EventType(Enum):
    """系统事件类型枚举"""
    # 数据相关事件
    MARKET_DATA_UPDATE = auto()      # 市场行情更新
    DATA_NEW_DATA = auto()           # DataAgent新数据入库
    
    # 策略相关事件
    STRATEGY_SIGNAL = auto()         # StrategyAgent生成信号
    STRATEGY_PARAM_UPDATE = auto()   # 策略参数更新
    
    # 交易相关事件
    TRADER_ORDER_REQUEST = auto()    # Trader请求下单
    TRADER_POSITION_CHANGE = auto()  # 持仓变动
    TRADER_ACCOUNT_SETTLE = auto()   # 账户结算
    
    # 执行相关事件
    EXECUTION_ORDER_SUBMIT = auto()  # 提交订单到执行引擎
    EXECUTION_ORDER_FILLED = auto()  # 订单成交
    EXECUTION_ORDER_REJECTED = auto() # 订单被拒绝
    
    # 风控相关事件
    RISK_CHECK_REQUEST = auto()      # 风控检查请求
    RISK_CHECK_PASS = auto()         # 风控检查通过
    RISK_CHECK_FAIL = auto()         # 风控检查失败
    RISK_WARNING = auto()            # 风控警告
    RISK_FORCE_LIQUIDATION = auto()  # 强制平仓
    
    # 系统事件
    SYSTEM_START = auto()            # 系统启动
    SYSTEM_STOP = auto()             # 系统停止
    SYSTEM_CONFIG_RELOAD = auto()    # 配置热更新
    
    # 回测事件
    BACKTEST_START = auto()          # 回测开始
    BACKTEST_PROGRESS = auto()       # 回测进度
    BACKTEST_COMPLETE = auto()       # 回测完成


@dataclass
class Event:
    """
    事件数据类
    
    Attributes:
        type: 事件类型 (EventType)
        data: 事件数据，根据事件类型不同而不同
        source: 事件来源（哪个Agent产生的）
        timestamp: 事件产生时间
        event_id: 唯一事件ID
        priority: 事件优先级，数值越小优先级越高
    """
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    priority: int = 5  # 默认优先级，1-10，1最高
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'event_id': self.event_id,
            'type': self.type.name,
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'priority': self.priority,
            'data': self.data
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Event':
        """从字典创建Event"""
        return cls(
            type=EventType[d['type']],
            data=d.get('data', {}),
            source=d.get('source', ''),
            timestamp=datetime.fromisoformat(d['timestamp']),
            event_id=d.get('event_id', ''),
            priority=d.get('priority', 5)
        )
    
    def __repr__(self) -> str:
        return f"Event({self.event_id}|{self.type.name}|{self.source})"
