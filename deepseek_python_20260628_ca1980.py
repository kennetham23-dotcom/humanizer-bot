import os
import tempfile
import PyPDF2
import docx
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# ---------- YOUR CONFIG (keys from Render environment) ----------
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

HUMANIZING_PROMPT = """You are an expert text humanizer. Rewrite the following text so it sounds completely natural, human-written, and free of any AI or formal patterns. Keep the original meaning and tone, but make it conversational and warm. Output only the rewritten text — no explanations, no introductions.

Text to humanize:
"""

# ---------- AI client setup ----------
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# ---------- Text extraction from files ----------
def extract_text(file_path: str, mime_type: str) -> str:
    if mime_type == "application/pdf":
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    elif mime_type and mime_type.startswith("text/"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError("Unsupported file type. Send PDF, DOCX, or TXT.")

# ---------- Humanizer ----------
def humanize_text(text: str) -> str:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": HUMANIZING_PROMPT + text}
        ],
        temperature=0.7,
        max_tokens=4096
    )
    return response.choices[0].message.content

# ---------- Telegram handlers ----------
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Send me text or upload a document (PDF, Word, TXT). I'll make it sound human-written."
    )

async def handle_input(update: Update, context):
    message = update.message
    user_text = ""

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "file"
        mime = message.document.mime_type

        file = await context.bot.get_file(file_id)
        suffix = os.path.splitext(file_name)[1]
        tmp = tempfile.mktemp(suffix=suffix)
        await file.download_to_drive(tmp)

        try:
            user_text = extract_text(tmp, mime)
        except Exception as e:
            await message.reply_text(f"❌ Could not read file: {e}")
            return
        finally:
            os.unlink(tmp)

    elif message.text:
        user_text = message.text
    else:
        await message.reply_text("Please send text or a supported file.")
        return

    if not user_text.strip():
        await message.reply_text("The file appears to be empty.")
        return

    await message.chat.send_action(action="typing")
    try:
        result = humanize_text(user_text)
        await message.reply_text(result[:4096])
    except Exception as e:
        await message.reply_text(f"⚠️ Error: {str(e)}")

# ---------- Main ----------
if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_input))

    # Webhook for Render
    port = int(os.environ.get("PORT", 10000))
    render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if render_host:
        webhook_url = f"https://{render_host}/webhook"
        print(f"Setting webhook to {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=webhook_url
        )
    else:
        # Fallback to polling (local testing)
        print("🤖 Bot is running via polling (local)...")
        app.run_polling()