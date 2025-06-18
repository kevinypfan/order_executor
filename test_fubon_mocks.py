"""
FubonAccount 測試用 Mock 對象和工具

提供模擬富邦證券 API 響應的工具
"""
import datetime
from unittest.mock import Mock, MagicMock
from typing import Dict, List, Any, Optional

from fubon_neo.constant import OrderType, BSAction, MarketType, PriceType, TimeInForce
from test_base import MockAPIResponse, TestDataFactory


class FubonMockFactory:
    """富邦 Mock 數據工廠"""
    
    @staticmethod
    def create_mock_account(account_id: str = "12345678") -> Mock:
        """創建模擬帳戶對象"""
        mock_account = Mock()
        mock_account.account = account_id
        mock_account.account_type = "Stock"
        return mock_account
    
    @staticmethod
    def create_mock_accounts_response(accounts: Optional[List[Mock]] = None) -> MockAPIResponse:
        """創建模擬帳戶列表響應"""
        if accounts is None:
            accounts = [FubonMockFactory.create_mock_account()]
        
        response = MockAPIResponse(is_success=True, data=accounts)
        return response
    
    @staticmethod
    def create_mock_order_data(
        seq_no: str = "12345",
        stock_no: str = "2330",
        price: float = 100.0,
        after_qty: int = 1000,
        filled_qty: int = 0,
        status: int = 10,
        **kwargs
    ) -> Mock:
        """創建模擬委託單數據"""
        mock_order = Mock()
        mock_order.seq_no = seq_no
        mock_order.stock_no = stock_no
        mock_order.price = price
        mock_order.after_qty = after_qty
        mock_order.filled_qty = filled_qty
        mock_order.status = status
        mock_order.buy_sell = kwargs.get('buy_sell', BSAction.Buy)
        mock_order.order_type = kwargs.get('order_type', OrderType.Stock)
        mock_order.date = kwargs.get('date', '2024/01/15')
        mock_order.last_time = kwargs.get('last_time', '09:30:00.000')
        mock_order.can_cancel = kwargs.get('can_cancel', True)
        mock_order.market_type = kwargs.get('market_type', MarketType.Common)
        return mock_order
    
    @staticmethod
    def create_mock_orders_response(orders: Optional[List[Mock]] = None) -> MockAPIResponse:
        """創建模擬委託單列表響應"""
        if orders is None:
            orders = [FubonMockFactory.create_mock_order_data()]
        
        return MockAPIResponse(is_success=True, data=orders)
    
    @staticmethod
    def create_mock_quote_data(
        symbol: str = "2330",
        close_price: float = 100.0,
        **kwargs
    ) -> Dict[str, Any]:
        """創建模擬報價數據 (字典格式)"""
        return {
            'symbol': symbol,
            'openPrice': kwargs.get('open_price', close_price * 0.98),
            'highPrice': kwargs.get('high_price', close_price * 1.02),
            'lowPrice': kwargs.get('low_price', close_price * 0.96),
            'closePrice': close_price,
            'lastPrice': close_price,
            'bids': kwargs.get('bids', [
                {'price': close_price - 0.5, 'size': 1000},
                {'price': close_price - 1.0, 'size': 2000}
            ]),
            'asks': kwargs.get('asks', [
                {'price': close_price + 0.5, 'size': 1500},
                {'price': close_price + 1.0, 'size': 2500}
            ])
        }
    
    @staticmethod
    def create_mock_quote_object(
        symbol: str = "2330",
        close_price: float = 100.0,
        **kwargs
    ) -> Mock:
        """創建模擬報價數據 (對象格式)"""
        mock_quote = Mock()
        mock_quote.symbol = symbol
        mock_quote.openPrice = kwargs.get('open_price', close_price * 0.98)
        mock_quote.open_price = mock_quote.openPrice  # 兼容性
        mock_quote.highPrice = kwargs.get('high_price', close_price * 1.02)
        mock_quote.high_price = mock_quote.highPrice  # 兼容性
        mock_quote.lowPrice = kwargs.get('low_price', close_price * 0.96)
        mock_quote.low_price = mock_quote.lowPrice  # 兼容性
        mock_quote.closePrice = close_price
        mock_quote.close_price = close_price  # 兼容性
        mock_quote.lastPrice = close_price
        
        # 委買委賣
        mock_bid = Mock()
        mock_bid.price = close_price - 0.5
        mock_bid.size = 1000
        
        mock_ask = Mock()
        mock_ask.price = close_price + 0.5
        mock_ask.size = 1500
        
        mock_quote.bids = [mock_bid]
        mock_quote.asks = [mock_ask]
        
        return mock_quote
    
    @staticmethod
    def create_mock_position_data(
        stock_no: str = "2330",
        today_qty: int = 1000,
        order_type: OrderType = OrderType.Stock,
        buy_sell: BSAction = BSAction.Buy
    ) -> Mock:
        """創建模擬持倉數據"""
        mock_position = Mock()
        mock_position.stock_no = stock_no
        mock_position.today_qty = today_qty
        mock_position.order_type = order_type
        mock_position.buy_sell = buy_sell
        return mock_position
    
    @staticmethod
    def create_mock_positions_response(positions: Optional[List[Mock]] = None) -> MockAPIResponse:
        """創建模擬持倉列表響應"""
        if positions is None:
            positions = [FubonMockFactory.create_mock_position_data()]
        
        return MockAPIResponse(is_success=True, data=positions)
    
    @staticmethod
    def create_mock_bank_remain_data(available_balance: float = 100000.0) -> Mock:
        """創建模擬銀行餘額數據"""
        mock_balance = Mock()
        mock_balance.available_balance = available_balance
        return mock_balance
    
    @staticmethod
    def create_mock_bank_remain_response(balance: Optional[float] = None) -> MockAPIResponse:
        """創建模擬銀行餘額響應"""
        if balance is None:
            balance = 100000.0
        
        balance_data = FubonMockFactory.create_mock_bank_remain_data(balance)
        return MockAPIResponse(is_success=True, data=balance_data)
    
    @staticmethod
    def create_mock_settlement_detail(
        settlement_date: str = "2024/01/17",
        total_settlement_amount: float = 50000.0
    ) -> Mock:
        """創建模擬交割明細"""
        mock_detail = Mock()
        mock_detail.settlement_date = settlement_date
        mock_detail.total_settlement_amount = total_settlement_amount
        return mock_detail
    
    @staticmethod
    def create_mock_settlement_data(details: Optional[List[Mock]] = None) -> Mock:
        """創建模擬交割數據"""
        if details is None:
            details = [FubonMockFactory.create_mock_settlement_detail()]
        
        mock_settlement = Mock()
        mock_settlement.details = details
        return mock_settlement
    
    @staticmethod
    def create_mock_settlement_response(settlement_amount: Optional[float] = None) -> MockAPIResponse:
        """創建模擬交割響應"""
        if settlement_amount is None:
            settlement_amount = 50000.0
        
        settlement_data = FubonMockFactory.create_mock_settlement_data([
            FubonMockFactory.create_mock_settlement_detail(
                total_settlement_amount=settlement_amount
            )
        ])
        return MockAPIResponse(is_success=True, data=settlement_data)
    
    @staticmethod
    def create_mock_place_order_response(order_id: str = "67890") -> MockAPIResponse:
        """創建模擬下單響應"""
        mock_order = Mock()
        mock_order.seq_no = order_id
        return MockAPIResponse(is_success=True, data=mock_order)
    
    @staticmethod
    def create_mock_sdk() -> Mock:
        """創建完整的模擬 SDK"""
        mock_sdk = Mock()
        
        # 模擬登入
        mock_accounts = FubonMockFactory.create_mock_accounts_response()
        mock_sdk.login.return_value = mock_accounts
        
        # 模擬股票相關 API
        mock_sdk.stock = Mock()
        mock_sdk.stock.get_order_results.return_value = FubonMockFactory.create_mock_orders_response()
        mock_sdk.stock.place_order.return_value = FubonMockFactory.create_mock_place_order_response()
        mock_sdk.stock.cancel_order.return_value = MockAPIResponse(is_success=True)
        mock_sdk.stock.modify_price.return_value = MockAPIResponse(is_success=True)
        mock_sdk.stock.modify_quantity.return_value = MockAPIResponse(is_success=True)
        mock_sdk.stock.make_modify_price_obj.return_value = Mock()
        mock_sdk.stock.make_modify_quantity_obj.return_value = Mock()
        
        # 模擬會計相關 API
        mock_sdk.accounting = Mock()
        mock_sdk.accounting.bank_remain.return_value = FubonMockFactory.create_mock_bank_remain_response()
        mock_sdk.accounting.unrealized_gains_and_loses.return_value = FubonMockFactory.create_mock_positions_response()
        mock_sdk.accounting.query_settlement.return_value = FubonMockFactory.create_mock_settlement_response()
        mock_sdk.accounting.inventories.return_value = MockAPIResponse(is_success=True, data=[])
        mock_sdk.accounting.realized_pnl_detail.return_value = MockAPIResponse(is_success=True, data=[])
        
        # 模擬行情相關 API
        mock_sdk.marketdata = Mock()
        mock_sdk.marketdata.rest_client = Mock()
        mock_sdk.marketdata.rest_client.stock = Mock()
        mock_sdk.marketdata.rest_client.stock.intraday = Mock()
        mock_sdk.marketdata.rest_client.stock.intraday.quote.return_value = FubonMockFactory.create_mock_quote_data()
        
        # 模擬初始化方法
        mock_sdk.init_realtime.return_value = None
        mock_sdk.logout.return_value = None
        
        return mock_sdk


class FubonTestScenarios:
    """富邦測試場景生成器"""
    
    @staticmethod
    def successful_login_scenario():
        """成功登入場景"""
        return {
            'accounts': [FubonMockFactory.create_mock_account("12345678")],
            'expected_account_id': "12345678"
        }
    
    @staticmethod
    def multiple_accounts_scenario():
        """多帳戶場景"""
        return {
            'accounts': [
                FubonMockFactory.create_mock_account("12345678"),
                FubonMockFactory.create_mock_account("87654321")
            ],
            'target_account': "87654321"
        }
    
    @staticmethod
    def order_lifecycle_scenario():
        """訂單生命週期場景"""
        return {
            'new_order': FubonMockFactory.create_mock_order_data(
                seq_no="ORDER001",
                status=10,  # NEW
                filled_qty=0
            ),
            'partially_filled_order': FubonMockFactory.create_mock_order_data(
                seq_no="ORDER001",
                status=10,  # NEW but has filled quantity
                after_qty=1000,
                filled_qty=300
            ),
            'filled_order': FubonMockFactory.create_mock_order_data(
                seq_no="ORDER001",
                status=50,  # FILLED
                after_qty=1000,
                filled_qty=1000
            ),
            'cancelled_order': FubonMockFactory.create_mock_order_data(
                seq_no="ORDER001",
                status=30  # CANCELLED
            )
        }
    
    @staticmethod
    def market_time_scenarios():
        """市場時間場景"""
        return {
            'regular_hours': datetime.time(10, 30),      # 正常交易時間
            'odd_lot_session': datetime.time(13, 50),    # 零股交易時間
            'fixing_session': datetime.time(14, 15),     # 定盤交易時間
            'after_hours': datetime.time(15, 30)         # 盤後時間
        }
    
    @staticmethod
    def error_scenarios():
        """錯誤場景"""
        return {
            'api_failure': MockAPIResponse(is_success=False, message="API 調用失敗"),
            'network_error': Exception("網絡連接失敗"),
            'invalid_data': None,
            'empty_response': MockAPIResponse(is_success=True, data=[])
        }