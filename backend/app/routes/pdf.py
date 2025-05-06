from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.pdf_document import DocumentUploadResponse, DocumentQuery, DocumentQueryResponse, QueryType
from app.services.pdf_processor import extract_text_from_pdf, extract_metadata_from_pdf, chunk_document, generate_embedding, store_in_vector_db, analyze_document
from app.services.gemini import search_vector_db, detect_query_type, analyze_with_gemini
from app.dependencies import get_client_user
from app.models.user import User
from app.models.activity_log import ActivityLog
from datetime import datetime

router = APIRouter()

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    document_name: str = Form(None),
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Extract metadata
        metadata = await extract_metadata_from_pdf(file_content, file.filename)
        
        # Override title if provided
        if document_name:
            metadata.title = document_name
        
        # Extract text by page
        pages = await extract_text_from_pdf(file_content)
        
        # Chunk document for embedding
        chunks = await chunk_document(pages, metadata.doc_id)
        
        # Store in vector database
        embedding_ids = await store_in_vector_db(chunks, metadata.doc_id, metadata)
        
        # Combine all text for analysis
        full_text = "\n\n".join([page["text"] for page in pages])
        
        # Analyze document
        analysis = await analyze_document(full_text, metadata)
        
        # Log activity
        db_log = ActivityLog(
            user_id=current_user.id,
            action=f"Uploaded PDF: {file.filename}",
            timestamp=datetime.utcnow()
        )
        db.add(db_log)
        db.commit()
        
        return DocumentUploadResponse(
            doc_id=metadata.doc_id,
            filename=metadata.filename,
            analysis=analysis,
            metadata=metadata
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query", response_model=DocumentQueryResponse)
async def query_pdf(
    query_data: DocumentQuery,
    current_user: User = Depends(get_client_user),
    db: Session = Depends(get_db)
):
    try:
        # Log activity
        db_log = ActivityLog(
            user_id=current_user.id,
            action=f"PDF query: {query_data.query}",
            timestamp=datetime.utcnow()
        )
        db.add(db_log)
        db.commit()

        # Auto-detect query type if not specified
        if not query_data.query_type:
            detected_type = await detect_query_type(query_data.query, "pdf" if query_data.doc_id else None)
            # Map the string result to the actual enum
            if detected_type == "SPECIFIC":
                query_data.query_type = QueryType.SPECIFIC
            elif detected_type == "COMPARATIVE":
                query_data.query_type = QueryType.COMPARATIVE
            else:
                query_data.query_type = QueryType.GENERAL
        
        # Process based on query type
        if query_data.query_type == QueryType.SPECIFIC and query_data.doc_id:
            # Search vector DB for relevant chunks
            relevant_chunks = await search_vector_db(query_data.query, "documents", query_data.doc_id)
            
            if not relevant_chunks:
                return DocumentQueryResponse(
                    query=query_data.query,
                    response="No relevant information found in the document.",
                    doc_id=query_data.doc_id,
                    query_type=QueryType.SPECIFIC
                )
            
            # Prepare context from chunks
            context = "\n\n".join([f"Page {chunk['page_num']}:\n{chunk['text']}" for chunk in relevant_chunks])
            
            # Analyze with Gemini
            analysis_prompt = f"""
            Based on the following excerpts from document ID {query_data.doc_id}, please answer this query:
            
            Query: {query_data.query}
            
            Document excerpts:
            {context}
            
            Provide a detailed answer based solely on the information provided in these excerpts.
            Include relevant quotes or page numbers where applicable.
            
            If the document excerpts don't contain enough information to answer the query fully,
            acknowledge this limitation in your response.
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return DocumentQueryResponse(
                query=query_data.query,
                response=analysis,
                doc_id=query_data.doc_id,
                query_type=QueryType.SPECIFIC,
                source_chunks=relevant_chunks
            )
        
        elif query_data.query_type == QueryType.COMPARATIVE:
            # Search across all documents or specified documents
            relevant_chunks = await search_vector_db(query_data.query, "documents", query_data.doc_id, limit=10)
            
            if not relevant_chunks:
                return DocumentQueryResponse(
                    query=query_data.query,
                    response="No relevant information found for comparison.",
                    doc_id=query_data.doc_id,
                    query_type=QueryType.COMPARATIVE
                )
            
            # Group chunks by document
            docs = {}
            for chunk in relevant_chunks:
                doc_id = chunk["doc_id"]
                if doc_id not in docs:
                    docs[doc_id] = []
                docs[doc_id].append(chunk)
            
            # Prepare context for comparison
            comparison_context = ""
            for doc_id, chunks in docs.items():
                doc_info = f"Document: {chunks[0]['title'] or chunks[0]['filename'] or doc_id}\n"
                doc_context = "\n".join([f"Page {c['page_num']}:\n{c['text']}" for c in chunks])
                comparison_context += f"{doc_info}{doc_context}\n\n{'='*50}\n\n"
            
            # Analyze with Gemini
            analysis_prompt = f"""
            Compare the following document excerpts to answer this query:
            
            Query: {query_data.query}
            
            Document excerpts:
            {comparison_context}
            
            Provide a detailed comparison based on the information provided in these excerpts.
            Include relevant quotes or page numbers to support your analysis.
            
            Structure your answer to clearly identify similarities and differences between 
            the documents or sections being compared.
            """
            
            analysis = await analyze_with_gemini(analysis_prompt)
            
            return DocumentQueryResponse(
                query=query_data.query,
                response=analysis,
                doc_id=query_data.doc_id,
                query_type=QueryType.COMPARATIVE,
                source_chunks=relevant_chunks
            )
        
        else:  # GENERAL query
            # Use Gemini without specific document context
            prompt = f"""
            You are a document analysis expert. Answer this question about document analysis:
            
            {query_data.query}
            
            Provide a detailed but concise response with factual information.
            If the question is about analyzing financial documents specifically:
            1. Mention common sections of financial reports to look for
            2. Explain key metrics or terminology that might be relevant
            3. Suggest approaches for extracting valuable insights
            
            Format your response in a clear, easy-to-read structure with bullet points 
            or numbered lists where appropriate.
            """
            
            analysis = await analyze_with_gemini(prompt)
            
            return DocumentQueryResponse(
                query=query_data.query,
                response=analysis,
                doc_id=query_data.doc_id,
                query_type=QueryType.GENERAL
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))