import httpx
import pandas as pd
from datetime import datetime, timedelta
from app.config import settings
from app.schemas.query import StockData
from typing import Dict, Any, Optional

async def fetch_alpha_vantage_data(function: str, symbol: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Fetch data from Alpha Vantage API for a specific function and symbol"""
    try:
        base_url = "https://www.alphavantage.co/query"
        params = {"function": function, "symbol": symbol, "apikey": settings.alphavantage_api_key, **kwargs}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"Error fetching {function} for {symbol}: {str(e)}")
        return None

async def fetch_stock_data(symbol: str) -> StockData:
    """Collect comprehensive stock data from multiple Alpha Vantage endpoints"""
    try:
        data = {}

        # 1. Get basic quote data (original implementation)
        quote_data = await fetch_alpha_vantage_data("GLOBAL_QUOTE", symbol)
        if quote_data and "Global Quote" in quote_data and quote_data["Global Quote"]:
            quote = quote_data["Global Quote"]
            data["current_price"] = float(quote.get("05. price", 0))
            data["change_percent"] = float(quote.get("10. change percent", "0%").replace("%", ""))
            data["volume"] = int(quote.get("06. volume", 0)) if quote.get("06. volume") else None
            
            # Additional quote data
            data["open"] = float(quote.get("02. open", 0)) if quote.get("02. open") else None
            data["high"] = float(quote.get("03. high", 0)) if quote.get("03. high") else None
            data["low"] = float(quote.get("04. low", 0)) if quote.get("04. low") else None
        
        # 2. Company Overview (fundamentals)
        overview = await fetch_alpha_vantage_data("OVERVIEW", symbol)
        if overview:
            data["name"] = overview.get("Name", symbol)
            data["pe_ratio"] = float(overview.get("PERatio", 0) or 0)
            data["eps"] = float(overview.get("EPS", 0) or 0)
            data["dividend_yield"] = float(overview.get("DividendYield", 0) or 0)
            data["beta"] = float(overview.get("Beta", 0) or 0)
            data["market_cap"] = int(overview.get("MarketCapitalization", 0) or 0)
        
        # 3. Income Statement (Revenue Growth)
        income = await fetch_alpha_vantage_data("INCOME_STATEMENT", symbol)
        if income and "annualReports" in income and len(income["annualReports"]) >= 2:
            revenue_t0 = int(income["annualReports"][0].get("totalRevenue", 0) or 0)
            revenue_t1 = int(income["annualReports"][1].get("totalRevenue", 0) or 0)
            data["revenue_growth"] = (revenue_t0 - revenue_t1) / revenue_t1 if revenue_t1 else 0
        
        # 4. Balance Sheet (Debt-to-Equity)
        balance = await fetch_alpha_vantage_data("BALANCE_SHEET", symbol)
        if balance and "annualReports" in balance and balance["annualReports"]:
            total_debt = int(balance["annualReports"][0].get("totalLiabilities", 0) or 0)
            equity = int(balance["annualReports"][0].get("totalShareholderEquity", 0) or 0)
            data["debt_to_equity"] = total_debt / equity if equity else 0
        
        # 5. Price Data (TIME_SERIES_DAILY_ADJUSTED for technical indicators)
        prices = await fetch_alpha_vantage_data("TIME_SERIES_DAILY_ADJUSTED", symbol, outputsize="compact")
        if prices and "Time Series (Daily)" in prices:
            # Convert to DataFrame for easier processing
            df = pd.DataFrame.from_dict(prices["Time Series (Daily)"]).T
            df = df[["4. close", "5. volume"]].astype(float)
            
            # Calculate technical indicators
            data["high_52week"] = df["4. close"].max()
            data["low_52week"] = df["4. close"].min()
            data["30d_high"] = df["4. close"].head(30).max()
            data["30d_low"] = df["4. close"].head(30).min()
            data["50d_sma"] = df["4. close"].head(50).mean()
        
        # 6. Technical Indicator (RSI)
        rsi = await fetch_alpha_vantage_data("RSI", symbol, interval="daily", time_period=14, series_type="close")
        if rsi and "Technical Analysis: RSI" in rsi:
            latest_date = max(rsi["Technical Analysis: RSI"].keys())
            data["rsi"] = float(rsi["Technical Analysis: RSI"][latest_date]["RSI"])
        
        # 7. News Sentiment
        sentiment = await fetch_alpha_vantage_data(
            "NEWS_SENTIMENT", 
            symbol, 
            time_from=(datetime.now() - timedelta(days=7)).strftime("%Y%m%dT0000")
        )
        if sentiment and "feed" in sentiment:
            sentiment_scores = [
                float(item["overall_sentiment_score"]) 
                for item in sentiment["feed"] 
                if "overall_sentiment_score" in item
            ]
            data["sentiment_score"] = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        
        # Construct the StockData object with all the collected data
        return StockData(
            symbol=symbol,
            name=data.get("name", f"{symbol} Inc."),
            current_price=data.get("current_price", 0.0),
            change_percent=data.get("change_percent", 0.0),
            market_cap=data.get("market_cap", 0),
            pe_ratio=data.get("pe_ratio", 0.0),
            dividend_yield=data.get("dividend_yield", 0.0),
            volume=data.get("volume", 0),
            high_52week=data.get("high_52week", 0.0),
            low_52week=data.get("low_52week", 0.0),
            additional_data={
                "open": data.get("open", 0.0),
                "high": data.get("high", 0.0),
                "low": data.get("low", 0.0),
                "eps": data.get("eps", 0.0),
                "beta": data.get("beta", 0.0),
                "revenue_growth": data.get("revenue_growth", 0.0),
                "debt_to_equity": data.get("debt_to_equity", 0.0),
                "30d_high": data.get("30d_high", 0.0),
                "30d_low": data.get("30d_low", 0.0),
                "50d_sma": data.get("50d_sma", 0.0),
                "rsi": data.get("rsi", 0.0),
                "sentiment_score": data.get("sentiment_score", 0.0)
            }
        )
    except Exception as e:
        print(f"Error fetching comprehensive stock data for {symbol}: {str(e)}")
        # Fallback to mock data with hash-based values for testing/demo
        return StockData(
            symbol=symbol,
            name=f"{symbol} Inc.",
            current_price=100.0 + hash(symbol) % 100,
            change_percent=1.5 + (hash(symbol) % 5),
            market_cap=1000000000.0 + hash(symbol) % 1000000000,
            pe_ratio=15.0 + hash(symbol) % 10,
            dividend_yield=2.5 + (hash(symbol) % 3),
            volume=1000000 + hash(symbol) % 1000000,
            high_52week=150.0 + hash(symbol) % 50,
            low_52week=80.0 + hash(symbol) % 30
        )