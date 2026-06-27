"""
Django REST Framework Serializers
将 Model 数据序列化为 JSON API 响应
"""
from rest_framework import serializers
from .models import Account, Position, MarketQuote, TradingSignal, RiskMetric, NetValuePoint, SystemLog


class AccountSerializer(serializers.ModelSerializer):
    """账户序列化器 —— 对应 Dashboard 统计卡片"""
    class Meta:
        model = Account
        fields = [
            'id', 'name', 'strategy_name', 'total_asset', 'available_cash',
            'holding_pnl', 'capital_utilization', 'total_return_pct',
            'max_drawdown_pct', 'sharpe_ratio', 'is_active',
            'created_at', 'updated_at',
        ]


class PositionSerializer(serializers.ModelSerializer):
    """持仓序列化器 —— 对应持仓表格"""
    symbol_display = serializers.CharField(source='symbol', read_only=True)

    class Meta:
        model = Position
        fields = [
            'id', 'symbol', 'symbol_display', 'name', 'side', 'quantity',
            'avg_price', 'current_price', 'market_value', 'weight_pct',
            'unrealized_pnl', 'unrealized_pnl_pct', 'updated_at',
        ]


class MarketQuoteSerializer(serializers.ModelSerializer):
    """行情序列化器 —— 对应自选行情面板"""
    class Meta:
        model = MarketQuote
        fields = [
            'id', 'symbol', 'name', 'price', 'change', 'change_pct',
            'volume', 'is_watching', 'has_alert', 'updated_at',
        ]


class TradingSignalSerializer(serializers.ModelSerializer):
    """交易信号序列化器 —— 对应信号日志面板"""
    time_display = serializers.DateTimeField(source='timestamp', format='%H:%M:%S', read_only=True)

    class Meta:
        model = TradingSignal
        fields = [
            'id', 'time_display', 'type', 'symbol', 'message', 'status',
            'strategy_source', 'timestamp',
        ]


class RiskMetricSerializer(serializers.ModelSerializer):
    """风控指标序列化器 —— 对应风控监控面板"""
    class Meta:
        model = RiskMetric
        fields = [
            'id', 'name', 'current_value', 'limit_value', 'usage_pct', 'status',
            'updated_at',
        ]


class NetValuePointSerializer(serializers.ModelSerializer):
    """净值数据点序列化器 —— 对应净值曲线图表"""
    time = serializers.CharField(source='time_label', read_only=True)
    value = serializers.DecimalField(source='strategy_value', max_digits=12, decimal_places=4, read_only=True)
    benchmark = serializers.DecimalField(source='benchmark_value', max_digits=12, decimal_places=4, read_only=True)

    class Meta:
        model = NetValuePoint
        fields = ['time', 'value', 'benchmark']


class SystemLogSerializer(serializers.ModelSerializer):
    """系统日志序列化器 —— 对应日志中心"""
    class Meta:
        model = SystemLog
        fields = [
            'id', 'timestamp', 'level', 'module', 'error_code',
            'message', 'correlation_id', 'context',
        ]
