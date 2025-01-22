from AlgorithmImports import *
from main import TurtleTradingStrategy
from tests.test_turtle_trading import TestTurtleTrading

class TestRunner(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2010, 1, 1)
        self.SetEndDate(2010, 1, 2)
        
        # Test results tracking
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        
        self.Log("=== Starting Test Suite ===")
        
        try:
            # Run main algorithm tests
            self.RunMainTests()
            
            # Run separate test suite
            self.RunTestSuite()
            
        except Exception as e:
            self.Log(f"ERROR: Test suite failed with exception: {str(e)}")
            
        finally:
            # Log test summary
            self.LogTestSummary()
            self.Quit()
    
    def RunMainTests(self):
        """Run tests defined in main algorithm"""
        self.Log("\n=== Running Main Algorithm Tests ===")
        
        strategy = TurtleTradingStrategy()
        strategy.Initialize()
        
        # Run tests and track results
        self.RunTest("CreateDrawdownMap", strategy.Test_CreateDrawdownMap)
        self.RunTest("GetAvailablePortfolioValue", strategy.Test_GetAvailablePortfolioValue)
    
    def RunTestSuite(self):
        """Run separate test suite"""
        self.Log("\n=== Running Extended Test Suite ===")
        
        test_suite = TestTurtleTrading()
        test_suite.Initialize()
        
        # Run tests and track results
        self.RunTest("DrawdownMapCreation", test_suite.Test_DrawdownMapCreation)
        self.RunTest("PortfolioValueLookup", test_suite.Test_PortfolioValueLookup)
    
    def RunTest(self, test_name, test_func):
        """
        Run a single test and track its result
        
        Args:
            test_name (str): Name of the test
            test_func (callable): Test function to run
        """
        self.Log(f"\nRunning test: {test_name}")
        self.tests_run += 1
        
        try:
            test_func()
            self.tests_passed += 1
            self.Log(f"✓ {test_name} PASSED")
            
        except AssertionError as e:
            self.tests_failed += 1
            self.Log(f"✗ {test_name} FAILED: {str(e)}")
            
        except Exception as e:
            self.tests_failed += 1
            self.Log(f"✗ {test_name} ERROR: {str(e)}")
    
    def LogTestSummary(self):
        """Log summary of all test results"""
        self.Log("\n=== Test Summary ===")
        self.Log(f"Total Tests Run: {self.tests_run}")
        self.Log(f"Tests Passed: {self.tests_passed}")
        self.Log(f"Tests Failed: {self.tests_failed}")
        self.Log(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        self.Log("===================") 