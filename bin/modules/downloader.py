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
        self.successful_chunks = []  # Track successfully downloaded chunks

    def run(self):
        logging.info(f'Start download of {self.filename}')

        # Check if the file already exists in the output directory
        output_file_path = os.path.join(fm.output_path, self.filename)
        if os.path.exists(output_file_path) and os.path.getsize(output_file_path) > 0:
            logging.info(f"File already exists in output directory: {output_file_path}")
            return output_file_path

        for obj in db.get_bots():
            bot = TelegramBot(obj[2], obj[3])
            self.t_bots.append(bot)
        logging.info(f"Initialized {len(self.t_bots)} Telegram bots")

        file_info = db.get_file_by_name(self.filename)
        if not file_info or len(file_info) == 0:
            logging.error(f"File {self.filename} not found in database")
            return None
            
        file_hash = file_info[0][2]
        chunks = db.get_chunks(file_hash)
        
        if not chunks:
            logging.error(f"No chunks found for file {self.filename} with hash {file_hash}")
            return None
            
        chunk_groups = split_chunks(chunks, len(self.t_bots))
        self.chunks_total = len(chunks)

        logging.info(f'Downloading {self.chunks_total} chunks')
        threads = []
        for i, chunk_group in enumerate(chunk_groups):
            thread = threading.Thread(target=self.bot_download, args=(chunk_group, self.t_bots[i]))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

        # Check if we have any chunks to merge
        if not self.successful_chunks:
            logging.error("No chunks were successfully downloaded. Cannot create file.")
            return None
            
        # Merge chunks into a single file
        output_file_path = fm.merge_chunks(self.filename, file_hash)
        logging.info(f"File merged: {output_file_path}")
        
        return output_file_path

    def bot_download(self, chunks: list, bot: TelegramBot):
        for chunk in chunks:
            # Correctly access chunk data based on database schema:
            # id, main_file, hash, chunk_index, file_id, key
            chunk_hash = chunk[2]  # Hash of this specific chunk
            chunk_index = chunk[3]  # Index of the chunk
            chunk_file_id = chunk[4]  # Telegram file_id
            main_file_hash = chunk[1]  # Main file hash that this chunk belongs to
            
            # Define the expected path for this chunk
            chunk_path = os.path.join(fm.loaded_chunks, f"{main_file_hash}_{chunk_index}")
            
            # Check if chunk already exists locally
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                logging.info(f"Chunk already exists locally, skipping download: {chunk_path}")
                
                # Track successful usage of existing chunk
                with lock:
                    self.successful_chunks.append(chunk_hash)
                    self.downloaded_chunks_counter += 1
                    logging.info(f"Using cached chunk: {chunk_hash} ({self.downloaded_chunks_counter}/{self.chunks_total})")
                continue
            
            logging.info(f"Downloading chunk: {chunk_file_id}")
            
            # Skip invalid file IDs
            if not chunk_file_id or len(str(chunk_file_id)) < 10:  # Simple validation
                logging.error(f"Invalid file ID format: {chunk_file_id}")
                continue

            # Download chunk using Telegram bot
            try:
                chunk_data = bot.download_document(chunk_file_id)
                if not chunk_data:
                    logging.error(f"No data returned for chunk: {chunk_file_id}")
                    continue
                
                with open(chunk_path, "wb") as chunk_file:
                    chunk_file.write(chunk_data)
                logging.info(f"Downloaded chunk: {chunk_path}")
                
                # Track successful download
                with lock:
                    self.successful_chunks.append(chunk_hash)
                    self.downloaded_chunks_counter += 1
                    logging.info(f"Chunk downloaded: {chunk_hash} ({self.downloaded_chunks_counter}/{self.chunks_total})")
            except Exception as e:
                logging.error(f"Error downloading chunk from Telegram: {e}")
                continue
