import hashlib
from database import SessionLocal, User, Profile, init_db

def run_seeder():
    # 1. تهيئة قاعدة البيانات والتأكد من وجود الجداول
    init_db()
    db = SessionLocal()

    # الرمز السري الموحد (1234) مشفر بـ SHA256 ليتوافق مع نظام تسجيل الدخول
    password_hash = hashlib.sha256("1234".encode()).hexdigest()

    print("⏳ بدأ حقن بيانات المحاكاة في manarah.db...")

    # --- السيناريو الأول: الأب نواف والابن جعفر (حالة التنمر) ---
    nawaf = db.query(User).filter(User.Username == "nawaf").first()
    if not nawaf:
        nawaf = User(Username="nawaf", PasswordHash=password_hash, Email="nawaf@manarah.sa", Role="parent")
        db.add(nawaf)
        db.commit()
        db.refresh(nawaf)
        print("✅ تم إنشاء حساب الأب: نواف")

    jafar = db.query(Profile).filter(Profile.DisplayName == "جعفر").first()
    if not jafar:
        jafar = Profile(
            UserID=nawaf.UserID,
            DisplayName="جعفر",
            Age="9",
            Gender="male",
            Interests="لعب كرة القدم، حب الفضاء، وقصص الأبطال",
            Notes="ملاحظة للأب: جعفر يمر بفترة صعبة بسبب مضايقات بعض الزملاء في المدرسة (تنمر)"
        )
        db.add(jafar)
        print("   👶 تم ربط الابن جعفر بحساب نواف")

    # --- السيناريو الثاني: الأم سارة وفهد وليان (تعدد الأطفال) ---
    sara = db.query(User).filter(User.Username == "sara").first()
    if not sara:
        sara = User(Username="sara", PasswordHash=password_hash, Email="sara@manarah.sa", Role="parent")
        db.add(sara)
        db.commit()
        db.refresh(sara)
        print("✅ تم إنشاء حساب الأم: سارة")

    # إضافة فهد (الابن الأول لسارة)
    if not db.query(Profile).filter(Profile.DisplayName == "فهد").first():
        db.add(Profile(
            UserID=sara.UserID,
            DisplayName="فهد",
            Age="7",
            Gender="male",
            Interests="استكشاف الفضاء، الديناصورات، وصناعة الليغو"
        ))
        print("   👦 تم إضافة فهد لحساب سارة")

    # إضافة ليان (الابنة الثانية لسارة)
    if not db.query(Profile).filter(Profile.DisplayName == "ليان").first():
        db.add(Profile(
            UserID=sara.UserID,
            DisplayName="ليان",
            Age="5",
            Gender="female",
            Interests="الرسم والتلوين، حب القطط، وقصص الأميرات"
        ))
        print("   👧 تم إضافة ليان لحساب سارة")

    db.commit()
    db.close()
    print("\n✨ المحاكاة جاهزة! افتح الموقع الآن واستمتع بالعرض.")

if __name__ == "__main__":
    run_seeder()