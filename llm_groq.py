import os
import json
import time
import re

from groq import Groq
from dotenv import load_dotenv

from rag_retriever import (
    retrieve_context,
    documents
)

# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

# ============================================================
# GROQ CLIENT
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY غير موجود في ملف .env"
    )

client = Groq(
    api_key=GROQ_API_KEY
)

# ============================================================
# MODELS
# 🧠 عقل منار
# ============================================================

MODEL_NAME = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b"
)

# 🛡️ فحص السلامة

SAFETY_MODEL = os.getenv(
    "GROQ_SAFETY_MODEL",
    "openai/gpt-oss-safeguard-20b"
)

# ============================================================
# SETTINGS
# مهم جداً:
# False = منار تعتمد على Groq بشكل أساسي
# True = الردود الجاهزة تعمل قبل Groq
#
# نخليها False حتى لا تتحول منار إلى بوت يكرر نفس الجمل.
# ============================================================

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
# ============================================================
# ARABIC NORMALIZATION
# ============================================================

def normalize_arabic(text: str) -> str:

    if not text:
        return ""

    text = str(text).strip()

    text = (
        text
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
    )

    text = (
        text
        .replace("ة", "ه")
        .replace("ى", "ي")
    )

    # إزالة التشكيل
    text = re.sub(
        r"[\u064B-\u065F\u0670]",
        "",
        text
    )

    # إزالة الرموز
    text = re.sub(
        r"[^\w\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# ============================================================
# DEMO RESPONSES
# ============================================================

DEMO_RESPONSES = [

    {
        "keywords": [
            "حزين",
            "زعلان",
            "ضايق",
            "محد يحبني",
            "ما عندي اصحاب",
            "وحيد"
        ],
        "reply":
            "أفهمك يا {name}، الحزن شعور ثقيل أحياناً، بس أنت مو لحالك وأنا معك. وش أكثر شيء زعلك اليوم؟"
    },

    {
        "keywords": [
            "ما ابغى اروح المدرسه",
            "ما ابي اروح المدرسه",
            "اكره المدرسه",
            "اخاف من المدرسه"
        ],
        "reply":
            "واضح إن المدرسة مضايقتك يا {name}، وهذا شعور مهم نسمعه. هل صار شيء في المدرسة خلاك ما تبغى تروح؟"
    },

    {
        "keywords": [
            "يضحكون علي",
            "يتنمرون",
            "دفني",
            "يضربني",
            "ما يلعبون معي",
            "ينادوني باسماء"
        ],
        "reply":
            "هذا يزعل يا {name}، ومهم تعرف إن الغلط مو عليك أبداً. الأفضل تقول لأبوك أو لمعلم تثق فيه عشان يساعدك ويحميك."
    },

    {
        "keywords": [
            "اخاف من الاختبار",
            "خايف من الاختبار",
            "متوتر من الاختبار",
            "عندي اختبار"
        ],
        "reply":
            "طبيعي تتوتر من الاختبار يا {name}، بس نقدر نهدأ شوي ونقسم المذاكرة لأجزاء صغيرة. وش المادة اللي مخوفتك؟"
    },

    {
        "keywords": [
            "انا سعيد",
            "انا مبسوط",
            "مبسوط اليوم",
            "لعبت كوره",
            "طلعت مع بابا",
            "عندي صديق جديد"
        ],
        "reply":
            "يا سلام يا {name}! فرحتني معك، واضح إن يومك كان جميل. وش أحلى شيء صار لك اليوم؟"
    },

    {
        "keywords": [
            "بابا زعل مني",
            "ماما زعلت مني",
            "هاوشوني",
            "انهاوشت"
        ],
        "reply":
            "أفهم إن هذا يضايقك يا {name}، أحياناً الكبار يزعلون بس هذا ما يعني إنهم ما يحبونك. تبغى تقول لي وش صار؟"
    }

]


# ============================================================
# DEMO RESPONSE
# ============================================================

def get_demo_response(
    user_text: str,
    child_name: str
) -> str | None:

    if not DEMO_MODE:
        return None

    normalized_text = normalize_arabic(
        user_text
    )

    for scenario in DEMO_RESPONSES:

        for keyword in scenario["keywords"]:

            normalized_keyword = normalize_arabic(
                keyword
            )

            if normalized_keyword in normalized_text:

                return scenario["reply"].format(
                    name=child_name
                )

    return None


# ============================================================
# ENSURE CHILD NAME
# ============================================================

def ensure_child_name(
    text: str,
    child_name: str
) -> str:

    if not text:
        return text

    if not child_name:
        return text

    # إذا الاسم موجود بالفعل لا نضيفه مرة ثانية
    if child_name.strip() in text:
        return text

    # لا نضيف الاسم إذا الاسم الافتراضي
    if child_name.strip() in [
        "يا بطل",
        "بطل",
        "طفل"
    ]:
        return text

    # إضافة الاسم بشكل طبيعي في بداية الرد
    return f"يا {child_name}، {text}"


# ============================================================
# CLEAN CHILD REPLY
# ============================================================

def clean_child_reply(
    text: str,
    child_name: str = ""
) -> str:

    if not text:

        fallback = (
            "أنا معك يا بطل، "
            "قل لي وش صار معك؟"
        )

        return ensure_child_name(
            fallback,
            child_name
        )

    text = str(text).strip()

    # --------------------------------------------------------
    # إزالة بدايات غير مناسبة
    # --------------------------------------------------------

    bad_starts = [

        "بالطبع",
        "أكيد",
        "Sure",
        "Of course",
        "Here is",
        "Here’s",
        "Response:",
        "الرد:",
        "الإجابة:",
        "إليك الرد:"
    ]

    for bad in bad_starts:

        if text.lower().startswith(
            bad.lower()
        ):

            text = text[
                len(bad):
            ].strip()

    # --------------------------------------------------------
    # إزالة Markdown
    # --------------------------------------------------------

    text = re.sub(
        r"[*_`#]+",
        "",
        text
    )

    # --------------------------------------------------------
    # إزالة الكلمات الإنجليزية
    # --------------------------------------------------------

    text = re.sub(
        r"[A-Za-z]{3,}",
        "",
        text
    )

    # --------------------------------------------------------
    # تنظيف المسافات
    # --------------------------------------------------------

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    if not text:

        text = (
            "أنا معك يا بطل، "
            "قل لي وش صار معك؟"
        )

    # --------------------------------------------------------
    # ضمان عدم تكرار الاسم
    # --------------------------------------------------------

    text = ensure_child_name(
        text,
        child_name
    )

    return text


# ============================================================
# GET RESPONSE
# 🧠 عقل منار
# ============================================================

def get_response(
    user_text: str,
    child_info: dict = None
) -> str:

    # --------------------------------------------------------
    # CHILD INFO
    # --------------------------------------------------------

    child_info = child_info or {}

    child_name = str(
        child_info.get(
            "name",
            ""
        )
    ).strip()

    if not child_name:
        child_name = "يا بطل"

    age = str(
        child_info.get(
            "age",
            ""
        )
    )

    gender = str(
        child_info.get(
            "gender",
            ""
        )
    )

    interests = str(
        child_info.get(
            "interests",
            ""
        )
    )

    mood = str(
        child_info.get(
            "mood",
            ""
        )
    )

    notes = str(
        child_info.get(
            "notes",
            ""
        )
    )

    # --------------------------------------------------------
    # DEMO RESPONSE
    #
    # حالياً False لذلك لن يسيطر على عقل منار
    # --------------------------------------------------------

    demo_reply = get_demo_response(
        user_text,
        child_name
    )

    if demo_reply:
        return demo_reply

    # --------------------------------------------------------
    # RAG
    # --------------------------------------------------------

    try:

        context = retrieve_context(
            user_text,
            documents,
            top_k=2
        )

    except Exception as e:

        print(
            f"⚠️ خطأ في RAG: {e}"
        )

        context = ""

    # --------------------------------------------------------
    # SYSTEM PROMPT
    # --------------------------------------------------------

    system_prompt = f"""

أنتِ منار، صديقة ذكية ولطيفة للأطفال في السعودية.

أنتِ لستِ روبوت ردود جاهزة.
كل رسالة من الطفل يجب أن تفهمي معناها وتردي عليها حسب كلامه الحالي.

معلومات الطفل:

الاسم:
{child_name}

العمر:
{age}

الجنس:
{gender}

الاهتمامات:
{interests}

الطبع العام:
{mood}

ملاحظات خاصة:
{notes}

المعرفة التربوية:
{context}

قواعد منار:

ردي بالعربية فقط.
استخدمي لهجة سعودية بيضاء بسيطة وطبيعية.
الرد مناسب لطفل عمره من 5 إلى 12 سنة.
لا تذكري أنك نموذج ذكاء اصطناعي.
لا تستخدمي مصطلحات نفسية أو طبية معقدة.
لا تشخّصي الطفل.
افهمي كلام الطفل الحالي قبل الرد.
لا تكرري نفس الجملة في كل رسالة.
لا تستخدمي ردوداً محفوظة إلا إذا كانت مناسبة جداً للسياق.
اجعلي كل رد مختلفاً حسب كلام الطفل.
تعاطفي مع شعور الطفل إذا كان حزيناً أو خائفاً.
إذا كان سعيداً شاركيه فرحته.
إذا كان يسأل سؤالاً، أجيبي عن سؤاله مباشرة.
إذا كان يتحدث عن لعبة أو هواية، تفاعلي معه في نفس الموضوع.
إذا ذكر شيئاً عن المدرسة، ناقشي الموضوع نفسه.
إذا كان يتحدث عن أهله، اسمعيه ولا تلومي أحداً.
لا تحولي كل محادثة إلى نصائح مدرسية.
لا تحولي كل رسالة إلى سؤال.
إذا كان السؤال يحتاج سؤالاً إضافياً، اسألي سؤالاً واحداً فقط.
الرد من جملة إلى ثلاث جمل.
لا تكتبي قوائم.
لا تكتبي شرحاً طويلاً.
لا تستخدمي الإنجليزية.
لا تذكري معلومات الطفل الخاصة بشكل غير طبيعي.
استخدمي اسم الطفل مرة واحدة فقط عندما يكون ذلك مناسباً.
اسم الطفل هو: {child_name}
لا تنادي الطفل دائماً باسمه في كل رسالة؛ استخدميه بشكل طبيعي ومتباعد.
لا تقولي نفس العبارة في كل رد.
لا تبدأي كل رد بعبارة "أفهمك".
كوني دافئة ومرحة وطبيعية وكأنك صديقة حقيقية للطفل.

أمثلة على الأسلوب فقط، وليست ردوداً ثابتة:

إذا قال الطفل:
"لعبت كورة اليوم وفزنا"

يمكن أن تردي:
"يا سلام! أكيد كانت مباراة حماس 😄 مين سجل الهدف؟"

إذا قال:
"أنا طفشان"

يمكن أن تردي:
"أوه الطفش مزعج 😄 وش رايك نسوي شيء ممتع؟ تبغى لغز ولا لعبة سريعة؟"

إذا قال:
"أنا خايف من الاختبار"

يمكن أن تردي:
"طبيعي تحس بخوف شوي، خلنا نرتبها مع بعض. وش المادة اللي عندك اختبار فيها؟"

لا تنسخي هذه الأمثلة حرفياً، واكتبي رداً مناسباً للرسالة الحالية.
"""

    # --------------------------------------------------------
    # GROQ
    # --------------------------------------------------------

    for attempt in range(3):

        try:

            response = client.chat.completions.create(

                model=MODEL_NAME,

                messages=[

                    {
                        "role": "system",
                        "content": system_prompt
                    },

                    {
                        "role": "user",
                        "content": user_text
                    }

                ],

                temperature=0.75,

                max_tokens=180,

                timeout=20.0
            )

            reply = (
                response
                .choices[0]
                .message
                .content
            )

            reply = clean_child_reply(
                reply,
                child_name
            )

            return reply

        except Exception as e:

            print(
                f"⚠️ محاولة جلب الرد "
                f"{attempt + 1} فشلت: {e}"
            )

            if attempt < 2:
                time.sleep(1)

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    fallback = (
        "معليش يا بطل، صار عندي "
        "خلل بسيط 😅 قل لي مرة ثانية "
        "وش كنت تقول؟"
    )

    return ensure_child_name(
        fallback,
        child_name
    )


# ============================================================
# SESSION ANALYSIS
# ============================================================

def analyze_session_deeply(
    full_transcript: str
):

    normalized = normalize_arabic(
        full_transcript
    )

    # --------------------------------------------------------
    # BULLYING
    # --------------------------------------------------------

    bullying_words = [
        "يضحكون علي",
        "يتنمرون",
        "دفني",
        "يضربني",
        "ما يلعبون معي",
        "ينادوني باسماء"
    ]

    if any(
        normalize_arabic(word) in normalized
        for word in bullying_words
    ):

        return {

            "emotions": {
                "joy": 20,
                "sadness": 80,
                "fear": 65,
                "anger": 30
            },

            "advice":
                "تم رصد مؤشرات تنمر أو ضيق مدرسي. يُنصح ولي الأمر بالاستماع للطفل بهدوء والتواصل مع المدرسة عند الحاجة.",

            "status":
                "Needs Attention"
        }

    # --------------------------------------------------------
    # SCHOOL FEAR
    # --------------------------------------------------------

    school_words = [
        "ما ابغى اروح المدرسه",
        "ما ابي اروح المدرسه",
        "اخاف من المدرسه",
        "اكره المدرسه"
    ]

    if any(
        normalize_arabic(word) in normalized
        for word in school_words
    ):

        return {

            "emotions": {
                "joy": 35,
                "sadness": 50,
                "fear": 70,
                "anger": 10
            },

            "advice":
                "يظهر وجود قلق مرتبط بالمدرسة. يُنصح بطمأنة الطفل وسؤاله عن سبب الخوف دون ضغط.",

            "status":
                "Needs Attention"
        }

    # --------------------------------------------------------
    # SADNESS
    # --------------------------------------------------------

    sadness_words = [
        "حزين",
        "زعلان",
        "محد يحبني",
        "وحيد"
    ]

    if any(
        normalize_arabic(word) in normalized
        for word in sadness_words
    ):

        return {

            "emotions": {
                "joy": 30,
                "sadness": 75,
                "fear": 25,
                "anger": 10
            },

            "advice":
                "يحتاج الطفل إلى احتواء عاطفي ووقت تواصل مباشر مع ولي الأمر لتعزيز شعوره بالأمان والانتماء.",

            "status":
                "Average"
        }

    # --------------------------------------------------------
    # HAPPINESS
    # --------------------------------------------------------

    happy_words = [
        "مبسوط",
        "سعيد",
        "لعبت كوره",
        "صديق جديد"
    ]

    if any(
        normalize_arabic(word) in normalized
        for word in happy_words
    ):

        return {

            "emotions": {
                "joy": 85,
                "sadness": 10,
                "fear": 5,
                "anger": 0
            },

            "advice":
                "تظهر مؤشرات إيجابية وتحسن في المزاج. يُنصح بتعزيز الأنشطة الاجتماعية والهوايات التي أسعدت الطفل.",

            "status":
                "Excellent"
        }

    # --------------------------------------------------------
    # RAG
    # --------------------------------------------------------

    try:

        context = retrieve_context(
            full_transcript,
            documents,
            top_k=3
        )

    except Exception as e:

        print(
            f"⚠️ خطأ في RAG أثناء التحليل: {e}"
        )

        context = ""

    # --------------------------------------------------------
    # ANALYSIS PROMPT
    # --------------------------------------------------------

    system_instruction = """

أنت محلل مؤشرات عاطفية للأطفال.

حلل النص كمؤشرات فقط وليس تشخيصاً طبياً.

أعد JSON فقط.

يجب أن يحتوي JSON على:

{
"emotions": {
"joy": 0,
"sadness": 0,
"fear": 0,
"anger": 0
},
"advice": "توصية قصيرة بالعربية لولي الأمر",
"status": "Good"
}

القواعد:

joy من 0 إلى 100.
sadness من 0 إلى 100.
fear من 0 إلى 100.
anger من 0 إلى 100.

status يجب أن يكون واحداً من:

Excellent
Good
Average
Needs Attention

إذا ظهر تنمر أو خوف واضح من المدرسة أو عزلة واضحة:
Needs Attention

لا تقدم تشخيصاً طبياً.
"""

    prompt = f"""

السياق التربوي:

{context}

نص الجلسة:

{full_transcript}
"""

    # --------------------------------------------------------
    # GROQ ANALYSIS
    # --------------------------------------------------------

    for attempt in range(2):

        try:

            response = client.chat.completions.create(

                model=MODEL_NAME,

                messages=[

                    {
                        "role": "system",
                        "content": system_instruction
                    },

                    {
                        "role": "user",
                        "content": prompt
                    }

                ],

                response_format={
                    "type": "json_object"
                },

                temperature=0.1,

                max_tokens=300,

                timeout=20.0
            )

            raw_content = (
                response
                .choices[0]
                .message
                .content
            )

            data = json.loads(
                raw_content
            )

            emotions = data.get(
                "emotions",
                {}
            )

            def clamp(value, default=0):

                try:
                    value = int(value)
                except Exception:
                    value = default

                return max(
                    0,
                    min(
                        100,
                        value
                    )
                )

            data["emotions"] = {

                "joy": clamp(
                    emotions.get(
                        "joy",
                        50
                    ),
                    50
                ),

                "sadness": clamp(
                    emotions.get(
                        "sadness",
                        0
                    )
                ),

                "fear": clamp(
                    emotions.get(
                        "fear",
                        0
                    )
                ),

                "anger": clamp(
                    emotions.get(
                        "anger",
                        0
                    )
                )
            }

            data["advice"] = str(
                data.get(
                    "advice",
                    "يرجى متابعة جلسات الطفل بانتظام."
                )
            )

            status = str(
                data.get(
                    "status",
                    "Good"
                )
            )

            allowed_statuses = [
                "Excellent",
                "Good",
                "Average",
                "Needs Attention"
            ]

            if status not in allowed_statuses:
                status = "Good"

            data["status"] = status

            return data

        except Exception as e:

            print(
                f"⚠️ محاولة تحليل الجلسة "
                f"{attempt + 1} فشلت: {e}"
            )

            if attempt < 1:
                time.sleep(1)

    return {

        "emotions": {
            "joy": 50,
            "sadness": 0,
            "fear": 0,
            "anger": 0
        },

        "advice":
            "يرجى متابعة جلسات الطفل بانتظام لضمان دقة المؤشرات.",

        "status":
            "Good"
    }


# ============================================================
# SAFETY DEFAULT
# ============================================================

def safe_default_result():

    return {

        "is_dangerous": False,

        "level": "safe",

        "reason":
            "لا يوجد خطر واضح.",

        "recommendation":
            ""
    }


# ============================================================
# DIRECT SAFETY DETECTION
# ============================================================

def detect_danger(
    text: str
) -> dict:

    normalized = normalize_arabic(
        text
    )

    # ========================================================
    # BULLYING / WARNING
    # ========================================================

    bullying_keywords = [

        "يضحكون علي",
        "يتنمرون",
        "دفني",
        "يضربني",
        "ما يلعبون معي",
        "ينادوني باسماء"
    ]

    for keyword in bullying_keywords:

        if normalize_arabic(
            keyword
        ) in normalized:

            return {

                "is_dangerous": True,

                "level": "warning",

                "reason":
                    "تم رصد مؤشرات تنمر أو أذى مدرسي.",

                "recommendation":
                    "ينصح بالتحدث مع الطفل بهدوء والتواصل مع المدرسة إذا تكرر الموقف."
            }

    # ========================================================
    # DIRECT DANGER
    # ========================================================

    danger_keywords = [

        "اموت",
        "اكره حياتي",
        "ابي اختفي",
        "ابغى اختفي",
        "ما ابي اعيش",
        "ما ابغى اعيش",
        "ابي اموت",
        "ابغى اموت"
    ]

    for keyword in danger_keywords:

        if normalize_arabic(
            keyword
        ) in normalized:

            return {

                "is_dangerous": True,

                "level": "danger",

                "reason":
                    "تم رصد عبارات خطرة مرتبطة بإيذاء النفس.",

                "recommendation":
                    "ينصح بتدخل ولي الأمر فوراً وطلب مساعدة مختص عند الحاجة."
            }

    # ========================================================
    # GROQ SAFETY MODEL
    # ========================================================

    safety_system_prompt = """

أنت نظام مراقبة سلامة للأطفال.

حلل كلام الطفل وحدد مستوى السلامة.

أعد كائن JSON واحد فقط.

المفاتيح المطلوبة فقط:

is_dangerous
level
reason
recommendation

القيم الممكنة لـ level فقط:

safe
warning
danger

safe:
لا يوجد خطر واضح.

warning:
تنمر أو خوف شديد أو عزلة أو بكاء متكرر أو رفض المدرسة أو مشكلة تحتاج متابعة.

danger:
إيذاء النفس أو الرغبة بالموت أو تهديد مباشر أو عنف شديد أو إساءة خطيرة.

is_dangerous:
true إذا كان level هو warning أو danger.
false إذا كان level هو safe.

reason:
سبب قصير باللغة العربية.

recommendation:
نصيحة قصيرة باللغة العربية لولي الأمر.

لا تستخدم Markdown.
لا تستخدم عناوين.
لا تضف أي مفاتيح أخرى.
لا تكتب أي شيء خارج JSON.
"""

    try:

        response = client.chat.completions.create(

            model=SAFETY_MODEL,

            messages=[

                {
                    "role": "system",
                    "content":
                        safety_system_prompt
                },

                {
                    "role": "user",
                    "content":
                        text
                }

            ],

            # مهم:
            # نستخدم JSON Object مع موديل الحماية
            # لكن إذا فشل سنرجع safe بدلاً من تعطيل /ask
            response_format={
                "type": "json_object"
            },

            temperature=0,

            max_tokens=400,

            timeout=15.0
        )

        raw_content = (
            response
            .choices[0]
            .message
            .content
        )

        if not raw_content:

            print(
                "⚠️ موديل السلامة أعاد رداً فارغاً"
            )

            return safe_default_result()

        # ----------------------------------------------------
        # محاولة JSON
        # ----------------------------------------------------

        try:

            data = json.loads(
                raw_content
            )

        except json.JSONDecodeError:

            print(
                "⚠️ نتيجة موديل السلامة ليست JSON صالحاً"
            )

            return safe_default_result()

        # ----------------------------------------------------
        # LEVEL
        # ----------------------------------------------------

        level = str(
            data.get(
                "level",
                "safe"
            )
        ).lower().strip()

        if level not in [
            "safe",
            "warning",
            "danger"
        ]:

            level = "safe"

        # ----------------------------------------------------
        # IS DANGEROUS
        # ----------------------------------------------------

        is_dangerous = (
            level in [
                "warning",
                "danger"
            ]
        )

        # ----------------------------------------------------
        # FINAL RESULT
        # ----------------------------------------------------

        return {

            "is_dangerous":
                is_dangerous,

            "level":
                level,

            "reason":
                str(
                    data.get(
                        "reason",
                        ""
                    )
                ),

            "recommendation":
                str(
                    data.get(
                        "recommendation",
                        ""
                    )
                )
        }

    except Exception as e:

        print(
            f"⚠️ فشل فحص الأمان: {e}"
        )

        return safe_default_result()