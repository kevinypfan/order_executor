"""
FubonAccount 全面測試套件

包含單元測試、集成測試和性能測試
"""
import unittest
import datetime
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

from test_base import (
    MockTestCase, IntegrationTestCase, PerformanceTestCase,
    TestConstants, TestDataFactory
)
from test_fubon_mocks import FubonMockFactory, FubonTestScenarios
from fubon_account import FubonAccount, STOCK_LOT_SIZE
from finlab.online.enums import OrderCondition, OrderStatus, Action
from finlab.online.order_executor import OrderExecutor, Position
from finlab.online.base_account import Stock, Order
from fubon_neo.constant import OrderType, BSAction, MarketType


class TestFubonAccountUnit(MockTestCase):
    """FubonAccount 單元測試"""
    
    def create_account(self):
        """創建模擬的 FubonAccount"""
        with patch('fubon_account.FubonSDK') as mock_sdk_class:
            mock_sdk = FubonMockFactory.create_mock_sdk()
            mock_sdk_class.return_value = mock_sdk
            
            with patch.dict('os.environ', {
                'FUBON_NATIONAL_ID': 'A123456789',
                'FUBON_ACCOUNT_PASS': 'password',
                'FUBON_CERT_PATH': '/path/to/cert'
            }):
                account = FubonAccount()
                account.sdk = mock_sdk  # 確保使用模擬的 SDK
                return account
    
    def test_extract_price_data_from_dict(self):
        """測試從字典提取價格數據"""
        quote_dict = FubonMockFactory.create_mock_quote_data(
            symbol="2330",
            close_price=100.0,
            open_price=98.0,
            high_price=102.0,
            low_price=96.0
        )
        
        stock_id, price_data = self.account._extract_price_data(quote_dict, "2330")
        
        self.assertEqual(stock_id, "2330")
        self.assertEqual(price_data['open'], 98.0)
        self.assertEqual(price_data['high'], 102.0)
        self.assertEqual(price_data['low'], 96.0)
        self.assertEqual(price_data['close'], 100.0)
    
    def test_extract_price_data_from_object(self):
        """測試從對象提取價格數據"""
        quote_obj = FubonMockFactory.create_mock_quote_object(
            symbol="2317",
            close_price=50.0
        )
        
        stock_id, price_data = self.account._extract_price_data(quote_obj, "2317")
        
        self.assertEqual(stock_id, "2317")
        self.assertEqual(price_data['close'], 50.0)
        self.assertIn('open', price_data)
        self.assertIn('high', price_data)
        self.assertIn('low', price_data)
    
    def test_extract_price_data_fallback_to_original_id(self):
        """測試當提取失敗時回退到原始ID"""
        empty_quote = {}
        
        stock_id, price_data = self.account._extract_price_data(empty_quote, "1101")
        
        self.assertEqual(stock_id, "1101")
        self.assertEqual(price_data['close'], 0.0)
    
    def test_extract_bid_ask_data_from_dict(self):
        """測試從字典提取委買委賣數據"""
        quote_dict = FubonMockFactory.create_mock_quote_data(
            bids=[
                {'price': 99.5, 'size': 1000},
                {'price': 99.0, 'size': 2000}
            ],
            asks=[
                {'price': 100.5, 'size': 1500},
                {'price': 101.0, 'size': 2500}
            ]
        )
        
        bid_ask_data = self.account._extract_bid_ask_data(quote_dict)
        
        self.assertEqual(bid_ask_data['bid_price'], 99.5)
        self.assertEqual(bid_ask_data['bid_volume'], 1000)
        self.assertEqual(bid_ask_data['ask_price'], 100.5)
        self.assertEqual(bid_ask_data['ask_volume'], 1500)
    
    def test_extract_bid_ask_data_empty(self):
        """測試空的委買委賣數據"""
        quote_dict = {'bids': [], 'asks': []}
        
        bid_ask_data = self.account._extract_bid_ask_data(quote_dict)
        
        self.assertEqual(bid_ask_data['bid_price'], 0)
        self.assertEqual(bid_ask_data['bid_volume'], 0)
        self.assertEqual(bid_ask_data['ask_price'], 0)
        self.assertEqual(bid_ask_data['ask_volume'], 0)
    
    def test_extract_first_bid_ask_dict(self):
        """測試提取第一檔委買委賣 - 字典格式"""
        bid_item = {'price': 99.5, 'size': 1000}
        
        result = self.account._extract_first_bid_ask(bid_item)
        
        self.assertEqual(result['price'], 99.5)
        self.assertEqual(result['volume'], 1000)
    
    def test_extract_first_bid_ask_object(self):
        """測試提取第一檔委買委賣 - 對象格式"""
        bid_item = Mock()
        bid_item.price = 99.5
        bid_item.size = 1000
        
        result = self.account._extract_first_bid_ask(bid_item)
        
        self.assertEqual(result['price'], 99.5)
        self.assertEqual(result['volume'], 1000)
    
    def test_extract_first_bid_ask_none(self):
        """測試空的委買委賣項目"""
        result = self.account._extract_first_bid_ask(None)
        
        self.assertEqual(result['price'], 0)
        self.assertEqual(result['volume'], 0)
    
    def test_create_empty_stock(self):
        """測試創建空股票數據"""
        stock = self.account._create_empty_stock("2330")
        
        self.assertEqual(stock.stock_id, "2330")
        self.assertEqual(stock.open, 0)
        self.assertEqual(stock.high, 0)
        self.assertEqual(stock.low, 0)
        self.assertEqual(stock.close, 0)
        self.assertEqual(stock.bid_price, 0)
        self.assertEqual(stock.ask_price, 0)
        self.assertEqual(stock.bid_volume, 0)
        self.assertEqual(stock.ask_volume, 0)
    
    def test_determine_market_type_regular_hours(self):
        """測試正常交易時間的市場類型"""
        with patch('fubon_account.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(2024, 1, 15, 10, 30)
            mock_datetime.time = datetime.time
            
            # 測試整股
            market_type = self.account._determine_market_type(odd_lot=False)
            self.assertEqual(market_type, MarketType.Common)
            
            # 測試零股
            market_type = self.account._determine_market_type(odd_lot=True)
            self.assertEqual(market_type, MarketType.IntradayOdd)
    
    def test_determine_market_type_odd_lot_session(self):
        """測試零股交易時間的市場類型"""
        with patch('fubon_account.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(2024, 1, 15, 13, 50)
            mock_datetime.time = datetime.time
            
            # 測試零股
            market_type = self.account._determine_market_type(odd_lot=True)
            self.assertEqual(market_type, MarketType.Odd)
    
    def test_determine_market_type_fixing_session(self):
        """測試定盤交易時間的市場類型"""
        with patch('fubon_account.datetime') as mock_datetime:
            mock_datetime.datetime.now.return_value = datetime.datetime(2024, 1, 15, 14, 15)
            mock_datetime.time = datetime.time
            
            # 測試整股
            market_type = self.account._determine_market_type(odd_lot=False)
            self.assertEqual(market_type, MarketType.Fixing)
    
    def test_parse_order_status_mapping(self):
        """測試訂單狀態映射"""
        test_cases = [
            (10, OrderStatus.NEW),
            (30, OrderStatus.CANCEL),
            (50, OrderStatus.FILLED),
            (90, OrderStatus.CANCEL),
            (99, OrderStatus.NEW)  # 未知狀態預設為 NEW
        ]
        
        for status_code, expected_status in test_cases:
            with self.subTest(status_code=status_code):
                mock_order = Mock()
                mock_order.status = status_code
                mock_order.filled_qty = 0
                mock_order.after_qty = 1000
                
                status = self.account._parse_order_status(mock_order)
                self.assertEqual(status, expected_status)
    
    def test_parse_order_status_partially_filled(self):
        """測試部分成交狀態"""
        mock_order = Mock()
        mock_order.status = 10  # NEW
        mock_order.filled_qty = 500
        mock_order.after_qty = 1000
        
        status = self.account._parse_order_status(mock_order)
        self.assertEqual(status, OrderStatus.PARTIALLY_FILLED)
    
    def test_parse_quantities(self):
        """測試數量解析"""
        mock_order = Mock()
        mock_order.after_qty = 2000
        mock_order.filled_qty = 500
        
        quantity, filled_quantity = self.account._parse_quantities(mock_order)
        
        self.assertAlmostEqual(quantity, 2.0, places=3)  # 2000 / 1000
        self.assertAlmostEqual(filled_quantity, 0.5, places=3)  # 500 / 1000
    
    def test_parse_date_with_slash(self):
        """測試解析斜線格式日期"""
        # 測試 YYYY/MM/DD 格式
        year, month, day = self.account._parse_date("2024/01/15")
        self.assertEqual((year, month, day), (2024, 1, 15))
        
        # 測試 MM/DD 格式
        year, month, day = self.account._parse_date("01/15")
        self.assertEqual(month, 1)
        self.assertEqual(day, 15)
        self.assertEqual(year, datetime.datetime.now().year)
    
    def test_parse_date_yyyymmdd(self):
        """測試解析 YYYYMMDD 格式日期"""
        year, month, day = self.account._parse_date("20240115")
        self.assertEqual((year, month, day), (2024, 1, 15))
    
    def test_parse_time_with_microseconds(self):
        """測試解析帶毫秒的時間"""
        hour, minute, second, microsecond = self.account._parse_time("09:30:15.123")
        
        self.assertEqual(hour, 9)
        self.assertEqual(minute, 30)
        self.assertEqual(second, 15)
        self.assertEqual(microsecond, 123000)  # 123 * 1000
    
    def test_parse_time_without_microseconds(self):
        """測試解析不帶毫秒的時間"""
        hour, minute, second, microsecond = self.account._parse_time("14:25:30")
        
        self.assertEqual(hour, 14)
        self.assertEqual(minute, 25)
        self.assertEqual(second, 30)
        self.assertEqual(microsecond, 0)
    
    @patch('fubon_account.logging')
    def test_handle_exceptions_decorator(self, mock_logging):
        """測試錯誤處理裝飾器"""
        # 測試成功情況
        cash = self.account.get_cash()
        self.assertIsInstance(cash, (int, float))
        
        # 測試異常情況
        self.account.sdk.accounting.bank_remain.side_effect = Exception("API 錯誤")
        cash = self.account.get_cash()
        self.assertEqual(cash, 0)  # 預設返回值
        
        # 驗證日誌記錄
        mock_logging.warning.assert_called()


class TestFubonAccountIntegration(IntegrationTestCase):
    """FubonAccount 集成測試 - 使用真實 API"""
    
    def create_account(self):
        """創建真實的 FubonAccount"""
        try:
            return FubonAccount()
        except Exception as e:
            self.skipTest(f"無法創建 FubonAccount: {e}")
    
    def validate_environment(self):
        """驗證環境變數"""
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
        balance = self.account.get_total_balance()
        self.assertIsInstance(balance, (int, float))
        self.assertGreaterEqual(balance, 0)
    
    def test_get_cash(self):
        """測試獲取可用資金"""
        cash = self.account.get_cash()
        self.assertIsInstance(cash, (int, float))
        self.assertGreaterEqual(cash, 0)
    
    def test_get_settlement(self):
        """測試獲取未交割款項"""
        settlement = self.account.get_settlement()
        self.assertIsInstance(settlement, (int, float))
    
    def test_get_position(self):
        """測試獲取持有部位"""
        position = self.account.get_position()
        self.assertIsInstance(position, Position)
    
    def test_get_orders(self):
        """測試獲取委託單"""
        orders = self.account.get_orders()
        self.assertIsInstance(orders, dict)
    
    def test_get_stocks(self):
        """測試獲取股票報價"""
        test_stocks = self.test_constants.TEST_STOCKS['tw_stock'][:2]
        stocks = self.account.get_stocks(test_stocks)
        
        self.assertIsInstance(stocks, dict)
        for stock_id in test_stocks:
            if stock_id in stocks:
                self.assert_stock_data_valid(stocks[stock_id])
    
    def test_create_and_cancel_order(self):
        """測試建立和取消委託單"""
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
                order = orders[order_id]
                self.assert_order_matches(order, {
                    'stock_id': stock_id,
                    'action': Action.BUY,
                    'quantity': quantity
                })
            
            # 取消委託單
            self.account.cancel_order(order_id)
            self.wait_for_api('medium')
    
    def test_order_executor_workflow(self):
        """測試 OrderExecutor 工作流程"""
        position = self.data_factory.create_test_position({
            '00940': 1.0,
            '00878': 1.0
        })
        
        oe = OrderExecutor(position, self.account)
        self.check_order_executor_workflow(oe)
    
    def test_odd_lot_order_workflow(self):
        """測試零股訂單工作流程"""
        position = self.data_factory.create_test_position({
            '0056': 0.1  # 100股 = 0.1張
        })
        
        oe = OrderExecutor(position, self.account)
        
        # 創建零股訂單
        orders = oe.generate_orders()
        oe.execute_orders(orders, view_only=False)
        
        self.wait_for_api('medium')
        
        # 驗證訂單創建
        created_orders = self.account.get_orders()
        self.assertGreater(len(created_orders), 0)
        
        # 清理
        oe.cancel_orders()


class TestFubonAccountPerformance(PerformanceTestCase):
    """FubonAccount 性能測試"""
    
    def create_account(self):
        """創建用於性能測試的帳戶"""
        try:
            return FubonAccount()
        except Exception as e:
            self.skipTest(f"無法創建 FubonAccount: {e}")
    
    def test_get_stocks_performance(self):
        """測試批量獲取股票報價的性能"""
        stock_list = self.test_constants.TEST_STOCKS['tw_stock'] * 3  # 9 只股票
        
        with self.measure_time('get_stocks_batch'):
            stocks = self.account.get_stocks(stock_list)
        
        # 驗證結果
        self.assertIsInstance(stocks, dict)
        
        # 驗證性能 (應在10秒內完成)
        self.assert_performance_within_limit('get_stocks_batch', 10.0)
    
    def test_order_execution_performance(self):
        """測試訂單執行性能"""
        position = self.data_factory.create_test_position({
            '00940': 1.0,
            '00878': 1.0,
            '0056': 1.0
        })
        
        oe = OrderExecutor(position, self.account)
        
        with self.measure_time('order_execution'):
            try:
                oe.create_orders(view_only=True)  # 只測試生成，不實際下單
            except Exception as e:
                self.logger.warning(f"訂單執行測試失敗: {e}")
        
        # 驗證性能 (應在5秒內完成)
        if 'order_execution' in self.performance_metrics:
            self.assert_performance_within_limit('order_execution', 5.0)
    
    def test_concurrent_api_calls(self):
        """測試並發 API 調用"""
        import threading
        import time
        
        results = {}
        
        def api_call(call_name, method):
            start_time = time.time()
            try:
                method()
                results[call_name] = time.time() - start_time
            except Exception as e:
                results[call_name] = f"Error: {e}"
        
        # 準備並發調用
        threads = [
            threading.Thread(target=api_call, args=('get_cash', self.account.get_cash)),
            threading.Thread(target=api_call, args=('get_orders', self.account.get_orders)),
            threading.Thread(target=api_call, args=('get_position', self.account.get_position))
        ]
        
        # 啟動所有線程
        start_time = time.time()
        for thread in threads:
            thread.start()
        
        # 等待所有線程完成
        for thread in threads:
            thread.join()
        
        total_time = time.time() - start_time
        
        # 驗證結果
        self.assertLessEqual(total_time, 15.0, "並發 API 調用總時間應在15秒內")
        
        # 驗證所有調用都成功
        for call_name, result in results.items():
            self.assertIsInstance(result, (int, float), f"{call_name} 調用失敗: {result}")


class TestFubonAccountErrorHandling(MockTestCase):
    """FubonAccount 錯誤處理測試"""
    
    def create_account(self):
        """創建帶有錯誤模擬的帳戶"""
        with patch('fubon_account.FubonSDK') as mock_sdk_class:
            mock_sdk = FubonMockFactory.create_mock_sdk()
            mock_sdk_class.return_value = mock_sdk
            
            with patch.dict('os.environ', {
                'FUBON_NATIONAL_ID': 'A123456789',
                'FUBON_ACCOUNT_PASS': 'password',
                'FUBON_CERT_PATH': '/path/to/cert'
            }):
                account = FubonAccount()
                account.sdk = mock_sdk
                return account
    
    def test_api_failure_handling(self):
        """測試 API 失敗處理"""
        # 模擬 API 調用失敗
        self.account.sdk.accounting.bank_remain.return_value = FubonTestScenarios.error_scenarios()['api_failure']
        
        cash = self.account.get_cash()
        self.assertEqual(cash, 0)  # 應返回預設值
    
    def test_network_error_handling(self):
        """測試網絡錯誤處理"""
        # 模擬網絡錯誤
        self.account.sdk.stock.get_order_results.side_effect = FubonTestScenarios.error_scenarios()['network_error']
        
        orders = self.account.get_orders()
        self.assertEqual(orders, {})  # 應返回空字典
    
    def test_invalid_data_handling(self):
        """測試無效數據處理"""
        # 模擬無效響應
        self.account.sdk.accounting.unrealized_gains_and_loses.return_value = None
        
        position = self.account.get_position()
        self.assertIsInstance(position, Position)
        self.assertEqual(len(position.position), 0)
    
    def test_empty_response_handling(self):
        """測試空響應處理"""
        # 模擬空響應
        empty_response = FubonTestScenarios.error_scenarios()['empty_response']
        self.account.sdk.stock.get_order_results.return_value = empty_response
        
        orders = self.account.get_orders()
        self.assertEqual(orders, {})


if __name__ == "__main__":
    # 創建測試套件
    unittest.main(verbosity=2)