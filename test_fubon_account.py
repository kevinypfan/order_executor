"""
FubonAccount 測試模塊 (重構版)

使用新的測試基礎設施進行集成測試
"""
import logging
from test_base import IntegrationTestCase, TestConstants
from fubon_account import FubonAccount

# 設定測試環境的日誌級別
logging.basicConfig(level=logging.INFO)

class TestFubonAccount(IntegrationTestCase):
    """測試 FubonAccount 類 - 集成測試"""
    
    def create_account(self):
        """創建 FubonAccount 實例"""
        try:
            return FubonAccount()
        except Exception as e:
            self.skipTest(f"無法創建 FubonAccount: {e}")
    
    def validate_environment(self):
        """驗證測試環境"""
        import os
        required_vars = [
            'FUBON_NATIONAL_ID',
            'FUBON_ACCOUNT_PASS', 
            'FUBON_CERT_PATH'
        ]
        
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            self.skipTest(f"缺少環境變數: {missing_vars}")
    
    def test_account_initialization(self):
        """測試帳戶初始化"""
        self.assertIsNotNone(self.account)
        self.assertIsNotNone(self.account.sdk)
        self.assertIsNotNone(self.account.target_account)
    
    def test_get_total_balance(self):
        """測試獲取總資產餘額"""
        total_balance = self.account.get_total_balance()
        self.logger.info(f'總資產餘額: {total_balance}')
        self.assertIsInstance(total_balance, (int, float))
        self.assertGreaterEqual(total_balance, 0)
    
    def test_get_cash(self):
        """測試獲取可用資金"""
        cash = self.account.get_cash()
        self.logger.info(f'可用資金: {cash}')
        self.assertIsInstance(cash, (int, float))
        self.assertGreaterEqual(cash, 0)
    
    def test_get_settlement(self):
        """測試獲取未交割款項"""
        settlement = self.account.get_settlement()
        self.logger.info(f'未交割款項: {settlement}')
        self.assertIsInstance(settlement, (int, float))
    
    def test_get_position(self):
        """測試獲取持有部位"""
        from finlab.online.order_executor import Position
        position = self.account.get_position()
        self.logger.info(f'持有部位: \n{position}')
        self.assertIsInstance(position, Position)
    
    def test_get_orders(self):
        """測試獲取委託單"""
        orders = self.account.get_orders()
        self.logger.info(f'委託單數量: {len(orders)}')
        self.assertIsInstance(orders, dict)
    
    def test_get_stocks(self):
        """測試獲取股票報價"""
        test_stocks = self.test_constants.TEST_STOCKS['tw_stock'][:2]
        stocks = self.account.get_stocks(test_stocks)
        self.assertIsInstance(stocks, dict)
        
        for stock_id in test_stocks:
            if stock_id in stocks:
                self.assertEqual(stocks[stock_id].stock_id, stock_id)
                self.assert_stock_data_valid(stocks[stock_id])
    
    def test_create_and_cancel_order(self):
        """測試建立和取消委託單"""
        from finlab.online.enums import Action
        
        stock_id = '0056'
        quantity = 1
        price = 32.0
        
        # 建立委託單
        order_id = self.account.create_order(
            action=Action.BUY,
            stock_id=stock_id,
            quantity=quantity,
            price=price
        )
        
        if order_id:
            self.wait_for_api('medium')
            
            # 驗證委託單
            orders = self.account.get_orders()
            if order_id in orders:
                self.assert_order_matches(orders[order_id], {
                    'stock_id': stock_id,
                    'action': Action.BUY,
                    'quantity': quantity
                })
            
            # 取消委託單
            self.account.cancel_order(order_id)
            self.wait_for_api('medium')

    def test_update_odd_lot_order_price(self):
        """測試更新零股委託單價格"""
        from finlab.online.enums import Action
        
        stock_id = '0056'
        quantity = 100  # 100股
        original_price = 32.0
        new_price = 32.5
        
        order_id = self.account.create_order(
            action=Action.BUY,
            stock_id=stock_id,
            quantity=quantity,
            price=original_price,
            odd_lot=True
        )
        
        if order_id:
            self.wait_for_api('medium')
            self.account.update_order(order_id, price=new_price)
            self.wait_for_api('long')  # 零股更新需要更長時間
            self.account.cancel_order(order_id)

    def test_update_order_quantity(self):
        """測試更新委託單數量"""
        from finlab.online.enums import Action
        
        stock_id = '0056'
        original_quantity = 1
        new_quantity = 2
        price = 32.0

        order_id = self.account.create_order(
            action=Action.BUY,
            stock_id=stock_id,
            quantity=original_quantity,
            price=price
        )

        if order_id:
            self.wait_for_api('medium')
            self.account.update_order(order_id, quantity=new_quantity)
            self.wait_for_api('medium')
            self.account.cancel_order(order_id)

    def test_order_executor_workflow(self):
        """測試 OrderExecutor 工作流程"""
        from finlab.online.order_executor import OrderExecutor, Position
        
        position = self.data_factory.create_test_position({
            '00940': 1.0,
            '00878': 1.0
        })
        
        oe = OrderExecutor(position, self.account)
        self.check_order_executor_workflow(oe)

    def test_order_executor_odd_lot(self):
        """測試 OrderExecutor 零股工作流程"""
        from finlab.online.order_executor import OrderExecutor, Position
        
        position = self.data_factory.create_test_position({
            '0056': 0.1  # 100股 = 0.1張
        })
        
        oe = OrderExecutor(position, self.account)
        self.check_order_executor_workflow(oe)

    def test_mixed_order_workflow(self):
        """測試混合買賣訂單工作流程"""
        from finlab.online.order_executor import OrderExecutor, Position
        
        if self.account.support_day_trade_condition():
            position = Position({
                '00940': 1.0,   # 買入
                '00878': -1.0   # 賣出 (當沖)
            }, day_trading_short=True)
            
            oe = OrderExecutor(position, self.account)
            self.check_order_executor_workflow(oe)

    def test_price_update_workflow(self):
        """測試價格更新工作流程"""
        from finlab.online.order_executor import OrderExecutor, Position
        
        position = self.data_factory.create_test_position({'00878': 1.0})
        oe = OrderExecutor(position, self.account)
        
        # 創建訂單
        view_orders = oe.create_orders(view_only=True)
        self.wait_for_api('short')
        oe.create_orders()
        self.wait_for_api('medium')
        
        orders = oe.account.get_orders()
        if not orders:
            self.skipTest("沒有創建的訂單，跳過測試")
        
        # 更新價格 (提高5%)
        oe.update_order_price(extra_bid_pct=0.05)
        self.wait_for_api('long')
        
        # 清理
        oe.cancel_orders()


if __name__ == "__main__":
    unittest.main(verbosity=2)