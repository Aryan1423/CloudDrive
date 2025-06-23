import os
import hashlib
import logging

class FileManager:
    def __init__(self, base_path="TEMP", base_output="output"):
        self.base_path = self.create_path(base_path)
        self.split_chunks = self.create_path(os.path.join(self.base_path, "split"))
        self.loaded_chunks = self.create_path(os.path.join(self.base_path, "loaded"))
        self.output_path = self.create_path(base_output)
        self.chunk_size = 20  # MB

    def create_path(self, path: str) -> str:
        if not os.path.exists(path):
            os.makedirs(path)
        return os.path.abspath(path)

    def get_file_hash(self, file_path: str):
        hasher = hashlib.md5()
        
        def gen():
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
                    yield len(chunk)  # Progress info (if needed)
        return gen(), hasher

    def get_file_size(self, file_path: str) -> int:
        return os.path.getsize(file_path)

    def merge_chunks(self, filename: str, filehash: str, filepath: str = None) -> str:
        if filepath is None:
            filepath = self.output_path
        output_file_path = os.path.join(filepath, filename)
        
        # List only chunks whose file name starts with the filehash and contains an underscore.
        chunks = [f for f in os.listdir(self.loaded_chunks) 
                  if f.startswith(filehash) and "_" in f]
        
        logging.info(f"Chunks found for merging: {chunks}")
        
        try:
            # Sort chunks based on the index (the part after the underscore)
            chunks = sorted(chunks, key=lambda x: int(x.split("_")[1]))
        except (IndexError, ValueError) as e:
            logging.error(f"Error sorting chunks: {e}")
            raise

        with open(output_file_path, 'wb') as output_file:
            for chunk in chunks:
                chunk_path = os.path.join(self.loaded_chunks, chunk)
                with open(chunk_path, 'rb') as chunk_file:
                    output_file.write(chunk_file.read())
        
        return output_file_path

    def split_file(self, file_path: str):
        # Assumes that self.hash_filename is already set
        with open(file_path, "rb") as f:
            i = 0
            while True:
                data = f.read(self.chunk_size * 1024 * 1024)
                if not data:
                    break
                i += 1
                # Format: filehash_index
                yield f"{self.hash_filename}_{i}", data

    def process_file(self, file_path: str):
        # Calculate file hash and update self.hash_filename
        gen, hasher = self.get_file_hash(file_path)
        for _ in gen:
            pass
        self.hash_filename = hasher.hexdigest()
        
        file_size_bytes = self.get_file_size(file_path)
        chunk_size_bytes = self.chunk_size * 1024 * 1024

        if file_size_bytes <= chunk_size_bytes:
            # File is small; do not split
            chunk_name = f"{self.hash_filename}_1"
            chunk_path = os.path.join(self.split_chunks, chunk_name)
            with open(file_path, "rb") as src:
                data = src.read()
            with open(chunk_path, "wb") as dst:
                dst.write(data)
            logging.info(f"File size ({file_size_bytes} bytes) is less than or equal to {chunk_size_bytes} bytes. Not splitting.")
            yield "1"
        else:
            # File is larger; split into chunks
            for file_name, data in self.split_file(file_path):
                chunk_path = os.path.join(self.split_chunks, file_name)
                with open(chunk_path, "wb") as f:
                    f.write(data)
                logging.info(f"Created chunk: {file_name}")
                yield file_name.split('_')[1]

    def get_split_chunks(self, dir_chunks: str = None) -> list:
        if not dir_chunks:
            dir_chunks = self.split_chunks
        chunks = os.listdir(dir_chunks)
        try:
            chunks = sorted(chunks, key=lambda x: int(x.split("_")[1]))
        except (IndexError, ValueError) as e:
            logging.error(f"Error sorting split chunks: {e}")
            raise
        return chunks
