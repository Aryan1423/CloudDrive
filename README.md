# 🕵️‍♂️ CloudDrive – Telegram File Harvester Bot

⚠️ **WARNING**\
Use this tool responsibly. It downloads unlimited files (documents, photos, videos) from Telegram channels, groups, or chats. You must comply with Telegram’s Terms of Service and local laws. The author is not liable for misuse.

---

## 📌 Features

- Automatically downloads documents, photos, videos, and other attachments from a specified Telegram chat.
- Uses a Telegram **bot**, authenticated via Bot Token (`.env`).
- Ideal for headless setups (server, VPS, Codespaces).

---

## 🧱 Prerequisites

- Python **3.7+**
- Telegram Bot and Bot Token (via [BotFather](https://core.telegram.org/bots))
- Target Chat/Channel/Group ID
- Basic knowledge of `.env` and environment variables

---

## 🛠 Setup & Installation

```bash
# Clone the repo
git clone https://github.com/Aryan1423/CloudDrive.git
cd CloudDrive

# (Optional) Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 🔒 Configuration via .env

Create a `.env` file in the root directory containing:

```ini
BOT_TOKEN=<your_bot_token_here>
TARGET_CHAT_ID=<chat_or_channel_id_here>
DOWNLOAD_DIR=./downloads
```

- **BOT\_TOKEN**: Bot token obtained from BotFather
- **TARGET\_CHAT\_ID**: Numeric chat ID (groups/channels often have negative IDs)
- **DOWNLOAD\_DIR**: (Optional) Folder where downloads will be saved

### ▶️ Running the Bot

```bash
python bot.py
```

The bot will:

- Authenticate using `BOT_TOKEN`
- Listen for messages in `TARGET_CHAT_ID`
- Download attachments into `DOWNLOAD_DIR`

## 🧠 How It Works

Uses **python-telegram-bot (v20+)** to handle files like Document, Photo, and Video.

Downloads via `get_file()` and `download_to_drive()` methods.

Files are saved with their original names in the specified directory.

### 💡 Example `bot.py` Snippet

```python
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, MessageHandler, filters

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")

async def downloader(update, context):
    if update.message and update.message.chat_id == CHAT_ID:
        attachment = update.message.effective_attachment
        file = await attachment.get_file()
        saved_path = await file.download_to_drive(custom_path=DOWNLOAD_DIR)
        print(f"Saved file to {saved_path}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, downloader))
    app.run_polling()
```

### 🛠 Customization Tips

Filter specific file types using:

- `filters.Document.ALL`
- `filters.PHOTO`
- `filters.VIDEO`

For large files over 20 MB, use local mode with a custom Bot API server (see documentation).

## ⚠️ Limitations & Tips

- **Max file size (Bot API)**:
  - Downloads: up to 20 MB
  - Uploads: up to 50 MB

To exceed these limits, run your own Bot API server in local mode (allows downloads up to \~2 GB).

- Bot cannot access chat history unless it's a member of the chat.
- Ensure proper bot permissions in the target chat.

## 🧾 Troubleshooting

- **No downloads?**

  - Verify the correct `TARGET_CHAT_ID`.
  - Confirm your filters match the message types being sent.

- **File size errors?**

  - Use local mode for larger files with a self-hosted Bot API server.

## 💡 Deploy with Docker

**Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "bot.py"]
```

Run the container:

```bash
docker build -t clouddrive-bot .
docker run -d \
  --env-file .env \
  -v $(pwd)/downloads:/app/downloads \
  clouddrive-bot
```

## 📄 License & Ethics

Released under the **MIT License**. Use ethically and responsibly. Respect Telegram’s terms and user privacy.

## 📝 Contributing

Found a bug or want a feature? Open an issue or submit a pull request!

## ✅ Summary

**CloudDrive** is a Telegram bot that securely saves files from specified chats using environment-based configuration. It's easy to deploy and adapt, especially in headless environments—but use it with care.

