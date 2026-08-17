from database import (
    SessionLocal,
    Session,
    Message,
    User,
    Profile,
    Alert,
    init_db
)

from datetime import datetime


# ============================================================
# INITIALIZE DATABASE
# ============================================================

init_db()


# ============================================================
# SAVE CONVERSATION MESSAGE
# ============================================================

def save_message(
    transcript: str,
    audio_url: str,
    child_id: int,
    child_audio_url: str = None
) -> int:

    db = SessionLocal()

    try:

        session = (
            db.query(Session)
            .filter(
                Session.ChildID == child_id,
                Session.EndTime.is_(None)
            )
            .first()
        )

        if not session:

            session = Session(
                ChildID=child_id,
                StartTime=datetime.utcnow()
            )

            db.add(session)
            db.commit()
            db.refresh(session)

        message = Message(
            SessionID=session.SessionID,
            Transcript_Text=transcript,
            Audio_File_URL=audio_url,
            Child_Audio_URL=child_audio_url,
            Timestamp=datetime.utcnow()
        )

        db.add(message)
        db.commit()
        db.refresh(message)

        return message.MessageID

    finally:
        db.close()


# ============================================================
# SAVE SAFETY ALERT
# ============================================================

def save_alert(
    child_id: int,
    message_text: str,
    level: str
):

    db = SessionLocal()

    try:

        alert = Alert(
            ChildID=child_id,
            MessageText=message_text,
            Level=level,
            Timestamp=datetime.utcnow(),
            IsRead="false"
        )

        db.add(alert)
        db.commit()

    finally:
        db.close()


# ============================================================
# GET CHILD SESSIONS
# ============================================================

def get_all_sessions(child_id: int):

    db = SessionLocal()

    try:

        sessions = (
            db.query(Session)
            .filter(
                Session.ChildID == child_id
            )
            .order_by(
                Session.StartTime.desc()
            )
            .all()
        )

        result = []

        for session in sessions:

            result.append(
                {
                    "session_id": session.SessionID,

                    "start_time": (
                        session.StartTime.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if session.StartTime
                        else ""
                    ),

                    "end_time": (
                        session.EndTime.strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if session.EndTime
                        else None
                    ),

                    "notes": (
                        session.ParentNotes
                        if session.ParentNotes
                        else ""
                    ),

                    "advice": (
                        session.Advice
                        if session.Advice
                        else "بانتظار التحليل..."
                    )
                }
            )

        return result

    finally:
        db.close()


# ============================================================
# GET PARENT EMAIL
# ============================================================

def get_parent_email(child_id: int):

    db = SessionLocal()

    try:

        child = (
            db.query(Profile)
            .filter(
                Profile.ProfileID == child_id
            )
            .first()
        )

        if not child:
            return None

        user = (
            db.query(User)
            .filter(
                User.UserID == child.UserID
            )
            .first()
        )

        if not user:
            return None

        return user.Email

    finally:
        db.close()


# ============================================================
# CHECK CHILD OWNERSHIP
# ============================================================

def user_owns_child(
    user_id: int,
    child_id: int
) -> bool:

    db = SessionLocal()

    try:

        child = (
            db.query(Profile)
            .filter(
                Profile.ProfileID == child_id,
                Profile.UserID == user_id
            )
            .first()
        )

        return child is not None

    finally:
        db.close()


# ============================================================
# GET OWNED CHILD
# ============================================================

def get_owned_child(
    user_id: int,
    child_id: int
):

    db = SessionLocal()

    try:

        return (
            db.query(Profile)
            .filter(
                Profile.ProfileID == child_id,
                Profile.UserID == user_id
            )
            .first()
        )

    finally:
        db.close()


# ============================================================
# CHECK SESSION OWNERSHIP
# ============================================================

def user_owns_session(
    user_id: int,
    session_id: int
) -> bool:

    db = SessionLocal()

    try:

        result = (
            db.query(Session)
            .join(
                Profile,
                Session.ChildID == Profile.ProfileID
            )
            .filter(
                Session.SessionID == session_id,
                Profile.UserID == user_id
            )
            .first()
        )

        return result is not None

    finally:
        db.close()


# ============================================================
# GET OWNED SESSION
# ============================================================

def get_owned_session(
    user_id: int,
    session_id: int
):

    db = SessionLocal()

    try:

        return (
            db.query(Session)
            .join(
                Profile,
                Session.ChildID == Profile.ProfileID
            )
            .filter(
                Session.SessionID == session_id,
                Profile.UserID == user_id
            )
            .first()
        )

    finally:
        db.close()


# ============================================================
# CHECK USER EXISTS
# ============================================================

def user_exists(username: str) -> bool:

    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.Username == username
            )
            .first()
        )

        return user is not None

    finally:
        db.close()


# ============================================================
# GET PARENT USERS
# ============================================================
# تستخدم فقط في وضع التطوير المحلي.
# لا تستخدم في تجربة الطفل العامة.
# ============================================================

def get_all_parent_users():

    db = SessionLocal()

    try:

        users = (
            db.query(User)
            .filter(
                User.Role == "parent"
            )
            .order_by(
                User.UserID.asc()
            )
            .all()
        )

        return [
            {
                "id": user.UserID,
                "username": user.Username
            }
            for user in users
        ]

    finally:
        db.close()


# ============================================================
# GET CHILDREN FOR SIMULATION
# ============================================================
# تستخدم فقط في وضع التطوير المحلي.
# ============================================================

def get_children_for_simulation(
    user_id: int
):

    db = SessionLocal()

    try:

        children = (
            db.query(Profile)
            .filter(
                Profile.UserID == user_id
            )
            .order_by(
                Profile.ProfileID.asc()
            )
            .all()
        )

        return [
            {
                "id": child.ProfileID,
                "name": child.DisplayName,
                "gender": child.Gender,
                "age": child.Age,
                "interests": child.Interests
            }
            for child in children
        ]

    finally:
        db.close()