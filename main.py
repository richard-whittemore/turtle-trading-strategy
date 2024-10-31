# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion

class TurtleTradingStrategy(QCAlgorithm):

    def Initialize(self):
        """
        Initialize the algorithm with start and end dates, initial cash, and strategy parameters.
        Set up the equities to trade and initialize indicators and stop losses.
        """
        self.SetStartDate(2010, 1, 1)
        self.SetEndDate(datetime.now())
        self.SetCash(1000000)

        # Define constants - Updated for System 2
        self.ENTRY_CHANNEL = 55  # Changed from 20 to 55
        self.EXIT_CHANNEL = 20   # Changed from 10 to 20
        self.RISK_PER_TRADE = 0.01
        self.ATR_PERIOD = 20
        self.ATR_MULTIPLIER = 2

        self.symbols = []
        self.entry_channels = {}
        self.exit_channels = {}
        self.atrs = {}
        self.stop_losses = {}
        self.entry_prices = {}  # Dictionary of lists to track multiple entry prices
        self.position_units = {}  # Track number of units for each position
        self.last_add_price = {}  # Track the price at which we last added to position
        self.MAX_UNITS = 4  # Maximum number of units per position

        # Add equities to trade
        for symbol_str in ["AAPL"]:
            equity = self.AddEquity(symbol_str, Resolution.Daily)
            self.symbols.append(equity.Symbol)
            self.entry_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.ENTRY_CHANNEL)
            self.exit_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.EXIT_CHANNEL)
            self.atrs[equity.Symbol] = self.ATR(equity.Symbol, self.ATR_PERIOD, MovingAverageType.Simple)
            self.Log(f"Added equity: {equity.Symbol}")

        # Increase warm-up period to account for longer entry channel
        self.SetWarmUp(timedelta(days=self.ENTRY_CHANNEL))

        self.daily_trades = []
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(16, 0), self.LogPortfolioState)

    def OnData(self, slice):
        """
        Handle new data slice. Check for breakout signals and manage open positions.
        """
        if self.IsWarmingUp:
            return

        self.Log(f"Processing slice at {slice.Time}")
        self.Log(f"Symbols in slice: {', '.join(str(symbol) for symbol in slice.Keys)}")
        
        for symbol in self.symbols:
            # Add validation check for stop loss
            if self.Portfolio[symbol].Invested and symbol not in self.stop_losses:
                self.Log(f"ERROR: Position exists for {symbol} but no stop loss is set!")
                self.Liquidate(symbol)  # Emergency exit if we somehow have a position without a stop loss
                continue

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
            donchain_long_entry = self.entry_channels[symbol].Upper.Current.Value
            donchain_short_entry = self.entry_channels[symbol].Lower.Current.Value
            donchain_short_exit = self.exit_channels[symbol].Upper.Current.Value
            donchain_long_exit = self.exit_channels[symbol].Lower.Current.Value

            self.Log(f"Symbol: {symbol}, Price: {current_price}, Donchain Long Entry: {donchain_long_entry}, Donchain Short Entry: {donchain_short_entry}")

            if not self.Portfolio[symbol].Invested:
                if current_price >= donchain_long_entry:
                    self.Log(f"Breakout signal: {symbol} price {current_price} above long entry {donchain_long_entry}")
                    self.EnterLong(symbol)
                elif current_price <= donchain_short_entry:
                    self.Log(f"Breakout signal: {symbol} price {current_price} below short entry {donchain_short_entry}")
                    self.EnterShort(symbol)
            else:
                if self.Portfolio[symbol].IsLong and current_price <= donchain_long_exit:
                    position = self.Portfolio[symbol]
                    profit_loss = (current_price - position.AveragePrice) * position.Quantity
                    profit_loss_percent = (profit_loss / (position.AveragePrice * position.Quantity)) * 100
                    exit_message = (f"Exited Long: {symbol}, Price: {current_price}, "
                                  f"P/L: ${profit_loss:.2f} ({profit_loss_percent:.2f}%)")
                    self.Log(f"Exit signal for long position: {symbol} price {current_price} below Donchainlong exit {donchain_long_exit}")
                    self.Log(exit_message)
                    
                    if symbol not in self.stop_losses:
                        self.Log(f"WARNING: Liquidating position for {symbol} that had no stop loss!")
                    else:
                        del self.stop_losses[symbol]
                        
                    self.Liquidate(symbol)
                    self.daily_trades.append(exit_message)

                elif self.Portfolio[symbol].IsShort and current_price >= donchain_short_exit:
                    position = self.Portfolio[symbol]
                    profit_loss = (position.AveragePrice - current_price) * abs(position.Quantity)
                    profit_loss_percent = (profit_loss / (position.AveragePrice * abs(position.Quantity))) * 100
                    exit_message = (f"Exited Short: {symbol}, Price: {current_price}, "
                                  f"P/L: ${profit_loss:.2f} ({profit_loss_percent:.2f}%)")
                    self.Log(f"Exit signal for short position: {symbol} price {current_price} above short exit {donchain_short_exit}")
                    self.Log(exit_message)
                    
                    if symbol not in self.stop_losses:
                        self.Log(f"WARNING: Liquidating position for {symbol} that had no stop loss!")
                    else:
                        del self.stop_losses[symbol]
                        
                    self.Liquidate(symbol)
                    self.daily_trades.append(exit_message)

                # Modified stop loss check
                if self.Portfolio[symbol].Invested and symbol in self.stop_losses:
                    current_price = slice.Bars[symbol].Close
                    if ((self.Portfolio[symbol].IsLong and current_price <= self.stop_losses[symbol]) or 
                        (self.Portfolio[symbol].IsShort and current_price >= self.stop_losses[symbol])):
                        position = self.Portfolio[symbol]
                        if position.IsLong:
                            profit_loss = (current_price - position.AveragePrice) * position.Quantity
                        else:
                            profit_loss = (position.AveragePrice - current_price) * abs(position.Quantity)
                        profit_loss_percent = (profit_loss / (position.AveragePrice * abs(position.Quantity))) * 100
                        exit_message = (f"Exited position due to stop loss: {symbol}, Price: {current_price}, "
                                      f"P/L: ${profit_loss:.2f} ({profit_loss_percent:.2f}%)")
                        self.Log(f"Stop loss hit for {symbol} at {current_price}")
                        self.Log(exit_message)
                        self.Liquidate(symbol)
                        self.daily_trades.append(exit_message)
                        del self.stop_losses[symbol]

                # Check for adding to position (pyramiding)
                if self.Portfolio[symbol].Invested:
                    current_units = self.position_units.get(symbol, 1)
                    if current_units < self.MAX_UNITS:
                        if self.Portfolio[symbol].IsLong:
                            last_price = self.last_add_price.get(symbol, self.entry_prices[symbol][-1])
                            if current_price >= last_price + self.atrs[symbol].Current.Value:
                                self.AddToLong(symbol)
                        elif self.Portfolio[symbol].IsShort:
                            last_price = self.last_add_price.get(symbol, self.entry_prices[symbol][-1])
                            if current_price <= last_price - self.atrs[symbol].Current.Value:
                                self.AddToShort(symbol)

    def EnterLong(self, symbol):
        """
        Enter a long position for the given symbol. Calculate position size and set stop loss.
        """
        equity = self.Securities[symbol]
        stop_price = equity.Price - self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        cost = quantity * equity.Price
        if cost > self.Portfolio.Cash:
            self.Log(f"Not enough cash to enter long position in {symbol}. Required: ${cost}, Available: ${self.Portfolio.Cash}")
            return
        entry_price = equity.Price  # Capture the exact entry price
        self.MarketOrder(symbol, quantity)
        self.entry_prices[symbol] = [entry_price]  # Initialize as list with first entry price
        self.position_units[symbol] = 1
        self.last_add_price[symbol] = entry_price
        trade_info = f"Entered Long: {symbol}, Quantity: {quantity}, Entry Price: ${entry_price}, Stop: ${stop_price}"
        self.Log(trade_info)
        self.daily_trades.append(trade_info)
        self.stop_losses[symbol] = stop_price

    def EnterShort(self, symbol):
        """
        Enter a short position for the given symbol. Calculate position size and set stop loss.
        """
        equity = self.Securities[symbol]
        stop_price = equity.Price + self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        cost = quantity * equity.Price
        if cost > self.Portfolio.Cash:
            self.Log(f"Not enough cash to enter short position in {symbol}. Required: ${cost}, Available: ${self.Portfolio.Cash}")
            return
        entry_price = equity.Price  # Capture the exact entry price
        self.MarketOrder(symbol, -quantity)
        self.entry_prices[symbol] = [entry_price]  # Initialize as list with first entry price
        self.position_units[symbol] = 1
        self.last_add_price[symbol] = entry_price
        trade_info = f"Entered Short: {symbol}, Quantity: {quantity}, Entry Price: ${entry_price}, Stop: ${stop_price}"
        self.Log(trade_info)
        self.daily_trades.append(trade_info)
        self.stop_losses[symbol] = stop_price

    def CalculatePositionSize(self, equity, stop_price):
        """
        Calculate the position size based on risk per trade and stop loss distance.
        """
        risk_amount = self.Portfolio.TotalPortfolioValue * self.RISK_PER_TRADE
        risk_per_share = abs(equity.Price - stop_price)
        if risk_per_share == 0:
            self.Log(f"Risk per share for {equity.Symbol} is 0, using minimum position size")
            return 1  # Return minimum position size instead of 0
        share_quantity = math.floor(risk_amount / risk_per_share)
        return max(1, share_quantity)  # Ensure we always return at least 1 share

    def DONCHIAN(self, symbol, period):
        """
        Create a Donchian Channel indicator for the given symbol and period.
        """
        return DonchianChannel(symbol, period)

    def LogPortfolioState(self):
        """
        Log the current state of the portfolio, including cash, equity value, and details of each holding.
        """
        # Log overall portfolio state
        self.Log(f"===== Portfolio State as of {self.Time} =====")
        self.Log(f"Total Portfolio Value: ${self.Portfolio.TotalPortfolioValue}")
        self.Log(f"Cash on Hand: ${self.Portfolio.Cash}")
        total_equity_value = sum(holding.AbsoluteHoldingsValue for holding in self.Portfolio.Values if holding.Invested)
        self.Log(f"Total Equity Value: ${total_equity_value}")

        # Log details for each holding
        for symbol, holding in self.Portfolio.items():
            if holding.Invested:
                if symbol not in self.stop_losses:
                    self.Log(f"WARNING: Position exists for {symbol} but no stop loss is set!")
                    continue

                entry_price = holding.AveragePrice
                current_price = self.Securities[symbol].Price
                quantity = holding.Quantity
                market_value = holding.AbsoluteHoldingsValue
                stop_loss = self.stop_losses[symbol]  # We know it exists now

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

    def AddToLong(self, symbol):
        """
        Add a unit to an existing long position when price moves up by 1N (1 ATR)
        """
        equity = self.Securities[symbol]
        stop_price = equity.Price - self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        
        if quantity * equity.Price > self.Portfolio.Cash:
            self.Log(f"Not enough cash to add to long position in {symbol}")
            return

        self.MarketOrder(symbol, quantity)
        
        # Update tracking variables
        if symbol not in self.entry_prices:
            self.entry_prices[symbol] = []
        self.entry_prices[symbol].append(equity.Price)
        self.last_add_price[symbol] = equity.Price
        self.position_units[symbol] = self.position_units.get(symbol, 1) + 1
        self.stop_losses[symbol] = stop_price  # Update stop loss for entire position

        trade_info = (f"Added to Long: {symbol}, Unit: {self.position_units[symbol]}, "
                     f"Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        self.Log(trade_info)
        self.daily_trades.append(trade_info)

    def AddToShort(self, symbol):
        """
        Add a unit to an existing short position when price moves down by 1N (1 ATR)
        """
        equity = self.Securities[symbol]
        stop_price = equity.Price + self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        
        if quantity * equity.Price > self.Portfolio.Cash:
            self.Log(f"Not enough cash to add to short position in {symbol}")
            return

        self.MarketOrder(symbol, -quantity)
        
        # Update tracking variables
        if symbol not in self.entry_prices:
            self.entry_prices[symbol] = []
        self.entry_prices[symbol].append(equity.Price)
        self.last_add_price[symbol] = equity.Price
        self.position_units[symbol] = self.position_units.get(symbol, 1) + 1
        self.stop_losses[symbol] = stop_price  # Update stop loss for entire position

        trade_info = (f"Added to Short: {symbol}, Unit: {self.position_units[symbol]}, "
                     f"Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        self.Log(trade_info)
        self.daily_trades.append(trade_info)

class DonchianChannel(PythonIndicator):
    def __init__(self, symbol, period):
        """
        Initialize a Donchian Channel indicator with the given symbol and period.
        """
        self.Symbol = symbol
        self.Period = period
        self.Upper = Maximum(f"{symbol}_Upper_{period}", period)
        self.Lower = Minimum(f"{symbol}_Lower_{period}", period)
        self.WarmUpPeriod = period
        self.Time = datetime.min
        self.Value = 0
        self.Samples = 0

    def Update(self, input):
        """
        Update the Donchian Channel with new data.
        """
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
        """
        Check if the Donchian Channel is ready (has enough data).
        """
        return self.Samples >= self.Period

    @property
    def Current(self):
        """
        Get the current value of the Donchian Channel.
        """
        return IndicatorDataPoint(self.Time, self.Value)
