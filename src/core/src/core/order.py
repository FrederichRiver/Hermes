"""
Order - 订单模型定义
ExecutionEngine处理的订单
"""
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class OrderSide(Enum):
    """订单方向"""
    BUY = auto()
    SELL = auto()


class OrderStatus(Enum):
    """订单状态"""
    PENDING = auto()       # 待提交
    SUBMITTED = auto()     # 已提交
    PARTIAL_FILLED = auto() # 部分成交
    FILLED = auto()        # 完全成交
    REJECTED = auto()      # 被拒绝
    CANCELLED = auto()     # 已撤销
    EXPIRED = auto()       # 已过期


class OrderType(Enum):
    """订单类型"""
    MARKET = auto()        # 市价单
    LIMIT = auto()         # 限价单
    STOP = auto()          # 止损单
    STOP_LIMIT = auto()    # 止损限价单


@dataclass
class Order:
    """
    订单数据类
    
    Attributes:
        order_id: 订单唯一ID
        signal_id: 关联的信号ID
        trader_account_id: 交易账户ID
        strategy_id: 策略ID
        
        side: 买卖方向
        symbol: 交易标的
        qty: 订单数量
        filled_qty: 已成交数量
        price: 订单价格（限价单）
        avg_fill_price: 成交均价
        
        order_type: 订单类型
        status: 订单状态
        
        created_at: 创建时间
        submitted_at: 提交时间
        filled_at: 成交时间
        
        commission: 手续费
        slippage: 滑点成本
        
        metadata: 额外元数据
    """
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    signal_id: str = ""
    trader_account_id: str = ""
    strategy_id: str = ""
    
    side: OrderSide = OrderSide.BUY
    symbol: str = ""
    qty: float = 0.0
    filled_qty: float = 0.0
    price: Optional[float] = None
    avg_fill_price: float = 0.0
    
    order_type: OrderType = OrderType.MARKET
    status: OrderStatus = OrderStatus.PENDING
    
    created_at: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    
    commission: float = 0.0
    slippage: float = 0.0
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def remaining_qty(self) -> float:
        """剩余未成交数量"""
        return self.qty - self.filled_qty
    
    @property
    def is_filled(self) -> bool:
        """是否已完全成交"""
        return self.status == OrderStatus.FILLED
    
    @property
    def is_active(self) -> bool:
        """订单是否还在活动中"""
        return self.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]
    
    @property
    def total_cost(self) -> float:
        """订单总成本（含手续费和滑点）"""
        fill_value = self.filled_qty * self.avg_fill_price
        return fill_value + self.commission + self.slippage
    
    def fill(self, qty: float, price: float, commission: float = 0.0, slippage: float = 0.0):
        """
        订单成交处理
        
        Args:
            qty: 成交数量
            price: 成交价格
            commission: 手续费
            slippage: 滑点
        """
        if qty <= 0 or qty > self.remaining_qty:
            raise ValueError(f"Invalid fill quantity: {qty}")
        
        # 更新成交均价（加权平均）
        total_value = self.filled_qty * self.avg_fill_price + qty * price
        self.filled_qty += qty
        self.avg_fill_price = total_value / self.filled_qty if self.filled_qty > 0 else 0
        
        self.commission += commission
        self.slippage += slippage
        
        # 更新状态
        if self.filled_qty >= self.qty:
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.now()
        else:
            self.status = OrderStatus.PARTIAL_FILLED
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'order_id': self.order_id,
            'signal_id': self.signal_id,
            'trader_account_id': self.trader_account_id,
            'strategy_id': self.strategy_id,
            'side': self.side.name,
            'symbol': self.symbol,
            'qty': self.qty,
            'filled_qty': self.filled_qty,
            'price': self.price,
            'avg_fill_price': self.avg_fill_price,
            'order_type': self.order_type.name,
            'status': self.status.name,
            'created_at': self.created_at.isoformat(),
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
            'commission': self.commission,
            'slippage': self.slippage,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_signal(cls, signal, trader_account_id: str = "") -> 'Order':
        """从Signal创建Order"""
        side = OrderSide.BUY if signal.signal_type.name in ['BUY'] else OrderSide.SELL
        order_type = OrderType.MARKET if signal.order_type == 'market' else OrderType.LIMIT
        
        return cls(
            signal_id=signal.signal_id,
            trader_account_id=trader_account_id or signal.trader_account_id,
            strategy_id=signal.strategy_id,
            side=side,
            symbol=signal.symbol,
            qty=signal.qty,
            price=signal.price,
            order_type=order_type
        )
    
    def __repr__(self) -> str:
        return f"Order({self.order_id}|{self.side.name}|{self.symbol}|{self.status.name}|{self.filled_qty}/{self.qty})"
