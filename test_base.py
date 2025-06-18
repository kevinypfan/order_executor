"""
測試基礎設施模組

提供通用的測試基類、工具方法和常數定義
"""
import time
import unittest
import logging
from typing import Dict, Any, Optional
from unittest.mock import Mock, patch
from abc import ABC, abstractmethod

from finlab.online.enums import OrderCondition, OrderStatus, Action
from finlab.online.order_executor import OrderExecutor, Position
from finlab.online.base_account import Account, Stock, Order


# 測試常數
class TestConstants:
    """測試常數定義"""
    
    # 測試股票代碼
    TEST_STOCKS = {
        'tw_stock': ['2330', '2317', '1101'],  # 台股
        'tw_etf': ['0050', '0056', '00878'],   # ETF
        'tw_small': ['3661', '6016', '00940']  # 小型股/測試用
    }
    
    # 測試數量
    TEST_QUANTITIES = {
        'regular': [1, 2, 5],       # 整張
        'odd_lot': [0.1, 0.5, 1.1]  # 零股
    }
    
    # 測試價格
    TEST_PRICES = {
        'low': [10.0, 25.5, 32.0],
        'medium': [50.0, 100.0, 150.0],
        'high': [200.0, 500.0, 1000.0]
    }
    
    # API 響應延遲
    API_DELAYS = {
        'short': 2,   # 短延遲
        'medium': 5,  # 中等延遲  
        'long': 10    # 長延遲
    }


class TestDataFactory:
    """測試數據工廠"""
    
    @staticmethod
    def create_mock_stock(stock_id: str = "2330", **kwargs) -> Stock:
        """創建模擬股票對象"""
        defaults = {
            'stock_id': stock_id,
            'open': 100.0,
            'high': 105.0,
            'low': 95.0,
            'close': 102.0,
            'bid_price': 101.5,
            'ask_price': 102.5,
            'bid_volume': 1000,
            'ask_volume': 1500
        }
        defaults.update(kwargs)
        return Stock(**defaults)
    
    @staticmethod
    def create_mock_order(order_id: str = "test_001", **kwargs) -> Order:
        """創建模擬訂單對象"""
        defaults = {
            'order_id': order_id,
            'stock_id': '2330',
            'action': Action.BUY,
            'price': 100.0,
            'quantity': 1.0,
            'filled_quantity': 0.0,
            'status': OrderStatus.NEW,
            'order_condition': OrderCondition.CASH,
            'time': None,
            'org_order': None
        }
        defaults.update(kwargs)
        
        if defaults['time'] is None:
            import datetime
            defaults['time'] = datetime.datetime.now()
            
        return Order(**defaults)
    
    @staticmethod
    def create_test_position(stocks: Optional[Dict[str, float]] = None, **kwargs) -> Position:
        """創建測試持倉"""
        if stocks is None:
            stocks = {'2330': 1.0, '2317': 2.0}
        return Position(stocks, **kwargs)


class MockAPIResponse:
    """模擬 API 響應"""
    
    def __init__(self, is_success: bool = True, data: Any = None, message: str = ""):
        self.is_success = is_success
        self.data = data
        self.message = message


class TestAccountBase(unittest.TestCase, ABC):
    """
    帳戶測試基類
    
    提供統一的測試基礎設施和通用方法
    """
    
    def setUp(self):
        """測試前設置"""
        self.account = self.create_account()
        self.test_constants = TestConstants()
        self.data_factory = TestDataFactory()
        
        # 設置日誌
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def tearDown(self):
        """測試後清理"""
        try:
            if hasattr(self, 'account') and self.account:
                self.cleanup_orders()
        except Exception as e:
            self.logger.warning(f"清理測試環境時發生錯誤: {e}")
    
    @abstractmethod
    def create_account(self) -> Account:
        """創建帳戶實例 - 子類必須實現"""
        pass
    
    def cleanup_orders(self):
        """清理所有未完成的訂單"""
        try:
            oe = OrderExecutor(Position({}), self.account)
            oe.cancel_orders()
        except Exception as e:
            self.logger.warning(f"取消訂單時發生錯誤: {e}")
    
    def wait_for_api(self, delay_type: str = 'short'):
        """API 調用間的等待"""
        delay = self.test_constants.API_DELAYS.get(delay_type, 2)
        time.sleep(delay)
    
    def assert_order_matches(self, actual_order: Order, expected_data: Dict[str, Any]):
        """驗證訂單是否符合預期"""
        for field, expected_value in expected_data.items():
            actual_value = getattr(actual_order, field)
            if field in ['quantity', 'price', 'filled_quantity']:
                self.assertAlmostEqual(float(actual_value), float(expected_value), places=3)
            else:
                self.assertEqual(actual_value, expected_value)
    
    def assert_stock_data_valid(self, stock: Stock):
        """驗證股票數據的有效性"""
        self.assertIsNotNone(stock.stock_id)
        self.assertGreaterEqual(stock.close, 0)
        self.assertGreaterEqual(stock.bid_price, 0)
        self.assertGreaterEqual(stock.ask_price, 0)
        self.assertGreaterEqual(stock.bid_volume, 0)
        self.assertGreaterEqual(stock.ask_volume, 0)
    
    def check_order_executor_workflow(self, oe: OrderExecutor, **create_order_kwargs):
        """檢查訂單執行器的完整工作流程"""
        # 1. 預覽訂單
        view_orders = oe.create_orders(view_only=True)
        self.assertIsInstance(view_orders, list)
        
        # 2. 清理現有訂單
        oe.cancel_orders()
        self.wait_for_api('short')
        
        # 3. 創建新訂單
        oe.create_orders(**create_order_kwargs)
        self.wait_for_api('medium')
        
        # 4. 驗證訂單創建
        orders = oe.account.get_orders()
        if not orders:
            self.skipTest("沒有創建的訂單，跳過測試")
        
        # 5. 驗證訂單內容
        self._validate_created_orders(orders, view_orders)
        
        # 6. 清理
        oe.cancel_orders()
    
    def _validate_created_orders(self, actual_orders: Dict[str, Order], expected_orders: list):
        """驗證創建的訂單是否符合預期"""
        stock_orders = {o['stock_id']: o for o in expected_orders}
        stock_quantity = {o.stock_id: 0 for oid, o in actual_orders.items()}
        
        for oid, order in actual_orders.items():
            if (order.status in [OrderStatus.CANCEL, OrderStatus.FILLED] or 
                order.stock_id not in stock_orders):
                continue
            
            # 檢查買賣方向
            expected_action = Action.BUY if stock_orders[order.stock_id]['quantity'] > 0 else Action.SELL
            self.assertEqual(order.action, expected_action)
            
            # 檢查訂單條件
            self.assertEqual(order.order_condition, stock_orders[order.stock_id]['order_condition'])
            
            # 累計數量
            stock_quantity[order.stock_id] += order.quantity
        
        # 驗證總數量
        for stock_id, actual_qty in stock_quantity.items():
            if actual_qty != 0:
                expected_qty = abs(stock_orders[stock_id]['quantity'])
                self.assertAlmostEqual(float(actual_qty), float(expected_qty), places=3)


class MockTestCase(TestAccountBase):
    """
    使用 Mock 的測試基類
    
    適用於單元測試，不依賴真實 API
    """
    
    def setUp(self):
        super().setUp()
        self.setup_mocks()
    
    def setup_mocks(self):
        """設置 Mock 對象"""
        # 子類可以覆寫此方法來設置特定的 Mock
        pass
    
    def create_mock_api_response(self, success: bool = True, data: Any = None) -> MockAPIResponse:
        """創建模擬 API 響應"""
        return MockAPIResponse(is_success=success, data=data)


class IntegrationTestCase(TestAccountBase):
    """
    集成測試基類
    
    使用真實 API 進行測試
    """
    
    def setUp(self):
        super().setUp()
        self.validate_environment()
    
    def validate_environment(self):
        """驗證測試環境"""
        # 檢查必要的環境變數
        # 子類可以覆寫此方法添加特定檢查
        pass
    
    def wait_for_api(self, delay_type: str = 'medium'):
        """集成測試需要更長的等待時間"""
        super().wait_for_api(delay_type)


class PerformanceTestCase(TestAccountBase):
    """
    性能測試基類
    """
    
    def setUp(self):
        super().setUp()
        self.performance_metrics = {}
    
    def measure_time(self, operation_name: str):
        """測量操作時間的上下文管理器"""
        import time
        from contextlib import contextmanager
        
        @contextmanager
        def timer():
            start_time = time.time()
            yield
            end_time = time.time()
            self.performance_metrics[operation_name] = end_time - start_time
            
        return timer()
    
    def assert_performance_within_limit(self, operation_name: str, max_seconds: float):
        """驗證操作時間在限制範圍內"""
        actual_time = self.performance_metrics.get(operation_name)
        self.assertIsNotNone(actual_time, f"沒有記錄到 {operation_name} 的性能數據")
        self.assertLessEqual(actual_time, max_seconds, 
                           f"{operation_name} 花費 {actual_time:.2f}s，超過限制 {max_seconds}s")