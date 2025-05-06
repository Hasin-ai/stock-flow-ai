from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.query import StockQuery, StockResponse, QueryType
from app.services.alphavantage import fetch_stock_data
from app.services.gemini import analyze_with_gemini, detect_query_type, search_vector_db
from app.dependencies import get_client_user
from app.models.user import User
from app.models.activity_log import ActivityLog
from datetime import datetime

router = APIRouter()

@router.post("/query", response_model=StockResponse)
async def query_stock(
    query_data: StockQuery,
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    try:
        # Log activity
        db_log = ActivityLog(
            user_id=current_user.id,
            action=f"Stock query: {query_data.query}",
            timestamp=datetime.utcnow()
        )
        db.add(db_log)
        db.commit()

        # If query type not specified, detect it
        if not query_data.query_type or query_data.query_type == QueryType.GENERAL:
            query_data.query_type = await detect_query_type(query_data.query)
            # print(f"Detected query type: {query_data.query_type}, Type: {type(query_data.query_type)}")
            # print(f"QueryType.SINGLE: {QueryType.SINGLE}, Type: {type(QueryType.SINGLE)}")
            # print(f"QueryType.LIST: {QueryType.LIST}, Type: {type(QueryType.LIST)}")
            # print(f"QueryType.COMPARISON: {QueryType.COMPARISON}, Type: {type(QueryType.COMPARISON)}")
            # print(f"Are they equal? {query_data.query_type == QueryType.SINGLE}")
            # print(f"String comparison: {str(query_data.query_type) == str(QueryType.SINGLE)}")

        # Process based on query type
        if (isinstance(query_data.query_type, str) and query_data.query_type == "SINGLE") or query_data.query_type == QueryType.SINGLE:

            # print(f"inside single scope")

            # Extract symbol if not provided
            if not query_data.symbols or len(query_data.symbols) == 0 or query_data.symbols[0] == "string":
                symbol_prompt = f"Extract the stock symbol from this query: '{query_data.query}'. Return only the symbol without any explanation or extra text."
                symbol = await analyze_with_gemini(symbol_prompt)
                symbol = symbol.strip().upper()
                query_data.symbols = [symbol]

            # Fetch comprehensive data for the single stock
            stock_data = await fetch_stock_data(query_data.symbols[0])

            # print(f"Fetched data for {stock_data.symbol}: {stock_data}")
            
            # Generate a comprehensive analysis prompt
            analysis_prompt = f"""
            Analyze the following stock data for {stock_data.symbol} ({stock_data.name}):
            
            Basic Information:
            - Current Price: ${stock_data.current_price}
            - Change: {stock_data.change_percent}%
            - Volume: {stock_data.volume or 'N/A'}
            - Market Cap: ${stock_data.market_cap:,} 
            
            Fundamental Analysis:
            - P/E Ratio: {stock_data.pe_ratio or 'N/A'}
            - EPS: ${stock_data.additional_data.get('eps', 'N/A')}
            - Dividend Yield: {stock_data.dividend_yield * 100:.2f}%
            - Revenue Growth (YoY): {stock_data.additional_data.get('revenue_growth', 0) * 100:.2f}%
            - Debt-to-Equity: {stock_data.additional_data.get('debt_to_equity', 'N/A')}
            
            Technical Analysis:
            - 52-Week High/Low: ${stock_data.high_52week}/${stock_data.low_52week}
            - 30-day High/Low: ${stock_data.additional_data.get('30d_high', 'N/A')}/${stock_data.additional_data.get('30d_low', 'N/A')}
            - 50-day SMA: ${stock_data.additional_data.get('50d_sma', 'N/A')}
            - RSI (14-day): {stock_data.additional_data.get('rsi', 'N/A')}
            
            Risk Metrics:
            - Beta: {stock_data.additional_data.get('beta', 'N/A')}
            - News Sentiment (last week): {stock_data.additional_data.get('sentiment_score', 'N/A')}
            
            Based on this information and addressing the query: '{query_data.query}'
            
            Provide a comprehensive analysis covering:
            1. Fundamental analysis (valuation, financial health)
            2. Technical analysis (trend, entry/exit points)
            3. Sentiment analysis (news impact)
            4. Risk assessment (market and company-specific risks)
            
            Conclude with a buy, hold, or sell recommendation, and a price target if possible.
            Keep your response concise (around 250 words).
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return StockResponse(
                query=query_data.query,
                response=analysis,
                data=[stock_data],
                query_type=QueryType.SINGLE
            )
        
        elif (isinstance(query_data.query_type, str) and query_data.query_type == "LIST") or query_data.query_type == QueryType.LIST:

            # print(f"inside list scope")

            # Comment out vector DB search for now
            # matching_stocks = await search_vector_db(query_data.query, collection="stocks")
            
            # # If we have matches from vector DB, use those symbols
            # if (matching_stocks and len(matching_stocks) > 0):
            #     symbols = [stock.get("symbol") for stock in matching_stocks if "symbol" in stock]
            # # Otherwise, ask Gemini to suggest stocks

            # Always ask Gemini to suggest stocks
            suggestion_prompt = f"""
            Based on this query: '{query_data.query}'
            Suggest 3-5 stock symbols that would be relevant for this query.
            Return only the symbols separated by commas without any explanation.
            Example: AAPL, MSFT, GOOG
            """
            symbols_text = await analyze_with_gemini(suggestion_prompt)
            symbols = [s.strip() for s in symbols_text.split(",")]
            
            # Fetch comprehensive data for each stock
            stock_data_list = []
            for symbol in symbols[:5]:  # Limit to 5 stocks
                try:
                    stock_data = await fetch_stock_data(symbol)
                    stock_data_list.append(stock_data)
                except Exception:
                    continue
            
            # print(f"Fetched data for stocks: {[stock.symbol for stock in stock_data_list]}")

            # Prepare detailed stock information for the prompt
            stocks_info = ""
            for stock in stock_data_list:
                stocks_info += f"""
                {stock.symbol} ({stock.name}):
                - Price: ${stock.current_price} ({stock.change_percent}%)
                - P/E: {stock.pe_ratio or 'N/A'}
                - Div Yield: {stock.dividend_yield * 100:.2f}%
                - Market Cap: ${stock.market_cap:,}
                - Beta: {stock.additional_data.get('beta', 'N/A')}
                - RSI: {stock.additional_data.get('rsi', 'N/A')}
                - Sentiment: {stock.additional_data.get('sentiment_score', 'N/A')}
                """
            
            analysis_prompt = f"""
            Based on this query: '{query_data.query}'
            
            Here are the relevant stocks with key metrics:
            {stocks_info}
            
            Please provide:
            1. Why these stocks are relevant to the query
            2. A brief analysis of each stock (strengths, weaknesses)
            3. How they compare to each other on key metrics
            4. Which stock(s) might be the best fit for the query criteria
            
            Keep your analysis factual and focused on the data provided.
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return StockResponse(
                query=query_data.query,
                response=analysis,
                data=stock_data_list,
                query_type=QueryType.LIST
            )
        
        elif (isinstance(query_data.query_type, str) and query_data.query_type == "COMPARISON") or query_data.query_type == QueryType.COMPARISON:

            # print(f"inside comparison scope")

            # Extract symbols from query if not provided
            if not query_data.symbols or len(query_data.symbols) < 2:
                symbols_prompt = f"""
                Extract the stock symbols being compared in this query: '{query_data.query}'.
                Return only the symbols separated by commas without any explanation.
                Example: AAPL, MSFT, GOOG
                """
                symbols_text = await analyze_with_gemini(symbols_prompt)
                query_data.symbols = [s.strip() for s in symbols_text.split(",")]
            
            # Fetch comprehensive data for each stock
            stock_data_list = []
            for symbol in query_data.symbols:
                try:
                    stock_data = await fetch_stock_data(symbol)
                    stock_data_list.append(stock_data)
                except Exception:
                    continue
            
            # print(f"Fetched data for comparison: {[stock.symbol for stock in stock_data_list]}")

            # Prepare comparative analysis data
            comparison_table = ""
            for stock in stock_data_list:
                comparison_table += f"""
                {stock.symbol} ({stock.name}):
                - Price: ${stock.current_price} ({stock.change_percent}%)
                - P/E Ratio: {stock.pe_ratio or 'N/A'}
                - EPS: ${stock.additional_data.get('eps', 'N/A')}
                - Div Yield: {stock.dividend_yield * 100:.2f}%
                - Market Cap: ${stock.market_cap:,}
                - Revenue Growth: {stock.additional_data.get('revenue_growth', 0) * 100:.2f}%
                - Debt/Equity: {stock.additional_data.get('debt_to_equity', 'N/A')}
                - Beta: {stock.additional_data.get('beta', 'N/A')}
                - RSI: {stock.additional_data.get('rsi', 'N/A')}
                - Sentiment: {stock.additional_data.get('sentiment_score', 'N/A')}
                """
            
            analysis_prompt = f"""
            Provide a detailed comparison of these stocks based on the query: '{query_data.query}'
            
            Comparative data:
            {comparison_table}
            
            Please provide:
            1. A side-by-side comparison of key metrics
            2. Relative strengths and weaknesses of each company
            3. Analysis of valuation (which is more fairly valued)
            4. Analysis of growth prospects
            5. Analysis of risk factors (volatility, debt, etc.)
            
            Conclude with a recommendation on which stock(s) might be better investments
            based on the specific criteria in the query, and explain your reasoning.
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return StockResponse(
                query=query_data.query,
                response=analysis,
                data=stock_data_list,
                query_type=QueryType.COMPARISON
            )
        
        else:  # GENERAL query

            # print(f"inside general scope")

            # Use Gemini API for general queries with more financial context
            prompt = f"""
            You are an expert financial advisor specializing in stock market analysis. 
            Answer this question about stocks, investing, or financial markets:
            
            {query_data.query}
            
            Provide a detailed but concise response with factual information.
            Include relevant financial concepts, market principles, or investing strategies 
            that would help the user understand the topic better.
            
            If applicable, mention:
            - Key financial metrics to consider
            - Risk factors to be aware of
            - Historical context or trends
            - Different approaches or strategies
            
            Keep your response educational and avoid making specific investment recommendations 
            unless the query explicitly asks for them.
            """
            
            analysis = await analyze_with_gemini(prompt)
            
            return StockResponse(
                query=query_data.query,
                response=analysis,
                data=None,
                query_type=QueryType.GENERAL
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))