import base64
import random
import secrets
import string
import unicodedata
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.db.redis_client import get_redis

CAPTCHA_PREFIX = "auth:captcha:"
CAPTCHA_TTL = 300

_AUTH_DIR = Path(__file__).resolve().parent
_BUNDLED_FONT = _AUTH_DIR / "assets" / "DejaVuSans-Bold.ttf"


def _font_candidates() -> list[Path]:
    candidates = [
        _BUNDLED_FONT,
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]

    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            ordered.append(path)

    for root in (Path("/usr/share/fonts"), Path("/usr/local/share/fonts")):
        if not root.is_dir():
            continue
        for pattern in ("*Bold*.ttf", "*.ttf"):
            for path in sorted(root.rglob(pattern)):
                if path not in seen:
                    seen.add(path)
                    ordered.append(path)

    return ordered


def _load_font(size: int = 28) -> ImageFont.FreeTypeFont:
    for path in _font_candidates():
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue

    raise RuntimeError(
        "No captcha font found. Install fonts-dejavu-core in the container or place "
        f"DejaVuSans-Bold.ttf at {_BUNDLED_FONT}"
    )


def _render_captcha_image(text: str) -> str:
    width, height = 120, 44
    image = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(image)

    for _ in range(6):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(200, 210, 220), width=1)

    for _ in range(80):
        draw.point((random.randint(0, width - 1), random.randint(0, height - 1)), fill=(180, 190, 200))

    font = _load_font(28)

    for index, char in enumerate(text):
        x = 14 + index * 24 + random.randint(-2, 2)
        y = random.randint(4, 10)
        color = (
            random.randint(20, 80),
            random.randint(20, 80),
            random.randint(20, 80),
        )
        draw.text((x, y), char, font=font, fill=color)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _normalize_answer(value: str) -> str:
    """去空白、全角转半角、统一大写，降低输入法导致的误判。"""
    text = unicodedata.normalize("NFKC", (value or "").strip())
    return "".join(text.split()).upper()


def create_captcha() -> tuple[str, str]:
    captcha_id = secrets.token_urlsafe(16)
    # 去掉易混字符 I/O/L
    alphabet = "".join(ch for ch in string.ascii_uppercase if ch not in {"I", "O", "L"})
    answer = "".join(secrets.choice(alphabet) for _ in range(4))
    get_redis().setex(f"{CAPTCHA_PREFIX}{captcha_id}", CAPTCHA_TTL, answer)
    image = _render_captcha_image(answer)
    return captcha_id, image


def verify_captcha(captcha_id: str, captcha_answer: str) -> bool:
    if not captcha_id or not captcha_answer:
        return False
    key = f"{CAPTCHA_PREFIX}{captcha_id.strip()}"
    client = get_redis()
    # 原子取出并删除，避免并发重复使用
    try:
        expected = client.getdel(key)
    except (AttributeError, TypeError):
        pipe = client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        expected, _ = pipe.execute()
    if not expected:
        return False
    return _normalize_answer(str(expected)) == _normalize_answer(captcha_answer)
