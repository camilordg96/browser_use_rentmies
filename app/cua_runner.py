python
"""HubSpot meeting automation with planner/executor split.

Usage examples (local):
    python cua_runner.py               # runs default
    python cua_runner.py "<hubspot URL>" "Ana" "López" "ana@email.com" "11"

When imported, call run_cua(meeting_url, ...) directly.

Environment variables consumed:
    OPENAI_API_KEY          OpenAI secret key
    OPENAI_MODEL_PLANNER    Defaults to "o3-mini"
    OPENAI_MODEL_EXECUTOR   Defaults to "computer-use-preview"

The script is designed for Render (FastAPI wrapper) **and** standalone CLI.
"""

import os
import sys
import time
import base64
from pathlib import Path
from typing import Optional

from openai import OpenAI
from playwright.sync_api import sync_playwright

# ──────────────────────────────────────────────────────────────────────────────
# Configuration from environment variables (with sane defaults)
# ──────────────────────────────────────────────────────────────────────────────
PLANNER_MODEL: str = os.getenv("OPENAI_MODEL_PLANNER", "o3-mini")
EXECUTOR_MODEL: str = os.getenv("OPENAI_MODEL_EXECUTOR", "computer-use-preview")
API_KEY: str | None = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise RuntimeError("⚠️  OPENAI_API_KEY env var is missing!")

client = OpenAI(api_key=API_KEY)

# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def handle_action(page, action):
    """Maps a `computer_call.action` to a real Playwright command."""
    try:
        match action.type:
            case "click":
                page.mouse.click(action.x, action.y, button=action.button or "left")
            case "scroll":
                page.mouse.move(action.x, action.y)
                page.evaluate(f"window.scrollBy({action.scroll_x}, {action.scroll_y})")
            case "type":
                page.keyboard.type(action.text)
            case "keypress":
                for k in action.keys:
                    page.keyboard.press("Enter" if k.lower() == "enter" else k)
            case "wait":
                time.sleep(2)
            # The model may request a screenshot explicitly; we always take one later.
            case "screenshot":
                pass
            case _:
                print(f"[handle_action] Unrecognised action: {action.type}")
    except Exception as exc:
        print("Playwright error while executing action:", exc)


def grab_screenshot(page) -> str:
    """Returns a base‑64 PNG string of the current viewport (60 s timeout)."""
    img_bytes = page.screenshot(timeout=60_000)
    return base64.b64encode(img_bytes).decode()


def plan_with_o3(prompt: str) -> str:
    """Uses the cheap `o3-mini` model to generate a high‑level plan (optional)."""
    chat = client.chat.completions.create(
        model=PLANNER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    return chat.choices[0].message.content.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Core runner (called by FastAPI or __main__)
# ──────────────────────────────────────────────────────────────────────────────

def run_cua(
    meeting_url: str,
    first_name: str = "Camilo",
    last_name: str = "Caceres",
    email: str = "camilo@rentmies.com",
    hour: str = "10",
):
    """Main function that drives the browser with the executor model."""

    if "hubspot.com" not in meeting_url:
        raise ValueError("meeting_url must be a valid HubSpot link")

    # User prompt the executor model will receive
    user_prompt = (
        f"Abre {meeting_url} y agenda cualquier cita disponible. "
        f"Luego rellena Nombre='{first_name}', Apellido='{last_name}', "
        f"Correo='{email}', Hora='{hour}' y confirma."
    )

    # Optional high‑level plan (mostly for logs/debugging)
    print("🧠  Generando plan con", PLANNER_MODEL)
    try:
        plan = plan_with_o3(user_prompt)
        for line in plan.splitlines():
            print("   ·", line)
    except Exception as exc:  # plan step is best‑effort
        print("[plan_with_o3]", exc)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-extensions", "--disable-file-system"],
        )
        page = browser.new_page()
        page.set_viewport_size({"width": 1024, "height": 768})
        page.goto(meeting_url)

        # First message to executor model
        response = client.responses.create(
            model=EXECUTOR_MODEL,
            tools=[{
                "type": "computer_use_preview",
                "display_width": 1024,
                "display_height": 768,
                "environment": "browser",
            }],
            input=[{"role": "user", "content": user_prompt}],
            truncation="auto",
        )

        # Main loop — keep feeding screenshots until no more computer_call
        while True:
            calls = [item for item in response.output if item.type == "computer_call"]
            if not calls:
                print("✅  Sin más acciones. Proceso concluido.")
                break

            call = calls[0]
            handle_action(page, call.action)

            response = client.responses.create(
                model=EXECUTOR_MODEL,
                previous_response_id=response.id,
                tools=[{
                    "type": "computer_use_preview",
                    "display_width": 1024,
                    "display_height": 768,
                    "environment": "browser",
                }],
                input=[{
                    "call_id": call.call_id,
                    "type": "computer_call_output",
                    "output": {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{grab_screenshot(page)}",
                    },
                }],
                truncation="auto",
            )

        browser.close()


# ──────────────────────────────────────────────────────────────────────────────
# CLI helper so you can run:  python cua_runner.py <url> [first last mail hour]
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        # Default quick test
        run_cua("https://meetings.hubspot.com/caceres-d/prueba-rentmies")
    else:
        run_cua(*args)
```
