from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    Request,
    HTTPException
)

from fastapi.responses import (
    FileResponse,
    JSONResponse,
    StreamingResponse
)

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.sessions import SessionMiddleware

from whisper_stt import transcribe_audio

from llm_groq import (
    get_response,
    analyze_session_deeply,
    detect_danger
)

from tts_openai import text_to_speech

from db_helper import (
    save_message,
    save_alert,
    get_parent_email,
    user_owns_child,
    user_owns_session
)

from email_alert import send_alert_email

from pydantic import BaseModel

import uvicorn
import shutil
import os
import qrcode
import io
import json
import hashlib
import hmac
import secrets

from datetime import datetime


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Manarah"
)


# ============================================================
# CONFIG
# ============================================================

SECRET_KEY = os.getenv(
    "MANARAH_SECRET_KEY",
    "manarah-development-secret-change-this"
)


# وضع المحاكاة:
#
# 1 = مفعّل على جهازك فقط
# 0 = مغلق
#
# عند النشر:
# MANARAH_DEV_MODE=0
#
# عند التطوير:
# MANARAH_DEV_MODE=1
# ============================================================

DEV_MODE = (
    os.getenv(
        "MANARAH_DEV_MODE",
        "0"
    ).lower()
    in [
        "1",
        "true",
        "yes",
        "on"
    ]
)


# ============================================================
# SESSION
# ============================================================

app.add_middleware(
    SessionMiddleware,

    secret_key=SECRET_KEY,

    session_cookie="manarah_session",

    max_age=60 * 60 * 8,

    same_site="lax",

    https_only=False
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000"
    ],

    allow_credentials=True,

    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "OPTIONS"
    ],

    allow_headers=[
        "Content-Type",
        "Authorization"
    ]
)


# ============================================================
# STATIC
# ============================================================

app.mount(
    "/static",
    StaticFiles(
        directory="static"
    ),
    name="static"
)


if not os.path.exists(
    "static/uploads"
):

    os.makedirs(
        "static/uploads"
    )


# ============================================================
# REQUEST MODELS
# ============================================================

class NoteRequest(BaseModel):

    note: str


class UserCreate(BaseModel):

    username: str

    password: str

    email: str


class UserLogin(BaseModel):

    username: str

    password: str


class ChildCreate(BaseModel):

    # لا نثق بهذا الحقل.
    # المستخدم الحالي يؤخذ من Session.

    user_id: int | None = None

    name: str

    gender: str = "male"

    age: str = ""

    interests: str = ""


# ============================================================
# PASSWORD
# ============================================================

def hash_password(
    password: str
) -> str:

    iterations = 310_000

    salt = secrets.token_hex(
        16
    )

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations
    ).hex()

    return (
        f"pbkdf2${iterations}"
        f"${salt}"
        f"${password_hash}"
    )


def verify_password(
    password: str,
    stored_hash: str
) -> tuple[bool, bool]:

    if not stored_hash:

        return False, False


    # --------------------------------------------------------
    # PBKDF2
    # --------------------------------------------------------

    if stored_hash.startswith(
        "pbkdf2$"
    ):

        try:

            parts = stored_hash.split(
                "$"
            )

            if len(parts) != 4:

                return False, False

            (
                _,
                iterations_text,
                salt,
                expected_hash
            ) = parts

            iterations = int(
                iterations_text
            )

            calculated_hash = (
                hashlib.pbkdf2_hmac(
                    "sha256",
                    password.encode(
                        "utf-8"
                    ),
                    salt.encode(
                        "utf-8"
                    ),
                    iterations
                ).hex()
            )

            valid = hmac.compare_digest(
                calculated_hash,
                expected_hash
            )

            return valid, False

        except Exception:

            return False, False


    # --------------------------------------------------------
    # LEGACY SHA256
    # --------------------------------------------------------

    legacy_hash = hashlib.sha256(
        password.encode(
            "utf-8"
        )
    ).hexdigest()


    if hmac.compare_digest(
        legacy_hash,
        stored_hash
    ):

        return True, True


    return False, False


# ============================================================
# AUTH HELPERS
# ============================================================

def get_current_user_id(
    request: Request
) -> int:

    user_id = request.session.get(
        "user_id"
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="يجب تسجيل الدخول أولاً"
        )

    try:

        return int(user_id)

    except (
        TypeError,
        ValueError
    ):

        request.session.clear()

        raise HTTPException(
            status_code=401,
            detail="جلسة تسجيل الدخول غير صالحة"
        )


def get_current_role(
    request: Request
) -> str:

    role = request.session.get(
        "role"
    )

    if not role:

        raise HTTPException(
            status_code=401,
            detail="يجب تسجيل الدخول أولاً"
        )

    return str(
        role
    ).lower()


def require_parent(
    request: Request
) -> int:

    user_id = get_current_user_id(
        request
    )

    role = get_current_role(
        request
    )

    if role != "parent":

        raise HTTPException(
            status_code=403,
            detail="هذه العملية متاحة لولي الأمر فقط"
        )

    return user_id


def require_child_owner(
    request: Request,
    child_id: int
) -> int:

    user_id = require_parent(
        request
    )

    if not user_owns_child(
        user_id,
        child_id
    ):

        raise HTTPException(
            status_code=403,
            detail="لا تملك صلاحية الوصول إلى هذا الطفل"
        )

    return user_id


def require_session_owner(
    request: Request,
    session_id: int
) -> int:

    user_id = require_parent(
        request
    )

    if not user_owns_session(
        user_id,
        session_id
    ):

        raise HTTPException(
            status_code=403,
            detail="لا تملك صلاحية الوصول إلى هذه الجلسة"
        )

    return user_id


# ============================================================
# DEV MODE
# ============================================================

def require_dev_mode():

    if not DEV_MODE:

        raise HTTPException(
            status_code=404,
            detail="Not Found"
        )


# ============================================================
# CHILD ACCESS TOKEN
# ============================================================

def create_child_token(child_id: int) -> str:
    payload = str(int(child_id))
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def verify_child_token(
    child_id: int,
    token: str | None
) -> bool:
    if not token:
        return False

    expected = create_child_token(child_id)
    return hmac.compare_digest(
        str(token),
        expected
    )


def require_child_access(
    request: Request,
    child_id: int,
    token: str | None = None
) -> None:
    # QR token يسمح للطفل باستخدام واجهة المحادثة بدون
    # حمل جلسة ولي الأمر على جهاز الطفل.
    if verify_child_token(child_id, token):
        return

    # وإذا كان الطلب من ولي الأمر نفسه، نسمح له إذا كان الطفل تابعاً له.
    user_id = request.session.get("user_id")
    role = str(
        request.session.get("role", "")
    ).lower()

    if user_id and role == "parent":
        try:
            if user_owns_child(int(user_id), child_id):
                return
        except Exception:
            pass

    raise HTTPException(
        status_code=403,
        detail="رابط الطفل غير صالح أو منتهي الصلاحية"
    )


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():

    return FileResponse(
        "static/index.html"
    )


# ============================================================
# REGISTER
# ============================================================

@app.post("/register")
async def register(
    user: UserCreate
):

    from database import (
        SessionLocal,
        User
    )

    username = (
        user.username.strip()
    )

    email = (
        user.email.strip()
    )


    if not username:

        return JSONResponse(
            {
                "success": False,
                "message": "اسم المستخدم مطلوب"
            },
            status_code=400
        )


    if len(
        user.password
    ) < 6:

        return JSONResponse(
            {
                "success": False,
                "message":
                    "كلمة المرور يجب أن تكون 6 أحرف على الأقل"
            },
            status_code=400
        )


    db = SessionLocal()

    try:

        existing_user = (
            db.query(User)
            .filter(
                User.Username
                == username
            )
            .first()
        )


        if existing_user:

            return JSONResponse(
                {
                    "success": False,
                    "message":
                        "اسم المستخدم موجود مسبقاً"
                },
                status_code=409
            )


        new_user = User(

            Username=username,

            PasswordHash=hash_password(
                user.password
            ),

            Email=email,

            Role="parent"
        )


        db.add(
            new_user
        )

        db.commit()

        db.refresh(
            new_user
        )


        return {

            "success": True,

            "message":
                "تم التسجيل بنجاح"
        }


    except Exception as e:

        db.rollback()

        print(
            "Register error:",
            type(e).__name__
        )

        return JSONResponse(
            {
                "success": False,
                "message":
                    "فشل إنشاء الحساب"
            },
            status_code=500
        )

    finally:

        db.close()


# ============================================================
# LOGIN
# ============================================================

@app.post("/login")
async def login(
    user: UserLogin,
    request: Request
):

    from database import (
        SessionLocal,
        User
    )

    db = SessionLocal()

    try:

        db_user = (
            db.query(User)
            .filter(
                User.Username
                == user.username.strip()
            )
            .first()
        )


        if not db_user:

            return JSONResponse(
                {
                    "success": False,
                    "message":
                        "بيانات الدخول غير صحيحة"
                },
                status_code=401
            )


        valid, legacy_password = (
            verify_password(
                user.password,
                db_user.PasswordHash
            )
        )


        if not valid:

            return JSONResponse(
                {
                    "success": False,
                    "message":
                        "بيانات الدخول غير صحيحة"
                },
                status_code=401
            )


        if legacy_password:

            db_user.PasswordHash = (
                hash_password(
                    user.password
                )
            )

            db.commit()


        request.session.clear()


        request.session["user_id"] = (
            db_user.UserID
        )

        request.session["username"] = (
            db_user.Username
        )

        request.session["role"] = (
            "parent"
        )


        return {

            "success": True,

            "user_id":
                db_user.UserID,

            "username":
                db_user.Username,

            "role":
                "parent"
        }


    finally:

        db.close()


# ============================================================
# LOGOUT
# ============================================================

@app.post("/logout")
async def logout(
    request: Request
):

    request.session.clear()

    return {

        "success": True,

        "message":
            "تم تسجيل الخروج"
    }


# ============================================================
# CURRENT USER
# ============================================================

@app.get("/me")
async def current_user(
    request: Request
):

    user_id = require_parent(
        request
    )

    from database import (
        SessionLocal,
        User
    )

    db = SessionLocal()

    try:

        user = (
            db.query(User)
            .filter(
                User.UserID
                == user_id
            )
            .first()
        )


        if not user:

            request.session.clear()

            raise HTTPException(
                status_code=401,
                detail="المستخدم غير موجود"
            )


        return {

            "user_id":
                user.UserID,

            "username":
                user.Username,

            "email":
                user.Email,

            "role":
                "parent"
        }


    finally:

        db.close()


# ============================================================
# ADD CHILD
# ============================================================

@app.post("/add_child")
async def add_child(
    child: ChildCreate,
    request: Request
):

    user_id = require_parent(
        request
    )

    from database import (
        SessionLocal,
        Profile
    )


    name = child.name.strip()


    if not name:

        return JSONResponse(
            {
                "success": False,
                "message":
                    "اسم الطفل مطلوب"
            },
            status_code=400
        )


    db = SessionLocal()

    try:

        new_profile = Profile(

            UserID=user_id,

            DisplayName=name,

            Gender=child.gender,

            Age=child.age,

            Interests=child.interests
        )


        db.add(
            new_profile
        )

        db.commit()

        db.refresh(
            new_profile
        )


        return {

            "success": True,

            "message":
                "تمت إضافة الطفل بنجاح",

            "child_id":
                new_profile.ProfileID
        }


    except Exception as e:

        db.rollback()

        print(
            "Add child error:",
            type(e).__name__
        )

        return JSONResponse(
            {
                "success": False,
                "message":
                    "فشل في إضافة الطفل"
            },
            status_code=500
        )

    finally:

        db.close()


# ============================================================
# GET MY CHILDREN
# ============================================================

@app.get("/get_my_children")
async def get_my_children(
    request: Request
):

    user_id = require_parent(
        request
    )

    from database import (
        SessionLocal,
        Profile
    )

    db = SessionLocal()

    try:

        children = (
            db.query(Profile)
            .filter(
                Profile.UserID
                == user_id
            )
            .order_by(
                Profile.ProfileID.asc()
            )
            .all()
        )


        return [

            {

                "id":
                    child.ProfileID,

                "name":
                    child.DisplayName,

                "gender":
                    child.Gender,

                "age":
                    child.Age,

                "interests":
                    child.Interests

            }

            for child in children
        ]


    finally:

        db.close()


# ============================================================
# OLD ENDPOINT
# ============================================================
# أبقيناه للتوافق مع بعض الواجهات القديمة،
# لكنه الآن محمي ولا يستطيع الأب طلب مستخدم آخر.
# ============================================================

@app.get("/get_user_children/{user_id}")
async def get_user_children(
    request: Request,
    user_id: int
):

    current_user_id = require_parent(
        request
    )


    if user_id != current_user_id:

        raise HTTPException(
            status_code=403,
            detail="لا تملك صلاحية الوصول إلى هذا المستخدم"
        )


    from database import (
        SessionLocal,
        Profile
    )

    db = SessionLocal()

    try:

        children = (
            db.query(Profile)
            .filter(
                Profile.UserID
                == current_user_id
            )
            .order_by(
                Profile.ProfileID.asc()
            )
            .all()
        )


        return [

            {

                "id":
                    child.ProfileID,

                "name":
                    child.DisplayName,

                "gender":
                    child.Gender,

                "age":
                    child.Age,

                "interests":
                    child.Interests

            }

            for child in children
        ]


    finally:

        db.close()


# ============================================================
# CHILD INFO
# ============================================================

@app.get("/child_info/{child_id}")
async def get_child_info(
    child_id: int,
    request: Request
):

    from database import (
        SessionLocal,
        Profile
    )

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
            return {"found": False}

        user_id = request.session.get("user_id")

        if user_id:
            role = str(
                request.session.get("role", "")
            ).lower()

            if role != "parent":
                raise HTTPException(
                    status_code=403,
                    detail="صلاحية غير صحيحة"
                )

            if not user_owns_child(
                int(user_id),
                child_id
            ):
                raise HTTPException(
                    status_code=403,
                    detail="لا تملك صلاحية الوصول إلى هذا الطفل"
                )

            return {
                "found": True,
                "id": child.ProfileID,
                "name": child.DisplayName,
                "age": child.Age,
                "gender": child.Gender,
                "interests": child.Interests,
                "mood": child.Mood,
                "notes": child.Notes
            }

        raise HTTPException(
            status_code=401,
            detail="يتطلب هذا المسار جلسة ولي الأمر"
        )

    finally:
        db.close()


# ============================================================
# PUBLIC CHILD INFO - QR
# ============================================================

@app.get("/public/child_info/{child_id}")
async def public_child_info(
    child_id: int,
    token: str
):

    require_child_access_token = verify_child_token(
        child_id,
        token
    )

    if not require_child_access_token:
        raise HTTPException(
            status_code=403,
            detail="رابط الطفل غير صالح"
        )

    from database import (
        SessionLocal,
        Profile
    )

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
            return {"found": False}

        return {
            "found": True,
            "id": child.ProfileID,
            "name": child.DisplayName
        }

    finally:
        db.close()


# ============================================================
# DEVELOPMENT CHILD INFO
# ============================================================

@app.get("/dev/child_info/{child_id}")
async def dev_child_info(
    child_id: int,
    request: Request
):

    require_dev_mode()

    from database import (
        SessionLocal,
        Profile
    )

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
            return {"found": False}

        return {
            "found": True,
            "id": child.ProfileID,
            "name": child.DisplayName,
            "age": child.Age,
            "gender": child.Gender,
            "interests": child.Interests,
            "mood": child.Mood,
            "notes": child.Notes
        }

    finally:
        db.close()


# ============================================================
# DEVELOPMENT CHILD TOKEN
# ============================================================

@app.get("/dev/child_token/{child_id}")
async def dev_child_token(
    child_id: int,
    request: Request
):

    require_dev_mode()

    return {
        "child_id": child_id,
        "token": create_child_token(child_id)
    }


# ============================================================
# QR CODE
# ============================================================

@app.get("/qrcode/{child_id}")
async def generate_qrcode(
    child_id: int,
    request: Request,
    token: str | None = None
):

    from database import (
        SessionLocal,
        Profile
    )

    db = SessionLocal()

    try:

        child = (
            db.query(Profile)
            .filter(
                Profile.ProfileID
                == child_id
            )
            .first()
        )


        if not child:

            raise HTTPException(
                status_code=404,
                detail="الطفل غير موجود"
            )


        user_id = request.session.get(
            "user_id"
        )

        if not verify_child_token(child_id, token) and not user_id and not DEV_MODE:
            raise HTTPException(
                status_code=401,
                detail="يجب تسجيل الدخول لإنشاء QR"
            )


        # ----------------------------------------------------
        # إذا كان الأب مسجل دخول:
        # يجب أن يكون الطفل تابعاً له.
        # ----------------------------------------------------

        if user_id and not verify_child_token(child_id, token):

            role = str(
                request.session.get(
                    "role",
                    ""
                )
            ).lower()

            if role != "parent":
                raise HTTPException(
                    status_code=403,
                    detail="صلاحية غير صحيحة"
                )

            # في وضع التطوير:
            # السماح لأداة التطوير بإنشاء QR لأي طفل للاختبار
            if not DEV_MODE:

                if not user_owns_child(
                    int(user_id),
                    child_id
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="لا تملك صلاحية إنشاء هذا الباركود"
                    )



        # ----------------------------------------------------
        # QR HOST
        # ----------------------------------------------------

        computer_ip = os.getenv(
            "MANARAH_HOST_IP",
            "127.0.0.1"
        )


        token = create_child_token(child_id)

        url = (
            f"http://{computer_ip}:8000"
            f"/static/child_welcome.html"
            f"?child_id={child_id}"
            f"&token={token}"
        )


        img = qrcode.make(
            url
        )


        buf = io.BytesIO()

        img.save(
            buf,
            format="PNG"
        )

        buf.seek(0)


        return StreamingResponse(
            buf,
            media_type="image/png"
        )


    finally:

        db.close()


# ============================================================
# ASK / CHILD CONVERSATION
# ============================================================

@app.post("/ask")
async def ask(
    request: Request,
    audio: UploadFile = File(...),
    child_id: int = Form(...),
    token: str | None = Form(None)
):

    require_child_access(
        request,
        child_id,
        token
    )

    child_audio_filename = (
        f"static/uploads/"
        f"child_{os.urandom(4).hex()}.wav"
    )


    try:

        from database import (
            SessionLocal,
            Profile
        )


        db = SessionLocal()

        try:

            child = (
                db.query(Profile)
                .filter(
                    Profile.ProfileID
                    == child_id
                )
                .first()
            )


            if not child:

                return JSONResponse(
                    {
                        "error":
                            "Child not found"
                    },
                    status_code=404
                )


            child_info = {

                "name":
                    child.DisplayName,

                "age":
                    child.Age or "",

                "gender":
                    child.Gender or "",

                "interests":
                    child.Interests or "",

                "mood":
                    child.Mood or "",

                "notes":
                    child.Notes or ""
            }


        finally:

            db.close()


        # ----------------------------------------------------
        # SAVE CHILD AUDIO
        # ----------------------------------------------------

        with open(
            child_audio_filename,
            "wb"
        ) as f:

            shutil.copyfileobj(
                audio.file,
                f
            )


        # ----------------------------------------------------
        # STT
        # ----------------------------------------------------

        user_text = transcribe_audio(
            child_audio_filename
        )


        # ----------------------------------------------------
        # AI
        # ----------------------------------------------------

        response_text = get_response(
            user_text,
            child_info
        )


        # ----------------------------------------------------
        # TTS
        # ----------------------------------------------------

        agent_audio_filename = (
            f"static/uploads/"
            f"response_{os.urandom(4).hex()}.mp3"
        )


        text_to_speech(
            response_text,
            agent_audio_filename
        )


        # ----------------------------------------------------
        # SAVE MESSAGE
        # ----------------------------------------------------

        save_message(

            f"الطفل: {user_text} | "
            f"منار: {response_text}",

            agent_audio_filename,

            child_id,

            child_audio_filename
        )


        # ----------------------------------------------------
        # DANGER DETECTION
        # ----------------------------------------------------

        danger = detect_danger(
            user_text
        )


        if danger.get(
            "level"
        ) in [
            "warning",
            "danger"
        ]:

            save_alert(

                child_id,

                user_text,

                danger["level"]
            )


            parent_email = (
                get_parent_email(
                    child_id
                )
            )


            if parent_email:

                send_alert_email(

                    child_info["name"],

                    user_text,

                    danger["level"],

                    danger.get(
                        "reason",
                        ""
                    ),

                    danger.get(
                        "recommendation",
                        ""
                    ),

                    parent_email
                )


        return JSONResponse(

            {

                "user_text":
                    user_text,

                "response_text":
                    response_text,

                "audio_url":
                    "/" +
                    agent_audio_filename,

                "child_audio_url":
                    "/" +
                    child_audio_filename
            }
        )


    except Exception as e:

        import traceback

        print(
            "❌ Error in /ask:\n"
            f"{traceback.format_exc()}"
        )


        return JSONResponse(
            {
                "error":
                    "حدث خطأ أثناء معالجة التسجيل"
            },
            status_code=500
        )


# ============================================================
# END SESSION
# ============================================================

@app.post("/end_session/{child_id}")
async def end_session(
    request: Request,
    child_id: int,
    token: str | None = None
):

    require_child_access(
        request,
        child_id,
        token
    )


    from database import (
        SessionLocal,
        Session,
        Message
    )


    db = SessionLocal()

    try:

        session = (
            db.query(Session)
            .filter(
                Session.ChildID
                == child_id,

                Session.EndTime.is_(None)
            )
            .order_by(
                Session.SessionID.desc()
            )
            .first()
        )


        if not session:

            return {

                "success": False,

                "message":
                    "لا توجد جلسة مفتوحة"
            }


        messages = (
            db.query(Message)
            .filter(
                Message.SessionID
                == session.SessionID
            )
            .all()
        )


        if messages:

            full_transcript = (
                "\n".join(
                    [
                        message.Transcript_Text
                        for message in messages
                    ]
                )
            )


            analysis = (
                analyze_session_deeply(
                    full_transcript
                )
            )


            session.Advice = (
                analysis.get(
                    "advice",
                    "لا توجد توصية."
                )
            )


            session.EmotionalMap = (
                json.dumps(
                    analysis.get(
                        "emotions",
                        {
                            "joy": 50,
                            "sadness": 0,
                            "fear": 0,
                            "anger": 0
                        }
                    ),
                    ensure_ascii=False
                )
            )


        session.EndTime = (
            datetime.utcnow()
        )


        db.commit()


        return {

            "success": True,

            "session_id":
                session.SessionID,

            "message":
                "تم إنهاء الجلسة وحفظ التحليل"
        }


    except Exception as e:

        db.rollback()

        import traceback

        print(
            "❌ Error in end_session:\n"
            f"{traceback.format_exc()}"
        )


        return JSONResponse(
            {
                "success": False,
                "message":
                    "فشل إنهاء الجلسة"
            },
            status_code=500
        )


    finally:

        db.close()


# ============================================================
# ANALYZE SESSION
# ============================================================

@app.get("/analyze_session/{session_id}")
async def analyze_session(
    request: Request,
    session_id: int
):

    require_session_owner(
        request,
        session_id
    )


    from database import (
        SessionLocal,
        Session,
        Message
    )


    db = SessionLocal()

    try:

        session = (
            db.query(Session)
            .filter(
                Session.SessionID
                == session_id
            )
            .first()
        )


        if not session:

            return JSONResponse(
                {
                    "error":
                        "Session not found"
                },
                status_code=404
            )


        messages = (
            db.query(Message)
            .filter(
                Message.SessionID
                == session_id
            )
            .all()
        )


        if not messages:

            return JSONResponse(
                {
                    "error":
                        "No data"
                }
            )


        if (
            session.EmotionalMap
            and session.Advice
        ):

            try:

                emotions = json.loads(
                    session.EmotionalMap
                )

            except Exception:

                emotions = {

                    "joy": 50,

                    "sadness": 0,

                    "fear": 0,

                    "anger": 0
                }


            advice = session.Advice


        else:

            full_transcript = (
                "\n".join(
                    [
                        message.Transcript_Text
                        for message in messages
                    ]
                )
            )


            analysis = (
                analyze_session_deeply(
                    full_transcript
                )
            )


            emotions = analysis.get(
                "emotions",
                {
                    "joy": 50,
                    "sadness": 0,
                    "fear": 0,
                    "anger": 0
                }
            )


            advice = analysis.get(
                "advice",
                "يرجى متابعة جلسات الطفل بانتظام."
            )


            session.Advice = advice


            session.EmotionalMap = (
                json.dumps(
                    emotions,
                    ensure_ascii=False
                )
            )


            db.commit()


        script_data = []


        for message in messages:

            script_data.append(
                {

                    "text":
                        message.Transcript_Text,

                    "audio_url": (
                        "/"
                        + message.Audio_File_URL
                        if message.Audio_File_URL
                        else None
                    ),

                    "child_audio_url": (
                        "/"
                        + message.Child_Audio_URL
                        if message.Child_Audio_URL
                        else None
                    )
                }
            )


        return JSONResponse(
            {

                "emotions":
                    emotions,

                "advice":
                    advice,

                "script":
                    script_data,

                "notes":
                    session.ParentNotes
                    or ""
            }
        )


    finally:

        db.close()


# ============================================================
# SAVE NOTE
# ============================================================

@app.post("/save_note/{session_id}")
async def save_note(
    request: Request,
    session_id: int,
    request_data: NoteRequest
):

    require_session_owner(
        request,
        session_id
    )


    from database import (
        SessionLocal,
        Session
    )


    db = SessionLocal()

    try:

        session = (
            db.query(Session)
            .filter(
                Session.SessionID
                == session_id
            )
            .first()
        )


        if not session:

            return {
                "success": False
            }


        session.ParentNotes = (
            request_data.note
        )


        db.commit()


        return {

            "success": True
        }


    finally:

        db.close()


# ============================================================
# SESSIONS
# ============================================================

@app.get("/sessions")
async def get_sessions_list(
    request: Request,
    user_id: int | None = None,
    child_id: int | None = None
):

    current_user_id = require_parent(
        request
    )


    if (
        user_id is not None
        and
        user_id != current_user_id
    ):

        raise HTTPException(
            status_code=403,
            detail="لا تملك صلاحية الوصول إلى هذه البيانات"
        )


    from database import (
        SessionLocal,
        Profile,
        Session,
        Message
    )


    db = SessionLocal()

    try:

        if child_id is not None:

            if not user_owns_child(
                current_user_id,
                child_id
            ):

                raise HTTPException(
                    status_code=403,
                    detail="لا تملك صلاحية الوصول إلى هذا الطفل"
                )


        children = (
            db.query(Profile)
            .filter(
                Profile.UserID
                == current_user_id
            )
            .all()
        )


        child_ids = [

            child.ProfileID

            for child in children
        ]


        if not child_ids:

            return []


        query = (
            db.query(Session)
            .filter(
                Session.ChildID.in_(
                    child_ids
                )
            )
        )


        if child_id is not None:

            query = query.filter(
                Session.ChildID
                == child_id
            )


        sessions = (
            query
            .order_by(
                Session.StartTime.desc()
            )
            .all()
        )


        result = []


        for session in sessions:

            child = (
                db.query(Profile)
                .filter(
                    Profile.ProfileID
                    == session.ChildID
                )
                .first()
            )


            messages = (
                db.query(Message)
                .filter(
                    Message.SessionID
                    == session.SessionID
                )
                .all()
            )


            emotions = None


            if session.EmotionalMap:

                try:

                    emotions = json.loads(
                        session.EmotionalMap
                    )

                except Exception:

                    emotions = None


            result.append(
                {

                    "session_id":
                        session.SessionID,

                    "child_id":
                        session.ChildID,

                    "child_name":
                        (
                            child.DisplayName
                            if child
                            else "غير معروف"
                        ),

                    "start_time":
                        (
                            session.StartTime.strftime(
                                "%Y-%m-%d %H:%M"
                            )
                            if session.StartTime
                            else ""
                        ),

                    "end_time":
                        (
                            session.EndTime.strftime(
                                "%Y-%m-%d %H:%M"
                            )
                            if session.EndTime
                            else None
                        ),

                    "advice":
                        (
                            session.Advice
                            if session.Advice
                            else "بانتظار التحليل..."
                        ),

                    "emotions":
                        emotions,

                    "notes":
                        (
                            session.ParentNotes
                            if session.ParentNotes
                            else ""
                        ),

                    "messages": [

                        {

                            "message_id":
                                message.MessageID,

                            "text":
                                message.Transcript_Text,

                            "audio_url":
                                (
                                    "/"
                                    + message.Audio_File_URL
                                    if message.Audio_File_URL
                                    else None
                                ),

                            "child_audio_url":
                                (
                                    "/"
                                    + message.Child_Audio_URL
                                    if message.Child_Audio_URL
                                    else None
                                ),

                            "timestamp":
                                (
                                    message.Timestamp.strftime(
                                        "%Y-%m-%d %H:%M"
                                    )
                                    if message.Timestamp
                                    else ""
                                )
                        }

                        for message in messages
                    ]
                }
            )


        return result


    finally:

        db.close()


# ============================================================
# DEV STATUS
# ============================================================

@app.get("/dev/status")
async def dev_status():
    return {
        "enabled": DEV_MODE
    }

# # ============================================================
# DEVELOPMENT SIMULATION
# ============================================================

@app.get("/get_all_users")
async def get_all_users(
    request: Request
):
    require_dev_mode()

    from database import (
        SessionLocal,
        User
    )

    db = SessionLocal()

    try:
        parents = (
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
                "username": user.Username,
                "email": user.Email
            }
            for user in parents
        ]

    finally:
        db.close()


@app.get("/dev/get_children")
async def dev_get_children(
    request: Request,
    user_id: int
):
    require_dev_mode()

    from database import (
        SessionLocal,
        Profile
    )

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

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    uvicorn.run(

        "main:app",

        host="0.0.0.0",

        port=8000,

        reload=True
    )