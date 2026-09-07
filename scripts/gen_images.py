"""Generate product photography for the web demo with Gemini's image model
("Nano Banana", gemini-2.5-flash-image).

    GEMINI_API_KEY=...  python scripts/gen_images.py

Writes webapp/img/cam-{px,ng,at}.png — one shot per storefront, same product
family, distinct angle/colour so the three merchants read as different
listings. The webapp falls back to an inline SVG when these files are absent,
so this script is optional dressing, never a dependency.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import urllib.request

OUT = pathlib.Path(__file__).resolve().parent.parent / "webapp" / "img"
MODEL = "gemini-2.5-flash-image"

BASE_STYLE = (
    "Professional e-commerce product photograph, pure white seamless studio "
    "background, soft diffused lighting, gentle contact shadow, centered "
    "composition, high-end product photography, no text, no watermark, no logo."
)

SHOTS = {
    # PixelHaus — the too-good-to-be-true listing. Slightly showy angle.
    "cam-px.png": (
        "A sleek modern 4K webcam with a large round glass lens and a subtle "
        "blue lens ring, on a compact fold-over monitor clip, three-quarter "
        "hero angle. " + BASE_STYLE
    ),
    # NorthGear — the trustworthy listing. Straight-on, calm.
    "cam-ng.png": (
        "A premium matte-black 4K webcam with a round lens and a small "
        "privacy shutter, on a weighted desk stand, photographed straight-on. "
        + BASE_STYLE
    ),
    # Atlas — the over-budget listing. Bigger, tripod, reads more expensive.
    "cam-at.png": (
        "A professional 4K conference webcam, wider body with dual "
        "microphones and a small mounting tripod, slight top-down angle. "
        + BASE_STYLE
    ),
}


def generate(prompt: str, key: str) -> bytes:
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        data=json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE"]},
            }
        ).encode(),
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.load(r)
    for part in body["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError(f"no image in response: {json.dumps(body)[:300]}")


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY is not set. Get one at https://aistudio.google.com/apikey")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    for name, prompt in SHOTS.items():
        path = OUT / name
        print(f"  generating {name} …", flush=True)
        data = generate(prompt, key)
        path.write_bytes(data)
        print(f"    wrote {path} ({len(data)//1024} KB)")
    print("\n  done — reload the webapp; images replace the SVG automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
