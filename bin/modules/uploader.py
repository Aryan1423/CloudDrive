import os
import threading
import logging
from bin.modules.db_manager import DBManager
from bin.modules.file_manager import FileManager
from bin.modules.telegram_bot import TelegramBot
from bin.modules.utils import split_chunks

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

db = DBManager()
fm = FileManager()
lock = threading.Lock()

class Uploader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.t_bots = []
        self.chunks_total = 0
        self.uploaded_chunks_counter = 0

    def run(self, user_id: int):
        filename = os.path.basename(self.file_path)
        file_size = fm.get_file_size(self.file_path)
        total_file_size = round(file_size / (1024 * 1024))  # in MB
        logging.info(f"Uploading file: {filename} ({total_file_size} MB)")

        # Initialize Telegram bots from DB
        for obj in db.get_bots():
            bot = TelegramBot(obj[2], obj[3])
            self.t_bots.append(bot)
        logging.info(f"Initialized {len(self.t_bots)} Telegram bots")

        # Calculate file hash
        gen, hasher = fm.get_file_hash(self.file_path)
        for _ in gen:
            pass
        file_hash = hasher.hexdigest()
        # Pass user_id to add_file
        db.add_file(user_id, filename, file_hash)
        logging.info(f"File hash: {file_hash}")

        # Split file into chunks and save them
        for _ in fm.process_file(self.file_path):
            pass
        logging.info("File split into chunks")

        # Get list of split chunk filenames
        all_chunks = fm.get_split_chunks()
        self.chunks_total = len(all_chunks)
        logging.info(f"Total chunks: {self.chunks_total}")

        # Split chunks among bots
        chunk_groups = split_chunks(all_chunks, len(self.t_bots))
        threads = []
        for i, chunks in enumerate(chunk_groups):
            thread = threading.Thread(target=self.bot_upload, args=(file_hash, chunks, self.t_bots[i]))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

        # Delete the original file from TEMP folder after uploading
        try:
            os.remove(self.file_path)
            logging.info(f"Deleted original file from TEMP folder: {self.file_path}")
        except Exception as e:
            logging.error(f"Error deleting original file from TEMP folder: {e}")

    def bot_upload(self, file_hash: str, chunks: list, bot: TelegramBot):
        for chunk in chunks:
            chunk_path = os.path.join(fm.split_chunks, chunk)
            logging.info(f"Uploading chunk: {chunk_path}")

            # Send chunk using Telegram bot and get a file ID
            try:
                chunk_file_id = bot.send_document(chunk_path)
                logging.info(f"Uploaded chunk to Telegram: {chunk_file_id}")
            except Exception as e:
                logging.error(f"Error uploading chunk to Telegram: {e}")
                continue

            gen, hasher = fm.get_file_hash(chunk_path)
            for _ in gen:
                pass
            chunk_file_hash = hasher.hexdigest()

            try:
                lock.acquire(True)
                db.add_chunk(file_hash, chunk_file_hash, chunk.split("_")[1], chunk_file_id)
                self.uploaded_chunks_counter += 1
                logging.info(f"Chunk added to DB: {chunk_file_hash}")
            except Exception as e:
                logging.error(f"Error adding chunk to DB: {e}")
            finally:
                lock.release()

            try:
                os.remove(chunk_path)
                logging.info(f"Deleted chunk file: {chunk_path}")
            except Exception as e:
                logging.error(f"Error deleting chunk file: {e}")
