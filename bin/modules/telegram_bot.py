import os
import json
import requests
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class TelegramBot:
    def __init__(self, bot_token: str = None, chat_id: str = None) -> None:
        # If bot_token or chat_id are not provided, load from environment variables.
        if bot_token is None:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if chat_id is None:
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}/"

    def update_bot_token(self, token: str) -> None:
        self.bot_token = token

    def update_chat_id(self, id: str) -> None:
        self.chat_id = id

    def send_document(self, file_path: str) -> str:
        url = self.base_url + "sendDocument"
        with open(file_path, "rb") as file:
            files = {"document": file}
            data = {"chat_id": self.chat_id}
            response = requests.post(url, data=data, files=files)
            response_data = response.json()
            if not response_data.get("ok"):
                raise Exception(f"Error uploading document: {response_data}")
            return response_data["result"]["document"]["file_id"]

    def download_document(self, file_id: str) -> bytes | None:
        url = self.base_url + f"getFile?file_id={file_id}"
        response = requests.get(url)
        for _ in range(10):
            if response.status_code == 200:
                file_info = response.json()["result"]
                file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_info['file_path']}"
                file_response = requests.get(file_url)
                return file_response.content
            elif response.status_code == 400:
                return None
            response = requests.get(url)
        return None
