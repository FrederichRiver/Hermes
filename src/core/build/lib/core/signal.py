"""
Signal - 策略信号模型定义
StrategyAgent生成的买卖信号
"""
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class SignalType(Enum):
    """信号类型枚举"""
    BUY = auto()           # 买入
    SELL = auto()          # 卖出
    HOLD = auto()          # 持有（观望）
    CLOSE_LONG = auto()    # 平多仓
    CLOSE_SHORT = auto()   # 平空仓
    

@dataclass
class Signal:
    """
    策略信号数据类
    
    Attributes:
        signal_id: 信号唯一ID
        strategy_id: 产生该信号的策略ID
        trader_account_id: 目标交易账户ID
        
        signal_type: 信号类型 (SignalType)
        symbol: 交易标的代码
        qty: 交易数量
        price: 目标价格（可选，市价单可不填）
        order_type: 订单类型 (market/limit/stop)
        
        timestamp: 信号生成时间
        confidence: 信号置信度 (0-1)
        reason: 信号产生原因/说明
        metadata: 额外元数据
    """
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    strategy_id: str = ""
    trader_account_id: str = ""
    
    signal_type: SignalType = SignalType.HOLD
    symbol: str = ""
    qty: float = 0.0
    price: Optional[float] = None
    order_type: str = "market"  # market, limit, stop
    
    timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'signal_id': self.signal_id,
            'strategy_id': self.strategy_id,
            'trader_account_id': self.trader_account_id,
            'signal_type': self.signal_type.name,
            'symbol': self.symbol,
            'qty': self.qty,
            'price': self.price,
            'order_type': self.order_type,
            'timestamp': self.timestamp.isoformat(),
            'confidence': self.confidence,
            'reason': self.reason,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Signal':
        """从字典创建Signal"""
        return cls(
            signal_id=d.get('signal_id', ''),
            strategy_id=d.get('strategy_id', ''),
            trader_account_id=d.get('trader_account_id', ''),
            signal_type=SignalType[d.get('signal_type', 'HOLD')],
            symbol=d.get('symbol', ''),
            qty=d.get('qty', 0.0),
            price=d.get('price'),
            order_type=d.get('order_type', 'market'),
            timestamp=datetime.fromisoformat(d['timestamp']) if 'timestamp' in d else datetime.now(),
            confidence=d.get('confidence', 0.5),
            reason=d.get('reason', ''),
            metadata=d.get('metadata', {})
        )
    
    def is_valid(self) -> bool:
        """验证信号是否有效"""
        if self.signal_type == SignalType.HOLD:
            return True
        if not self.symbol or self.qty <= 0:
            return False
        if self.order_type == 'limit' and self.price is None:
            return False
        return True
    
    def __repr__(self) -> str:
        return f"Signal({self.signal_id}|{self.signal_type.name}|{self.symbol}|{self.qty})"
