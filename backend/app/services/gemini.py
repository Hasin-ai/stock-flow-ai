import google.generativeai as genai
from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.http import models
from fastapi import HTTPException

# Initialize Gemini API
genai.configure(api_key=settings.gemini_api_key)
gemini_model = genai.GenerativeModel('gemini-1.5-pro')

# Initialize Qdrant client
qdrant_client = QdrantClient(url=settings.qdrant_url)

async def analyze_with_gemini(prompt: str) -> str:
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing with Gemini: {str(e)}")

async def detect_query_type(query: str, context: str = "stock") -> str:
    try:
        if context == "stock":
            prompt = f"""
            Analyze this stock-related query: "{query}"
            Classify it into one of these categories:
            - SINGLE: Query about a single specific stock
            - LIST: Query asking for a list of stocks based on certain criteria
            - COMPARISON: Query comparing multiple specific stocks
            - GENERAL: General query about the stock market or investing
            
            Return ONLY one of these exact strings: SINGLE, LIST, COMPARISON, or GENERAL
            """
        else:  # PDF context
            doc_context = "about a specific document" if context else "without specifying a document"
            prompt = f"""
            Analyze this document-related query: "{query}" {doc_context}
            
            Classify it into one of these categories:
            - SPECIFIC: Query about specific information in a document
            - COMPARATIVE: Query comparing multiple documents or aspects
            - GENERAL: General query about document analysis
            
            Return ONLY one of these exact strings: SPECIFIC, COMPARATIVE, or GENERAL
            """
        
        response = await analyze_with_gemini(prompt)
        return response.strip().upper()
    except Exception:
        # Provide a reasonable default if query type detection fails
        return "GENERAL" if context == "stock" else "SPECIFIC"

async def search_vector_db(query: str, collection: str, doc_id: str = None, limit: int = 5) -> list:
    try:
        # Generate embedding for the query
        embedding_response = genai.embed_content(
            model="models/embedding-001",
            content=query,
            task_type="RETRIEVAL_DOCUMENT"  # Changed from RETRIEVAL_QUERY to RETRIEVAL_DOCUMENT for consistency
        )
        embedding = embedding_response['embedding']
        
        # Verify embedding dimension and fix if needed
        if len(embedding) != 1536 and collection == "documents":
            print(f"Warning: Embedding dimension mismatch. Got {len(embedding)}, expected 1536.")
            # Force correct dimensions by padding or truncating
            if len(embedding) < 1536:
                # Pad with zeros if too short
                embedding = embedding + [0.0] * (1536 - len(embedding))
            else:
                # Truncate if too long
                embedding = embedding[:1536]
        
        # Create filter if doc_id is provided
        search_filter = None
        if doc_id and collection == "documents":
            search_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id)
                    )
                ]
            )
        
        # Execute search
        search_results = qdrant_client.search(
            collection_name=collection,
            query_vector=embedding,
            limit=limit,
            query_filter=search_filter
        )
        
        # Format results based on collection type
        results = []
        for result in search_results:
            if collection == "stocks":
                results.append(result.payload)
            else:
                results.append({
                    "score": result.score,
                    "doc_id": result.payload.get("doc_id"),
                    "chunk_id": result.payload.get("chunk_id"),
                    "page_num": result.payload.get("page_num"),
                    "text": result.payload.get("text"),
                    "filename": result.payload.get("filename"),
                    "title": result.payload.get("title")
                })
        return results
    except Exception as e:
        # Log the error details for debugging
        import traceback
        error_details = f"Error searching vector database: {str(e)}\n{traceback.format_exc()}"
        print(error_details)
        
        raise HTTPException(status_code=500, detail=f"Error searching vector database: {str(e)}")