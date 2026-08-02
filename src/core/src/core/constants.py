"""
Constants - 系统常量定义
"""
from enum import Enum


class Market(Enum):
    """市场枚举"""
    CN = "CN"              # 中国A股
    HK = "HK"              # 港股
    US = "US"              # 美股
    JP = "JP"              # 日本
    UK = "UK"              # 英国
    

# 默认配置
DEFAULT_CONFIG = {
    'risk_limits': {
        'max_position_ratio': 0.8,      # 最大仓位比例
        'max_single_position_ratio': 0.3, # 最大单仓比例
        'max_drawdown': 0.2,             # 最大回撤
        'min_cash_ratio': 0.1,           # 最小现金比例
    },
    'commission_rate': 0.0003,           # 默认手续费率 (万3)
    'slippage': 0.001,                   # 默认滑点 (0.1%)
    'settlement_time': '15:30',          # 默认结算时间
}


# 事件优先级
EVENT_PRIORITY = {
    'CRITICAL': 1,
    'HIGH': 2,
    'NORMAL': 5,
    'LOW': 8,
    'BACKGROUND': 10,
}
