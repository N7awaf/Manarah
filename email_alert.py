import smtplib
import os

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from dotenv import load_dotenv

load_dotenv()


def clean_email(value: str):
    if not value:
        return None

    value = value.strip()

    # لو أحد كتب: الاسم <email@gmail.com>
    if "<" in value and ">" in value:
        value = value.split("<")[1].split(">")[0].strip()

    return value


def send_alert_email(
    child_name: str,
    message_text: str,
    level: str,
    reason: str,
    recommendation: str,
    parent_email: str = None
):

    sender = clean_email(os.getenv("ALERT_EMAIL_FROM"))
    password = os.getenv("ALERT_EMAIL_PASSWORD")
    receiver = clean_email(parent_email) or clean_email(os.getenv("ALERT_EMAIL_TO"))

    if password:
        password = password.strip().replace(" ", "")

    if not sender or not password or not receiver:
        print("⚠️ إعدادات الإيميل غير مكتملة")
        print(f"sender={sender}, receiver={receiver}")
        return False

    level_ar = "تحذير" if level == "warning" else "خطر"

    html = f"""
    <html>
    <body dir="rtl" style="font-family: Arial; background:#111827; padding:20px; color:white;">
        <div style="max-width:600px;margin:auto;background:#1f2937;border-radius:15px;padding:25px;">
            <h1 style="color:#a78bfa;text-align:center;">منارة</h1>
            <h2 style="color:#f59e0b;text-align:center;">{level_ar}</h2>

            <hr style="border-color:#374151;">

            <p><strong>الطفل:</strong> {child_name}</p>

            <p><strong>ما قاله الطفل:</strong></p>
            <div style="background:#111827;padding:15px;border-radius:10px;margin-bottom:20px;">
                {message_text}
            </div>

            <p><strong>السبب:</strong></p>
            <div style="background:#111827;padding:15px;border-radius:10px;margin-bottom:20px;">
                {reason}
            </div>

            <p><strong>التوصية:</strong></p>
            <div style="background:#111827;padding:15px;border-radius:10px;">
                {recommendation}
            </div>
        </div>
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart("alternative")

        msg["Subject"] = str(Header(f"Manarah Alert - {child_name}", "utf-8"))
        msg["From"] = formataddr((str(Header("Manarah", "utf-8")), sender))
        msg["To"] = receiver

        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, [receiver], msg.as_string())

        print(f"✅ تم إرسال تنبيه إلى {receiver}")
        return True

    except Exception as e:
        print(f"❌ فشل إرسال الإيميل: {e}")
        print(f"sender={sender}")
        print(f"receiver={receiver}")
        return False