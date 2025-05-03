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

        # Process based on query type
        if query_data.query_type == QueryType.SINGLE:
            # Extract symbol if not provided
            if not query_data.symbols or len(query_data.symbols) == 0 or query_data.symbols[0] == "string":
                symbol_prompt = f"Extract the stock symbol from this query: '{query_data.query}'. Return only the symbol without any explanation or extra text."
                symbol = await analyze_with_gemini(symbol_prompt)
                symbol = symbol.strip().upper()
                query_data.symbols = [symbol]

            # Fetch data for the single stock
            stock_data = await fetch_stock_data(query_data.symbols[0])

            # Analyze with Gemini
            analysis_prompt = f"""
            Analyze this stock data for {stock_data.symbol}:
            Current Price: ${stock_data.current_price}
            Change: {stock_data.change_percent}%
            Volume: {stock_data.volume or 'N/A'}
            Additional Data: {stock_data.additional_data or 'N/A'}
            
            Based on this information and addressing this query: '{query_data.query}'
            Provide a concise analysis.
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return StockResponse(
                query=query_data.query,
                response=analysis,
                data=[stock_data],
                query_type=QueryType.SINGLE
            )
        
        elif query_data.query_type == QueryType.LIST:
            # Search vector DB for relevant stocks
            matching_stocks = await search_vector_db(query_data.query)
            
            # If we have matches from vector DB, use those symbols
            if matching_stocks and len(matching_stocks) > 0:
                symbols = [stock.get("symbol") for stock in matching_stocks if "symbol" in stock]
            # Otherwise, ask Gemini to suggest stocks
            else:
                suggestion_prompt = f"""
                Based on this query: '{query_data.query}'
                Suggest 3-5 stock symbols that would be relevant for this query.
                Return only the symbols separated by commas without any explanation.
                Example: AAPL, MSFT, GOOG
                """
                symbols_text = await analyze_with_gemini(suggestion_prompt)
                symbols = [s.strip() for s in symbols_text.split(",")]
            
            # Fetch data for each stock
            stock_data_list = []
            for symbol in symbols[:5]:  # Limit to 5 stocks
                try:
                    stock_data = await fetch_stock_data(symbol)
                    stock_data_list.append(stock_data)
                except Exception:
                    continue
            
            # Analyze with Gemini
            stocks_info = "\n".join([
                f"{s.symbol}: ${s.current_price} ({s.change_percent}%)" 
                for s in stock_data_list
            ])
            
            analysis_prompt = f"""
            Based on this query: '{query_data.query}'
            
            Here are the relevant stocks:
            {stocks_info}
            
            Provide an analysis explaining why these stocks are relevant to the query
            and a brief analysis of each one.
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return StockResponse(
                query=query_data.query,
                response=analysis,
                data=stock_data_list,
                query_type=QueryType.LIST
            )
        
        elif query_data.query_type == QueryType.COMPARISON:
            # Extract symbols from query if not provided
            if not query_data.symbols or len(query_data.symbols) < 2:
                symbols_prompt = f"""
                Extract the stock symbols being compared in this query: '{query_data.query}'.
                Return only the symbols separated by commas without any explanation.
                Example: AAPL, MSFT, GOOG
                """
                symbols_text = await analyze_with_gemini(symbols_prompt)
                query_data.symbols = [s.strip() for s in symbols_text.split(",")]
            
            # Fetch data for each stock
            stock_data_list = []
            for symbol in query_data.symbols:
                try:
                    stock_data = await fetch_stock_data(symbol)
                    stock_data_list.append(stock_data)
                except Exception:
                    continue
            
            # Analyze with Gemini
            comparison_data = "\n".join([
                f"{s.symbol}: Price=${s.current_price}, Change={s.change_percent}%"
                for s in stock_data_list
            ])
            
            analysis_prompt = f"""
            Compare these stocks based on the query: '{query_data.query}'
            
            Stock data:
            {comparison_data}
            
            Provide a detailed comparison highlighting the strengths and weaknesses of each,
            and recommend which might be better based on the specific criteria in the query.
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return StockResponse(
                query=query_data.query,
                response=analysis,
                data=stock_data_list,
                query_type=QueryType.COMPARISON
            )
        
        else:  # GENERAL query
            # Use Gemini API for general queries
            prompt = f"""
            You are a stock market expert. Answer this question about stocks or investing:
            
            {query_data.query}
            
            Provide a detailed but concise response with factual information.
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