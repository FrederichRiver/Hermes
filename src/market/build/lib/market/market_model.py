# MarketModel 市场模型基础实现
class MarketModel:
    def subscribe_market_data(self, symbols, callback):
        """订阅行情推送"""
        pass

    def get_latest_price(self, symbol):
        """获取最新价格"""
        pass

    def match_orders(self, order_list):
        """撮合订单，返回成交结果"""
        pass

    def replay_historical_data(self, start_time, end_time, callback):
        """历史行情回放"""
        pass
