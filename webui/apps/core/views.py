"""
Django REST Framework Views
为前端 Dashboard 各模块提供 REST API 接口
"""
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum
from .models import Account, Position, MarketQuote, TradingSignal, RiskMetric, NetValuePoint, SystemLog
from .serializers import (
    AccountSerializer, PositionSerializer, MarketQuoteSerializer,
    TradingSignalSerializer, RiskMetricSerializer, NetValuePointSerializer,
    SystemLogSerializer,
)

from django.shortcuts import render
from django.views import View


class DashboardStatsAPI(APIView):
    """
    GET /api/v1/dashboard/stats/
    返回 Dashboard 顶部 4 张统计卡片数据
    """
    def get(self, request):
        # 获取主账户数据
        account = Account.objects.filter(is_active=True).first()
        if not account:
            return Response({
                'total_asset': {'value': '¥ 0.00', 'change': '+0.00%', 'type': 'neutral'},
                'available_cash': {'value': '¥ 0.00', 'change': '-0.00%', 'type': 'neutral'},
                'holding_pnl': {'value': '¥ +0.00', 'change': '+0.00%', 'type': 'neutral'},
                'capital_utilization': {'value': '0.0%', 'change': '0.0%', 'type': 'neutral'},
            })

        # 计算今日变化（简化：从账户字段直接读取）
        total_asset_change = float(account.total_return_pct)
        holding_pnl_change = float(account.holding_pnl) / float(account.total_asset) * 100 if account.total_asset else 0

        stats = {
            'total_asset': {
                'value': f"¥ {float(account.total_asset):,.2f}",
                'change': f"{total_asset_change:+.2f}%",
                'change_type': 'up' if total_asset_change >= 0 else 'down',
                'subtitle': '较昨日',
            },
            'available_cash': {
                'value': f"¥ {float(account.available_cash):,.2f}",
                'change': f"{float(account.available_cash) / float(account.total_asset) * 100:.2f}%",
                'change_type': 'neutral',
                'subtitle': '资金占比',
            },
            'holding_pnl': {
                'value': f"¥ {float(account.holding_pnl):+,.2f}",
                'change': f"{holding_pnl_change:+.2f}%",
                'change_type': 'up' if account.holding_pnl >= 0 else 'down',
                'subtitle': '累计浮动',
            },
            'capital_utilization': {
                'value': f"{float(account.capital_utilization):.1f}%",
                'change': f"{float(account.capital_utilization) - 65:.1f}%",
                'change_type': 'neutral',
                'subtitle': '目标≤80%',
            },
        }
        return Response(stats)


class PositionListAPI(generics.ListAPIView):
    """
    GET /api/v1/positions/
    返回当前持仓列表
    """
    # order by market value descending by default
    queryset = Position.objects.all().select_related('account').order_by('-market_value')
    serializer_class = PositionSerializer
    
    class StandardResultsSetPagination(PageNumberPagination):
        page_size = 20
        page_size_query_param = 'page_size'
        max_page_size = 100

    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = super().get_queryset()
        account_id = self.request.query_params.get('account')
        if account_id:
            qs = qs.filter(account_id=account_id)
        return qs


class MarketQuoteListAPI(generics.ListAPIView):
    """
    GET /api/v1/quotes/
    返回自选行情列表
    """
    queryset = MarketQuote.objects.filter(is_watching=True)
    serializer_class = MarketQuoteSerializer


class TradingSignalListAPI(generics.ListAPIView):
    """
    GET /api/v1/signals/
    返回最近交易信号和日志
    """
    queryset = TradingSignal.objects.all()[:20]
    serializer_class = TradingSignalSerializer

    def get_queryset(self):
        limit = int(self.request.query_params.get('limit', 20))
        return TradingSignal.objects.all().select_related('account')[:limit]


class RiskMetricListAPI(generics.ListAPIView):
    """
    GET /api/v1/risk/
    返回风控指标监控数据
    """
    queryset = RiskMetric.objects.all()
    serializer_class = RiskMetricSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        account_id = self.request.query_params.get('account')
        if account_id:
            qs = qs.filter(account_id=account_id)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # 附加综合评分
        metrics = self.get_queryset()
        total_score = 100
        for m in metrics:
            if m.status == 'warning':
                total_score -= 5
            elif m.status == 'danger':
                total_score -= 20
        response.data = {
            'metrics': response.data,
            'overall_score': max(0, total_score),
        }
        return response


class NetValueListAPI(generics.ListAPIView):
    """
    GET /api/v1/netvalue/
    返回净值曲线数据点
    """
    queryset = NetValuePoint.objects.all()
    serializer_class = NetValuePointSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        account_id = self.request.query_params.get('account')
        if account_id:
            qs = qs.filter(account_id=account_id)
        return qs[:50]


class SystemLogListAPI(generics.ListAPIView):
    """
    GET /api/v1/logs/
    返回系统日志
    """
    queryset = SystemLog.objects.all()[:50]
    serializer_class = SystemLogSerializer

    def get_queryset(self):
        limit = int(self.request.query_params.get('limit', 50))
        level = self.request.query_params.get('level')
        module = self.request.query_params.get('module')
        qs = SystemLog.objects.all()
        if level:
            qs = qs.filter(level=level.upper())
        if module:
            qs = qs.filter(module__icontains=module)
        return qs[:limit]


class AccountListAPI(generics.ListAPIView):
    """
    GET /api/v1/accounts/
    返回账户列表
    """
    queryset = Account.objects.filter(is_active=True)
    serializer_class = AccountSerializer


class DashboardView(View):
    """Render the index dashboard with server-side stat cards"""
    template_name = 'index.html'

    def get(self, request, *args, **kwargs):
        account = Account.objects.filter(is_active=True).first()
        if not account:
            stats = None
        else:
            total_asset_change = float(account.total_return_pct)
            holding_pnl_change = float(account.holding_pnl) / float(account.total_asset) * 100 if account.total_asset else 0
            stats = {
                'total_asset': {
                    'title': '总资产',
                    'value': f"¥ {float(account.total_asset):,.2f}",
                    'change': f"{total_asset_change:+.2f}%",
                    'change_type': 'up' if total_asset_change >= 0 else 'down',
                    'subtitle': '较昨日',
                    'icon_html': '',
                },
                'available_cash': {
                    'title': '可用资金',
                    'value': f"¥ {float(account.available_cash):,.2f}",
                    'change': f"{float(account.available_cash) / float(account.total_asset) * 100:.2f}%",
                    'change_type': 'neutral',
                    'subtitle': '资金占比',
                    'icon_html': '',
                },
                'holding_pnl': {
                    'title': '持仓盈亏',
                    'value': f"¥ {float(account.holding_pnl):+,.2f}",
                    'change': f"{holding_pnl_change:+.2f}%",
                    'change_type': 'up' if account.holding_pnl >= 0 else 'down',
                    'subtitle': '累计浮动',
                    'icon_html': '',
                },
                'capital_utilization': {
                    'title': '资金利用率',
                    'value': f"{float(account.capital_utilization):.1f}%",
                    'change': f"{float(account.capital_utilization) - 65:.1f}%",
                    'change_type': 'neutral',
                    'subtitle': '目标≤80%',
                    'icon_html': '',
                },
            }

        return render(request, self.template_name, {'stats': stats})
