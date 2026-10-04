"""Backend wspólnego czatu. Konfiguracja przez zmienne środowiskowe."""
import hmac
import os
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

ROOM_CODE = os.environ.get("CHAT_ROOM_CODE", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./chat.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nickname: Mapped[str] = mapped_column(String(24), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

class MessageInput(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)
    text: str = Field(min_length=1, max_length=2000)

app = FastAPI(title="Czat znajomych", docs_url=None, redoc_url=None)

@app.on_event("startup")
def startup():
    if len(ROOM_CODE) < 8:
        raise RuntimeError("Ustaw CHAT_ROOM_CODE na kod o długości co najmniej 8 znaków.")
    Base.metadata.create_all(engine)

def authorize(x_room_code: str = Header(default="")):
    if not ROOM_CODE or not hmac.compare_digest(x_room_code, ROOM_CODE):
        raise HTTPException(status_code=401, detail="Nieprawidłowy kod pokoju.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/messages")
def list_messages(after_id: int = Query(default=0, ge=0), _auth: None = Depends(authorize), db: Session = Depends(get_db)):
    query = select(Message).where(Message.id > after_id).order_by(Message.id.desc()).limit(100)
    messages = list(reversed(db.scalars(query).all()))
    return [{"id": m.id, "nickname": m.nickname, "text": m.text, "created_at": m.created_at.isoformat()} for m in messages]

@app.post("/messages")
def send_message(payload: MessageInput, _auth: None = Depends(authorize), db: Session = Depends(get_db)):
    nickname, text = payload.nickname.strip(), payload.text.strip()
    if not nickname or not text:
        raise HTTPException(status_code=422, detail="Nick i wiadomość nie mogą być puste.")
    message = Message(nickname=nickname, text=text, created_at=datetime.now(timezone.utc))
    db.add(message)
    db.commit()
    db.refresh(message)
    return {"id": message.id, "nickname": message.nickname, "text": message.text, "created_at": message.created_at.isoformat()}
