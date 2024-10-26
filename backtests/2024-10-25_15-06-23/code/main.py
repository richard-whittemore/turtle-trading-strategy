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

        # Define constants
        self.ENTRY_CHANNEL = 20
        self.EXIT_CHANNEL = 10
        self.RISK_PER_TRADE = 0.01
        self.ATR_PERIOD = 20
        self.ATR_MULTIPLIER = 2

        self.symbols = []
        self.entry_channels = {}
        self.exit_channels = {}
        self.atrs = {}

        for symbol_str in ["AAPL", "JPM", "PFE", "KO", "TSLA", "XOM", "NVDA", "PG", "HD", "DUK"]:
            equity = self.AddEquity(symbol_str, Resolution.Daily)
            self.symbols.append(equity.Symbol)
            self.entry_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.ENTRY_CHANNEL)
            self.exit_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.EXIT_CHANNEL)
            self.atrs[equity.Symbol] = self.ATR(equity.Symbol, self.ATR_PERIOD, MovingAverageType.Simple)
            self.Log(f"Added equity: {equity.Symbol}")

        self.SetWarmUp(timedelta(days=self.ENTRY_CHANNEL))

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        self.Log(f"Processing slice at {slice.Time}")
        self.Log(f"Symbols in slice: {', '.join(str(symbol) for symbol in slice.Keys)}")
        
        for symbol in self.symbols:
            if symbol not in self.Securities:
                self.Log(f"Symbol {symbol} not found in Securities dictionary")
                continue

            if symbol not in slice.Bars:
                self.Log(f"No data for {symbol} in this slice")
                continue

            equity = self.Securities[symbol]
            
            self.Log(f"Data for {symbol}: Open={slice.Bars[symbol].Open}, High={slice.Bars[symbol].High}, Low={slice.Bars[symbol].Low}, Close={slice.Bars[symbol].Close}")

            # Update custom indicators
            self.entry_channels[symbol].Update(slice.Bars[symbol])
            self.exit_channels[symbol].Update(slice.Bars[symbol])

            if not self.entry_channels[symbol].IsReady or not self.exit_channels[symbol].IsReady or not self.atrs[symbol].IsReady:
                self.Log(f"Indicators not ready for {symbol}. Entry: {self.entry_channels[symbol].IsReady}, Exit: {self.exit_channels[symbol].IsReady}, ATR: {self.atrs[symbol].IsReady}")
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
                    self.EnterLong(symbol)
                elif current_price <= lower_entry:
                    self.Log(f"Breakout signal: {symbol} price {current_price} below lower channel {lower_entry}")
                    self.EnterShort(symbol)
            else:
                if self.Portfolio[symbol].IsLong and current_price <= lower_exit:
                    self.Log(f"Exit signal for long position: {symbol} price {current_price} below exit channel {lower_exit}")
                    self.Liquidate(symbol)
                elif self.Portfolio[symbol].IsShort and current_price >= upper_exit:
                    self.Log(f"Exit signal for short position: {symbol} price {current_price} above exit channel {upper_exit}")
                    self.Liquidate(symbol)

    def EnterLong(self, symbol):
        equity = self.Securities[symbol]
        stop_price = equity.Price - self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        if quantity > 0:
            self.MarketOrder(symbol, quantity)
            self.Log(f"Entering Long: {symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        else:
            self.Log(f"Calculated quantity for long position in {symbol} is 0, no trade executed")

    def EnterShort(self, symbol):
        equity = self.Securities[symbol]
        stop_price = equity.Price + self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        if quantity > 0:
            self.MarketOrder(symbol, -quantity)
            self.Log(f"Entering Short: {symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        else:
            self.Log(f"Calculated quantity for short position in {symbol} is 0, no trade executed")

    def CalculatePositionSize(self, equity, stop_price):
        risk_amount = self.Portfolio.TotalPortfolioValue * self.RISK_PER_TRADE
        risk_per_share = abs(equity.Price - stop_price)
        if risk_per_share == 0:
            self.Log(f"Risk per share for {equity.Symbol} is 0, cannot calculate position size")
            return 0
        share_quantity = math.floor(risk_amount / risk_per_share)
        return share_quantity

    def DONCHIAN(self, symbol, period):
        return DonchianChannel(symbol, period)

class DonchianChannel(PythonIndicator):
    def __init__(self, symbol, period):
        self.Symbol = symbol
        self.Period = period
        self.Upper = Maximum(f"{symbol}_Upper_{period}", period)
        self.Lower = Minimum(f"{symbol}_Lower_{period}", period)
        self.WarmUpPeriod = period

    def Update(self, input):
        self.Upper.Update(input.EndTime, input.High)
        self.Lower.Update(input.EndTime, input.Low)
        return self.IsReady

    @property
    def IsReady(self):
        return self.Upper.IsReady and self.Lower.IsReady

    @property
    def Current(self):
        return IndicatorDataPoint(self.Upper.Current.Time, (self.Upper.Current.Value + self.Lower.Current.Value) / 2)
