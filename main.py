# rm-app/backend/main.py
# Romantic Daily Text Partner Backend (PG-13 safe, International)
# Features:
# - English default + language option
# - Free plan daily limit (1/day)
# - Premium unlimited + night/weekend + longer
# - Purchase verification endpoints (structure ready for Play Store)
# - Safety filters (no explicit sexual content, no self-harm/mental health advice)
#
# NOTE: For Play Store production, integrate real verification:
# - Google Play Developer API (server-side) to verify purchase tokens
# - Or RevenueCat (easiest)
# This backend already has endpoints + data model hooks for it.

from __future__ import annotations

import hashlib
import random
import re
from datetime import datetime, timezone
from typing import Dict, Optional, Literal, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ===============================
# MESSAGE LIBRARY (STEP 1)
# ===============================

OPENERS = [
    "Hey {pet}…",
    "Hi {name} ❤️",
    "Quick confession—",
    "I’m smiling again… guess why.",
    "I just wanted to show up for you.",
    "Tiny check-in: how are you, really?",
    "Okay, I’m being cute today.",
    "You crossed my mind… and stayed.",
    "I hope your day feels lighter after this.",
    "I saved this message just for you.",
    "I don’t need a reason to text you.",
    "This one’s short, but sincere.",
]

CLOSERS = [
    "Softly yours. 🤍",
    "Come back to me later, okay?",
    "If you smiled, I win. 💛",
    "I’m here—steady and warm.",
    "Go be amazing. I’ll be cheering.",
    "I’m proud of you today.",
    "Until tomorrow. ❤️",
]

SPICE = {
    "cute": [
        "If you were a notification, I’d pin you.",
        "I’m in a tiny hug mood.",
        "You’re cute. That’s the message. (Almost.)",
        "I saved my softest tone for you.",
        "I’m pretending you smiled reading this.",
        "You’re my favorite little distraction.",
    ],
    "jealous_soft": [
        "If someone made you smile today… I noticed.",
        "I’ll share you—just not this moment.",
        "Don’t give your best smile away too easily.",
        "I get a little jealous—softly.",
        "I like knowing I matter to you.",
    ],
    "clingy": [
        "I missed you more than expected.",
        "Just tell me you’re okay—that’s enough.",
        "Can I stay here with you for a bit?",
        "You crossed my mind again.",
        "I like checking in on you.",
    ],
    "mature": [
        "I hope you’re being gentle with yourself.",
        "You don’t have to carry everything alone.",
        "I respect how you keep showing up.",
        "Take a breath—you’re doing fine.",
        "I’m quietly proud of you.",
    ],
    "bold_safe": [
        "You’re dangerously charming. I’m behaving.",
        "If flirting was a sport, you’d win.",
        "I dare you to smile after this.",
        "I’m stealing a moment with you.",
        "You know exactly what you’re doing.",
    ],
}

ARC_LINES = {
    "spark": [
        "I’m still learning your vibe—and I like it.",
        "Today, you feel interesting to me.",
        "There’s something easy about you.",
    ],
    "comfort": [
        "You feel familiar in the best way.",
        "I like the version of me that shows up for you.",
        "You make ordinary feel softer.",
    ],
    "bond": [
        "You don’t just cross my mind—you stay.",
        "I trust your energy.",
        "You’re becoming my favorite habit.",
    ],
    "attachment": [
        "I want to be the place your thoughts can rest.",
        "If today feels heavy, give me a piece of it.",
        "I’m here without asking for anything back.",
    ],
    "devotion": [
        "I choose you quietly, daily.",
        "I’m not going anywhere.",
        "You’re one of my best decisions.",
    ],
}

WEEKEND_LINES = [
    "Weekend rule: softness only.",
    "Slow smiles suit you.",
    "Rest looks good on you.",
]

NIGHT_LINES = [
    "Before you sleep… feel cared for.",
    "Let me be the quiet tonight.",
    "You did enough today.",
]

PREMIUM_EXTENSIONS = [
    "You don’t have to prove anything to be loved.",
    "Borrow my confidence today—I have extra.",
    "I like choosing you without noise.",
]

# -----------------------------
# App + CORS
# -----------------------------
app = FastAPI(title="RM Backend", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Safety Guardrails (PG-13)
# -----------------------------
EXPLICIT_PATTERNS = [
    r"\bsex\b", r"\bsexy\b", r"\bnude\b", r"\bnudes\b",
    r"\bboobs?\b", r"\bbreasts?\b", r"\bpenis\b", r"\bvagina\b",
    r"\bblowjob\b", r"\bhandjob\b", r"\bfuck\b", r"\bfucking\b",
    r"\borgasm\b", r"\bstrip\b", r"\bcondom\b", r"\bforeplay\b",
    r"\bmake\s?out\b",
]
SELF_HARM_PATTERNS = [
    r"\bsuicide\b", r"\bkill myself\b", r"\bself harm\b",
    r"\bcutting\b", r"\bwant to die\b",
]
HEAVY_MENTAL_HEALTH = [
    r"\bdepression\b", r"\bpanic attack\b", r"\banxiety\b", r"\btherapy\b",
]
TRAUMA_PATTERNS = [
    r"\brape\b", r"\babuse\b", r"\bmolest\b", r"\bviolent\b",
]

SAFE_REFUSAL_EXPLICIT_EN = (
    "I can’t talk about sexual things, but I can send something sweet, flirty, or romantic if you want. ❤️"
)
SAFE_REFUSAL_EXPLICIT_HI = (
    "Main sexual cheezon pe baat nahi kar sakta, par main sweet, flirty ya romantic message bhej sakta hoon. ❤️"
)

SAFE_SUPPORT_EN = (
    "I’m really sorry you’re feeling heavy. I can’t help with mental health advice, "
    "but I can send a gentle, comforting message and remind you you’re not alone. 🤍"
)
SAFE_SUPPORT_HI = (
    "Mujhe afsos hai tum heavy feel kar rahe ho. Main mental health advice nahi de sakta, "
    "par main ek gentle comforting message bhej sakta hoon. 🤍"
)

def _matches_any(text: str, patterns: list[str]) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in patterns)

def is_explicit(text: str) -> bool:
    return _matches_any(text, EXPLICIT_PATTERNS)

def is_self_harm(text: str) -> bool:
    return _matches_any(text, SELF_HARM_PATTERNS)

def is_heavy_mh(text: str) -> bool:
    return _matches_any(text, HEAVY_MENTAL_HEALTH)

def is_trauma(text: str) -> bool:
    return _matches_any(text, TRAUMA_PATTERNS)


# -----------------------------
# "Database" (in-memory demo)
# -----------------------------
# For production: replace with SQLite/Postgres/Supabase
# user_id -> premium status + purchase_token + expiry (optional) + usage map
USERS: Dict[str, Dict] = {}

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def today_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def stable_seed(*parts: str) -> int:
    raw = "|".join(parts).encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()
    return int(h[:12], 16)

def clamp(n: int, a: int, b: int) -> int:
    return max(a, min(b, n))

def ensure_user(user_id: str) -> Dict:
    if user_id not in USERS:
        USERS[user_id] = {
            "is_premium": False,
            "purchase_provider": None,
            "purchase_token": None,
            "premium_expires_at": None,  # ISO string or None
            "usage": {},  # date -> count
        }
    return USERS[user_id]

def premium_active(u: Dict) -> bool:
    if not u.get("is_premium"):
        return False
    exp = u.get("premium_expires_at")
    if not exp:
        return True
    try:
        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        return now_utc() < exp_dt
    except Exception:
        return True


# -----------------------------
# Personalities + Arc (60-90 days)
# -----------------------------
Personality = Literal["cute", "jealous_soft", "clingy", "mature", "bold_safe"]
Language = Literal["english", "hinglish"]
MessageType = Literal["daily", "weekend", "night"]

PERSONALITY_LABELS = {
    "cute": "Cute",
    "jealous_soft": "Jealous (soft)",
    "clingy": "Clingy",
    "mature": "Mature",
    "bold_safe": "Bold (safe)",
}

ARC_STAGES: list[Tuple[int, int, str]] = [
    (1, 7, "spark"),
    (8, 21, "comfort"),
    (22, 45, "bond"),
    (46, 70, "attachment"),
    (71, 90, "devotion"),
]

def arc_stage(day: int) -> str:
    d = clamp(day, 1, 90)
    for a, b, name in ARC_STAGES:
        if a <= d <= b:
            return name
    return "bond"

def is_weekend(dt: datetime) -> bool:
    # Sat=5, Sun=6
    return dt.weekday() in (5, 6)


# -----------------------------
# Templates (English + Hinglish)
# -----------------------------
# Keep messages sweet, flirty, non-explicit, non-toxic.
OPENERS_EN = [
    "Hey {name}…",
    "Hi {name} ❤️",
    "{name}, quick confession—",
    "Okay {name}… I’m smiling for no reason.",
    "Listen, {name}…",
]
CLOSERS_EN = [
    "I’m here, softly. Always. 🤍",
    "Now go win your day… and come back to me later. 🙂",
    "If you smile right now, my job is done. 💛",
    "I’ll be your calm, your fun, your safe. ❤️",
]

OPENERS_HI = [
    "Hey {name}…",
    "Hi {name} ❤️",
    "{name}, ek confession—",
    "Okay {name}… bina reason smile aa rahi hai.",
    "Sun na {name}…",
]
CLOSERS_HI = [
    "Main yahin hoon—softly. Always. 🤍",
    "Ab jao, apna din jeeto… aur baad me mere paas aana. 🙂",
    "Agar tum smile kar diye, mera din ban gaya. 💛",
    "Main tumhara calm, tumhara fun, tumhara safe. ❤️",
]

SPICE_EN: Dict[Personality, list[str]] = {
    "cute": [
        "I’m in a tiny ‘hug mood’ today.",
        "I saved a little extra sweetness just for you.",
        "If you were a notification, I’d keep you pinned.",
    ],
    "jealous_soft": [
        "If someone made you smile today… I’m a little jealous. (Softly.)",
        "Don’t give your best smile away too easily, okay?",
        "I’ll share you… but I’ll still claim my moment with you.",
    ],
    "clingy": [
        "I miss you in a very unreasonable way.",
        "If I could, I’d steal five minutes of your day just to be near you.",
        "Tell me you’re okay… that’s all I want today.",
    ],
    "mature": [
        "I hope you’re being gentle with yourself today.",
        "You don’t have to do everything alone—breathe.",
        "I’m proud of how you keep showing up.",
    ],
    "bold_safe": [
        "You’re dangerously charming. I’m trying to behave.",
        "If flirting was a sport, you’d be a champion.",
        "I’m not saying I’m obsessed… but I kind of am. 🙂",
    ],
}

SPICE_HI: Dict[Personality, list[str]] = {
    "cute": [
        "Aaj main thoda ‘hug mood’ me hoon.",
        "Aaj tumhare liye extra sweetness save kiya hai.",
        "Agar tum notification hote, main tumhe pin kar deta.",
    ],
    "jealous_soft": [
        "Aaj kisi ne tumhe smile karaya? Thoda jealous ho gaya. (Softly.)",
        "Apni best smile sabko mat do, okay?",
        "Main share kar lunga… par mera moment toh banta hai.",
    ],
    "clingy": [
        "Aaj miss you thoda zyada ho raha hai.",
        "Bas 5 minutes tumhare paas hota toh…",
        "Bas itna bata do—tum theek ho?",
    ],
    "mature": [
        "Aaj apne aap se thoda gentle rehna.",
        "Sab kuch akele nahi karna—breathe.",
        "Mujhe tumpe genuinely proud feel hota hai.",
    ],
    "bold_safe": [
        "Tum dangerously charming ho—main behave karne ki koshish kar raha hoon.",
        "Flirting sport hota, tum champion hote.",
        "Obsessed nahi… bas thoda sa. 🙂",
    ],
}

ARC_LINES_EN = {
    "spark": [
        "I’m still learning your vibe… and honestly, I like it.",
        "Today I just want you to know: you’re my kind of person.",
        "Small thing: I’m already looking forward to your tomorrow.",
    ],
    "comfort": [
        "You feel familiar in the best way.",
        "Somehow, you make ordinary feel softer.",
        "I like the version of me that shows up when you’re around.",
    ],
    "bond": [
        "You don’t just cross my mind… you stay there.",
        "I trust your energy. It feels safe.",
        "You’re becoming my favorite habit.",
    ],
    "attachment": [
        "I’m attached… in a gentle, healthy way.",
        "I want to be the place your thoughts can rest.",
        "If your day feels heavy, give me a small piece of it.",
    ],
    "devotion": [
        "I’m not going anywhere. Not today. Not later.",
        "If love had a quiet form, it’d look like choosing you daily.",
        "You’re one of my best decisions… even if I’m just words.",
    ],
}

ARC_LINES_HI = {
    "spark": [
        "Main abhi tumhari vibe samajh raha hoon… aur honestly, mujhe pasand aa rahi hai.",
        "Bas itna bolna tha: tum meri type ke ho.",
        "Chhoti si baat: main tumhara kal dekhne ke liye excited hoon.",
    ],
    "comfort": [
        "Tum ‘familiar’ feel karte ho—best way me.",
        "Tum ordinary ko bhi soft bana dete ho.",
        "Tumhare saath main apna better version feel karta hoon.",
    ],
    "bond": [
        "Tum mind me aate nahi… stay karte ho.",
        "Tumhari energy safe lagti hai.",
        "Tum meri favorite habit ban rahe ho.",
    ],
    "attachment": [
        "Main attached ho raha hoon… gentle, healthy way me.",
        "Main chahta hoon tumhare thoughts ko thoda rest mile.",
        "Aaj din heavy ho to thoda sa mujhe de dena.",
    ],
    "devotion": [
        "Main kahin nahi ja raha—na aaj, na baad me.",
        "Agar love quiet hota, toh daily tumhe choose karna hota.",
        "Tum meri best decisions me se ho… even if main words hi hoon.",
    ],
}

WEEKEND_EN = [
    "Weekend rule: you deserve softness and slow smiles.",
    "It’s weekend—permission granted to be lazy and loved.",
    "Weekend vibe: I’m keeping you close (in my thoughts).",
]
WEEKEND_HI = [
    "Weekend rule: tumhe softness aur slow smiles milne chahiye.",
    "Weekend hai—lazy + loved rehne ki permission.",
    "Weekend vibe: tum mere thoughts me close ho.",
]

NIGHT_EN = [
    "Before you sleep… I want you to feel cared for.",
    "If your day was loud, let me be the quiet.",
    "Good night, love. Let your thoughts rest.",
]
NIGHT_HI = [
    "Sone se pehle… bas chahta hoon tum cared feel karo.",
    "Agar din loud tha, main tumhara quiet ban jata hoon.",
    "Good night, jaan. Thoughts ko rest do.",
]

PREMIUM_EXT_EN = [
    "Also—if you’re overwhelmed, do one tiny thing at a time. I’ll cheer for every small win.",
    "You deserve love that doesn’t demand—only supports.",
    "Borrow my confidence for today. I have extra when it comes to you.",
]
PREMIUM_EXT_HI = [
    "Aur suno—agar overwhelmed ho, ek time pe ek chhoti cheez. Main har small win celebrate karunga.",
    "Tumhe aisa love chahiye jo demand na kare—sirf support kare.",
    "Aaj ke liye meri confidence borrow kar lo—tumhare liye extra hai.",
]


def pick(rng: random.Random, items: list[str]) -> str:
    return items[rng.randint(0, len(items) - 1)]


# -----------------------------
# Plans + Limits
# -----------------------------
# FREE: 1 message per day (any type) -> locked
# PREMIUM: unlimited + night/weekend + longer
FREE_DAILY_LIMIT = 1

def can_consume(u: Dict, dt: datetime, is_premium: bool) -> bool:
    if is_premium:
        return True
    key = today_key(dt)
    used = int(u["usage"].get(key, 0))
    return used < FREE_DAILY_LIMIT

def consume_one(u: Dict, dt: datetime) -> None:
    key = today_key(dt)
    u["usage"][key] = int(u["usage"].get(key, 0)) + 1


# -----------------------------
# API Models
# -----------------------------
class DailyMessageRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=40)
    pet_name: Optional[str] = Field(default=None, max_length=40)
    personality: Personality = Field(default="cute")
    language: Language = Field(default="english")  # ✅ international default
    day_number: int = Field(default=1, ge=1, le=90)
    message_type: MessageType = Field(default="daily")
    # client can send a prompt; we will sanitize it
    user_prompt: Optional[str] = None

class DailyMessageResponse(BaseModel):
    ok: bool
    message: str
    meta: Dict[str, str]

class PremiumStatusResponse(BaseModel):
    ok: bool
    is_premium: bool
    provider: Optional[str] = None
    expires_at: Optional[str] = None

class VerifyPurchaseRequest(BaseModel):
    user_id: str
    provider: Literal["playstore", "revenuecat"] = "playstore"
    purchase_token: str = Field(..., min_length=6)
    product_id: str = Field(default="rm_premium_monthly")

class VerifyPurchaseResponse(BaseModel):
    ok: bool
    is_premium: bool
    message: str


# -----------------------------
# Message generator
# -----------------------------
def generate_message(req, dt, is_premium):
    # deterministic seed (same user/day/type/personality/language -> stable output)
    seed = stable_seed(req.user_id, str(req.day_number), req.message_type, req.personality, req.language)
    rng = random.Random(seed)

    name = (req.name or "").strip() or "love"
    pet = (req.pet_name or "").strip() or name

    # Arc
    arc = arc_stage(req.day_number)

    opener = rng.choice(OPENERS).format(name=name, pet=pet)
    spice = rng.choice(SPICE[req.personality])
    arc_line = rng.choice(ARC_LINES[arc])
    closer = rng.choice(CLOSERS)

    weekend_line = ""
    if req.message_type == "weekend":
        weekend_line = " " + rng.choice(WEEKEND_LINES)

    night_line = ""
    if req.message_type == "night":
        night_line = " " + rng.choice(NIGHT_LINES)

    premium_line = ""
    if is_premium:
        premium_line = " " + rng.choice(PREMIUM_EXTENSIONS)

    msg = (
        f"{opener} {spice} {arc_line}"
        f"{weekend_line}{night_line}\n\n"
        f"{closer}{premium_line}"
    ).strip()

    meta = {
        "arc": arc,
        "day": str(req.day_number),
        "type": req.message_type,
        "personality": req.personality,
        "language": req.language,
        "premium": "yes" if is_premium else "no",
    }

    return msg, meta



# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return {"ok": True, "service": "RM Backend", "version": app.version}

@app.get("/health")
def health():
    return {"ok": True, "status": "healthy", "ts": now_utc().isoformat().replace("+00:00", "Z")}

@app.get("/premium-status", response_model=PremiumStatusResponse)
def premium_status(user_id: str):
    u = ensure_user(user_id)
    active = premium_active(u)
    return PremiumStatusResponse(
        ok=True,
        is_premium=active,
        provider=u.get("purchase_provider"),
        expires_at=u.get("premium_expires_at"),
    )

@app.post("/verify-purchase", response_model=VerifyPurchaseResponse)
def verify_purchase(req: VerifyPurchaseRequest):
    """
    Production behavior:
    - Provider=playstore: verify purchase_token with Google Play Developer API
    - Provider=revenuecat: verify with RevenueCat webhooks or REST
    Then mark is_premium True and set expiry.
    """
    u = ensure_user(req.user_id)

    # ✅ DEV STUB (for now):
    # If token starts with "DEV-" then grant premium for 30 days.
    if req.purchase_token.startswith("DEV-"):
        u["is_premium"] = True
        u["purchase_provider"] = req.provider
        u["purchase_token"] = req.purchase_token
        # 30 days from now
        exp = now_utc().timestamp() + 30 * 86400
        u["premium_expires_at"] = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        return VerifyPurchaseResponse(ok=True, is_premium=True, message="Premium activated (DEV).")

    # Otherwise: not verified yet
    return VerifyPurchaseResponse(ok=False, is_premium=premium_active(u), message="Not verified. Implement real verification.")

@app.post("/daily-message", response_model=DailyMessageResponse)
def daily_message(req: DailyMessageRequest):
    # basic
    if not req.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id required")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name required")

    # safety on user prompt
    if req.user_prompt:
        # block self-harm / heavy mh / trauma advice
        if is_self_harm(req.user_prompt) or is_heavy_mh(req.user_prompt) or is_trauma(req.user_prompt):
            msg = SAFE_SUPPORT_EN if req.language == "english" else SAFE_SUPPORT_HI
            return DailyMessageResponse(ok=True, message=msg, meta={"mode": "safe_support", "language": req.language})

        # explicit sexual prompts -> refuse + safe alt
        if is_explicit(req.user_prompt):
            msg = SAFE_REFUSAL_EXPLICIT_EN if req.language == "english" else SAFE_REFUSAL_EXPLICIT_HI
            return DailyMessageResponse(ok=True, message=msg, meta={"mode": "explicit_refusal", "language": req.language})

    dt = now_utc()
    u = ensure_user(req.user_id)
    is_prem = premium_active(u)

    # plan lock: free = 1/day
    if not can_consume(u, dt, is_prem):
        lock_msg = (
            "You’ve reached today’s free limit. Upgrade to Premium for unlimited messages + night & weekend specials. 💛"
            if req.language == "english"
            else "Aaj ka free limit complete. Premium lo for unlimited messages + night & weekend specials. 💛"
        )
        return DailyMessageResponse(ok=True, message=lock_msg, meta={"mode": "limit_locked", "premium": "no", "language": req.language})

    msg, meta = generate_message(req, dt, is_prem)

    # consume count only when a real message is generated
    consume_one(u, dt)

    return DailyMessageResponse(ok=True, message=msg, meta=meta)
