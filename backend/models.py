from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    whatsapp_number = Column(String, nullable=False)
    refresh_token = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

class ProcessedEmail(Base):
    __tablename__ = "processed_emails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail_message_id = Column(String, unique=True, index=True, nullable=False)
    sender = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    status = Column(String, default="PROCESSED")
    processed_at = Column(DateTime, default=func.now())

    analysis = relationship("EmailAnalysis", back_populates="email", uselist=False)

class EmailAnalysis(Base):
    __tablename__ = "email_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_id = Column(Integer, ForeignKey('processed_emails.id'), unique=True)
    category = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    deadline = Column(String, nullable=True)
    deadline_iso = Column(DateTime, nullable=True, index=True)
    action_required = Column(Text, nullable=True)
    execution_tier = Column(String, nullable=True)
    reminder_sent = Column(Boolean, default=False, nullable=False, index=True)

    email = relationship("ProcessedEmail", back_populates="analysis")
