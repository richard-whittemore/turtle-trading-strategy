# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion

class TurtleTradingStrategy(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2020, 6, 29)  # TSLA's IPO date
        self.SetEndDate(datetime.now())
        self.SetCash(100000)

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

        self.SetWarmUp(timedelta(days=self.ENTRY_CHANNEL * 2))
        
        # Schedule the LogPortfolioState method to run at 16:00 (4 PM) every day
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(16, 0), self.LogPortfolioState)

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        all_indicators_ready = all(
            self.entry_channels[symbol].IsReady and
            self.exit_channels[symbol].IsReady and
            self.atrs[symbol].IsReady
            for symbol in self.symbols
        )

        if not all_indicators_ready:
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
            self.Log(f"Entered Long: {symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        else:
            self.Log(f"Calculated quantity for long position in {symbol} is 0, no trade executed")

    def EnterShort(self, symbol):
        equity = self.Securities[symbol]
        stop_price = equity.Price + self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        if quantity > 0:
            self.MarketOrder(symbol, -quantity)
            self.Log(f"Entered Short: {symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
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

    def LogPortfolioState(self):
        # Log overall portfolio state
        self.Log(f"===== Portfolio State as of {self.Time} =====")
        self.Log(f"Total Portfolio Value: ${self.Portfolio.TotalPortfolioValue}")
        self.Log(f"Cash on Hand: ${self.Portfolio.Cash}")
        total_equity_value = sum(holding.AbsoluteHoldingsValue for holding in self.Portfolio.Values if holding.Invested)
        self.Log(f"Total Equity Value: ${total_equity_value}")

        # Log details for each holding
        for symbol, holding in self.Portfolio.items():
            if holding.Invested:
                entry_price = holding.AveragePrice
                current_price = self.Securities[symbol].Price
                quantity = holding.Quantity
                market_value = holding.AbsoluteHoldingsValue

                # Calculate exit price based on the Turtle Trading rules
                if holding.IsLong:
                    exit_price = self.exit_channels[symbol].Lower.Current.Value
                else:
                    exit_price = self.exit_channels[symbol].Upper.Current.Value

                self.Log(f"Holding: {symbol}")
                self.Log(f"  Position: {'Long' if holding.IsLong else 'Short'}")
                self.Log(f"  Quantity: {quantity}")
                self.Log(f"  Entry Price: ${entry_price}")
                self.Log(f"  Current Price: ${current_price}")
                self.Log(f"  Market Value: ${market_value}")
                self.Log(f"  Unrealized P/L: ${holding.UnrealizedProfitLoss} ({holding.UnrealizedProfitLoss / market_value:.2%})")
                self.Log(f"  Exit Price: ${exit_price}")

        self.Log("=====================================")

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
