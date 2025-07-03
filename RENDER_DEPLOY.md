# Render.com deployment configuration
# This file contains instructions for deploying on Render

## Deployment Options:

### Option 1: Basic Deployment (Recommended)
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- This will deploy without torrent support but all other features work

### Option 2: With Torrent Support Attempt
- Build Command: `./build.sh`
- Start Command: `gunicorn app:app`
- This tries to install libtorrent but continues if it fails

### Option 3: Docker Deployment (Most Reliable for Torrents)
- Use the provided Dockerfile
- Enable "Docker" in Render service type
- This gives full control over the build environment

## Environment Variables to Set:
- TELEGRAM_BOT_TOKEN: Your Telegram bot token
- TELEGRAM_CHAT_ID: Your Telegram chat ID
- SECRET_KEY: A secure secret key for Flask sessions

## Notes:
- The app gracefully handles missing libtorrent
- Torrent downloads will show clear error messages if not available
- All other features (HTTP downloads, uploads, sharing) work regardless
