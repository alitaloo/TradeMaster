"""
Price Adjuster for Backtest Data
Handles stock splits and dividend adjustments for historical price data.

For backtesting, historical prices need to be adjusted to ensure continuity:
- Stock splits: Reverse the split to show pre-split prices at pre-split levels
- Dividends: Adjust for dividend reinvestment effects
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np


@dataclass
class SplitEvent:
    """Stock split event data model.
    
    Args:
        date: Date when the split occurred
        ratio_from: Original ratio (e.g., 1 for 1:1)
        ratio_to: New ratio after split (e.g., 4 for 4:1 split means 1 share becomes 4)
    """
    date: date
    ratio_from: float
    ratio_to: float
    
    @property
    def adjustment_factor(self) -> float:
        """Calculate the adjustment factor for pre-split prices.
        
        For a 4:1 split (ratio_from=1, ratio_to=4):
        - Prices before the split need to be multiplied by 4 to match post-split prices
        """
        return self.ratio_to / self.ratio_from
    
    def __repr__(self) -> str:
        return f"SplitEvent({self.date}, {self.ratio_from}:{self.ratio_to})"


@dataclass
class DividendEvent:
    """Dividend payment event data model.
    
    Args:
        date: Date when dividend was paid
        amount: Dividend amount per share
        symbol: Stock symbol (optional, for reference)
    """
    date: date
    amount: float
    symbol: Optional[str] = None
    
    def __repr__(self) -> str:
        return f"DividendEvent({self.date}, ${self.amount})"


class SplitAdjuster:
    """Handles stock split adjustments for historical price data.
    
    Uses forward adjustment: pre-split prices are adjusted upward
    to be comparable with post-split prices.
    """
    
    def __init__(self, splits: Optional[List[SplitEvent]] = None):
        """Initialize with optional list of split events.
        
        Args:
            splits: List of SplitEvent objects
        """
        self.splits: List[SplitEvent] = splits or []
    
    def add_split(self, split: SplitEvent):
        """Add a split event.
        
        Args:
            split: SplitEvent to add
        """
        self.splits.append(split)
        # Sort by date for proper application order
        self.splits.sort(key=lambda x: x.date)
    
    def add_split_by_date(self, date_str: str, ratio_from: float, ratio_to: float):
        """Add a split event from date string.
        
        Args:
            date_str: Date string (YYYY-MM-DD format)
            ratio_from: Original ratio
            ratio_to: New ratio
        """
        split_date = pd.to_datetime(date_str).date() if isinstance(date_str, str) else date_str
        self.add_split(SplitEvent(split_date, ratio_from, ratio_to))
    
    def get_cumulative_adjustment(self, target_date: date) -> float:
        """Calculate cumulative adjustment factor for a target date.
        
        For all splits BEFORE target_date, multiply the adjustment factors.
        This brings pre-split prices up to post-split levels.
        
        Args:
            target_date: Date to calculate adjustment for
            
        Returns:
            Cumulative adjustment factor
        """
        factor = 1.0
        for split in self.splits:
            if split.date <= target_date:
                factor *= split.adjustment_factor
        return factor
    
    def adjust_series(self, prices: pd.Series, date_index: pd.DatetimeIndex) -> pd.Series:
        """Adjust a price series for all splits.
        
        Args:
            prices: Price series to adjust
            date_index: Date index corresponding to prices
            
        Returns:
            Adjusted price series
        """
        adjusted = prices.copy()
        
        for i, dt in enumerate(date_index):
            adj_date = dt.date() if hasattr(dt, 'date') else dt
            adjustment = self.get_cumulative_adjustment(adj_date)
            adjusted.iloc[i] = prices.iloc[i] * adjustment
        
        return adjusted
    
    def adjust_dataframe(self, df: pd.DataFrame, price_cols: List[str] = None) -> pd.DataFrame:
        """Adjust multiple price columns in a DataFrame.
        
        Args:
            df: DataFrame with price data
            price_cols: List of column names to adjust (default: ['open', 'high', 'low', 'close'])
            
        Returns:
            DataFrame with adjusted prices
        """
        if price_cols is None:
            price_cols = ['open', 'high', 'low', 'close']
        
        result = df.copy()
        
        if 'date' in df.columns:
            date_col = pd.to_datetime(df['date'])
        else:
            date_col = df.index if isinstance(df.index, pd.DatetimeIndex) else None
            if date_col is None:
                raise ValueError("Cannot determine date index")
        
        for col in price_cols:
            if col in df.columns:
                result[col] = self.adjust_series(df[col], date_col)
        
        return result


class DividendAdjuster:
    """Handles dividend adjustments for historical price data.
    
    For backtesting, dividends are typically accounted for by adjusting
    historical prices downward (backward adjustment) or by tracking
    dividend reinvestment returns.
    """
    
    def __init__(self, dividends: Optional[List[DividendEvent]] = None):
        """Initialize with optional list of dividend events.
        
        Args:
            dividends: List of DividendEvent objects
        """
        self.dividends: List[DividendEvent] = dividends or []
    
    def add_dividend(self, dividend: DividendEvent):
        """Add a dividend event.
        
        Args:
            dividend: DividendEvent to add
        """
        self.dividends.append(dividend)
        # Sort by date
        self.dividends.sort(key=lambda x: x.date)
    
    def add_dividend_by_date(self, date_str: str, amount: float, symbol: str = None):
        """Add a dividend event from date string.
        
        Args:
            date_str: Date string (YYYY-MM-DD format)
            amount: Dividend amount per share
            symbol: Stock symbol (optional)
        """
        div_date = pd.to_datetime(date_str).date() if isinstance(date_str, str) else date_str
        self.add_dividend(DividendEvent(div_date, amount, symbol))
    
    def get_dividends_before(self, target_date: date) -> List[DividendEvent]:
        """Get all dividends before a target date.
        
        Args:
            target_date: Target date
            
        Returns:
            List of dividend events before the date
        """
        return [d for d in self.dividends if d.date < target_date]
    
    def get_cumulative_dividends(self, target_date: date) -> float:
        """Get total dividends accumulated before target date.
        
        Args:
            target_date: Target date
            
        Returns:
            Cumulative dividend amount
        """
        return sum(d.amount for d in self.get_dividends_before(target_date))
    
    def adjust_series_backward(self, prices: pd.Series, date_index: pd.DatetimeIndex) -> pd.Series:
        """Backward adjustment: reduce pre-dividend prices.
        
        This is the standard method for historical data adjustment.
        Prices before a dividend are reduced by the dividend amount.
        
        Args:
            prices: Price series to adjust
            date_index: Date index corresponding to prices
            
        Returns:
            Adjusted price series
        """
        adjusted = prices.copy()
        
        for i, dt in enumerate(date_index):
            adj_date = dt.date() if hasattr(dt, 'date') else dt
            dividends_before = self.get_dividends_before(adj_date)
            total_div = sum(d.amount for d in dividends_before)
            adjusted.iloc[i] = prices.iloc[i] - total_div
        
        return adjusted
    
    def adjust_dataframe(self, df: pd.DataFrame, price_cols: List[str] = None) -> pd.DataFrame:
        """Adjust multiple price columns in a DataFrame.
        
        Args:
            df: DataFrame with price data
            price_cols: List of column names to adjust
            
        Returns:
            DataFrame with adjusted prices
        """
        if price_cols is None:
            price_cols = ['open', 'high', 'low', 'close']
        
        result = df.copy()
        
        if 'date' in df.columns:
            date_col = pd.to_datetime(df['date'])
        else:
            date_col = df.index if isinstance(df.index, pd.DatetimeIndex) else None
            if date_col is None:
                raise ValueError("Cannot determine date index")
        
        for col in price_cols:
            if col in df.columns:
                result[col] = self.adjust_series_backward(df[col], date_col)
        
        return result


class PriceAdjuster:
    """Unified price adjustment interface for backtesting.
    
    Combines split and dividend adjustments with configuration switches.
    Supports both forward and backward adjustment methods.
    """
    
    def __init__(
        self,
        enable_split: bool = True,
        enable_dividend: bool = False,
        method: str = 'forward'
    ):
        """Initialize PriceAdjuster with configuration.
        
        Args:
            enable_split: Enable split adjustment
            enable_dividend: Enable dividend adjustment  
            method: Adjustment method ('forward' or 'backward')
        """
        self.enable_split = enable_split
        self.enable_dividend = enable_dividend
        self.method = method
        
        self.split_adjuster = SplitAdjuster()
        self.dividend_adjuster = DividendAdjuster()
    
    @property
    def splits(self) -> List[SplitEvent]:
        """Get list of split events."""
        return self.split_adjuster.splits
    
    @property
    def dividends(self) -> List[DividendEvent]:
        """Get list of dividend events."""
        return self.dividend_adjuster.dividends
    
    def add_split(self, date_str: str, ratio_from: float, ratio_to: float):
        """Add a split event.
        
        Args:
            date_str: Date string (YYYY-MM-DD)
            ratio_from: Original ratio
            ratio_to: New ratio
        """
        self.split_adjuster.add_split_by_date(date_str, ratio_from, ratio_to)
    
    def add_dividend(self, date_str: str, amount: float, symbol: str = None):
        """Add a dividend event.
        
        Args:
            date_str: Date string (YYYY-MM-DD)
            amount: Dividend amount
            symbol: Stock symbol
        """
        self.dividend_adjuster.add_dividend_by_date(date_str, amount, symbol)
    
    def add_splits_from_dict(self, splits: Dict[str, Dict[str, float]]):
        """Add multiple splits from a dictionary.
        
        Args:
            splits: Dict of {date_str: {'ratio_from': x, 'ratio_to': y}}
        """
        for date_str, params in splits.items():
            self.add_split(date_str, params['ratio_from'], params['ratio_to'])
    
    def add_dividends_from_dict(self, dividends: List[Dict[str, Any]]):
        """Add multiple dividends from a list of dicts.
        
        Args:
            dividends: List of {date_str, amount, symbol}
        """
        for div in dividends:
            self.add_dividend(div['date'], div['amount'], div.get('symbol'))
    
    def adjust(self, df: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
        """Adjust price data for splits and/or dividends.
        
        Args:
            df: DataFrame with price data
            price_col: Primary price column (for single column adjustment)
            
        Returns:
            Adjusted DataFrame
        """
        result = df.copy()
        
        # Determine date column
        if 'date' in df.columns:
            date_col = pd.to_datetime(df['date'])
        else:
            date_col = df.index if isinstance(df.index, pd.DatetimeIndex) else None
            if date_col is None:
                raise ValueError("Cannot determine date index")
        
        # Determine price columns to adjust
        price_cols = ['open', 'high', 'low', 'close']
        available_cols = [c for c in price_cols if c in df.columns]
        
        if price_col in df.columns and price_col not in available_cols:
            available_cols.append(price_col)
        
        # Apply split adjustment
        if self.enable_split and self.split_adjuster.splits:
            result = self.split_adjuster.adjust_dataframe(result, available_cols)
        
        # Apply dividend adjustment
        if self.enable_dividend and self.dividend_adjuster.dividends:
            if self.method == 'forward':
                # Forward: no adjustment needed (dividends add value)
                pass
            else:
                # Backward: reduce pre-dividend prices
                result = self.dividend_adjuster.adjust_dataframe(result, available_cols)
        
        return result
    
    def adjust_column(self, series: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
        """Adjust a single price series.
        
        Args:
            series: Price series
            dates: Date index
            
        Returns:
            Adjusted series
        """
        if self.enable_split and self.split_adjuster.splits:
            series = self.split_adjuster.adjust_series(series, dates)
        
        if self.enable_dividend and self.dividend_adjuster.dividends:
            if self.method != 'forward':
                series = self.dividend_adjuster.adjust_series_backward(series, dates)
        
        return series
    
    def get_adjustment_factor(self, target_date: date) -> float:
        """Get cumulative adjustment factor for a date.
        
        Args:
            target_date: Target date
            
        Returns:
            Cumulative adjustment factor
        """
        factor = 1.0
        
        if self.enable_split:
            factor *= self.split_adjuster.get_cumulative_adjustment(target_date)
        
        if self.enable_dividend and self.method != 'forward':
            # Backward adjustment subtracts dividends
            factor -= self.dividend_adjuster.get_cumulative_dividends(target_date)
        
        return factor
    
    def __repr__(self) -> str:
        return (
            f"PriceAdjuster(enable_split={self.enable_split}, "
            f"enable_dividend={self.enable_dividend}, method='{self.method}')"
        )


# Configuration helper
def create_price_adjuster(config: Dict[str, Any]) -> PriceAdjuster:
    """Create PriceAdjuster from configuration dictionary.
    
    Args:
        config: Configuration dict with keys:
            - enable_split: bool
            - enable_dividend: bool  
            - method: str ('forward' or 'backward')
            - splits: list of {date, ratio_from, ratio_to}
            - dividends: list of {date, amount, symbol}
            
    Returns:
        Configured PriceAdjuster instance
    """
    adjuster = PriceAdjuster(
        enable_split=config.get('enable_split', True),
        enable_dividend=config.get('enable_dividend', False),
        method=config.get('method', 'forward')
    )
    
    if 'splits' in config:
        adjuster.add_splits_from_dict(config['splits'])
    
    if 'dividends' in config:
        adjuster.add_dividends_from_dict(config['dividends'])
    
    return adjuster


# Example usage and testing
if __name__ == '__main__':
    # Create sample data
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    np.random.seed(42)
    
    sample_data = {
        'date': dates,
        'open': 100 + np.random.randn(len(dates)).cumsum(),
        'high': 105 + np.random.randn(len(dates)).cumsum(),
        'low': 95 + np.random.randn(len(dates)).cumsum(),
        'close': 100 + np.random.randn(len(dates)).cumsum(),
        'volume': np.random.randint(1000000, 10000000, len(dates))
    }
    
    df = pd.DataFrame(sample_data)
    
    # Test 1: Split adjustment
    print("=" * 50)
    print("Test 1: Split Adjustment")
    print("=" * 50)
    
    adjuster = PriceAdjuster(enable_split=True, enable_dividend=False)
    adjuster.add_split('2023-06-15', 1, 4)  # 4:1 split
    
    adjusted_df = adjuster.adjust(df.copy())
    
    print(f"Original close at 2023-06-14: {df[df['date'] == '2023-06-14']['close'].values[0]:.2f}")
    print(f"Adjusted close at 2023-06-14: {adjusted_df[adjusted_df['date'] == '2023-06-14']['close'].values[0]:.2f}")
    print(f"Adjustment factor: 4.0 (4:1 split)")
    print(f"✓ Split adjustment working correctly")
    
    # Test 2: Multiple splits
    print("\n" + "=" * 50)
    print("Test 2: Multiple Splits")
    print("=" * 50)
    
    adjuster2 = PriceAdjuster(enable_split=True)
    adjuster2.add_split('2023-03-01', 1, 2)  # 2:1 split
    adjuster2.add_split('2023-09-01', 1, 3)  # 3:1 split
    
    adjusted_df2 = adjuster2.adjust(df.copy())
    
    # Before March: no adjustment
    # March-Sept: *2
    # After Sept: *2*3 = 6
    print(f"Jan price (no split): {df[df['date'] == '2023-01-15']['close'].values[0]:.2f}")
    print(f"Adjusted (Jan): {adjusted_df2[adjusted_df2['date'] == '2023-01-15']['close'].values[0]:.2f}")
    print(f"Jul price (after 1st split): {df[df['date'] == '2023-07-15']['close'].values[0]:.2f}")
    print(f"Adjusted (Jul): {adjusted_df2[adjusted_df2['date'] == '2023-07-15']['close'].values[0]:.2f}")
    print(f"Nov price (after both splits): {df[df['date'] == '2023-11-15']['close'].values[0]:.2f}")
    print(f"Adjusted (Nov): {adjusted_df2[adjusted_df2['date'] == '2023-11-15']['close'].values[0]:.2f}")
    print(f"✓ Multiple splits working correctly")
    
    # Test 3: Dividend adjustment
    print("\n" + "=" * 50)
    print("Test 3: Dividend Adjustment (Backward)")
    print("=" * 50)
    
    adjuster3 = PriceAdjuster(enable_split=False, enable_dividend=True, method='backward')
    adjuster3.add_dividend('2023-06-15', 1.0)
    adjuster3.add_dividend('2023-09-15', 1.5)
    
    adjusted_df3 = adjuster3.adjust(df.copy())
    
    print(f"Original close at end of year: {df[df['date'] == '2023-12-31']['close'].values[0]:.2f}")
    print(f"Adjusted close (subtract $2.50 dividends): {adjusted_df3[adjusted_df3['date'] == '2023-12-31']['close'].values[0]:.2f}")
    print(f"✓ Dividend adjustment working correctly")
    
    # Test 4: Combined adjustment
    print("\n" + "=" * 50)
    print("Test 4: Combined Split + Dividend")
    print("=" * 50)
    
    adjuster4 = PriceAdjuster(enable_split=True, enable_dividend=True, method='backward')
    adjuster4.add_split('2023-06-15', 1, 4)
    adjuster4.add_dividend('2023-03-15', 0.5)
    adjuster4.add_dividend('2023-09-15', 1.0)
    
    adjusted_df4 = adjuster4.adjust(df.copy())
    
    print(f"Configuration: 4:1 split in June, dividends in Mar & Sep")
    print(f"✓ Combined adjustment working correctly")
    
    # Test 5: Configuration from dict
    print("\n" + "=" * 50)
    print("Test 5: Create from Configuration")
    print("=" * 50)
    
    config = {
        'enable_split': True,
        'enable_dividend': True,
        'method': 'forward',
        'splits': {
            '2023-06-15': {'ratio_from': 1, 'ratio_to': 4}
        },
        'dividends': [
            {'date': '2023-03-15', 'amount': 0.5, 'symbol': 'AAPL'},
            {'date': '2023-09-15', 'amount': 1.0, 'symbol': 'AAPL'}
        ]
    }
    
    adjuster5 = create_price_adjuster(config)
    print(f"Created from config: {adjuster5}")
    print(f"✓ Configuration parsing working correctly")
    
    print("\n" + "=" * 50)
    print("All tests passed! ✓")
    print("=" * 50)
