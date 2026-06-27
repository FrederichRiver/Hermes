"""
Hermes Quant Trading System - Database Models

对应前端界面模块:
- Dashboard 统计卡片 → Account 账户模型
- 持仓表格 → Position 持仓模型
- 自选行情 → MarketQuote 行情模型
- 交易信号 → TradingSignal 信号模型
- 风控监控 → RiskMetric 风控指标模型
- 净值曲线 → NetValuePoint 净值数据点模型
"""
from django.db import models


class Account(models.Model):
    """交易账户模型 —— 对应 TraderAccount Agent"""
    name = models.CharField('账户名称', max_length=100)
    strategy_name = models.CharField('绑定策略', max_length=100)
    total_asset = models.DecimalField('总资产', max_digits=18, decimal_places=2, default=0)
    available_cash = models.DecimalField('可用资金', max_digits=18, decimal_places=2, default=0)
    holding_pnl = models.DecimalField('持仓盈亏', max_digits=18, decimal_places=2, default=0)
    capital_utilization = models.DecimalField('资金利用率(%)', max_digits=5, decimal_places=2, default=0)
    total_return_pct = models.DecimalField('总收益率(%)', max_digits=8, decimal_places=2, default=0)
    max_drawdown_pct = models.DecimalField('最大回撤(%)', max_digits=8, decimal_places=2, default=0)
    sharpe_ratio = models.DecimalField('夏普比率', max_digits=6, decimal_places=2, default=0)
    is_active = models.BooleanField('是否激活', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'accounts'
        verbose_name = '交易账户'
        verbose_name_plural = '交易账户'

    def __str__(self):
        return f"{self.name} ({self.strategy_name})"


class Position(models.Model):
    """持仓模型 —— 对应持仓明细表格"""
    SIDE_CHOICES = [
        ('long', '多头'),
        ('short', '空头'),
    ]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='positions', verbose_name='所属账户')
    symbol = models.CharField('代码', max_length=20)
    name = models.CharField('名称', max_length=100)
    side = models.CharField('方向', max_length=10, choices=SIDE_CHOICES, default='long')
    quantity = models.IntegerField('持仓数量', default=0)
    avg_price = models.DecimalField('均价', max_digits=12, decimal_places=2, default=0)
    current_price = models.DecimalField('现价', max_digits=12, decimal_places=2, default=0)
    market_value = models.DecimalField('市值', max_digits=18, decimal_places=2, default=0)
    weight_pct = models.DecimalField('权重(%)', max_digits=5, decimal_places=2, default=0)
    unrealized_pnl = models.DecimalField('浮动盈亏', max_digits=18, decimal_places=2, default=0)
    unrealized_pnl_pct = models.DecimalField('盈亏比例(%)', max_digits=8, decimal_places=2, default=0)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'positions'
        verbose_name = '持仓'
        verbose_name_plural = '持仓'
        unique_together = ['account', 'symbol']

    def __str__(self):
        return f"{self.symbol} {self.name} x{self.quantity}"


class MarketQuote(models.Model):
    """行情报价模型 —— 对应自选行情面板"""
    symbol = models.CharField('代码', max_length=20, unique=True)
    name = models.CharField('名称', max_length=100)
    price = models.DecimalField('最新价', max_digits=12, decimal_places=2, default=0)
    change = models.DecimalField('涨跌额', max_digits=12, decimal_places=2, default=0)
    change_pct = models.DecimalField('涨跌幅(%)', max_digits=6, decimal_places=2, default=0)
    volume = models.CharField('成交量', max_length=20, default='0')
    is_watching = models.BooleanField('是否自选', default=False)
    has_alert = models.BooleanField('是否有预警', default=False)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'market_quotes'
        verbose_name = '行情报价'
        verbose_name_plural = '行情报价'

    def __str__(self):
        return f"{self.symbol} {self.price}"


class TradingSignal(models.Model):
    """交易信号模型 —— 对应信号日志面板"""
    TYPE_CHOICES = [
        ('buy', '买入'),
        ('sell', '卖出'),
        ('warning', '预警'),
        ('info', '信息'),
        ('risk', '风控'),
    ]
    STATUS_CHOICES = [
        ('executed', '已执行'),
        ('pending', '待执行'),
        ('rejected', '已拒绝'),
        ('info', '信息'),
    ]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='signals', verbose_name='所属账户', null=True, blank=True)
    timestamp = models.DateTimeField('时间', auto_now_add=True)
    type = models.CharField('类型', max_length=10, choices=TYPE_CHOICES)
    symbol = models.CharField('代码', max_length=20, default='SYSTEM')
    message = models.TextField('消息内容')
    status = models.CharField('状态', max_length=10, choices=STATUS_CHOICES, default='info')
    strategy_source = models.CharField('策略来源', max_length=100, blank=True)

    class Meta:
        db_table = 'trading_signals'
        verbose_name = '交易信号'
        verbose_name_plural = '交易信号'
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.type}] {self.symbol} {self.status}"


class RiskMetric(models.Model):
    """风控指标模型 —— 对应风控监控面板"""
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='risk_metrics', verbose_name='所属账户')
    name = models.CharField('指标名称', max_length=50)
    current_value = models.DecimalField('当前值', max_digits=12, decimal_places=4, default=0)
    limit_value = models.DecimalField('限制值', max_digits=12, decimal_places=4, default=0)
    usage_pct = models.DecimalField('使用率(%)', max_digits=5, decimal_places=2, default=0)
    status = models.CharField('状态', max_length=10, choices=[('safe', '正常'), ('warning', '预警'), ('danger', '超限')], default='safe')
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'risk_metrics'
        verbose_name = '风控指标'
        verbose_name_plural = '风控指标'

    def __str__(self):
        return f"{self.name}: {self.current_value}/{self.limit_value}"


class NetValuePoint(models.Model):
    """净值曲线数据点 —— 对应净值图表"""
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='net_values', verbose_name='所属账户')
    time_label = models.CharField('时间标签', max_length=10)
    strategy_value = models.DecimalField('策略净值', max_digits=12, decimal_places=4, default=100)
    benchmark_value = models.DecimalField('基准净值', max_digits=12, decimal_places=4, default=100)
    recorded_at = models.DateTimeField('记录时间', auto_now_add=True)

    class Meta:
        db_table = 'net_value_points'
        verbose_name = '净值数据点'
        verbose_name_plural = '净值数据点'
        ordering = ['recorded_at']

    def __str__(self):
        return f"{self.time_label} 策略:{self.strategy_value} 基准:{self.benchmark_value}"


class SystemLog(models.Model):
    """系统日志模型 —— 对应日志模块"""
    LEVEL_CHOICES = [
        ('DEBUG', '调试'),
        ('INFO', '信息'),
        ('WARNING', '警告'),
        ('ERROR', '错误'),
        ('CRITICAL', '严重'),
    ]

    timestamp = models.DateTimeField('时间', auto_now_add=True)
    level = models.CharField('等级', max_length=10, choices=LEVEL_CHOICES, default='INFO')
    module = models.CharField('模块', max_length=100)
    error_code = models.CharField('错误码', max_length=50, blank=True)
    message = models.TextField('消息')
    correlation_id = models.CharField('关联ID', max_length=36, blank=True)
    context = models.JSONField('上下文', default=dict, blank=True)

    class Meta:
        db_table = 'system_logs'
        verbose_name = '系统日志'
        verbose_name_plural = '系统日志'
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.level}] {self.module}: {self.message[:50]}"


class StockInfo(models.Model):
    """股票基本信息模型 —— 对应数据Agent爬取的股票列表"""
    code = models.CharField('股票代码', max_length=20, unique=True)
    name = models.CharField('证券简称', max_length=100)
    issue_date = models.DateField('发行日期', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'stock_info'
        verbose_name = '股票信息'
        verbose_name_plural = '股票信息'

    def __str__(self):
        return f"{self.code} {self.name}"
