from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import VECTOR
from app.database import Base

class PDFDocument(Base):
    __tablename__ = "pdf_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    text_content = Column(String, nullable=False)
    embedding = Column(VECTOR(384))  # Assuming 384-dim embeddings from sentence-transformers

    user = relationship("User", back_populates="pdf_documents")