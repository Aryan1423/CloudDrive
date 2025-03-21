import os
import requests
import logging
import libtorrent as lt
import time
import shutil
import zipfile
from urllib.parse import urlparse, unquote

class URLDownloader:
    def __init__(self, base_path="TEMP"):
        self.base_path = base_path
        if not os.path.exists(base_path):
            os.makedirs(base_path)
        
    def download_from_url(self, url, progress_callback=None):
        """Download a file from a URL and return the local path"""
        logging.info(f"Downloading file from URL: {url}")
        
        # Parse URL to get filename
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # If no filename in URL, create a generic one
        if not filename:
            filename = f"download_{int(time.time())}"
        
        # URL decode the filename to handle special characters
        filename = unquote(filename)
            
        local_path = os.path.join(self.base_path, filename)
        
        # Check if URL is a magnet link or torrent
        if url.startswith('magnet:') or url.endswith('.torrent'):
            return self.download_torrent(url, local_path, progress_callback)
        
        # Regular HTTP download
        try:
            # Stream the download to support large files
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                bytes_downloaded = 0
                
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                            
                            # Report progress if callback provided
                            if progress_callback and total_size:
                                progress = (bytes_downloaded / total_size) * 100
                                progress_callback(progress)
                
            logging.info(f"Downloaded file to {local_path}")
            return local_path
        
        except Exception as e:
            logging.error(f"Error downloading from URL: {e}")
            raise
    
    def download_torrent(self, torrent_url, destination_path, progress_callback=None):
        """Download a file from a torrent or magnet link"""
        logging.info(f"Downloading from torrent: {torrent_url}")
        
        # Create a session with default settings
        ses = lt.session()
        ses.listen_on(6881, 6891)  # Listen on ports between 6881-6891
        
        # Create temporary directory
        temp_download_dir = os.path.join(self.base_path, 'torrent_temp')
        if not os.path.exists(temp_download_dir):
            os.makedirs(temp_download_dir)
        
        # Add the torrent
        handle = None
        torrent_name = None
        
        try:
            if torrent_url.startswith('magnet:'):
                # For magnet links
                handle = ses.add_torrent({'url': torrent_url, 'save_path': temp_download_dir})
                # Extract torrent name from magnet link if possible
                if 'dn=' in torrent_url:
                    torrent_name = unquote(torrent_url.split('dn=')[1].split('&')[0])
            else:
                # For .torrent files
                response = requests.get(torrent_url)
                torrent_data = response.content
                info = lt.torrent_info(lt.bdecode(torrent_data))
                torrent_name = info.name()
                handle = ses.add_torrent({'ti': info, 'save_path': temp_download_dir})
                
            # If no name found, create a generic one
            if not torrent_name:
                torrent_name = f"torrent_{int(time.time())}"
                
            logging.info(f"Torrent name: {torrent_name}")
        except Exception as e:
            logging.error(f"Error adding torrent: {e}")
            raise
        
        # Check for seeders and download status
        max_wait_time = 300  # 5 minutes max wait for seeders
        start_time = time.time()
        stall_start_time = None
        last_downloaded = 0
        
        # Wait for download to complete
        logging.info("Starting torrent download...")
        while not handle.status().is_seeding:
            status = handle.status()
            
            # Check if we have seeders
            if status.num_seeds == 0 and status.num_complete == 0:
                current_time = time.time()
                if current_time - start_time > max_wait_time:
                    raise Exception("No seeders available after waiting. The link may be dead.")
                
                if progress_callback:
                    progress_callback(0)
                    if int(current_time - start_time) % 15 == 0:  # Update status message every 15 seconds
                        progress_callback(0, status_message="Waiting for seeders...")
                
                time.sleep(5)
                continue
            
            # Check for stalled download
            if status.total_download == last_downloaded:
                if stall_start_time is None:
                    stall_start_time = time.time()
                elif time.time() - stall_start_time > 120:  # 2 minutes of stall
                    if status.progress < 0.01:  # If less than 1% progress and stalled
                        raise Exception("Download stalled with no progress. Please try again later.")
                    # Otherwise we keep waiting - download might just be slow
            else:
                last_downloaded = status.total_download
                stall_start_time = None
            
            # Report progress
            if progress_callback:
                progress = status.progress * 100
                download_speed = status.download_rate / 1024  # KB/s
                
                status_message = f"Downloading: {progress:.1f}% ({download_speed:.1f} KB/s) | Seeds: {status.num_seeds}"
                progress_callback(progress, status_message=status_message)
            
            logging.info(f"Torrent progress: {status.progress * 100:.2f}% | Seeds: {status.num_seeds}")
            time.sleep(1)
        
        logging.info("Torrent download complete, preparing files...")
        
        # Prepare the final path - in case it's a directory
        torrent_contents = os.listdir(temp_download_dir)
        
        # Ensure we have a valid filename for the zip
        safe_torrent_name = ''.join(c for c in torrent_name if c.isalnum() or c in ' ._-')
        if not safe_torrent_name:
            safe_torrent_name = f"torrent_{int(time.time())}"
            
        # If original destination path doesn't end with .zip, add it
        if not destination_path.lower().endswith('.zip'):
            zip_path = os.path.join(self.base_path, f"{safe_torrent_name}.zip")
        else:
            zip_path = destination_path
        
        # Create a zip file with all content (even if it's just one file)
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for item in torrent_contents:
                    item_path = os.path.join(temp_download_dir, item)
                    if os.path.isfile(item_path):
                        zipf.write(item_path, os.path.basename(item_path))
                    else:  # It's a directory
                        for root, _, files in os.walk(item_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                zipf.write(file_path, os.path.relpath(file_path, temp_download_dir))
                                
            logging.info(f"Created zip archive at {zip_path}")
            
            # Update progress to show we're finalizing
            if progress_callback:
                progress_callback(100, status_message="Packaging files complete")
            
            # Clean up
            try:
                shutil.rmtree(temp_download_dir)
            except Exception as e:
                logging.error(f"Error removing temp directory: {e}")
            
            return zip_path
            
        except Exception as e:
            logging.error(f"Error creating zip file: {e}")
            raise