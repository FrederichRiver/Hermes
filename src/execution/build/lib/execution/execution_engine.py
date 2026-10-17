# ExecutionEngine 策略执行引擎基础实现
class ExecutionEngine:
    def __init__(self):
        self.order_queue = []

    def receive_signal(self, signal, trader_id):
        """接收Trader发来的信号，加入订单队列"""
        self.order_queue.append((trader_id, signal))

    def process_orders(self, market_model):
        """批量处理订单队列，调用MarketModel撮合"""
        if not self.order_queue:
            return

        order_list = [order for trader_id, order in self.order_queue]
        
        # 调用MarketModel.match_orders进行撮合
        match_results = market_model.match_orders(order_list)
        
        # 将成交结果反馈给对应的Trader
        # 简单对应示例
        for i, (trader_id, _) in enumerate(self.order_queue):
            if match_results and i < len(match_results):
                self.send_order_feedback(trader_id, match_results[i])
                
        self.order_queue.clear()

    def send_order_feedback(self, trader_id, result):
        """将成交结果反馈给对应Trader"""
        pass
