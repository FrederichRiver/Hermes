"""
Django Seed Script —— 初始化示例数据

使用方法:
    cd backend
    python manage.py shell < seed_data.py
    
或者:
    python manage.py shell
    >>> exec(open('seed_data.py').read())
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hermes.settings')
django.setup()

from apps.core.models import Account, Position, MarketQuote, TradingSignal, RiskMetric, NetValuePoint

# 1. 创建交易账户
account, _ = Account.objects.get_or_create(
    id=1,
    defaults={
        'name': '主账户-001',
        'strategy_name': '多因子动量策略',
        'total_asset': 2847293.50,
        'available_cash': 893450.00,
        'holding_pnl': 124832.20,
        'capital_utilization': 68.6,
        'total_return_pct': 12.45,
        'max_drawdown_pct': 5.2,
        'sharpe_ratio': 1.85,
    }
)

# 2. 创建持仓
positions_data = [
    {'symbol': '000001.SZ', 'name': '平安银行', 'quantity': 5000, 'avg_price': 12.35, 'current_price': 13.82, 'market_value': 69100.00, 'weight_pct': 24.3, 'unrealized_pnl': 7350.00, 'unrealized_pnl_pct': 11.9},
    {'symbol': '600519.SH', 'name': '贵州茅台', 'quantity': 200, 'avg_price': 1680.00, 'current_price': 1725.50, 'market_value': 345100.00, 'weight_pct': 12.1, 'unrealized_pnl': 9100.00, 'unrealized_pnl_pct': 2.71},
    {'symbol': '300750.SZ', 'name': '宁德时代', 'quantity': 800, 'avg_price': 198.50, 'current_price': 185.20, 'market_value': 148160.00, 'weight_pct': 5.2, 'unrealized_pnl': -10640.00, 'unrealized_pnl_pct': -6.7},
    {'symbol': '000333.SZ', 'name': '美的集团', 'quantity': 3000, 'avg_price': 58.20, 'current_price': 62.45, 'market_value': 187350.00, 'weight_pct': 6.6, 'unrealized_pnl': 12750.00, 'unrealized_pnl_pct': 7.3},
    {'symbol': '002594.SZ', 'name': '比亚迪', 'quantity': 600, 'avg_price': 245.00, 'current_price': 268.80, 'market_value': 161280.00, 'weight_pct': 5.7, 'unrealized_pnl': 14280.00, 'unrealized_pnl_pct': 9.71},
]

for p in positions_data:
    Position.objects.get_or_create(
        account=account,
        symbol=p['symbol'],
        defaults={
            'name': p['name'],
            'side': 'long',
            'quantity': p['quantity'],
            'avg_price': p['avg_price'],
            'current_price': p['current_price'],
            'market_value': p['market_value'],
            'weight_pct': p['weight_pct'],
            'unrealized_pnl': p['unrealized_pnl'],
            'unrealized_pnl_pct': p['unrealized_pnl_pct'],
        }
    )

# 3. 创建行情报价
quotes_data = [
    {'symbol': '000001.SZ', 'name': '平安银行', 'price': 13.82, 'change': 0.35, 'change_pct': 2.6, 'volume': '12.5M', 'is_watching': True, 'has_alert': True},
    {'symbol': '600519.SH', 'name': '贵州茅台', 'price': 1725.50, 'change': 15.20, 'change_pct': 0.89, 'volume': '3.2M', 'is_watching': True, 'has_alert': False},
    {'symbol': '300750.SZ', 'name': '宁德时代', 'price': 185.20, 'change': -4.80, 'change_pct': -2.52, 'volume': '8.7M', 'is_watching': True, 'has_alert': False},
    {'symbol': '000333.SZ', 'name': '美的集团', 'price': 62.45, 'change': 1.12, 'change_pct': 1.83, 'volume': '5.1M', 'is_watching': True, 'has_alert': False},
    {'symbol': '002594.SZ', 'name': '比亚迪', 'price': 268.80, 'change': 6.50, 'change_pct': 2.48, 'volume': '4.8M', 'is_watching': True, 'has_alert': True},
    {'symbol': '600036.SH', 'name': '招商银行', 'price': 35.12, 'change': -0.28, 'change_pct': -0.79, 'volume': '6.3M', 'is_watching': True, 'has_alert': False},
]

for q in quotes_data:
    MarketQuote.objects.get_or_create(
        symbol=q['symbol'],
        defaults={
            'name': q['name'],
            'price': q['price'],
            'change': q['change'],
            'change_pct': q['change_pct'],
            'volume': q['volume'],
            'is_watching': q['is_watching'],
            'has_alert': q['has_alert'],
        }
    )

# 4. 创建交易信号
signals_data = [
    {'type': 'buy', 'symbol': '000001.SZ', 'message': '均线突破策略触发买入信号', 'status': 'executed', 'strategy_source': 'MA_Cross'},
    {'type': 'sell', 'symbol': '300750.SZ', 'message': '止损信号：回撤超过5%', 'status': 'pending', 'strategy_source': 'StopLoss'},
    {'type': 'warning', 'symbol': '002594.SZ', 'message': '仓位接近上限预警', 'status': 'info', 'strategy_source': 'RiskAgent'},
    {'type': 'buy', 'symbol': '600519.SH', 'message': '套利策略触发买入', 'status': 'executed', 'strategy_source': 'Arbitrage'},
    {'type': 'risk', 'symbol': 'SYSTEM', 'message': 'RiskAgent: 单仓风控检查通过', 'status': 'info', 'strategy_source': 'RiskAgent'},
    {'type': 'sell', 'symbol': '000333.SZ', 'message': '止盈信号：收益超过8%', 'status': 'rejected', 'strategy_source': 'TakeProfit'},
]

for s in signals_data:
    TradingSignal.objects.create(
        account=account if s['symbol'] != 'SYSTEM' else None,
        type=s['type'],
        symbol=s['symbol'],
        message=s['message'],
        status=s['status'],
        strategy_source=s['strategy_source'],
    )

# 5. 创建风控指标
risk_data = [
    {'name': '单日回撤', 'current_value': 1.2, 'limit_value': 5.0, 'usage_pct': 24.0, 'status': 'safe'},
    {'name': '单仓上限', 'current_value': 18.5, 'limit_value': 20.0, 'usage_pct': 92.5, 'status': 'warning'},
    {'name': '总仓比例', 'current_value': 68.6, 'limit_value': 80.0, 'usage_pct': 85.8, 'status': 'safe'},
    {'name': '可用资金', 'current_value': 893450.0, 'limit_value': 1000000.0, 'usage_pct': 11.3, 'status': 'safe'},
]

for r in risk_data:
    RiskMetric.objects.get_or_create(
        account=account,
        name=r['name'],
        defaults={
            'current_value': r['current_value'],
            'limit_value': r['limit_value'],
            'usage_pct': r['usage_pct'],
            'status': r['status'],
        }
    )

# 6. 创建净值曲线数据点
netvalue_data = [
    {'time_label': '09:30', 'strategy_value': 100.0, 'benchmark_value': 100.0},
    {'time_label': '10:00', 'strategy_value': 100.8, 'benchmark_value': 100.3},
    {'time_label': '10:30', 'strategy_value': 101.2, 'benchmark_value': 100.1},
    {'time_label': '11:00', 'strategy_value': 100.9, 'benchmark_value': 100.4},
    {'time_label': '11:30', 'strategy_value': 101.5, 'benchmark_value': 100.6},
    {'time_label': '13:00', 'strategy_value': 101.8, 'benchmark_value': 100.5},
    {'time_label': '13:30', 'strategy_value': 102.3, 'benchmark_value': 100.8},
    {'time_label': '14:00', 'strategy_value': 102.0, 'benchmark_value': 101.0},
    {'time_label': '14:30', 'strategy_value': 102.5, 'benchmark_value': 101.2},
    {'time_label': '15:00', 'strategy_value': 102.4, 'benchmark_value': 101.3},
]

for nv in netvalue_data:
    NetValuePoint.objects.get_or_create(
        account=account,
        time_label=nv['time_label'],
        defaults={
            'strategy_value': nv['strategy_value'],
            'benchmark_value': nv['benchmark_value'],
        }
    )

print("Seed data created successfully!")
print(f"Account: {account.name}")
print(f"Positions: {Position.objects.filter(account=account).count()}")
print(f"Quotes: {MarketQuote.objects.filter(is_watching=True).count()}")
print(f"Signals: {TradingSignal.objects.count()}")
print(f"Risk Metrics: {RiskMetric.objects.filter(account=account).count()}")
print(f"NetValue Points: {NetValuePoint.objects.filter(account=account).count()}")
