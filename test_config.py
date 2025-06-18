"""
測試配置文件

集中管理測試相關的配置和設定
"""
import os
import logging
from typing import Dict, Any


class TestConfig:
    """測試配置類"""
    
    # 日誌設定
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 測試超時設定 (秒)
    API_TIMEOUT = {
        'short': 2,
        'medium': 5,
        'long': 10,
        'extra_long': 30
    }
    
    # 測試股票配置
    TEST_STOCKS = {
        'tw_large_cap': ['2330', '2317', '2454'],    # 大型股
        'tw_etf': ['0050', '0056', '00878', '00940'], # ETF
        'tw_test': ['3661', '6016'],                  # 測試用小型股
    }
    
    # 測試數量配置
    TEST_QUANTITIES = {
        'regular': [1, 2, 5],           # 整張
        'odd_lot': [0.1, 0.5, 1.1],     # 零股
        'large': [10, 20, 50]           # 大量
    }
    
    # 測試價格配置
    TEST_PRICES = {
        'etf_low': [25.0, 30.0, 35.0],      # ETF 低價
        'etf_medium': [40.0, 50.0, 60.0],   # ETF 中價
        'stock_low': [50.0, 100.0, 150.0],  # 股票低價
        'stock_high': [200.0, 500.0, 1000.0] # 股票高價
    }
    
    # 環境變數配置
    REQUIRED_ENV_VARS = {
        'fubon': [
            'FUBON_NATIONAL_ID',
            'FUBON_ACCOUNT_PASS',
            'FUBON_CERT_PATH'
        ],
        'fugle': [
            'FUGLE_CONFIG_PATH',
            'FUGLE_MARKET_API_KEY'
        ],
        'sinopac': [
            'SHIOAJI_API_KEY',
            'SHIOAJI_SECRET_KEY',
            'SHIOAJI_CERT_PERSON_ID',
            'SHIOAJI_CERT_PATH'
        ]
    }
    
    # 性能測試基準
    PERFORMANCE_BENCHMARKS = {
        'get_stocks_single': 3.0,      # 單一股票查詢 (秒)
        'get_stocks_batch': 10.0,      # 批量股票查詢 (秒)
        'create_order': 5.0,           # 創建訂單 (秒)
        'cancel_order': 3.0,           # 取消訂單 (秒)
        'get_position': 5.0,           # 獲取持倉 (秒)
        'get_orders': 3.0,             # 獲取委託單 (秒)
    }
    
    # 重試配置
    RETRY_CONFIG = {
        'max_attempts': 3,
        'delay_between_attempts': 1.0,
        'exponential_backoff': True
    }
    
    @classmethod
    def setup_logging(cls):
        """設置日誌配置"""
        logging.basicConfig(
            level=cls.LOG_LEVEL,
            format=cls.LOG_FORMAT,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('test.log', encoding='utf-8')
            ]
        )
    
    @classmethod
    def check_environment(cls, broker: str) -> Dict[str, Any]:
        """檢查特定券商的環境變數"""
        result = {
            'broker': broker,
            'available': True,
            'missing_vars': [],
            'message': ''
        }
        
        if broker not in cls.REQUIRED_ENV_VARS:
            result['available'] = False
            result['message'] = f"不支援的券商: {broker}"
            return result
        
        required_vars = cls.REQUIRED_ENV_VARS[broker]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        
        if missing_vars:
            result['available'] = False
            result['missing_vars'] = missing_vars
            result['message'] = f"缺少環境變數: {missing_vars}"
        else:
            result['message'] = f"{broker} 環境變數設置完整"
        
        return result
    
    @classmethod
    def get_test_stock(cls, category: str, index: int = 0) -> str:
        """獲取測試股票代碼"""
        stocks = cls.TEST_STOCKS.get(category, cls.TEST_STOCKS['tw_test'])
        return stocks[index % len(stocks)]
    
    @classmethod
    def get_test_quantity(cls, category: str, index: int = 0) -> float:
        """獲取測試數量"""
        quantities = cls.TEST_QUANTITIES.get(category, cls.TEST_QUANTITIES['regular'])
        return quantities[index % len(quantities)]
    
    @classmethod
    def get_test_price(cls, category: str, index: int = 0) -> float:
        """獲取測試價格"""
        prices = cls.TEST_PRICES.get(category, cls.TEST_PRICES['etf_low'])
        return prices[index % len(prices)]
    
    @classmethod
    def is_performance_acceptable(cls, operation: str, duration: float) -> bool:
        """檢查性能是否可接受"""
        benchmark = cls.PERFORMANCE_BENCHMARKS.get(operation)
        if benchmark is None:
            return True  # 沒有基準則認為可接受
        return duration <= benchmark
    
    @classmethod
    def get_retry_config(cls) -> Dict[str, Any]:
        """獲取重試配置"""
        return cls.RETRY_CONFIG.copy()


# 測試裝飾器
def retry_on_failure(max_attempts=None):
    """重試裝飾器"""
    import time
    from functools import wraps
    
    if max_attempts is None:
        max_attempts = TestConfig.RETRY_CONFIG['max_attempts']
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = TestConfig.RETRY_CONFIG['delay_between_attempts']
                        if TestConfig.RETRY_CONFIG['exponential_backoff']:
                            delay *= (2 ** attempt)
                        time.sleep(delay)
                    else:
                        logging.warning(f"重試 {max_attempts} 次後仍失敗: {e}")
            
            raise last_exception
        
        return wrapper
    return decorator


def skip_if_env_missing(broker: str):
    """如果環境變數缺失則跳過測試的裝飾器"""
    import unittest
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            env_check = TestConfig.check_environment(broker)
            if not env_check['available']:
                self.skipTest(env_check['message'])
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


# 初始化日誌配置
TestConfig.setup_logging()