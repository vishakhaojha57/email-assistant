import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./email_assistant.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

if __name__ == "__main__":
    import sys
    # Add the root directory to sys.path to allow imports like 'backend.models'
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from backend.models import Base
    from backend.crud import is_email_already_processed, save_processed_email
    
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    # Test DB Session
    db = SessionLocal()
    
    dummy_id = "test_gmail_message_id_12345"
    
    print(f"Checking if '{dummy_id}' is processed (expected False on first run):", is_email_already_processed(db, dummy_id))
    
    if not is_email_already_processed(db, dummy_id):
        print(f"Saving dummy email '{dummy_id}'...")
        save_processed_email(
            db=db,
            gmail_message_id=dummy_id,
            sender="test@example.com",
            subject="Test Subject",
            analysis={"category": "TEST", "summary": "This is a test"}
        )
    else:
        print(f"Dummy email '{dummy_id}' already saved.")
    
    print(f"Checking if '{dummy_id}' is processed (expected True):", is_email_already_processed(db, dummy_id))
    
    unseen_id = "unseen_message_id_999"
    print(f"Checking if '{unseen_id}' is processed (expected False):", is_email_already_processed(db, unseen_id))
    
    db.close()
