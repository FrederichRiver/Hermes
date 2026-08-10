# TraderAccount 账户Agent/交易账户基础实现
from typing import Dict, List

class CashFlow:
    def __init__(self, amount: float, type_: str, desc: str = ""):
        self.amount = amount
        self.type = type_  # e.g. 'deposit', 'withdraw', 'trade', 'fee', 'dividend'
        self.desc = desc

class Position:
    def __init__(self, symbol: str, qty: float, avg_price: float, direction: str = "long"):
        self.symbol = symbol
        self.qty = qty
        self.avg_price = avg_price
        self.direction = direction  # 'long' or 'short'

class TraderAccount:
    def __init__(self, account_id: str, strategy, initial_cash: float = 1_000_000):
        self.account_id = account_id
        self.strategy = strategy
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.cash_flows: List[CashFlow] = []
        self.pnl = 0.0
        self.nav = initial_cash
        self.risk_limits = {}

    def execute_signal(self, signal):
        """根据策略信号执行买卖操作，更新持仓和现金流水"""
        # signal: dict, e.g. {'action': 'buy'/'sell'/'hold', 'symbol': str, 'qty': float, 'price': float}
        action = signal.get('action')
        symbol = signal.get('symbol')
        qty = signal.get('qty', 0)
        price = signal.get('price', 0)
        if action == 'buy' and qty > 0 and price > 0:
            cost = qty * price
            if self.cash >= cost:
                # 更新现金
                self.cash -= cost
                # 更新持仓
                if symbol in self.positions:
                    pos = self.positions[symbol]
                    total_qty = pos.qty + qty
                    pos.avg_price = (pos.avg_price * pos.qty + price * qty) / total_qty
                    pos.qty = total_qty
                else:
                    self.positions[symbol] = Position(symbol, qty, price)
                # 记录流水
                self.cash_flows.append(CashFlow(-cost, 'trade', f'buy {symbol} {qty}'))
            else:
                print(f"[WARN] 账户{self.account_id}资金不足，无法买入{symbol}")
        elif action == 'sell' and qty > 0 and price > 0:
            if symbol in self.positions and self.positions[symbol].qty >= qty:
                # 卖出
                pos = self.positions[symbol]
                self.cash += qty * price
                pos.qty -= qty
                # 记录流水
                self.cash_flows.append(CashFlow(qty * price, 'trade', f'sell {symbol} {qty}'))
                if pos.qty == 0:
                    del self.positions[symbol]
            else:
                print(f"[WARN] 账户{self.account_id}持仓不足，无法卖出{symbol}")
        elif action == 'hold':
            pass  # 不操作
        else:
            print(f"[WARN] 未知信号或参数错误: {signal}")

    def settle(self, market_prices: dict = None):
        """结算账户，更新净值、盈亏等。market_prices: {symbol: price}"""
        # 计算持仓市值
        market_prices = market_prices or {}
        position_value = 0.0
        unrealized_pnl = 0.0
        for symbol, pos in self.positions.items():
            price = market_prices.get(symbol, pos.avg_price)
            position_value += pos.qty * price
            unrealized_pnl += (price - pos.avg_price) * pos.qty
        # 计算已实现盈亏
        realized_pnl = sum(cf.amount for cf in self.cash_flows if cf.type == 'trade') + self.cash - self.nav
        self.pnl = realized_pnl + unrealized_pnl
        self.nav = self.cash + position_value
