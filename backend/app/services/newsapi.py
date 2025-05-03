# Example (not generated unless requested)
async def fetch_news(symbol: str) -> list:
    url = f"https://newsapi.org/v2/everything?q={symbol}&apiKey={settings.newsapi_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return []
            data = await response.json()
            return data.get("articles", [])[:5]