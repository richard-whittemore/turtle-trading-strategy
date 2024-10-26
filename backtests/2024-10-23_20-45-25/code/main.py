# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion

class TurtleTradingStrategy(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2010, 1, 1)
        self.SetEndDate(datetime.now())
        self.SetCash(1000000)

        self.symbols = [
            "AAPL", "JPM", "PFE", "KO", "TSLA",
            "XOM", "NVDA", "PG", "HD", "DUK"
        ]

        self.ENTRY_CHANNEL = 20
        self.EXIT_CHANNEL = 10
        self.RISK_PER_TRADE = 0.01
        self.ATR_PERIOD = 20  # Changed from 14 to 20
        self.ATR_MULTIPLIER = 2

        self.entry_channels = {}
        self.exit_channels = {}
        self.atrs = {}

        for symbol in self.symbols:
            equity = self.AddEquity(symbol, Resolution.Daily)
            self.entry_channels[symbol] = self.DONCHIAN(equity.Symbol, self.ENTRY_CHANNEL)
            self.exit_channels[symbol] = self.DONCHIAN(equity.Symbol, self.EXIT_CHANNEL)
            self.atrs[symbol] = self.atr(equity.Symbol, self.ATR_PERIOD, MovingAverageType.Simple)

        self.SetWarmUp(timedelta(days=self.ENTRY_CHANNEL))

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        for symbol in self.symbols:
            if symbol not in slice.Bars:
                continue

            equity = self.Securities[symbol]
            
            if not self.entry_channels[symbol].IsReady or not self.exit_channels[symbol].IsReady or not self.atrs[symbol].IsReady:
                self.Log(f"Indicators not ready for {symbol}")
                continue

            current_price = slice.Bars[symbol].Close
            upper_entry = self.entry_channels[symbol].Upper.Current.Value
            lower_entry = self.entry_channels[symbol].Lower.Current.Value
            upper_exit = self.exit_channels[symbol].Upper.Current.Value
            lower_exit = self.exit_channels[symbol].Lower.Current.Value

            self.Log(f"Symbol: {symbol}, Price: {current_price}, Upper Entry: {upper_entry}, Lower Entry: {lower_entry}")

            if not self.Portfolio[symbol].Invested:
                if current_price >= upper_entry:
                    self.Log(f"Breakout signal: {symbol} price {current_price} above upper channel {upper_entry}")
                    self.EnterLong(equity)
                elif current_price <= lower_entry:
                    self.Log(f"Breakout signal: {symbol} price {current_price} below lower channel {lower_entry}")
                    self.EnterShort(equity)
            else:
                if self.Portfolio[symbol].IsLong and current_price <= lower_exit:
                    self.Log(f"Exit signal for long position: {symbol} price {current_price} below exit channel {lower_exit}")
                    self.Liquidate(symbol)
                elif self.Portfolio[symbol].IsShort and current_price >= upper_exit:
                    self.Log(f"Exit signal for short position: {symbol} price {current_price} above exit channel {upper_exit}")
                    self.Liquidate(symbol)

    def EnterLong(self, equity):
        stop_price = equity.Price - self.atrs[equity.Symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        if quantity > 0:
            self.MarketOrder(equity.Symbol, quantity)
            self.Log(f"Entering Long: {equity.Symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        else:
            self.Log(f"Calculated quantity for long position in {equity.Symbol} is 0, no trade executed")

    def EnterShort(self, equity):
        stop_price = equity.Price + self.atrs[equity.Symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        if quantity > 0:
            self.MarketOrder(equity.Symbol, -quantity)
            self.Log(f"Entering Short: {equity.Symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        else:
            self.Log(f"Calculated quantity for short position in {equity.Symbol} is 0, no trade executed")

    def CalculatePositionSize(self, equity, stop_price):
        risk_amount = self.Portfolio.TotalPortfolioValue * self.RISK_PER_TRADE
        risk_per_share = abs(equity.Price - stop_price)
        if risk_per_share == 0:
            self.Log(f"Risk per share for {equity.Symbol} is 0, cannot calculate position size")
            return 0
        share_quantity = math.floor(risk_amount / risk_per_share)
        return share_quantity

    def DONCHIAN(self, symbol, period):
        return DonchianChannel(f"{symbol}_{period}", period, symbol)

class DonchianChannel(PythonIndicator):
    def __init__(self, name, period, symbol):
        self.Name = name
        self.Upper = Maximum(f"{name}_Upper", period)
        self.Lower = Minimum(f"{name}_Lower", period)
        self.WarmUpPeriod = period
        self.Symbol = symbol

    def Update(self, input):
        if input.Symbol != self.Symbol:
            return False
        
        upper_updated = self.Upper.Update(input.High)
        lower_updated = self.Lower.Update(input.Low)
        
        return upper_updated and lower_updated
