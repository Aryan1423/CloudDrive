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

class Downloader:
    def __init__(self, filename: str):
        self.filename = filename
        self.t_bots = []
        self.chunks_total = 0
        self.downloaded_chunks_counter = 0

    def run(self):
        logging.info('Start download')

        for obj in db.get_bots():
            bot = TelegramBot(obj[2], obj[3])
            self.t_bots.append(bot)
        logging.info(f"Initialized {len(self.t_bots)} Telegram bots")

        file_hash = db.get_file_by_name(self.filename)[0][2]
        chunks = db.get_chunks(file_hash)
        chunk_groups = split_chunks(chunks, len(self.t_bots))
        self.chunks_total = len(chunks)

        logging.info('Downloading chunks')
        threads = []
        for i, chunks in enumerate(chunk_groups):
            thread = threading.Thread(target=self.bot_download, args=(chunks, self.t_bots[i]))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

        # Merge chunks into a single file
        output_file_path = fm.merge_chunks(self.filename, file_hash)
        logging.info(f"File merged: {output_file_path}")

        # Comment out or remove deletion of the merged file:
        # try:
        #     os.remove(output_file_path)
        #     logging.info(f"Deleted merged file from output folder: {output_file_path}")
        # except Exception as e:
        #     logging.error(f"Error deleting merged file from output folder: {e}")

    def bot_download(self, chunks: list, bot: TelegramBot):
        for chunk in chunks:
            chunk_hash = chunk[1]
            chunk_file_id = chunk[3]
            logging.info(f"Downloading chunk: {chunk_file_id}")

            # Download chunk using Telegram bot
            try:
                chunk_data = bot.download_document(chunk_file_id)
                chunk_path = os.path.join(fm.loaded_chunks, f"{chunk_hash}.chunk")
                with open(chunk_path, "wb") as chunk_file:
                    chunk_file.write(chunk_data)
                logging.info(f"Downloaded chunk: {chunk_path}")
            except Exception as e:
                logging.error(f"Error downloading chunk from Telegram: {e}")
                continue

            try:
                lock.acquire(True)
                self.downloaded_chunks_counter += 1
                logging.info(f"Chunk downloaded: {chunk_hash}")
            except Exception as e:
                logging.error(f"Error processing downloaded chunk: {e}")
            finally:
                lock.release()
