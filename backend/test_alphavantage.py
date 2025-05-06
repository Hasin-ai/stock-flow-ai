import httpx
import asyncio
from app.config import settings

async def test_alphavantage():
    """Simple test for AlphaVantage API"""
    # Basic API endpoint for a simple stock quote
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=NVDA&apikey=IQALOI8LRDP85MNM"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()
        
        print("API Response:")
        print(data)
        
        # Check if the response has the expected structure
        if "Global Quote" in data:
            print("\nAPI test successful!")
            print(f"Current price of MSFT: {data['Global Quote'].get('05. price', 'Not available')}")
        else:
            print("\nAPI test failed or response format unexpected")
            print("Check your API key or if you've exceeded your API call limits")

if __name__ == "__main__":
    asyncio.run(test_alphavantage())