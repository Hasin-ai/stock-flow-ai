import pypdf
import io
import uuid
from typing import List, Dict, Any
from fastapi import HTTPException
from app.schemas.pdf_document import DocumentMetadata, DocumentChunk, DocumentAnalysis
from app.services.gemini import analyze_with_gemini, search_vector_db, detect_query_type
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings
import google.generativeai as genai

# Initialize Gemini API
genai.configure(api_key=settings.gemini_api_key)

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

# filepath: g:\AI Hackathon\stock_flow_ai\backend\app\services\pdf_processor.py
async def generate_embedding(text: str) -> List[float]:
    try:
        embedding_response = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="RETRIEVAL_DOCUMENT"  # This produces 1536-dim embeddings
        )
        return embedding_response['embedding']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embedding: {str(e)}")
    
async def store_in_vector_db(chunks: List[DocumentChunk], doc_id: str, metadata: DocumentMetadata) -> List[str]:
    try:
        embedding_ids = []
        
        for chunk in chunks:
            try:
                embedding = await generate_embedding(chunk.text)
                
                # Debug - verify embedding dimension
                if len(embedding) != 1536:
                    print(f"Warning: Embedding dimension mismatch. Got {len(embedding)}, expected 1536.")
                    # Force correct dimensions by padding or truncating if needed
                    if len(embedding) < 1536:
                        # Pad with zeros if too short (shouldn't happen with Gemini)
                        embedding = embedding + [0.0] * (1536 - len(embedding))
                    else:
                        # Truncate if too long 
                        embedding = embedding[:1536]
                        
                embedding_id = f"{chunk.chunk_id}_emb"
                
                # Use a more deterministic ID to avoid collisions and enable updates
                point_id = abs(hash(f"{doc_id}_{chunk.chunk_id}")) % (2**31 - 1)
                
                qdrant_client.upsert(
                    collection_name="documents",
                    points=[
                        models.PointStruct(
                            id=point_id,
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
                
            except Exception as chunk_error:
                print(f"Error processing chunk {chunk.chunk_id}: {str(chunk_error)}")
                # Continue with other chunks instead of failing the entire operation
                continue
                
        if not embedding_ids:
            raise ValueError("No chunks were successfully embedded and stored")
            
        return embedding_ids
    except Exception as e:
        print(f"Vector database storage error: {str(e)}")
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
        
        # Try to parse JSON response
        try:
            import json
            import re
            
            # Extract JSON if it's embedded in markdown or other text
            json_match = re.search(r'```json\s*(.*?)\s*```|```\s*(.*?)\s*```|({.*})', analysis_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1) or json_match.group(2) or json_match.group(3)
                analysis_data = json.loads(json_str)
            else:
                # If no JSON formatting found, attempt to parse the entire response
                analysis_data = json.loads(analysis_text)
                
            return DocumentAnalysis(
                doc_id=metadata.doc_id,
                summary=analysis_data.get("summary", "No summary available."),
                key_points=analysis_data.get("key_points", ["No key points available."]),
                topics=analysis_data.get("topics", ["No topics available."]),
                sentiment=analysis_data.get("sentiment", "Neutral"),
                recommendations=analysis_data.get("recommendations", ["No recommendations available."])
            )
            
        except (json.JSONDecodeError, AttributeError, KeyError) as json_err:
            # Fallback to a more robust approach if JSON parsing fails
            print(f"JSON parsing error: {str(json_err)}. Using fallback extraction method.")
            
            # Simple text extraction approach
            summary = extract_section(analysis_text, ["summary", "overview"], 200)
            key_points = extract_list_items(analysis_text, ["key points", "main points", "important points"])
            topics = extract_list_items(analysis_text, ["topics", "themes", "subject"])
            sentiment = extract_section(analysis_text, ["sentiment", "tone"], 20)
            recommendations = extract_list_items(analysis_text, ["recommendations", "next steps", "actions"])
            
            return DocumentAnalysis(
                doc_id=metadata.doc_id,
                summary=summary or "This document contains information that could not be fully analyzed.",
                key_points=key_points[:7] if key_points else ["The document requires manual review."],
                topics=topics[:5] if topics else ["General content"],
                sentiment=sentiment or "Neutral",
                recommendations=recommendations[:5] if recommendations else ["Review the document manually."]
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing document: {str(e)}")

def extract_section(text: str, keywords: List[str], max_length: int = 100) -> str:
    """Extract a section from text based on keywords."""
    lower_text = text.lower()
    for keyword in keywords:
        if keyword.lower() in lower_text:
            start_idx = lower_text.find(keyword.lower())
            section_start = text.find(":", start_idx)
            if section_start != -1:
                section_text = text[section_start + 1:].strip()
                end_markers = ["\n\n", "\n#", "\n*"]
                for marker in end_markers:
                    if marker in section_text:
                        section_text = section_text.split(marker)[0].strip()
                return section_text[:max_length].strip()
    return ""

def extract_list_items(text: str, keywords: List[str]) -> List[str]:
    """Extract list items following certain keywords."""
    items = []
    lower_text = text.lower()
    
    for keyword in keywords:
        if keyword.lower() in lower_text:
            start_idx = lower_text.find(keyword.lower())
            section_start = text.find(":", start_idx)
            if section_start != -1:
                section_text = text[section_start + 1:].strip()
                
                # Try to find list items with different markers
                patterns = [
                    r'\n\s*[-•*]\s*(.*?)(?=\n\s*[-•*]|\n\n|$)',  # Bullet points
                    r'\n\s*(\d+)[.):]\s*(.*?)(?=\n\s*\d+[.):]|\n\n|$)',  # Numbered items
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, "\n" + section_text, re.DOTALL)
                    if matches:
                        # Handle different match group structures
                        if isinstance(matches[0], tuple):
                            new_items = [m[-1].strip() for m in matches if m[-1].strip()]
                        else:
                            new_items = [m.strip() for m in matches if m.strip()]
                        items.extend(new_items)
                        break
                
                # If no structured list found, try splitting by newlines
                if not items:
                    potential_items = section_text.split("\n")
                    items = [item.strip().lstrip('-•*').strip() for item in potential_items if item.strip()]
                    
                # If we found items, no need to check other keywords
                if items:
                    break
    
    return [item for item in items if len(item) > 5]  # Filter out very short items