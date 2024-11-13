# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion

class TurtleTradingStrategy(QCAlgorithm):

    # TODO: NEED TO SAVE TO STATE 
    # TODO: NEED TO CONSIDER TESTING

    def Initialize(self):
        """
        Initialize the algorithm with start and end dates, initial cash, and strategy parameters.
        Set up the equities to trade and initialize indicators and stop losses.
        """
        self.SetStartDate(2010, 1, 1)    # TODO: Production version won't need this
        self.SetEndDate(datetime.now())  # TODO: Production version won't need this
        self.SetCash(1000000)            # TODO: Change this to read directly from the account

        # Define constants 
        self.ENTRY_CHANNEL = 55      # Per Turtle Trading Strategy System 2 
        self.EXIT_CHANNEL = 20       # Per Turtle Trading Strategy System 2 
        self.RISK_PER_TRADE = 0.02   # Per Turtle Trading Strategy default of risking 2% of account equity per trade
        self.ATR_PERIOD = 20         # Per Turtle Trading Strategy default of 20 days
        self.ATR_MULTIPLIER = 2      # Per Turtle Trading Strategy default of 2 ATRs (i.e. 2N) 

        # Technical Indicators - Used for generating trading signals and calculating volatility
        self.entry_channels = {}  # Dictionary[Symbol, DonchianChannel] - Tracks entry channel indicators for each symbol
        self.exit_channels = {}   # Dictionary[Symbol, DonchianChannel] - Tracks exit channel indicators for each symbol
        self.atrs = {}            # Dictionary[Symbol, ATR] - Tracks Average True Range indicators for each symbol

        # Position Management - Track active positions and their characteristics
        self.stop_losses = {}     # Dictionary[Symbol, float] - Tracks stop loss prices for each position
        self.entry_prices = {}    # Dictionary[Symbol, List[float]] - Tracks entry prices for each unit of a position
        self.position_units = {}  # Dictionary[Symbol, int] - Tracks number of units held for each position (1-4 units)

        # Trade Management - Track trading activity and enforce trading rules
        self.last_add_price = {}  # Dictionary[Symbol, float] - Tracks the price at which we last added a unit to a position
        self.MAX_UNITS = 4        # int - Maximum number of units allowed per position per Turtle Trading rules ## TODO: Make this dynamic per Turtle Trading rules
        self.daily_trades = []    # List[str] - Tracks trades made during the current day for daily reporting

        # Symbol Management - Track which symbols we're trading
        self.symbols = []         # List[Symbol] - Collection of trading symbols (e.g., equities) being traded by the algorithm

        # Initialize trading symbols and their technical indicators
        for symbol_str in ["AAPL"]: # TODO: Make this dynamic - Choose diversified set of symbols that meet breakout criteria (ie. Sublime Trading Criteria)
            # Add the equity to our universe with daily resolution data
            equity = self.AddEquity(symbol_str, Resolution.Daily)
            
            # Store the Symbol object for future reference
            self.symbols.append(equity.Symbol)
            
            # Create and store technical indicators for this symbol:
            # 1. Entry channel (55-day Donchian) for generating entry signals
            self.entry_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.ENTRY_CHANNEL)
            
            # 2. Exit channel (20-day Donchian) for generating exit signals
            self.exit_channels[equity.Symbol] = self.DONCHIAN(equity.Symbol, self.EXIT_CHANNEL)
            
            # 3. Average True Range (ATR) for volatility measurement and position sizing
            self.atrs[equity.Symbol] = self.ATR(equity.Symbol, self.ATR_PERIOD, MovingAverageType.Simple)
            
            # Log the addition of this symbol to our universe
            self.Log(f"Added equity: {equity.Symbol}")

        # Increase warm-up period to account for longer entry channel
        self.SetWarmUp(timedelta(days=self.ENTRY_CHANNEL))

        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(16, 0), self.LogPortfolioState) # TODO: Too much logging - need to reduce this

    def OnData(self, slice):
        """
        Process new market data and manage trading positions.
        This is the main trading logic implementation of the Turtle Trading Strategy.

        The method performs the following steps for each symbol:
        1. Skip processing if still in warm-up period
        2. Validate position integrity (ensure stop losses exist)
        3. Update technical indicators with new data
        4. Check if indicators are ready for trading decisions
        5. Process trading signals:
            a. For non-invested positions:
               - Enter long if price breaks above 55-day high
               - Enter short if price breaks below 55-day low
            b. For existing positions:
               - Exit long if price breaks below 20-day low
               - Exit short if price breaks above 20-day high
               - Exit if stop loss is hit  #TODO: Perhaps it might be better to use a 'STOP MARKET ORDER' when entering a position
               - Add units (pyramid) if price moves favorably by 1N (1 ATR)

        Args:
            slice: Contains market data for the current time step

        Trading Rules Implemented:
        - System 2 breakout periods (55 days for entry, 20 days for exit)
        - Position sizing based on N (ATR)
        - Stop losses at 2N from entry
        - Maximum 4 units per position
        - Add units when price moves by 1N in favorable direction
        """
        # Skip processing during warm-up period
        if self.IsWarmingUp:
            return

        # Log current processing time and available symbols
        self.Log(f"Processing slice at {slice.Time}")
        self.Log(f"Symbols in slice: {', '.join(str(symbol) for symbol in slice.Keys)}")
        
        # Process each symbol in our trading universe
        for symbol in self.symbols:
            # SECTION 1: VALIDATION CHECKS
            # Ensure position integrity - check for positions without stop losses
            if self.Portfolio[symbol].Invested and symbol not in self.stop_losses:
                self.Log(f"ERROR: Position exists for {symbol} but no stop loss is set!")
                self.Liquidate(symbol)  # Emergency exit if we somehow have a position without a stop loss
                continue

            # Verify symbol exists in our Securities collection
            # self.Securities is a QuantConnect dictionary that contains all securities we can trade in our algorithm. It's populated when we call self.AddEquity() in the Initialize method.
            if symbol not in self.Securities:
                self.Log(f"Symbol {symbol} not found in Securities dictionary")
                continue

            # Verify we have current market data for this symbol
            if symbol not in slice.Bars:
                self.Log(f"No data for {symbol} in this slice")
                continue

            # SECTION 2: DATA PREPARATION
            # Log current price data
            self.Log(f"Data for {symbol}: Open={slice.Bars[symbol].Open}, High={slice.Bars[symbol].High}, Low={slice.Bars[symbol].Low}, Close={slice.Bars[symbol].Close}")

            # Update technical indicators with latest price data
            self.entry_channels[symbol].Update(slice.Bars[symbol])
            self.exit_channels[symbol].Update(slice.Bars[symbol])
            # Note: ATR indicator (self.atrs[symbol]) is updated automatically by QuantConnect

            # Verify indicators are ready before making trading decisions
            if not self.entry_channels[symbol].IsReady or not self.exit_channels[symbol].IsReady or not self.atrs[symbol].IsReady:
                self.Log(f"Indicators not ready for {symbol}. Entry: {self.entry_channels[symbol].IsReady}, Exit: {self.exit_channels[symbol].IsReady}, ATR: {self.atrs[symbol].IsReady}")
                continue

            # SECTION 3: CALCULATE TRADING SIGNALS
            # Get current price and breakout levels
            # TODO: USING THE BUILT-IN DONCHAIN CHANNEL INDICATORS INSTEAD OF CUSTOM ONES
            current_price = slice.Bars[symbol].Close
            donchain_long_entry = self.entry_channels[symbol].Upper.Current.Value    # 55-day high for long entries
            donchain_short_entry = self.entry_channels[symbol].Lower.Current.Value   # 55-day low for short entries
            donchain_short_exit = self.exit_channels[symbol].Upper.Current.Value     # 20-day high for short exits
            donchain_long_exit = self.exit_channels[symbol].Lower.Current.Value      # 20-day low for long exits

            # Log current price and entry levels
            self.Log(f"Symbol: {symbol}, Price: {current_price}, Donchain Long Entry: {donchain_long_entry}, Donchain Short Entry: {donchain_short_entry}")

            # SECTION 4: ENTRY LOGIC
            # Check for new position entry signals if not currently invested
            if not self.Portfolio[symbol].Invested:
                # Check for long entry - price breaks above 55-day high
                if current_price >= donchain_long_entry:
                    self.Log(f"Breakout signal: {symbol} price {current_price} above long entry {donchain_long_entry}")
                    self.EnterLong(symbol)
                # Check for short entry - price breaks below 55-day low
                elif current_price <= donchain_short_entry:
                    self.Log(f"Breakout signal: {symbol} price {current_price} below short entry {donchain_short_entry}")
                    self.EnterShort(symbol)

            # SECTION 5: POSITION MANAGEMENT
            else:
                # SECTION 5A: EXIT SIGNALS
                # Check for long position exit - price breaks below 20-day low
                if self.Portfolio[symbol].IsLong and current_price <= donchain_long_exit:
                    # Calculate and log profit/loss for the exit
                    position = self.Portfolio[symbol]
                    profit_loss = (current_price - position.AveragePrice) * position.Quantity
                    profit_loss_percent = (profit_loss / (position.AveragePrice * position.Quantity)) * 100
                    exit_message = (f"Exited Long: {symbol}, Price: {current_price}, "
                                  f"P/L: ${profit_loss:.2f} ({profit_loss_percent:.2f}%)")
                    self.Log(f"Exit signal for long position: {symbol} price {current_price} below Donchainlong exit {donchain_long_exit}")
                    self.Log(exit_message)
                    self.Liquidate(symbol)
                    self.CleanupPosition(symbol)  # Clean up all tracking variables
                    self.daily_trades.append(exit_message)

                # Check for short position exit - price breaks above 20-day high
                elif self.Portfolio[symbol].IsShort and current_price >= donchain_short_exit:
                    # Calculate and log profit/loss for the exit
                    position = self.Portfolio[symbol]
                    profit_loss = (position.AveragePrice - current_price) * abs(position.Quantity)
                    profit_loss_percent = (profit_loss / (position.AveragePrice * abs(position.Quantity))) * 100
                    exit_message = (f"Exited Short: {symbol}, Price: {current_price}, "
                                  f"P/L: ${profit_loss:.2f} ({profit_loss_percent:.2f}%)")
                    self.Log(f"Exit signal for short position: {symbol} price {current_price} above short exit {donchain_short_exit}")
                    self.Log(exit_message)
                    self.Liquidate(symbol)
                    self.CleanupPosition(symbol)  # Clean up all tracking variables
                    self.daily_trades.append(exit_message)

                # SECTION 5B: STOP LOSS CHECK
                # Check if price has hit our stop loss level
                if self.Portfolio[symbol].Invested and symbol in self.stop_losses:
                    current_price = slice.Bars[symbol].Close
                    if ((self.Portfolio[symbol].IsLong and current_price <= self.stop_losses[symbol]) or 
                        (self.Portfolio[symbol].IsShort and current_price >= self.stop_losses[symbol])):
                        # Calculate and log profit/loss for the stop loss exit
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
                        self.CleanupPosition(symbol)  # Clean up all tracking variables
                        self.daily_trades.append(exit_message)
                        del self.stop_losses[symbol]

                # SECTION 5C: POSITION SCALING (PYRAMIDING)
                # Check if we can add units to our position
                if self.Portfolio[symbol].Invested:
                    current_units = self.position_units[symbol]
                    if current_units < self.MAX_UNITS:
                        # Add to long position if price moves up by 1N (1 ATR)
                        if self.Portfolio[symbol].IsLong:
                            last_price = self.last_add_price.get(symbol, self.entry_prices[symbol][-1])
                            if current_price >= last_price + self.atrs[symbol].Current.Value:
                                self.AddToLong(symbol)
                        # Add to short position if price moves down by 1N (1 ATR)
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
        Add a unit to an existing long position when price moves up by 1N (1 ATR).
        This implements the pyramiding rules of the Turtle Trading strategy.

        Args:
            symbol: The trading symbol to add units to

        Position Management:
        1. Calculate new stop price based on current ATR
        2. Calculate position size based on risk parameters
        3. Place market order for additional unit
        4. Update tracking variables:
           - Add new entry price to history
           - Update last price for future pyramiding
           - Increment unit counter
           - Update stop loss for entire position
        """
        equity = self.Securities[symbol]
        stop_price = equity.Price - self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        
        # Check if we have enough cash for the additional unit
        if quantity * equity.Price > self.Portfolio.Cash:
            self.Log(f"Not enough cash to add to long position in {symbol}")
            return

        # Place the order for the additional unit
        self.MarketOrder(symbol, quantity)
        
        # Update position tracking variables
        if symbol not in self.entry_prices:
            self.entry_prices[symbol] = []
        self.entry_prices[symbol].append(equity.Price)  # Record this unit's entry price
        self.last_add_price[symbol] = equity.Price      # Update price level for next pyramid entry
        self.position_units[symbol] = self.position_units[symbol] + 1  # Increment unit counter
        self.stop_losses[symbol] = stop_price  # Update stop loss for entire position

        # Log the addition to the position
        trade_info = (f"Added to Long: {symbol}, Unit: {self.position_units[symbol]}, "
                     f"Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        self.Log(trade_info)
        self.daily_trades.append(trade_info)

    def AddToShort(self, symbol):
        """
        Add a unit to an existing short position when price moves down by 1N (1 ATR).
        This implements the pyramiding rules of the Turtle Trading strategy.

        Args:
            symbol: The trading symbol to add units to

        Position Management:
        1. Calculate new stop price based on current ATR
        2. Calculate position size based on risk parameters
        3. Place market order for additional unit
        4. Update tracking variables:
           - Add new entry price to history
           - Update last price for future pyramiding
           - Increment unit counter
           - Update stop loss for entire position
        """
        equity = self.Securities[symbol]
        stop_price = equity.Price + self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER
        quantity = self.CalculatePositionSize(equity, stop_price)
        
        # Check if we have enough cash for the additional unit
        if quantity * equity.Price > self.Portfolio.Cash:
            self.Log(f"Not enough cash to add to short position in {symbol}")
            return

        # Place the order for the additional unit
        self.MarketOrder(symbol, -quantity)
        
        # Update position tracking variables
        if symbol not in self.entry_prices:
            self.entry_prices[symbol] = []
        self.entry_prices[symbol].append(equity.Price)  # Record this unit's entry price
        self.last_add_price[symbol] = equity.Price      # Update price level for next pyramid entry
        self.position_units[symbol] = self.position_units[symbol] + 1  # Increment unit counter
        self.stop_losses[symbol] = stop_price  # Update stop loss for entire position

        # Log the addition to the position
        trade_info = (f"Added to Short: {symbol}, Unit: {self.position_units[symbol]}, "
                     f"Quantity: {quantity}, Price: {equity.Price}, Stop: {stop_price}")
        self.Log(trade_info)
        self.daily_trades.append(trade_info)

    def CleanupPosition(self, symbol):
        """
        Clean up all tracking variables when exiting a position
        """
        if symbol in self.stop_losses:
            del self.stop_losses[symbol]
        if symbol in self.entry_prices:
            del self.entry_prices[symbol]
        if symbol in self.position_units:
            del self.position_units[symbol]
        if symbol in self.last_add_price:
            del self.last_add_price[symbol]

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
