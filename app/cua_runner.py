import os, time, base64
from openai import OpenAI
from playwright.sync_api import sync_playwright

PLANNER_MODEL   = os.getenv("OPENAI_MODEL_PLANNER",   "o3-mini")
EXECUTOR_MODEL  = os.getenv("OPENAI_MODEL_EXECUTOR",  "computer-use-preview")
API_KEY         = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=API_KEY)

def handle_action(page, a):
    try:
        match a.type:
            case "click":      page.mouse.click(a.x, a.y, button=a.button or "left")
            case "scroll":     page.mouse.move(a.x, a.y); page.evaluate(f"window.scrollBy({a.scroll_x},{a.scroll_y})")
            case "type":       page.keyboard.type(a.text)
            case "keypress":   [page.keyboard.press(k) for k in a.keys]
            case "wait":       time.sleep(2)
    except Exception as e:
        print("Playwright error:", e)

def screenshot(page):
    return base64.b64encode(page.screenshot(timeout=60000)).decode()

def plan_with_o3(user_prompt: str) -> str:
    """Usa o3-mini para producir un *plan textual* (pasos de alto nivel)."""
    chat = client.chat.completions.create(
        model=PLANNER_MODEL,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=300
    )
    return chat.choices[0].message.content

def run_cua():
    user_prompt = (
        "Abre https://meetings.hubspot.com/caceres-d/prueba-rentimies y "
        "agenda cualquier cita disponible; luego llena: "
        "Nombre=Camilo, Apellido=Caceres, email=camilo@rentmies.com, "
        "hora=10 y confirma."
    )

    print("🧠 Paso 1 — o3-mini (planner)")
    high_level_plan = plan_with_o3(user_prompt)
    print(high_level_plan)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-extensions", "--disable-file-system"])
        page    = browser.new_page()
        page.set_viewport_size({"width": 1024, "height": 768})
        page.goto("https://meetings.hubspot.com/caceres-d/prueba-rentimies")

        # Primer turno para el modelo de ejecución
        response = client.responses.create(
            model=EXECUTOR_MODEL,
            tools=[{"type": "computer_use_preview", "display_width": 1024,
                    "display_height": 768, "environment": "browser"}],
            input=[{"role": "user", "content": user_prompt}],
            truncation="auto"
        )

        while True:
            calls = [i for i in response.output if i.type == "computer_call"]
            if not calls:
                print("✅  Terminado")
                break

            call = calls[0]
            handle_action(page, call.action)

            response = client.responses.create(
                model=EXECUTOR_MODEL,
                previous_response_id=response.id,
                tools=[{"type": "computer_use_preview", "display_width": 1024,
                        "display_height": 768, "environment": "browser"}],
                input=[{
                    "call_id": call.call_id,
                    "type": "computer_call_output",
                    "output": {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{screenshot(page)}"
                    }
                }],
                truncation="auto"
            )

        browser.close()
