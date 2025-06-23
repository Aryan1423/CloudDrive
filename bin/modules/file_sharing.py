import os
import uuid
import time
from datetime import datetime, timedelta
import logging
from bin.modules.db_manager import DBManager

class FileSharing:
    def __init__(self, db_manager):
        self.db = db_manager
        # Create shared_files table if it doesn't exist
        self._create_share_table()
        
    def _create_share_table(self):
        """Create the shared_files table if it doesn't exist"""
        conn = self.db._DBManager__conn
        cursor = self.db._DBManager__cursor
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shared_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT,
                share_id TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY(file_hash) REFERENCES files(hash)
            )
        """)
        conn.commit()
        
    def create_share_link(self, file_hash, expires_days=None):
        """Create a share link for a file"""
        # Generate a unique share ID
        share_id = str(uuid.uuid4())
        
        # Calculate expiration date if provided
        expires_at = None
        if expires_days:
            expires_at = datetime.now() + timedelta(days=int(expires_days))
            
        # Store in database
        conn = self.db._DBManager__conn
        cursor = self.db._DBManager__cursor
        
        cursor.execute(
            "INSERT INTO shared_files (file_hash, share_id, expires_at) VALUES (?, ?, ?)",
            (file_hash, share_id, expires_at)
        )
        conn.commit()
        
        return {
            "share_id": share_id,
            "expires_at": expires_at
        }
        
    def get_shared_file(self, share_id):
        """Get file info for a shared link"""
        cursor = self.db._DBManager__cursor
        
        # Join with files table to get file details
        cursor.execute("""
            SELECT f.file_name, f.hash, s.expires_at 
            FROM shared_files s
            JOIN files f ON s.file_hash = f.hash
            WHERE s.share_id = ?
        """, (share_id,))
        
        result = cursor.fetchone()
        if not result:
            return None
            
        file_name, file_hash, expires_at = result
        
        # Check if link is expired
        if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
            # Delete expired link
            self.delete_share_link(share_id)
            return None
            
        return {
            "file_name": file_name,
            "file_hash": file_hash
        }
        
    def get_file_shares(self, file_hash):
        """Get all share links for a file"""
        cursor = self.db._DBManager__cursor
        
        cursor.execute("""
            SELECT share_id, created_at, expires_at
            FROM shared_files
            WHERE file_hash = ?
        """, (file_hash,))
        
        shares = []
        for row in cursor.fetchall():
            share_id, created_at, expires_at = row
            
            # Check if expired
            is_expired = False
            if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
                is_expired = True
                
            shares.append({
                "share_id": share_id,
                "created_at": created_at,
                "expires_at": expires_at,
                "is_expired": is_expired
            })
            
        return shares
        
    def delete_share_link(self, share_id):
        """Delete a share link"""
        conn = self.db._DBManager__conn
        cursor = self.db._DBManager__cursor
        
        cursor.execute("DELETE FROM shared_files WHERE share_id = ?", (share_id,))
        conn.commit()