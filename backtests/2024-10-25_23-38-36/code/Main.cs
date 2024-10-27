using System;
using System.Collections.Generic;
using System.Linq;
using QuantConnect;
using QuantConnect.Algorithm;
using QuantConnect.Data.Market;
using QuantConnect.Indicators;

namespace QuantConnect.Algorithm.CSharp
{
    public class TurtleTradingStrategy : QCAlgorithm
    {
        private const int EntryChannel = 20;
        private const int ExitChannel = 10;
        private const decimal RiskPerTrade = 0.01m;

        private Symbol _symbol;
        private Donchian _entryChannel;
        private Donchian _exitChannel;
        private decimal _atrMultiplier = 2;
        private AverageTrueRange _atr;

        public override void Initialize()
        {
            SetStartDate(2010, 1, 1);
            SetEndDate(DateTime.Now);
            SetCash(100000);

            _symbol = AddEquity("SPY", Resolution.Daily).Symbol;

            _entryChannel = new Donchian(_symbol, EntryChannel);
            _exitChannel = new Donchian(_symbol, ExitChannel);
            _atr = new AverageTrueRange(_symbol, 14, MovingAverageType.Simple);

            SetWarmUp(EntryChannel);
        }

        public override void OnData(Slice data)
        {
            if (!_entryChannel.IsReady || !_exitChannel.IsReady || !_atr.IsReady) return;

            if (!Portfolio.Invested)
            {
                if (data[_symbol].Close >= _entryChannel.Upper.Current.Value)
                {
                    EnterLong();
                }
                else if (data[_symbol].Close <= _entryChannel.Lower.Current.Value)
                {
                    EnterShort();
                }
            }
            else
            {
                if (Portfolio[_symbol].IsLong && data[_symbol].Close <= _exitChannel.Lower.Current.Value)
                {
                    Liquidate(_symbol);
                }
                else if (Portfolio[_symbol].IsShort && data[_symbol].Close >= _exitChannel.Upper.Current.Value)
                {
                    Liquidate(_symbol);
                }
            }
        }

        private void EnterLong()
        {
            decimal stopPrice = Securities[_symbol].Price - _atr.Current.Value * _atrMultiplier;
            decimal shares = CalculatePositionSize(stopPrice);
            SetHoldings(_symbol, shares / Portfolio.TotalPortfolioValue);
        }

        private void EnterShort()
        {
            decimal stopPrice = Securities[_symbol].Price + _atr.Current.Value * _atrMultiplier;
            decimal shares = CalculatePositionSize(stopPrice);
            SetHoldings(_symbol, -shares / Portfolio.TotalPortfolioValue);
        }

        private decimal CalculatePositionSize(decimal stopPrice)
        {
            decimal riskAmount = Portfolio.TotalPortfolioValue * RiskPerTrade;
            decimal riskPerShare = Math.Abs(Securities[_symbol].Price - stopPrice);
            return Math.Floor(riskAmount / riskPerShare);
        }
    }

    public class Donchian : IndicatorBase<IndicatorDataPoint>
    {
        private readonly int _period;
        private readonly RollingWindow<decimal> _window;
        public IndicatorBase<IndicatorDataPoint> Upper { get; }
        public IndicatorBase<IndicatorDataPoint> Lower { get; }

        public Donchian(Symbol symbol, int period)
            : base($"DC_{period}", false)
        {
            _period = period;
            _window = new RollingWindow<decimal>(period);
            Upper = new Maximum($"{symbol}.High", period);
            Lower = new Minimum($"{symbol}.Low", period);
        }

        public override bool IsReady => _window.IsReady;

        protected override decimal ComputeNextValue(IndicatorDataPoint input)
        {
            _window.Add(input.Value);
            Upper.Update(input.Time, _window.Max());
            Lower.Update(input.Time, _window.Min());
            return (Upper.Current.Value + Lower.Current.Value) / 2;
        }
    }
}
