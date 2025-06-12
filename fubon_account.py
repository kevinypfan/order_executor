"""
FubonAccount 模組

實現與富邦證券 API 交互的 Account 類
"""

import datetime
import logging
import time
import os
from decimal import Decimal

from finlab.online.base_account import Account, Stock, Order
from finlab.online.enums import *
from finlab.online.order_executor import Position
from finlab import data
from finlab.markets.tw import TWMarket
from fubon_neo.sdk import FubonSDK, Order as FBOrder
from fubon_neo.constant import TimeInForce, OrderType, PriceType, MarketType, BSAction


class FubonAccount(Account):
    """
    富邦證券賬戶類
    實現與富邦證券 API 的交互
    """

    required_module = 'fubon_neo'  # 需要的 Python 包名稱
    module_version = '1.0.0'  # 需要的版本號

    def __init__(self,
                 base_url=None,
                 national_id=None,
                 account=None,
                 account_pass=None,
                 cert_path=None,
                 cert_pass=None):
        """
        初始化富邦證券賬戶

        Args:
            national_id (str, optional): 身分證字號。預設從環境變數獲取。
            account (str, optional): 帳號。預設從環境變數獲取。
            account_pass (str, optional): 登入密碼。預設從環境變數獲取。
            cert_path (str, optional): 憑證路徑。預設從環境變數獲取。
            cert_pass (str, optional): 憑證密碼。預設從環境變數獲取。
        """
        # 從參數或環境變數獲取登錄信息
        self.base_url = base_url or os.environ.get('FUBON_BASE_URL')
        self.national_id = national_id or os.environ.get('FUBON_NATIONAL_ID')
        self.account = account or os.environ.get('FUBON_ACCOUNT')
        self.account_pass = account_pass or os.environ.get('FUBON_ACCOUNT_PASS')
        self.cert_path = cert_path or os.environ.get('FUBON_CERT_PATH')
        self.cert_pass = cert_pass or os.environ.get('FUBON_CERT_PASS')

        if not all([self.national_id, self.account_pass, self.cert_path]):
            raise ValueError(
                "缺少必要的登錄信息。請確保設置了 FUBON_NATIONAL_ID, FUBON_ACCOUNT_PASS, FUBON_CERT_PATH 環境變數或直接提供參數")

        # 初始化市場和時間戳
        self.market = 'tw_stock'
        self.order_records = {}
        self.timestamp_for_get_position = datetime.datetime(2021, 1, 1)

        # 初始化 SDK 和帳戶
        logging.info("初始化富邦 SDK...")
        self.sdk = FubonSDK(30,2,self.base_url)

        # 登入
        try:
            self.accounts = self.sdk.login(
                self.national_id,
                self.account_pass,
                self.cert_path,
                self.cert_pass
            )
        except Exception as e:
            logging.error(f"登入失敗: {e}")
            raise Exception(f"無法登入富邦證券: {e}")

        # 選擇帳戶
        if self.account:
            self.target_account = next((acc for acc in self.accounts.data if acc.account == self.account), None)
            if not self.target_account:
                logging.warning(f"未找到指定帳號 {self.account}，將使用第一個帳號")
                self.target_account = self.accounts.data[0] if self.accounts.data else None
        else:
            self.target_account = self.accounts.data[0] if self.accounts.data else None

        if not self.target_account:
            raise ValueError("無法獲取有效的富邦證券帳戶")

        print(self.target_account)
        logging.info(f"成功登入帳號: {self.target_account.account}")

        # 初始化行情連線
        try:
            self.sdk.init_realtime()
            logging.info("初始化行情元件成功")
        except Exception as e:
            logging.warning(f"初始化行情元件失敗: {e}")

    def __del__(self):
        """
        當物件被刪除時，確保登出
        """
        try:
            if hasattr(self, 'sdk'):
                # 確保登出
                if hasattr(self.sdk, 'logout'):
                    self.sdk.logout()
        except Exception as e:
            logging.warning(f"登出時發生錯誤: {e}")
            pass

    def get_cash(self):
        """
        獲取可用資金

        Returns:
            float: 可用資金
        """
        try:
            # 獲取銀行餘額
            result = self.sdk.accounting.bank_remain(self.target_account)
            if result and result.is_success and result.data:
                # 從返回結果中獲取可用餘額
                available_balance = getattr(result.data, 'available_balance', 0)
                # 確保可以轉換為浮點數
                if isinstance(available_balance, str):
                    available_balance = available_balance.replace(',', '')
                return float(available_balance)
            else:
                logging.warning("get_cash: 無法獲取可用資金")
                return 0
        except Exception as e:
            logging.warning(f"get_cash: 獲取可用資金失敗: {e}")
            return 0

    def get_orders(self):
        """
        獲取所有委託單

        Returns:
            dict: 委託單字典，以委託單編號為鍵
        """
        try:
            # 獲取所有委託單
            result = self.sdk.stock.get_order_results(self.target_account)
            if not result or not result.is_success:
                logging.warning("get_orders: 獲取委託單失敗")
                return {}
            print(result)
            orders = result.data
            order_dict = {}

            for order in orders:
                try:
                    finlab_order = self._create_finlab_order(order)
                    order_dict[finlab_order.order_id] = finlab_order
                except Exception as e:
                    logging.warning(f"get_orders: 處理委託單時發生錯誤: {e}")

            return order_dict

        except Exception as e:
            logging.warning(f"get_orders: 獲取委託單時發生錯誤: {e}")
            return {}

    def _map_order_action(self, order):
        """
        將富邦買賣別映射到 finlab Action

        Args:
            order: 富邦 API 返回的委託單對象

        Returns:
            Action: finlab 買賣操作
        """
        buy_sell = getattr(order, 'buy_sell', None)
        if buy_sell == BSAction.Buy:
            return Action.BUY
        elif buy_sell == BSAction.Sell:
            return Action.SELL
        else:
            # 無法識別買賣別時，嘗試從其他欄位判斷
            if hasattr(order, 'buy_sell') and isinstance(order.buy_sell, str):
                if order.buy_sell.upper() in ['B', 'BUY']:
                    return Action.BUY
                elif order.buy_sell.upper() in ['S', 'SELL']:
                    return Action.SELL

            raise ValueError(f"無法識別買賣別: {buy_sell}")

    def _map_order_condition(self, order):
        """
        將富邦委託類型映射到 finlab OrderCondition

        Args:
            order: 富邦 API 返回的委託單對象

        Returns:
            OrderCondition: finlab 委託條件
        """
        order_type = getattr(order, 'order_type', None)

        if order_type == OrderType.Stock:
            return OrderCondition.CASH
        elif order_type == OrderType.Margin:
            return OrderCondition.MARGIN_TRADING
        elif order_type == OrderType.Short:
            return OrderCondition.SHORT_SELLING
        elif order_type == OrderType.DayTrade:
            return OrderCondition.DAY_TRADING_SHORT
        else:
            # 嘗試從字串類型判斷
            if isinstance(order_type, str):
                order_type = order_type.upper()
                if "現股" in order_type or "STOCK" in order_type:
                    return OrderCondition.CASH
                elif "融資" in order_type or "MARGIN" in order_type:
                    return OrderCondition.MARGIN_TRADING
                elif "融券" in order_type or "SHORT" in order_type:
                    return OrderCondition.SHORT_SELLING
                elif "當沖" in order_type or "DAYTRADE" in order_type:
                    return OrderCondition.DAY_TRADING_SHORT

            # 默認為現股
            return OrderCondition.CASH

    def _create_finlab_order(self, order):
        """
        將富邦委託單轉換為 finlab Order 格式

        Args:
            order: 富邦委託單

        Returns:
            Order: finlab 格式的委託單
        """
        try:
            # 提取基本信息
            order_id = getattr(order, 'order_no', '')
            stock_id = getattr(order, 'stock_no', '')
            price = float(getattr(order, 'price', 0) or 0)

            # 解析委託狀態
            status_code = getattr(order, 'status', 0)
            status = OrderStatus.NEW

            if status_code == 10:  # 委託成功
                status = OrderStatus.NEW
            elif status_code == 30:  # 刪單成功
                status = OrderStatus.CANCEL
            elif status_code == 50:  # 完全成交
                status = OrderStatus.FILLED
            elif status_code == 90:  # 失敗
                status = OrderStatus.CANCEL

            # 檢查部分成交
            filled_qty = float(getattr(order, 'filled_qty', 0) or 0)
            after_qty = float(getattr(order, 'after_qty', 0) or 0)

            if filled_qty > 0 and filled_qty < after_qty and status != OrderStatus.CANCEL:
                status = OrderStatus.PARTIALLY_FILLED

            # 判斷是否為零股
            market_type = getattr(order, 'market_type', None)
            is_odd_lot = market_type in [MarketType.IntradayOdd, MarketType.Odd, MarketType.EmgOdd]
            divisor = 1 if is_odd_lot else 1000

            # 委託數量和成交數量
            quantity = float(after_qty) / divisor
            filled_quantity = float(filled_qty) / divisor

            # 獲取委託時間
            date_str = getattr(order, 'date', '')
            time_str = getattr(order, 'last_time', '')

            if date_str and time_str:
                try:
                    # 嘗試解析日期時間
                    if '/' in date_str:
                        date_parts = date_str.split('/')
                        if len(date_parts) == 3:
                            year, month, day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
                        else:
                            year, month, day = datetime.datetime.now().year, int(date_parts[0]), int(date_parts[1])
                    else:
                        # 假設日期格式為YYYYMMDD
                        year = int(date_str[:4])
                        month = int(date_str[4:6])
                        day = int(date_str[6:8])

                    # 解析時間
                    time_parts = time_str.split(':')
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])

                    # 解析秒和毫秒
                    second_parts = time_parts[2].split('.')
                    second = int(second_parts[0])
                    microsecond = int(second_parts[1]) * 1000 if len(second_parts) > 1 else 0

                    order_time = datetime.datetime(year, month, day, hour, minute, second, microsecond)
                except Exception as e:
                    logging.warning(f"_create_finlab_order: 解析委託時間失敗: {e}, 使用當前時間")
                    order_time = datetime.datetime.now()
            else:
                order_time = datetime.datetime.now()

            # 映射買賣別和委託條件
            try:
                action = self._map_order_action(order)
                order_condition = self._map_order_condition(order)
            except Exception as e:
                logging.warning(f"_create_finlab_order: 映射買賣別或委託條件失敗: {e}")
                action = Action.BUY  # 默認為買入
                order_condition = OrderCondition.CASH  # 默認為現股

            # 創建 finlab Order 物件
            return Order(
                order_id=order_id,
                stock_id=stock_id,
                action=action,
                price=price,
                quantity=quantity,
                filled_quantity=filled_quantity,
                status=status,
                order_condition=order_condition,
                time=order_time,
                org_order=order  # 保存原始委託單對象
            )
        except Exception as e:
            logging.error(f"_create_finlab_order: 轉換委託單失敗: {e}")
            raise

    def get_stocks(self, stock_ids):
        """
        獲取股票即時報價

        Args:
            stock_ids (list): 股票代碼列表

        Returns:
            dict: 股票報價字典，以股票代碼為鍵
        """
        ret = {}
        for stock_id in stock_ids:
            try:
                # 確保已初始化行情連線
                if not hasattr(self.sdk, 'marketdata') or not hasattr(self.sdk.marketdata, 'rest_client'):
                    logging.warning(f"get_stocks: 行情連線尚未初始化，嘗試重新初始化")
                    try:
                        self.sdk.init_realtime()
                    except Exception as e:
                        logging.error(f"get_stocks: 無法初始化行情連線: {e}")
                        continue

                # 使用正確的 API 獲取股票報價
                rest_stock = self.sdk.marketdata.rest_client.stock
                if not hasattr(rest_stock, 'intraday') or not hasattr(rest_stock.intraday, 'quote'):
                    logging.warning(f"get_stocks: SDK 無法存取 intraday.quote 方法")
                    continue

                # 使用富邦SDK獲取即時報價
                quote = rest_stock.intraday.quote(symbol=stock_id)
                logging.debug(quote)
                if quote:
                    ret[stock_id] = self._create_finlab_stock(quote, stock_id)
                else:
                    logging.warning(f"get_stocks: 無法獲取股票 {stock_id} 的報價")
            except Exception as e:
                logging.warning(f"get_stocks: 獲取股票 {stock_id} 報價時發生錯誤: {e}")

        return ret

    def _create_finlab_stock(self, quote, original_stock_id=None):
        """
        將富邦行情轉換為 finlab Stock 格式

        Args:
            quote: 富邦行情數據
            original_stock_id (str, optional): 原始股票代碼，用於備份

        Returns:
            Stock: finlab 格式的股票數據
        """
        # 嘗試直接從對象中獲取屬性
        try:
            # 匯理多種可能的屬性名稱
            stock_id = None
            # 先使用 get 方法嘗試（如果 quote 是字典）
            if isinstance(quote, dict):
                stock_id = quote.get('symbol', original_stock_id)
                open_price = float(quote.get('openPrice', 0) or 0)
                high_price = float(quote.get('highPrice', 0) or 0)
                low_price = float(quote.get('lowPrice', 0) or 0)
                close_price = float(quote.get('closePrice', 0) or 0)
            else:  # 嘗試使用 getattr（如果 quote 是物件）
                stock_id = getattr(quote, 'symbol', original_stock_id or '')
                open_price = float(getattr(quote, 'open_price', getattr(quote, 'openPrice', 0)) or 0)
                high_price = float(getattr(quote, 'high_price', getattr(quote, 'highPrice', 0)) or 0)
                low_price = float(getattr(quote, 'low_price', getattr(quote, 'lowPrice', 0)) or 0)
                close_price = float(getattr(quote, 'close_price', getattr(quote, 'closePrice', getattr(quote, 'lastPrice', 0))) or 0)

            logging.debug(f'stock_id: {stock_id}, open_price: {open_price}, high_price: {high_price}, low_price: {low_price}, close_price: {close_price}')

            # 嘗試不同的方法取得委買委賣資訊
            if isinstance(quote, dict):
                bids = quote.get('bids', [])
                asks = quote.get('asks', [])
            else:
                bids = getattr(quote, 'bids', [])
                asks = getattr(quote, 'asks', [])

            bid_price = 0
            bid_volume = 0
            ask_price = 0
            ask_volume = 0

            # 如果有委買資訊
            if bids and len(bids) > 0:
                first_bid = bids[0]
                if isinstance(first_bid, dict) and 'price' in first_bid:
                    bid_price = float(first_bid.get('price', 0) or 0)
                    bid_volume = float(first_bid.get('size', 0) or 0)
                else:
                    bid_price = float(getattr(first_bid, 'price', 0) or 0)
                    bid_volume = float(getattr(first_bid, 'size', 0) or 0)

            # 如果有委賣資訊
            if asks and len(asks) > 0:
                first_ask = asks[0]
                if isinstance(first_ask, dict) and 'price' in first_ask:
                    ask_price = float(first_ask.get('price', 0) or 0)
                    ask_volume = float(first_ask.get('size', 0) or 0)
                else:
                    ask_price = float(getattr(first_ask, 'price', 0) or 0)
                    ask_volume = float(getattr(first_ask, 'size', 0) or 0)

            # 確保股票代碼不為空
            if not stock_id and original_stock_id:
                stock_id = original_stock_id

            # 返回 finlab Stock 物件
            return Stock(
                stock_id=stock_id,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                bid_price=bid_price,
                ask_price=ask_price,
                bid_volume=bid_volume,
                ask_volume=ask_volume
            )
        except Exception as e:
            logging.warning(f"_create_finlab_stock: 轉換時發生錯誤: {e}")
            return Stock(
                stock_id=original_stock_id,
                open=0,
                high=0,
                low=0,
                close=0,
                bid_price=0,
                ask_price=0,
                bid_volume=0,
                ask_volume=0
            )

    def get_position(self):
        """
        獲取當前持有部位

        Returns:
            Position: 持有部位對象
        """
        now = datetime.datetime.now()

        # 限制請求頻率
        total_seconds = (now - self.timestamp_for_get_position).total_seconds()
        if total_seconds < 10:
            time.sleep(10 - total_seconds)

        try:
            # 獲取持倉
            result = self.sdk.accounting.inventories(self.target_account)
            self.timestamp_for_get_position = datetime.datetime.now()

            if not result or not result.is_success:
                logging.warning("get_position: 獲取持倉失敗")
                return Position({})

            inventories = result.data
            positions = []

            for inventory in inventories:
                try:
                    # 處理每個持倉項目
                    stock_id = getattr(inventory, 'stock_no', '')
                    if not stock_id:
                        continue

                    # 判斷委託類型
                    order_type = getattr(inventory, 'order_type', None)
                    order_condition = OrderCondition.CASH  # 默認為現股

                    if order_type == OrderType.Margin:
                        order_condition = OrderCondition.MARGIN_TRADING
                    elif order_type == OrderType.Short:
                        order_condition = OrderCondition.SHORT_SELLING
                    elif order_type == OrderType.DayTrade:
                        order_condition = OrderCondition.DAY_TRADING_SHORT

                    # 獲取持倉數量
                    today_qty = getattr(inventory, 'today_qty', 0)
                    if not today_qty:
                        continue

                    # 如果是空頭部位，數量為負數
                    quantity_sign = -1 if order_condition == OrderCondition.SHORT_SELLING else 1
                    quantity = float(today_qty) / 1000 * quantity_sign  # 轉換為張

                    # 處理零股部位
                    odd_lot = getattr(inventory, 'odd', None)
                    if odd_lot and hasattr(odd_lot, 'today_qty') and odd_lot.today_qty:
                        odd_qty = float(odd_lot.today_qty)
                        if odd_qty > 0:
                            # 如果有零股持倉，需要另外紀錄
                            positions.append({
                                'stock_id': stock_id,
                                'quantity': odd_qty / 1000 * quantity_sign,  # 轉換為張 (小於1張)
                                'order_condition': order_condition
                            })

                    # 紀錄整股持倉
                    if float(today_qty) > 0:
                        positions.append({
                            'stock_id': stock_id,
                            'quantity': quantity,
                            'order_condition': order_condition
                        })

                except Exception as e:
                    logging.warning(f"get_position: 處理持倉項目 {getattr(inventory, 'stock_no', '未知')} 時發生錯誤: {e}")

            logging.info(f"get_position: 成功獲取持倉，共 {len(positions)} 筆")
            return Position.from_list(positions)

        except Exception as e:
            logging.warning(f"get_position: 獲取持倉失敗: {e}")
            return Position({})

    def get_settlement(self):
        """
        獲取未交割款項

        Returns:
            float: 未交割款項
        """
        try:
            # 獲取交割資訊
            total_settlement = 0

            # 查詢過去 3 天和當日的交割款
            for time_range in ["3d", "0d"]:
                try:
                    result = self.sdk.accounting.query_settlement(self.target_account, time_range)
                    logging.debug(result)
                    if not result or not result.is_success or not result.data:
                        logging.warning(f"get_settlement: 無法獲取 {time_range} 交割資訊")
                        continue

                    # 取得交割款資料
                    settlement_data = result.data
                    if not hasattr(settlement_data, 'details') or not settlement_data.details:
                        continue

                    # 處理每一筆交割款資料
                    for detail in settlement_data.details:
                        try:
                            # 交割日為空時表示無交割資訊
                            if not getattr(detail, 'settlement_date', None):
                                continue

                            # 使用合計交割金額欄位
                            total_settlement_amount = getattr(detail, 'total_settlement_amount', None)
                            if total_settlement_amount is not None:
                                # 加入總交割款
                                total_settlement += float(total_settlement_amount)
                                logging.debug(f"get_settlement: 加入交割款 {total_settlement_amount}, 日期: {getattr(detail, 'settlement_date', 'unknown')}")
                        except Exception as e:
                            logging.warning(f"get_settlement: 處理交割款明細時發生錯誤: {e}")
                except Exception as e:
                    logging.warning(f"get_settlement: 查詢 {time_range} 交割款失敗: {e}")

            logging.info(f"get_settlement: 總交割款 = {total_settlement}")
            return total_settlement

        except Exception as e:
            logging.warning(f"get_settlement: 獲取未交割款項失敗: {e}")
            return 0

    def get_total_balance(self):
        """
        計算帳戶總淨值

        總淨值 = 現股市值 + (融資市值 - 融資金額) + (擔保金 + 保證金 - 融券市值) + 現金 + 未交割款項

        Returns:
            float: 總淨值
        """
        try:
            # 獲取可用資金
            cash = self.get_cash()

            # 獲取未交割款項
            settlements = self.get_settlement()

            # 獲取庫存資料
            try:
                position_response = self.sdk.accounting.inventories(self.target_account)
                if not position_response or not position_response.is_success:
                    logging.warning("get_total_balance: 無法獲取持倉資訊")
                    return cash + settlements

                # 計算總市值
                total_market_value = 0

                # 計算融資融券相關數據
                margin_position_market_value = 0  # 融資市值
                margin_amount = 0  # 融資金額
                short_position_market_value = 0  # 融券市值
                short_collateral = 0  # 擔保金
                guarantee_amount = 0  # 保證金

                # 從持倉數據中計算總市值
                for inventory in position_response.data:
                    # 計算市值
                    # 這裡需要根據富邦API的實際回傳格式調整
                    position_market_value = 0
                    try:
                        # 嘗試獲取市值資訊
                        if hasattr(inventory, 'market_value'):
                            position_market_value = float(getattr(inventory, 'market_value', 0) or 0)
                        # 若無市值資訊，嘗試通過數量和價格計算
                        elif hasattr(inventory, 'today_qty') and hasattr(inventory, 'price'):
                            position_market_value = float(getattr(inventory, 'today_qty', 0) or 0) * float(getattr(inventory, 'price', 0) or 0)

                        total_market_value += position_market_value

                        # 區分融資融券部位
                        order_type = getattr(inventory, 'order_type', None)
                        if order_type == OrderType.Margin:
                            margin_position_market_value += position_market_value
                            # 嘗試獲取融資金額
                            if hasattr(inventory, 'margin_amount'):
                                margin_amount += float(getattr(inventory, 'margin_amount', 0) or 0)
                        elif order_type == OrderType.Short:
                            short_position_market_value += position_market_value
                            # 嘗試獲取擔保金和保證金
                            if hasattr(inventory, 'short_collateral'):
                                short_collateral += float(getattr(inventory, 'short_collateral', 0) or 0)
                            if hasattr(inventory, 'guarantee_amount'):
                                guarantee_amount += float(getattr(inventory, 'guarantee_amount', 0) or 0)
                    except Exception as e:
                        logging.warning(f"get_total_balance: 計算持倉市值時發生錯誤: {e}")

                # 計算現股市值
                cash_position_market_value = total_market_value - margin_position_market_value - short_position_market_value

                # 計算總淨值
                total_balance = (
                    cash_position_market_value +  # 現股市值
                    (margin_position_market_value - margin_amount) +  # 融資淨值
                    (short_collateral + guarantee_amount - short_position_market_value) +  # 融券淨值
                    cash +  # 可用資金
                    settlements  # 未交割款項
                )

                logging.info(
                    f"總淨值計算: 現股市值={cash_position_market_value}, 融資淨值={(margin_position_market_value - margin_amount)}, " +
                    f"融券淨值={(short_collateral + guarantee_amount - short_position_market_value)}, " +
                    f"現金={cash}, 未交割款項={settlements}")

                return total_balance
            except Exception as e:
                logging.warning(f"get_total_balance: 處理持倉資訊時發生錯誤: {e}")
                return cash + settlements
        except Exception as e:
            logging.warning(f"get_total_balance: 獲取總資產失敗: {e}")
            return 0

    def create_order(self, action, stock_id, quantity, price=None, odd_lot=False,
                     best_price_limit=False, market_order=False,
                     order_cond=OrderCondition.CASH):
        """
        創建委託單

        Args:
            action (Action): 操作類型，買或賣
            stock_id (str): 股票代碼
            quantity (float): 數量，以張為單位
            price (float, optional): 價格
            odd_lot (bool): 是否為零股
            best_price_limit (bool): 是否使用最優價格限制
            market_order (bool): 是否為市價單
            order_cond (OrderCondition): 交易條件

        Returns:
            str: 委託單編號
        """
        if quantity <= 0:
            raise ValueError("委託數量必須大於零")

        # 將 finlab Action 轉換為富邦 BSAction
        buy_sell = BSAction.Buy if action == Action.BUY else BSAction.Sell

        # 確定市場類型
        market_type = MarketType.IntradayOdd if odd_lot else MarketType.Common
        now = datetime.datetime.now()

        # 盤後零股處理
        if datetime.time(13, 40) < datetime.time(now.hour, now.minute) < datetime.time(14, 30) and odd_lot:
            market_type = MarketType.Odd

        # 定盤處理
        if datetime.time(14, 00) < datetime.time(now.hour, now.minute) < datetime.time(14, 30) and not odd_lot:
            market_type = MarketType.Fixing

        # 確定價格類型
        price_type = PriceType.Limit
        if market_order:
            price = None
            if action == Action.BUY:
                price_type = PriceType.LimitUp
            elif action == Action.SELL:
                price_type = PriceType.LimitDown

        if best_price_limit:
            price = None
            if action == Action.BUY:
                price_type = PriceType.LimitDown
            elif action == Action.SELL:
                price_type = PriceType.LimitUp

        # 確定交易條件
        order_type = OrderType.Stock  # 預設為現股交易
        if order_cond == OrderCondition.MARGIN_TRADING:
            order_type = OrderType.Margin
        elif order_cond == OrderCondition.SHORT_SELLING:
            order_type = OrderType.Short
        elif order_cond == OrderCondition.DAY_TRADING_SHORT:
            order_type = OrderType.DayTrade

        # 設定委託時效
        time_in_force = TimeInForce.ROD

        # 建立委託單物件
        try:
            # 根據市場類型確定數量單位
            qty = int(quantity) if odd_lot else int(quantity * 1000)

            # 建立委託單
            order = FBOrder(
                buy_sell=buy_sell,
                symbol=stock_id,
                price=str(price) if price is not None else None,
                quantity=qty,
                market_type=market_type,
                price_type=price_type,
                time_in_force=time_in_force,
                order_type=order_type
            )

            # 送出委託單
            result = self.sdk.stock.place_order(self.target_account, order)
            if not result or not result.is_success:
                logging.warning(f"create_order: 送出委託單失敗: {result.message if result else '未知錯誤'}")
                return None

            order_id = self._get_order_id(result.data)
            logging.debug(f"#create_order order({order_id}): {order}")
            # 返回委託單號碼
            return order_id
        except Exception as e:
            logging.warning(f"create_order: 無法創建委託單: {e}")
            return None

    def _get_order_id(self, order):
        """
        從委託單對象中獲取委託單編號

        Args:
            order (object): 富邦 API 返回的委託單對象

        Returns:
            str: 委託單編號
        """
        # 對於物件式資料，假設有 order_no 屬性
        if hasattr(order, 'order_no'):
            return order.order_no

        # 對於字典式資料
        if isinstance(order, dict):
            return order.get('order_no', order.get('orderNo', order.get('ordNo', '')))

        # 嘗試其他常見屬性名
        for attr in ['order_no', 'orderNo', 'ordNo', 'seq_no', 'seqNo']:
            if hasattr(order, attr):
                return getattr(order, attr)

        # 無法找到委託單編號
        logging.warning(f"無法從委託單中獲取編號: {order}")
        return f"unknown_{int(time.time())}"

    def update_order(self, order_id, price=None, quantity=None):
        """
        更新委託單

        Args:
            order_id (str): 委託單編號
            price (float, optional): 新價格
            quantity (float, optional): 新數量
        """
        try:
            # 獲取委託單
            orders = self.get_orders()
            if not orders or order_id not in orders:
                logging.warning(f"update_order: 找不到委託單 {order_id}")
                return

            order = orders[order_id]
            logging.debug(f"#update_order price: {price}, qty: {quantity}, order({order_id}): {order}")

            # 更新價格
            if price is not None:
                order_record = order.org_order
                # 判斷是否為零股
                if getattr(order_record, 'market_type', '') in [MarketType.IntradayOdd, MarketType.Odd, MarketType.EmgOdd]:
                    # 零股模式需要特別處理：取消原委託單並重新創建
                    action = order.action
                    stock_id = order.stock_id
                    filled_qty = getattr(order_record, 'filled_qty', 0)
                    org_qty = getattr(order_record, 'after_qty', getattr(order_record, 'quantity', 0))
                    qty = float(org_qty) - float(filled_qty)

                    # 取消原委託單
                    try:
                        # 取消原委託單
                        modify_qty_obj = self.sdk.stock.make_modify_quantity_obj(order_record, 0)
                        cancel_result = self.sdk.stock.modify_quantity(self.target_account, modify_qty_obj)
                        if cancel_result and cancel_result.is_success:
                            logging.info(f"已將零股委託單 {order_id} 數量修改為0以進行取消")
                        else:
                            logging.warning(f"update_order: 無法取消零股委託單 {order_id}: {
                                cancel_result.message if cancel_result else '未知錯誤'}")
                            return
                    except Exception as e:
                        logging.warning(f"update_order: 修改零股數量為0時發生錯誤: {e}")
                        return

                    # 創建新委託單
                    if qty > 0:
                        self.create_order(action=action, stock_id=stock_id, quantity=qty/1000, price=price, odd_lot=True)
                        logging.info(f"已以新價格 {price} 重新創建零股委託單 {stock_id}")
                else:
                    # 整股模式使用 make_modify_price_obj 及 modify_price
                    try:
                        # 使用 make_modify_price_obj 建立修改價格物件
                        modify_price_obj = self.sdk.stock.make_modify_price_obj(order_record, str(price))
                        # 呼叫 modify_price 方法
                        result = self.sdk.stock.modify_price(self.target_account, modify_price_obj)
                        if not result or not result.is_success:
                            logging.warning(f"update_order: 無法更新委託單 {order_id} 的價格: {result.message if result else '未知錯誤'}")
                        else:
                            logging.info(f"已成功更新委託單 {order_id} 的價格為 {price}")
                    except Exception as e:
                        logging.warning(f"update_order: 修改價格時發生錯誤: {e}")

            # 更新數量
            if quantity is not None:
                try:
                    order_record = order.org_order
                    # 根據市場類型確定數量單位
                    market_type = getattr(order_record, 'market_type', None)
                    is_odd_lot = market_type in [MarketType.IntradayOdd, MarketType.Odd, MarketType.EmgOdd]
                    filled_qty = float(getattr(order_record, 'filled_qty', 0))

                    # 計算新的委託數量 - 注意文檔中說明「修改後數量包含此委託單已成交部份」
                    if is_odd_lot:
                        # 零股利用原本的單位
                        new_qty = int(quantity) + int(filled_qty)
                    else:
                        # 整股需要乘以 1000
                        new_qty = int(quantity * 1000) + int(filled_qty)

                    # 使用 make_modify_quantity_obj 建立修改數量物件
                    modify_qty_obj = self.sdk.stock.make_modify_quantity_obj(order_record, new_qty)
                    # 呼叫 modify_quantity 方法
                    result = self.sdk.stock.modify_quantity(self.target_account, modify_qty_obj)
                    if not result or not result.is_success:
                        logging.warning(f"update_order: 無法更新委託單 {order_id} 的數量: {result.message if result else '未知錯誤'}")
                    else:
                        logging.info(f"已成功更新委託單 {order_id} 的數量為 {quantity} (總數量為 {new_qty})")
                except Exception as e:
                    logging.warning(f"update_order: 修改數量時發生錯誤: {e}")

        except Exception as e:
            logging.warning(f"update_order: 更新委託單 {order_id} 時發生錯誤: {e}")

    def cancel_order(self, order_id):
        """
        取消委託單

        Args:
            order_id (str): 委託單編號
        """
        try:
            # 獲取所有委託單
            orders = self.get_orders()
            if not orders or order_id not in orders:
                logging.warning(f"cancel_order: 找不到委託單 {order_id}")
                return

            order = orders[order_id]
            org_order = order.org_order

            logging.debug(f"#cancel_order order({order_id}): {order}")

            # 檢查是否可以取消
            can_cancel = getattr(org_order, 'can_cancel', True)  # 預設可取消

            if can_cancel:
                try:
                    # 嘗試取消委託單
                    result = self.sdk.stock.cancel_order(self.target_account, org_order)
                    if not result or not result.is_success:
                        logging.warning(f"cancel_order: 無法取消委託單 {order_id}: {result.message if result else '未知錯誤'}")
                    else:
                        logging.info(f"已取消委託單 {order_id}")
                except Exception as e:
                    logging.warning(f"cancel_order: 取消委託單時發生錯誤: {e}")
            else:
                logging.warning(f"cancel_order: 委託單 {order_id} 不可取消")

        except Exception as e:
            logging.warning(f"cancel_order: 取消委託單 {order_id} 時發生錯誤: {e}")

    def _get_order_timestamp(self, order):
        """
        從委託單對象中獲取時間戳

        Args:
            order (object): 富邦 API 返回的委託單對象

        Returns:
            datetime: 委託單時間戳
        """
        try:
            # 嘗試獲取日期和時間
            date_str = getattr(order, 'date', '')
            time_str = getattr(order, 'last_time', getattr(order, 'order_time', ''))

            if not date_str or not time_str:
                return datetime.datetime.now()

            # 解析日期
            if '/' in date_str:
                # 假設格式為 MM/DD 或 YYYY/MM/DD
                date_parts = date_str.split('/')
                if len(date_parts) == 3:
                    year, month, day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
                else:
                    year = datetime.datetime.now().year
                    month, day = int(date_parts[0]), int(date_parts[1])
            elif len(date_str) == 8 and date_str.isdigit():
                # 假設格式為 YYYYMMDD
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
            else:
                # 預設使用當前日期
                now = datetime.datetime.now()
                year, month, day = now.year, now.month, now.day

            # 解析時間
            if ':' in time_str:
                # 假設格式為 HH:MM:SS 或 HH:MM:SS.mmm
                time_parts = time_str.split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1])

                if len(time_parts) > 2:
                    second_parts = time_parts[2].split('.')
                    second = int(second_parts[0])
                    microsecond = int(second_parts[1])*1000 if len(second_parts) > 1 else 0
                else:
                    second, microsecond = 0, 0
            else:
                # 預設時間
                hour, minute, second, microsecond = 0, 0, 0, 0

            return datetime.datetime(year, month, day, hour, minute, second, microsecond)
        except Exception as e:
            logging.warning(f"_get_order_timestamp: 解析時間戳失敗: {e}")
            return datetime.datetime.now()

    def _get_buy_orders(self):
        """
        獲取買入記錄

        Returns:
            list: 買入記錄列表
        """
        buy_orders = []

        try:
            # 獲取持倉
            result = self.sdk.accounting.inventories(self.target_account)
            if not result or not result.is_success or not result.data:
                logging.warning("_get_buy_orders: 無法獲取持倉資訊")
                return buy_orders

            positions = result.data
            market = self.get_market()

            for i, position in enumerate(positions):
                try:
                    # 獲取庫存明細
                    stock_id = getattr(position, 'stock_no', '')
                    if not stock_id:
                        continue

                    # 查詢持倉明細
                    detail_result = self.sdk.accounting.inventory_details(self.target_account, getattr(position, 'id', ''), stock_id)
                    if not detail_result or not detail_result.is_success or not detail_result.data:
                        continue

                    position_details = detail_result.data

                    for detail in position_details:
                        # 判斷數量
                        quantity = getattr(detail, 'qty', 0)
                        if not quantity or float(quantity) == 0:
                            continue

                        # 交易條件
                        order_condition = OrderCondition.CASH
                        trade_type = getattr(position, 'order_type', '')
                        if trade_type == OrderType.Margin:
                            order_condition = OrderCondition.MARGIN_TRADING
                        elif trade_type == OrderType.Short:
                            order_condition = OrderCondition.SHORT_SELLING
                        elif trade_type == OrderType.DayTrade:
                            order_condition = OrderCondition.DAY_TRADING_SHORT

                        # 交易日期
                        date_str = getattr(detail, 'order_date', getattr(detail, 'date', ''))
                        trade_date = datetime.datetime.now()
                        if date_str:
                            try:
                                if len(date_str) == 8 and date_str.isdigit():  # YYYYMMDD
                                    trade_date = datetime.datetime.strptime(date_str, '%Y%m%d')
                                else:
                                    trade_date = datetime.datetime.strptime(date_str, '%Y/%m/%d')
                            except:
                                pass

                        # 產生買入單的續碼
                        order_id = getattr(detail, 'order_no', getattr(detail, 'seq_no', f"fb_buy_{int(time.time())}_{i}"))

                        # 判斷是否為零股
                        is_odd_lot = getattr(detail, 'odd_lot', False) or quantity < 1000
                        divisor = 1 if is_odd_lot else 1000

                        # 轉換為 finlab Order 格式
                        buy_orders.append(Order(
                            order_id=order_id,
                            stock_id=stock_id,
                            action=Action.BUY,
                            price=float(getattr(detail, 'price', 0)),
                            quantity=float(quantity) / divisor,  # 轉換為張
                            filled_quantity=float(quantity) / divisor,  # 轉換為張
                            status=OrderStatus.FILLED,
                            order_condition=order_condition,
                            time=market.market_close_at_timestamp(trade_date).to_pydatetime().replace(hour=13, minute=30),
                            org_order=detail
                        ))
                except Exception as e:
                    logging.warning(f"_get_buy_orders: 處理持倉明細時發生錯誤: {e}")

                # 每處理 10 筆後休息一下，避免請求過於頻繁
                if i % 10 == 9 and i != len(positions) - 1:
                    time.sleep(1)

            return buy_orders
        except Exception as e:
            logging.warning(f"_get_buy_orders: 獲取買入記錄失敗: {e}")
            return []

    def _get_sell_orders(self, start=None, end=None):
        """
        獲取賣出記錄

        Args:
            start (datetime, optional): 開始時間
            end (datetime, optional): 結束時間

        Returns:
            list: 賣出記錄列表
        """
        if start is None:
            start = datetime.datetime.now() - datetime.timedelta(days=90)  # 預設查詢過去 90 天

        if end is None:
            end = datetime.datetime.now()

        # 轉換日期格式為 YYYYMMDD
        if hasattr(start, 'strftime'):
            start_str = start.strftime('%Y%m%d')
        else:
            start_str = start

        if hasattr(end, 'strftime'):
            end_str = end.strftime('%Y%m%d')
        else:
            end_str = end

        try:
            # 獲取已實現損益
            result = self.sdk.accounting.realized_pnl_detail(self.target_account, start_str, end_str)
            if not result or not result.is_success or not result.data:
                logging.warning("_get_sell_orders: 無法獲取已實現損益資訊")
                return []

            profit_loss = result.data
            market = self.get_market()

            sell_orders = []
            for i, record in enumerate(profit_loss):
                try:
                    # 取得日期和代碼
                    date_str = getattr(record, 'date', getattr(record, 'trade_date', ''))
                    if not date_str:
                        continue

                    stock_id = getattr(record, 'stock_no', getattr(record, 'symbol', ''))
                    if not stock_id:
                        continue

                    # 交易條件
                    order_condition = OrderCondition.CASH
                    trade_type = getattr(record, 'trade_type', getattr(record, 'cond', ''))
                    if trade_type == OrderType.Margin:
                        order_condition = OrderCondition.MARGIN_TRADING
                    elif trade_type == OrderType.Short:
                        order_condition = OrderCondition.SHORT_SELLING
                    elif trade_type == OrderType.DayTrade:
                        order_condition = OrderCondition.DAY_TRADING_SHORT

                    # 判斷交易日期
                    trade_date = datetime.datetime.now()
                    try:
                        if len(date_str) == 8 and date_str.isdigit():  # YYYYMMDD
                            trade_date = datetime.datetime.strptime(date_str, '%Y%m%d')
                        else:  # 假設為 YYYY/MM/DD
                            trade_date = datetime.datetime.strptime(date_str, '%Y/%m/%d')
                    except:
                        pass

                    # 判斷是否為零股
                    quantity = getattr(record, 'qty', getattr(record, 'quantity', 0))
                    is_odd_lot = getattr(record, 'odd_lot', False) or quantity < 1000
                    divisor = 1 if is_odd_lot else 1000

                    # 產生賣出單的續碼
                    order_id = getattr(record, 'order_no', getattr(record, 'seq_no', f"fb_sell_{int(time.time())}_{i}"))

                    # 轉換為 finlab Order 格式
                    sell_orders.append(Order(
                        order_id=order_id,
                        stock_id=stock_id,
                        action=Action.SELL,
                        price=float(getattr(record, 'price', 0)),
                        quantity=float(quantity) / divisor,  # 轉換為張
                        filled_quantity=float(quantity) / divisor,  # 轉換為張
                        status=OrderStatus.FILLED,
                        order_condition=order_condition,
                        time=market.market_close_at_timestamp(trade_date).to_pydatetime().replace(hour=13, minute=30),
                        org_order=record
                    ))
                except Exception as e:
                    logging.warning(f"_get_sell_orders: 處理已實現損益紀錄時發生錯誤: {e}")

                # 每處理 20 筆後休息一下，避免請求過於頻繁
                if i % 20 == 19 and i != len(profit_loss) - 1:
                    time.sleep(1)

            return sell_orders
        except Exception as e:
            logging.warning(f"_get_sell_orders: 獲取賣出記錄失敗: {e}")
            return []

    def get_trades(self, start, end):
        """
        獲取歷史交易記錄

        Args:
            start (datetime): 開始時間
            end (datetime): 結束時間

        Returns:
            list: 交易記錄列表
        """
        if isinstance(start, str):
            start = datetime.datetime.fromisoformat(start)

        if isinstance(end, str):
            end = datetime.datetime.fromisoformat(end)

        # 調整日期範圍以符合市場時間
        market = self.get_market()
        start = market.market_close_at_timestamp(start - datetime.timedelta(days=1))
        end = market.market_close_at_timestamp(end)

        # 調整時間範圍為整天
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

        try:
            # 獲取買入記錄
            buy_orders = self._get_buy_orders()

            # 獲取賣出記錄
            sell_orders = self._get_sell_orders(start, end)

            # 合併所有訂單
            orders = buy_orders + sell_orders

            # 過濾時間範圍內的交易
            return [o for o in orders if start <= o.time <= end]
        except Exception as e:
            logging.warning(f"get_trades: 獲取交易記錄失敗: {e}")
            return []

    def support_day_trade_condition(self):
        """
        是否支援當沖交易

        Returns:
            bool: 是否支援當沖交易
        """
        try:
            # 富邦帳戶支援當沖交易的標記
            # 當沖標記從帳戶信息中取得
            if hasattr(self.target_account, 's_mark'):
                # 標記常見值: B, Y, A, S 等 (具體請參考富邦 API 文件)
                day_trade_mark = getattr(self.target_account, 's_mark', '')
                return day_trade_mark in ['B', 'Y', 'A', 'S']

            # 如果沒有標記，嘗試查詢帳戶設定或權限
            info_result = self.sdk.account.get_account_info(self.target_account)
            if info_result and info_result.is_success and info_result.data:
                account_info = info_result.data
                # 從帳戶信息中查找當沖標記
                if hasattr(account_info, 'day_trade_enabled'):
                    return bool(account_info.day_trade_enabled)
                # 可能的其他權限屬性名
                for attr in ['day_trade', 'dayTradeEnabled', 'canDayTrade']:
                    if hasattr(account_info, attr):
                        return bool(getattr(account_info, attr))

            # 預設不支援當沖
            return False
        except Exception as e:
            logging.warning(f"support_day_trade_condition: 檢查當沖支援失敗: {e}")
            # 發生錯誤時預設不支援當沖，以避免風險
            return False

    def sep_odd_lot_order(self):
        """
        是否支援零股交易

        Returns:
            bool: 是否支援零股交易
        """
        # 富邦證券支援零股交易
        return True

    def get_price_info(self):
        """
        獲取價格信息

        Returns:
            dict: 價格信息字典
        """
        try:
            # 從 finlab 導入參考價格資料
            ref = data.get('reference_price')
            return ref.set_index('stock_id').to_dict(orient='index')
        except Exception as e:
            logging.warning(f"get_price_info: 獲取價格信息失敗: {e}")
            # 如果失敗，返回空字典
            return {}

    def get_market(self):
        """
        獲取市場信息

        Returns:
            TWMarket: 台灣市場對象
        """
        # 返回台灣市場對象
        return TWMarket()
