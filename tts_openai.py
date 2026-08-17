import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# يقرأ المفتاح تلقائياً من المتغير OPENAI_API_KEY في ملف .env
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# الأصوات المتاحة: alloy, echo, fable, onyx, nova, shimmer
VOICE_ID = "nova" 


def text_to_speech(text: str, output_path: str):
    try:
        # إنشاء ملف الصوت عبر نموذج tts-1 أو tts-1-hd
        response = client.audio.speech.create(
            model="tts-1",
            voice=VOICE_ID,
            input=text,
            response_format="mp3"
        )

        # حفظ الملف مباشرة
        response.stream_to_file(output_path)

        return output_path

    except Exception as e:
        print(f"❌ OpenAI TTS Error: {e}")
        raise e