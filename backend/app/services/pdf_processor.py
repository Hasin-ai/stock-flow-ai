import pypdf
import io
import uuid
from typing import List, Dict, Any
from fastapi import HTTPException
from app.schemas.pdf_document import DocumentMetadata, DocumentChunk, DocumentAnalysis
from app.services.gemini import analyze_with_gemini
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings

qdrant_client = QdrantClient(url=settings.qdrant_url)

async def extract_text_from_pdf(file_content: bytes) -> List[Dict[str, Any]]:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_content))
        pages = []
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append({
                    "page_num": i + 1,
                    "text": text
                })
        return pages
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting text from PDF: {str(e)}")

async def extract_metadata_from_pdf(file_content: bytes, filename: str) -> DocumentMetadata:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_content))
        info = reader.metadata
        
        metadata = DocumentMetadata(
            doc_id=str(uuid.uuid4()),
            filename=filename,
            title=info.title if info and hasattr(info, 'title') else None,
            author=info.author if info and hasattr(info, 'author') else None,
            num_pages=len(reader.pages),
            created_date=info.creation_date.strftime("%Y-%m-%d") if info and hasattr(info, 'creation_date') and info.creation_date else None,
            file_size_kb=len(file_content) / 1024
        )
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting metadata from PDF: {str(e)}")

async def chunk_document(pages: List[Dict[str, Any]], doc_id: str, chunk_size: int = 1000) -> List[DocumentChunk]:
    chunks = []
    
    for page in pages:
        page_text = page["text"]
        page_num = page["page_num"]
        
        text_chunks = []
        current_chunk = ""
        
        paragraphs = page_text.split("\n\n")
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) <= chunk_size:
                current_chunk += paragraph + "\n\n"
            else:
                if current_chunk:
                    text_chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
        
        if current_chunk:
            text_chunks.append(current_chunk.strip())
        
        for i, chunk_text in enumerate(text_chunks):
            chunk_id = f"{doc_id}_p{page_num}_c{i+1}"
            chunks.append(DocumentChunk(
                doc_id=doc_id,
                chunk_id=chunk_id,
                page_num=page_num,
                text=chunk_text
            ))
    return chunks

async def generate_embedding(text: str) -> List[float]:
    try:
        embedding_response = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="SEMANTIC_SIMILARITY"
        )
        return embedding_response['embedding']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embedding: {str(e)}")

async def store_in_vector_db(chunks: List[DocumentChunk], doc_id: str, metadata: DocumentMetadata) -> List[str]:
    try:
        embedding_ids = []
        
        for chunk in chunks:
            embedding = await generate_embedding(chunk.text)
            embedding_id = f"{chunk.chunk_id}_emb"
            
            qdrant_client.upsert(
                collection_name="documents",
                points=[
                    models.PointStruct(
                        id=hash(embedding_id) % 100000000,
                        vector=embedding,
                        payload={
                            "doc_id": doc_id,
                            "chunk_id": chunk.chunk_id,
                            "page_num": chunk.page_num,
                            "text": chunk.text,
                            "filename": metadata.filename,
                            "title": metadata.title
                        }
                    )
                ]
            )
            
            embedding_ids.append(embedding_id)
            chunk.embedding_id = embedding_id
        return embedding_ids
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error storing in vector database: {str(e)}")

async def analyze_document(doc_text: str, metadata: DocumentMetadata) -> DocumentAnalysis:
    try:
        max_text_length = 10000
        truncated_text = doc_text[:max_text_length] + "..." if len(doc_text) > max_text_length else doc_text
        
        analysis_prompt = f"""
        Please analyze this document and provide a comprehensive analysis:
        
        Document Title: {metadata.title or "Untitled"}
        Filename: {metadata.filename}
        Pages: {metadata.num_pages}
        
        Document Content:
        {truncated_text}
        
        Please provide:
        1. A concise summary of the document (3-5 sentences)
        2. 5-7 key points from the document
        3. Main topics discussed
        4. Overall sentiment (positive, negative, neutral)
        5. Recommendations or next steps based on the content
        
        Format your response as JSON with the following structure:
        {{
            "summary": "...",
            "key_points": ["point1", "point2", ...],
            "topics": ["topic1", "topic2", ...],
            "sentiment": "...",
            "recommendations": ["rec1", "rec2", ...]
        }}
        """
        
        analysis_text = await analyze_with_gemini(analysis_prompt)
        
        # In production, parse JSON response properly
        # For simplicity, return mock analysis
        return DocumentAnalysis(
            doc_id=metadata.doc_id,
            summary="This is a summary of the document based on its content.",
            key_points=[
                "Key point 1 about the document",
                "Key point 2 about the document",
                "Key point 3 about the document"
            ],
            topics=["Topic 1", "Topic 2", "Topic 3"],
            sentiment="Neutral",
            recommendations=["Recommendation 1", "Recommendation 2"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing document: {str(e)}")