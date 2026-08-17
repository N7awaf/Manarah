from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey
)

from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship
)

from datetime import datetime


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATABASE_URL = "sqlite:///manarah.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        "check_same_thread": False
    }
)

Base = declarative_base()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)


# ============================================================
# USER
# ============================================================

class User(Base):

    __tablename__ = "users"

    UserID = Column(
        Integer,
        primary_key=True,
        index=True
    )

    Username = Column(
        String,
        unique=True,
        nullable=False
    )

    PasswordHash = Column(
        String,
        nullable=False
    )

    Role = Column(
        String,
        default="parent",
        nullable=False
    )

    Email = Column(
        String,
        nullable=True
    )

    profiles = relationship(
        "Profile",
        back_populates="user",
        cascade="all, delete-orphan"
    )


# ============================================================
# CHILD PROFILE
# ============================================================

class Profile(Base):

    __tablename__ = "profiles"

    ProfileID = Column(
        Integer,
        primary_key=True,
        index=True
    )

    UserID = Column(
        Integer,
        ForeignKey("users.UserID"),
        nullable=False
    )

    DisplayName = Column(
        String,
        nullable=False
    )

    Age = Column(
        String,
        nullable=True
    )

    Gender = Column(
        String,
        nullable=True
    )

    FamilyOrder = Column(
        String,
        nullable=True
    )

    Interests = Column(
        Text,
        nullable=True
    )

    Mood = Column(
        String,
        nullable=True
    )

    Notes = Column(
        Text,
        nullable=True
    )

    user = relationship(
        "User",
        back_populates="profiles"
    )

    sessions = relationship(
        "Session",
        back_populates="child",
        cascade="all, delete-orphan"
    )


# ============================================================
# SESSION
# ============================================================

class Session(Base):

    __tablename__ = "sessions"

    SessionID = Column(
        Integer,
        primary_key=True,
        index=True
    )

    ChildID = Column(
        Integer,
        ForeignKey("profiles.ProfileID"),
        nullable=False
    )

    StartTime = Column(
        DateTime,
        default=datetime.utcnow
    )

    EndTime = Column(
        DateTime,
        nullable=True
    )

    Advice = Column(
        Text,
        nullable=True
    )

    EmotionalMap = Column(
        Text,
        nullable=True
    )

    ParentNotes = Column(
        Text,
        nullable=True
    )

    child = relationship(
        "Profile",
        back_populates="sessions"
    )

    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan"
    )


# ============================================================
# MESSAGE
# ============================================================

class Message(Base):

    __tablename__ = "messages"

    MessageID = Column(
        Integer,
        primary_key=True,
        index=True
    )

    SessionID = Column(
        Integer,
        ForeignKey("sessions.SessionID"),
        nullable=False
    )

    Transcript_Text = Column(
        Text,
        nullable=False
    )

    Audio_File_URL = Column(
        Text,
        nullable=True
    )

    Child_Audio_URL = Column(
        Text,
        nullable=True
    )

    Timestamp = Column(
        DateTime,
        default=datetime.utcnow
    )

    session = relationship(
        "Session",
        back_populates="messages"
    )


# ============================================================
# SAFETY ALERT
# ============================================================

class Alert(Base):

    __tablename__ = "alerts"

    AlertID = Column(
        Integer,
        primary_key=True,
        index=True
    )

    ChildID = Column(
        Integer,
        ForeignKey("profiles.ProfileID"),
        nullable=False
    )

    MessageText = Column(
        Text,
        nullable=False
    )

    Level = Column(
        String,
        nullable=False
    )

    Timestamp = Column(
        DateTime,
        default=datetime.utcnow
    )

    IsRead = Column(
        String,
        default="false"
    )


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def init_db():

    Base.metadata.create_all(
        bind=engine
    )


if __name__ == "__main__":

    init_db()