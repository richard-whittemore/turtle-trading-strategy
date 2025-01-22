from AlgorithmImports import *
from main import TurtleTradingStrategy

class TestTurtleTrading(QCAlgorithm):
    def Initialize(self):
        self.strategy = TurtleTradingStrategy()
        self.strategy.Initialize()
        
    def Test_DrawdownMapCreation(self):
        """Test suite for drawdown map functionality"""
        # Test with different starting values
        test_cases = [
            (1000000, 100),    # Standard case
            (500000, 100),     # Half size
            (100000, 100),     # Smaller portfolio
            (50000, 100),      # Very small portfolio
            (2000000, 100),    # Large portfolio
        ]
        
        for starting_value, min_value in test_cases:
            test_map = self.strategy.CreateDrawdownMap(starting_value, min_value)
            
            # Verify initial values
            self.AssertEqual(test_map[starting_value], starting_value, 
                           f"Initial value should match for {starting_value}")
            
            # Verify first drawdown level
            expected_first_drawdown = starting_value * 0.9  # 10% down
            expected_first_effective = starting_value * 0.8  # 20% down
            self.AssertEqual(test_map[expected_first_drawdown], expected_first_effective,
                           f"First drawdown level incorrect for {starting_value}")
            
            # Verify map properties
            self.AssertEqual(len(test_map) > 0, True, "Map should not be empty")
            self.AssertTrue(
                min(test_map.values()) >= min_value, 
                "Minimum effective value should be greater than or equal to min_value"
            )
        
    def Test_PortfolioValueLookup(self):
        """Test suite for portfolio value lookup functionality"""
        # Test different portfolio scenarios
        scenarios = [
            (1000000, "Standard portfolio"),
            (500000, "Medium portfolio"),
            (100000, "Small portfolio"),
            (2000000, "Large portfolio")
        ]
        
        for initial_value, scenario in scenarios:
            # Setup test environment
            self.strategy.peak_portfolio_value = initial_value
            self.strategy.drawdown_map = self.strategy.CreateDrawdownMap(initial_value, min_value=100)
            
            # Test exact matches
            self.strategy.Portfolio.TotalPortfolioValue = initial_value
            self.AssertEqual(
                self.strategy.GetAvailablePortfolioValue(), 
                initial_value, 
                f"{scenario}: Peak value should return itself"
            )
            
            # Test 10% drawdown
            test_value = initial_value * 0.9
            self.strategy.Portfolio.TotalPortfolioValue = test_value
            self.AssertEqual(
                self.strategy.GetAvailablePortfolioValue(), 
                initial_value * 0.8, 
                f"{scenario}: 10% drawdown should reduce effective value by 20%"
            )
            
            # Test value between thresholds
            test_value = initial_value * 0.95
            self.strategy.Portfolio.TotalPortfolioValue = test_value
            self.AssertEqual(
                self.strategy.GetAvailablePortfolioValue(), 
                initial_value, 
                f"{scenario}: Value between thresholds should use higher level"
            )
            
            # Test new peak
            test_value = initial_value * 1.1
            self.strategy.Portfolio.TotalPortfolioValue = test_value
            result = self.strategy.GetAvailablePortfolioValue()
            self.AssertEqual(
                result, 
                test_value, 
                f"{scenario}: New peak should update and return new value"
            )
            self.AssertEqual(
                self.strategy.peak_portfolio_value,
                test_value,
                f"{scenario}: Peak value should be updated"
            ) 