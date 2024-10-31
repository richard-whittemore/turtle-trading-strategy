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
        self.stop_losses = {}

        # for symbol_str in ["AAPL", "JPM", "PFE", "KO", "TSLA", "XOM", "NVDA", "PG", "HD", "DUK"]:
        for symbol_str in ["AAPL"]:
            equity = self.AddEquity(symbol_str, Resolution.Daily)
            self.symbols.append(equity.Symbol)
            self.entry_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.ENTRY_CHANNEL)
            self.exit_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.EXIT_CHANNEL)
            self.atrs[equity.Symbol] = self.ATR(equity.Symbol, self.ATR_PERIOD, MovingAverageType.Simple)
            self.Log(f"Added equity: {equity.Symbol}")

        self.SetWarmUp(timedelta(days=self.ENTRY_CHANNEL))

        self.daily_trades = []
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(16, 0), self.LogPortfolioState)

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
                    self.daily_trades.append(f"Exited Long: {symbol}, Price: {current_price}")
                elif self.Portfolio[symbol].IsShort and current_price >= upper_exit:
                    self.Log(f"Exit signal for short position: {symbol} price {current_price} above exit channel {upper_exit}")
                    self.Liquidate(symbol)
                    self.daily_trades.append(f"Exited Short: {symbol}, Price: {current_price}")
                if self.Portfolio[symbol].Invested:
                    current_price = slice.Bars[symbol].Close
                    if (self.Portfolio[symbol].IsLong and current_price <= self.stop_losses[symbol]) or \
                       (self.Portfolio[symbol].IsShort and current_price >= self.stop_losses[symbol]):
                        self.Log(f"Stop loss hit for {symbol} at {current_price}")
                        self.Liquidate(symbol)
                        self.daily_trades.append(f"Exited position due to stop loss: {symbol}, Price: {current_price}")
                        del self.stop_losses[symbol]

    def EnterLong(self, symbol):
        equity = self.Securities[symbol]
        stop_price = equity.Price - self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        cost = quantity * equity.Price
        if cost > self.Portfolio.Cash:
            self.Log(f"Not enough cash to enter long position in {symbol}. Required: ${cost}, Available: ${self.Portfolio.Cash}")
            return
        self.MarketOrder(symbol, quantity)
        trade_info = f"Entered Long: {symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}"
        self.Log(trade_info)
        self.daily_trades.append(trade_info)
        self.stop_losses[symbol] = stop_price

    def EnterShort(self, symbol):
        equity = self.Securities[symbol]
        stop_price = equity.Price + self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        cost = quantity * equity.Price
        if cost > self.Portfolio.Cash:
            self.Log(f"Not enough cash to enter short position in {symbol}. Required: ${cost}, Available: ${self.Portfolio.Cash}")
            return
        self.MarketOrder(symbol, -quantity)
        trade_info = f"Entered Short: {symbol}, Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}"
        self.Log(trade_info)
        self.daily_trades.append(trade_info)
        self.stop_losses[symbol] = stop_price

    def CalculatePositionSize(self, equity, stop_price):
        risk_amount = self.Portfolio.TotalPortfolioValue * self.RISK_PER_TRADE
        risk_per_share = abs(equity.Price - stop_price)
        if risk_per_share == 0:
            self.Log(f"Risk per share for {equity.Symbol} is 0, using minimum position size")
            return 1  # Return minimum position size instead of 0
        share_quantity = math.floor(risk_amount / risk_per_share)
        return max(1, share_quantity)  # Ensure we always return at least 1 share

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
                stop_loss = self.stop_losses.get(symbol, "No stop loss set")

                # Calculate exit price based on the Turtle Trading rules
                if holding.IsLong:
                    exit_price = self.exit_channels[symbol].Lower.Current.Value
                else:
                    exit_price = self.exit_channels[symbol].Upper.Current.Value

                unrealized_pnl = (current_price - entry_price) * quantity
                unrealized_pnl_percent = (unrealized_pnl / market_value) if market_value != 0 else 0

                self.Log(f"Holding: {symbol}")
                self.Log(f"  Position: {'Long' if holding.IsLong else 'Short'}")
                self.Log(f"  Quantity: {quantity}")
                self.Log(f"  Entry Price: ${entry_price}")
                self.Log(f"  Current Price: ${current_price}")
                self.Log(f"  Market Value: ${market_value}")
                self.Log(f"  Stop Loss: ${stop_loss}")
                self.Log(f"  Unrealized P/L: ${unrealized_pnl:.2f} ({unrealized_pnl_percent:.2%})")
                self.Log(f"  Exit Price: ${exit_price}")

        # Log the day's trades
        self.Log("Today's Trades:")
        if self.daily_trades:
            for trade in self.daily_trades:
                self.Log(f"  {trade}")
        else:
            self.Log("  No trades today")

        # Clear the daily trades for the next day
        self.daily_trades = []

        self.Log("=====================================")

class DonchianChannel(PythonIndicator):
    def __init__(self, symbol, period):
        self.Symbol = symbol
        self.Period = period
        self.Upper = Maximum(f"{symbol}_Upper_{period}", period)
        self.Lower = Minimum(f"{symbol}_Lower_{period}", period)
        self.WarmUpPeriod = period
        self.Time = datetime.min
        self.Value = 0
        self.Samples = 0

    def Update(self, input):
        if input.Symbol != self.Symbol:
            return False
        
        self.Time = input.EndTime
        self.Samples += 1
        
        upper_updated = self.Upper.Update(input.EndTime, input.High)
        lower_updated = self.Lower.Update(input.EndTime, input.Low)
        
        self.Value = (self.Upper.Current.Value + self.Lower.Current.Value) / 2
        
        return self.IsReady

    @property
    def IsReady(self):
        return self.Samples >= self.Period

    @property
    def Current(self):
        return IndicatorDataPoint(self.Time, self.Value)
