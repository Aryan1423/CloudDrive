# 🕵️‍♂️ CloudDrive – Unlimited Telegram Storage

⚠️ **WARNING**\
Use this tool responsibly. It uploads and downloads unlimited size files by Converting them into Chunks. You must comply with Telegram’s Terms of Service and local laws. The author is not liable for misuse.

---

## 📌 Features

- Automatically downloads or Upload files of unlimited size, no limit.
- Uses a Telegram **bot**, authenticated via Bot Token (`.env`).
- Ideal for headless setups (server, VPS, Codespaces).

---

## 🧱 Prerequisites

- Python **3.7+**
- Telegram Bot and Bot Token from BotFather (via [BotFather](https://core.telegram.org/bots))
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



## 🧾 Troubleshooting

- **No downloads?**

  - Verify the correct `TARGET_CHAT_ID`.
  - Confirm your filters match the message types being sent.


## 💡 Deploy 
```
python app.py
```

## 📄 License & Ethics

Released under the **MIT License**. Use ethically and responsibly. Respect Telegram’s terms and user privacy.

## 📝 Contributing

Found a bug or want a feature? Open an issue or submit a pull request!



