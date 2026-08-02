"""
Django Admin 注册 —— 便于在 Django Admin 后台管理数据
"""
from django.contrib import admin
from .models import Account, Position, MarketQuote, TradingSignal, RiskMetric, NetValuePoint, SystemLog


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'strategy_name', 'total_asset', 'available_cash', 'is_active', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'strategy_name']


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'name', 'account', 'quantity', 'current_price', 'unrealized_pnl', 'updated_at']
    list_filter = ['side', 'updated_at']
    search_fields = ['symbol', 'name']


@admin.register(MarketQuote)
class MarketQuoteAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'name', 'price', 'change_pct', 'is_watching', 'updated_at']
    list_filter = ['is_watching', 'has_alert']
    search_fields = ['symbol', 'name']


@admin.register(TradingSignal)
class TradingSignalAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'type', 'symbol', 'status', 'strategy_source']
    list_filter = ['type', 'status', 'timestamp']
    search_fields = ['symbol', 'message']


@admin.register(RiskMetric)
class RiskMetricAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'current_value', 'limit_value', 'usage_pct', 'status']
    list_filter = ['status', 'updated_at']


@admin.register(NetValuePoint)
class NetValuePointAdmin(admin.ModelAdmin):
    list_display = ['account', 'time_label', 'strategy_value', 'benchmark_value', 'recorded_at']
    list_filter = ['account', 'recorded_at']


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'level', 'module', 'error_code', 'message']
    list_filter = ['level', 'timestamp']
    search_fields = ['module', 'message', 'error_code', 'correlation_id']
