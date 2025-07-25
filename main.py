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
        # Run tests first
        self.Test_CreateDrawdownMap()
        self.Test_GetAvailablePortfolioValue()
        
        # Continue with normal initialization
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
        self.entry_channels = {}  # Dictionary[Symbol, DonchianChannel] - Tracks entry channel indicators using QuantConnect's built-in DCH indicator
        self.exit_channels = {}   # Dictionary[Symbol, DonchianChannel] - Tracks exit channel indicators using QuantConnect's built-in DCH indicator
        self.atrs = {}            # Dictionary[Symbol, ATR] - Tracks Average True Range indicators using QuantConnect's built-in ATR indicator

        # Position Management - Track active positions and their characteristics
        self.stop_losses = {}     # Dictionary[Symbol, float] - Tracks stop loss prices for each position
        self.entry_prices = {}    # Dictionary[Symbol, List[float]] - Tracks entry prices for each unit of a position
        self.pyramid_level = {}   # Dictionary[Symbol, int] - Tracks pyramid level for each position (1-4 levels)

        # Trade Management - Track trading activity and enforce trading rules
        self.last_add_price = {}  # Dictionary[Symbol, float] - Tracks the price at which we last added a unit to a position
        self.MAX_PYRAMID_LEVELS = 4  # int - Maximum number of times we can pyramid (add to) a position per Turtle Trading rules
        self.daily_trades = []    # List[str] - Tracks trades made during the current day for daily reporting

        # Symbol Management - Track which symbols we're trading
        self.symbols = []         # List[Symbol] - Collection of trading symbols (e.g., equities) being traded by the algorithm

        # Initialize trading symbols and their technical indicators
        for symbol_str in ["AAPL"]: # TODO: Make this dynamic - Choose diversified set of symbols that meet breakout criteria (ie. Sublime Trading Criteria)
            # Add the equity to our universe with daily resolution data
            equity = self.AddEquity(symbol_str, Resolution.Daily)
            
            # Store the Symbol object for future reference
            self.symbols.append(equity.Symbol)
            
            # Create and store technical indicators for this symbol using QuantConnect's built-in indicators:
            # 1. Entry channel (55-day Donchian) for generating entry signals using QuantConnect's DCH indicator
            self.entry_channels[equity.Symbol] = self.DCH(equity.Symbol, self.ENTRY_CHANNEL)
            
            # 2. Exit channel (20-day Donchian) for generating exit signals using QuantConnect's DCH indicator
            self.exit_channels[equity.Symbol] = self.DCH(equity.Symbol, self.EXIT_CHANNEL)
            
            # 3. Average True Range (ATR) for volatility measurement and position sizing
            self.atrs[equity.Symbol] = self.ATR(equity.Symbol, self.ATR_PERIOD, MovingAverageType.Simple)
            
            # Log the addition of this symbol to our universe
            self.Log(f"Added equity: {equity.Symbol}")

        # Increase warm-up period to account for longer entry channel
        self.SetWarmUp(timedelta(days=self.ENTRY_CHANNEL))

        # TODO: Too much logging - need to reduce this; change logging per the table shown in the Notion documentation
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(16, 0), self.LogPortfolioState) 
        
        # Portfolio Management - Track peak value and drawdown state
        self.peak_portfolio_value = self.Portfolio.TotalPortfolioValue
        self.original_portfolio_value = self.Portfolio.TotalPortfolioValue
        self.drawdown_map = self.CreateDrawdownMap(self.original_portfolio_value)

    def CreateDrawdownMap(self, starting_value, min_value=100):
        """
        Create a map of portfolio values to their corresponding effective values for position sizing.
        Each 10% drop in actual value corresponds to a 20% drop in effective value.
        
        Args:
            starting_value (float): Initial portfolio value
            min_value (float): Minimum value to calculate down to
            
        Returns:
            dict: Mapping of actual portfolio values to effective position sizing values
        """
        drawdown_map = {}
        current_actual = starting_value
        current_effective = starting_value
        
        while current_effective > min_value:
            drawdown_map[current_actual] = current_effective
            
            # Calculate next level values
            actual_reduction = current_effective * 0.10  # 10% of previous effective
            effective_reduction = current_effective * 0.20  # 20% of previous effective
            
            current_actual = current_actual - actual_reduction
            current_effective = current_effective - effective_reduction
            
        return drawdown_map

    def GetAvailablePortfolioValue(self):
        """
        Get the effective portfolio value for position sizing based on drawdown map.
        If current value exceeds peak, recreate the drawdown map from the new peak.
        
        Returns:
            float: The effective portfolio value to use for position sizing
        """
        current_portfolio_value = self.Portfolio.TotalPortfolioValue
        
        # If we're at a new peak, update peak and recreate drawdown map
        if current_portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = current_portfolio_value
            self.drawdown_map = self.CreateDrawdownMap(current_portfolio_value)
            return current_portfolio_value
            
        # Find the appropriate drawdown level
        keys = sorted(self.drawdown_map.keys(), reverse=True)
        previous_effective_value = self.drawdown_map[keys[0]]  # Start with highest level
        
        for key in keys:
            if current_portfolio_value > key:
                return previous_effective_value
            if current_portfolio_value == key:
                return self.drawdown_map[key]
            previous_effective_value = self.drawdown_map[key]
            
        # If we're below the lowest mapped value, return the lowest effective value
        return self.drawdown_map[keys[-1]]

    def OnData(self, slice):
        """
        Process new market data and manage trading positions.
        This is the main trading logic implementation of the Turtle Trading Strategy System 2.

        The method performs the following steps for each symbol:
        1. Skip processing if still in warm-up period
        2. Validate position integrity (ensure stop losses exist)
        3. Check if indicators are ready for trading decisions
        4. Process trading signals:
            a. For non-invested positions:
               - Enter long if price breaks above 55-day Donchian Channel high
               - Enter short if price breaks below 55-day Donchian Channel low
            b. For existing positions:
               - Exit long if price breaks below 20-day Donchian Channel low
               - Exit short if price breaks above 20-day Donchian Channel high
               - Exit if stop loss is hit  #TODO: Perhaps it might be better to use a 'STOP MARKET ORDER' when entering a position
               - Add units (pyramid) if price moves favorably by 1N (1 ATR)

        Args:
            slice: Contains market data for the current time step

        Trading Rules Implemented:
        - System 2 breakout periods (55-day Donchian Channel for entry, 20-day for exit)
        - Position sizing based on N (ATR)
        - Stop losses at 2N from entry
        - Maximum 4 pyramid levels per position
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

            # Verify QuantConnect's built-in indicators are ready before making trading decisions
            if not self.entry_channels[symbol].IsReady or not self.exit_channels[symbol].IsReady or not self.atrs[symbol].IsReady:
                self.Log(f"Indicators not ready for {symbol}. Entry: {self.entry_channels[symbol].IsReady}, Exit: {self.exit_channels[symbol].IsReady}, ATR: {self.atrs[symbol].IsReady}")
                continue

            # SECTION 3: CALCULATE TRADING SIGNALS
            # Get current price and Donchian Channel breakout levels from QuantConnect's DCH indicator
            current_price = slice.Bars[symbol].Close
            donchain_long_entry = self.entry_channels[symbol].Upper.Current.Value    # System 2: 55-day high for long entry signals
            donchain_short_entry = self.entry_channels[symbol].Lower.Current.Value   # System 2: 55-day low for short entry signals
            donchain_short_exit = self.exit_channels[symbol].Upper.Current.Value     # System 2: 20-day high for short exit signals
            donchain_long_exit = self.exit_channels[symbol].Lower.Current.Value      # System 2: 20-day low for long exit signals

            # Log current price and Donchian Channel levels
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
                    profit_loss = position.total_close_profit()  # Uses built-in method
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
                    profit_loss = position.total_close_profit()  # Uses built-in method
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
                        profit_loss = position.total_close_profit()  # Uses built-in method
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
                    current_pyramid_level = self.pyramid_level[symbol]
                    if current_pyramid_level < self.MAX_PYRAMID_LEVELS:
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
        Enter a long position for the given symbol. This implements the initial entry rules
        of the Turtle Trading strategy for long positions.

        Process:
        1. Calculate stop loss price using ATR (2N below entry price)
        2. Calculate position size based on risk parameters
        3. Verify sufficient capital for the trade
        4. Place the market order
        5. Initialize position tracking variables
        6. Log the trade details

        Args:
            symbol: The trading symbol to enter a long position in

        Position Management Variables Set:
        - entry_prices: List containing the entry price for this first unit
        - position_units: Set to 1 for this initial unit
        - last_add_price: Set to entry price for future pyramiding calculations
        - stop_losses: Set stop loss price for the position
        """
        # Get reference to the security for price and trading operations
        equity = self.Securities[symbol]

        # Calculate stop loss price (2N below entry)
        # N = ATR, and we multiply by ATR_MULTIPLIER (2) per Turtle Trading rules
        stop_price = equity.Price - self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER

        # Calculate the position size based on our risk parameters
        # This ensures we risk exactly RISK_PER_TRADE (2%) of our portfolio
        quantity = self.CalculatePositionSize(equity, stop_price)

        # Calculate the total cost of the position
        cost = quantity * equity.Price

        # Verify we have enough cash to enter the position
        if cost > self.Portfolio.Cash:
            self.Log(f"Not enough cash to enter long position in {symbol}. Required: ${cost}, Available: ${self.Portfolio.Cash}")
            return

        # Capture the exact entry price before placing the order
        entry_price = equity.Price

        # Place the market order for the calculated quantity
        self.MarketOrder(symbol, quantity)

        # Initialize position tracking variables
        self.entry_prices[symbol] = [entry_price]  # List with first entry price
        self.pyramid_level[symbol] = 1            # First pyramid level of potentially 4
        self.last_add_price[symbol] = entry_price  # Reference price for pyramiding
        self.stop_losses[symbol] = stop_price      # Stop loss for the position

        # Log the trade details
        trade_info = f"Entered Long: {symbol}, Quantity: {quantity}, Entry Price: ${entry_price}, Stop: ${stop_price}"
        self.Log(trade_info)
        self.daily_trades.append(trade_info)

    def EnterShort(self, symbol):
        """
        Enter a short position for the given symbol. This implements the initial entry rules
        of the Turtle Trading strategy for short positions.

        Process:
        1. Calculate stop loss price using ATR (2N above entry price)
        2. Calculate position size based on risk parameters
        3. Verify sufficient capital for the trade
        4. Place the market order
        5. Initialize position tracking variables
        6. Log the trade details

        Args:
            symbol: The trading symbol to enter a short position in

        Position Management Variables Set:
        - entry_prices: List containing the entry price for this first unit
        - position_units: Set to 1 for this initial unit
        - last_add_price: Set to entry price for future pyramiding calculations
        - stop_losses: Set stop loss price for the position
        """
        # Get reference to the security for price and trading operations
        equity = self.Securities[symbol]

        # Calculate stop loss price (2N above entry)
        # N = ATR, and we multiply by ATR_MULTIPLIER (2) per Turtle Trading rules
        stop_price = equity.Price + self.atrs[symbol].Current.Value * self.ATR_MULTIPLIER

        # Calculate the position size based on our risk parameters
        # This ensures we risk exactly RISK_PER_TRADE (2%) of our portfolio
        quantity = self.CalculatePositionSize(equity, stop_price)

        # Calculate the total cost of the position
        cost = quantity * equity.Price

        # Verify we have enough cash to enter the position
        if cost > self.Portfolio.Cash:
            self.Log(f"Not enough cash to enter short position in {symbol}. Required: ${cost}, Available: ${self.Portfolio.Cash}")
            return

        # Capture the exact entry price before placing the order
        entry_price = equity.Price

        # Place the market order for the calculated quantity (negative for short)
        self.MarketOrder(symbol, -quantity)

        # Initialize position tracking variables
        self.entry_prices[symbol] = [entry_price]  # List with first entry price
        self.pyramid_level[symbol] = 1            # First pyramid level of potentially 4
        self.last_add_price[symbol] = entry_price  # Reference price for pyramiding
        self.stop_losses[symbol] = stop_price      # Stop loss for the position

        # Log the trade details
        trade_info = f"Entered Short: {symbol}, Quantity: {quantity}, Entry Price: ${entry_price}, Stop: ${stop_price}"
        self.Log(trade_info)
        self.daily_trades.append(trade_info)

    def CalculatePositionSize(self, equity, stop_price):
        """
        Calculate the position size considering drawdown rules.
        """
        # Use adjusted portfolio value for risk calculations
        adjusted_portfolio_value = self.GetAvailablePortfolioValue()
        
        # Calculate the dollar amount we're willing to risk on this trade
        risk_amount = adjusted_portfolio_value * self.RISK_PER_TRADE

        # Calculate how much we'll lose per share if stopped out
        risk_per_share = abs(equity.Price - stop_price)

        # Handle edge case where entry price equals stop price
        if risk_per_share == 0:
            self.Log(f"Risk per share for {equity.Symbol} is 0, using minimum position size")
            return 1

        # Calculate number of shares based on risk parameters
        share_quantity = math.floor(risk_amount / risk_per_share)

        return max(1, share_quantity)

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

        self.Log(f"Current Portfolio Value: ${self.Portfolio.TotalPortfolioValue}")
        self.Log(f"Effective Portfolio Value: ${self.GetAvailablePortfolioValue()}")
        self.Log(f"Peak Portfolio Value: ${self.peak_portfolio_value}")
        
        # Log first few entries of drawdown map for verification
        levels = list(self.drawdown_map.items())[:5]
        self.Log("Current Drawdown Map (first 5 levels):")
        for actual, effective in levels:
            self.Log(f"  At ${actual:.2f} -> Use ${effective:.2f}")

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
        self.pyramid_level[symbol] = self.pyramid_level[symbol] + 1  # Increment unit counter
        self.stop_losses[symbol] = stop_price  # Update stop loss for entire position

        # Log the addition to the position
        trade_info = (f"Added to Long: {symbol}, Pyramid Level: {self.pyramid_level[symbol]}, "
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
        self.pyramid_level[symbol] = self.pyramid_level[symbol] + 1  # Increment unit counter
        self.stop_losses[symbol] = stop_price  # Update stop loss for entire position

        # Log the addition to the position
        trade_info = (f"Added to Short: {symbol}, Pyramid Level: {self.pyramid_level[symbol]}, "
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
        if symbol in self.pyramid_level:
            del self.pyramid_level[symbol]
        if symbol in self.last_add_price:
            del self.last_add_price[symbol]

    def Test_CreateDrawdownMap(self):
        """Test the drawdown map creation logic"""
        # Test case 1: Basic map creation
        test_map = self.CreateDrawdownMap(1000000, min_value=100)
        
        # Test initial and first few levels
        self.AssertEqual(test_map[1000000], 1000000, "First level should match")
        self.AssertEqual(test_map[900000], 800000, "Second level should be 20% lower")
        self.AssertEqual(test_map[820000], 640000, "Third level should compound correctly")
        self.AssertEqual(test_map[756000], 512000, "Fourth level should compound correctly")
        self.AssertEqual(test_map[704800], 409600, "Fifth level should compound correctly")
        
        # Test specific values throughout the range
        self.AssertEqual(test_map[604857.6], 209715.2, "Mid-range value should calculate correctly")
        
        # Test map properties
        sorted_keys = sorted(test_map.keys(), reverse=True)
        self.AssertEqual(sorted_keys[0], 1000000, "Highest key should be starting value")
        self.AssertGreater(len(test_map), 10, "Should have multiple drawdown levels")
        
    def Test_GetAvailablePortfolioValue(self):
        """Test the portfolio value lookup logic"""
        # Setup
        self.peak_portfolio_value = 1000000
        self.drawdown_map = self.CreateDrawdownMap(1000000, min_value=100)
        
        # Test cases
        test_cases = [
            # Test values at and near thresholds
            (1000000, 1000000, "Peak value should return itself"),
            (950000, 1000000, "Value between levels should use higher effective value"),
            (900000, 800000, "Exact match should use corresponding effective value"),
            (850000, 800000, "Value between levels should use higher effective value"),
        ]
        
        for current_value, expected_value, message in test_cases:
            # Mock the portfolio value
            self.Portfolio.TotalPortfolioValue = current_value
            result = self.GetAvailablePortfolioValue()
            self.AssertEqual(result, expected_value, message)
            
        # Test peak value update
        self.Portfolio.TotalPortfolioValue = 1500000
        result = self.GetAvailablePortfolioValue()
        self.AssertEqual(self.peak_portfolio_value, 1500000, "Peak value should update")
        self.AssertEqual(result, 1500000, "Should return new peak value")
