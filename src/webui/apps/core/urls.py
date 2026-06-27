"""
Core App URL Routes
"""
from django.urls import path
from . import views

urlpatterns = [
    # Dashboard 统计卡片
    path('dashboard/stats/', views.DashboardStatsAPI.as_view(), name='dashboard-stats'),

    # 持仓
    path('positions/', views.PositionListAPI.as_view(), name='position-list'),

    # 行情
    path('quotes/', views.MarketQuoteListAPI.as_view(), name='quote-list'),

    # 交易信号
    path('signals/', views.TradingSignalListAPI.as_view(), name='signal-list'),

    # 风控指标
    path('risk/', views.RiskMetricListAPI.as_view(), name='risk-list'),

    # 净值曲线
    path('netvalue/', views.NetValueListAPI.as_view(), name='netvalue-list'),

    # 系统日志
    path('logs/', views.SystemLogListAPI.as_view(), name='log-list'),

    # 账户
    path('accounts/', views.AccountListAPI.as_view(), name='account-list'),
]