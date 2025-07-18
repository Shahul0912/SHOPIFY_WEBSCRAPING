from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base

class Brand(Base):
    __tablename__ = "brands"
    id = Column(Integer, primary_key=True, index=True)
    website_url = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    insights = relationship("BrandInsight", back_populates="brand", cascade="all, delete-orphan")

class BrandInsight(Base):
    __tablename__ = "brand_insights"
    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    insights_json = Column(Text, nullable=False)  # Store as JSON string
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    brand = relationship("Brand", back_populates="insights") 