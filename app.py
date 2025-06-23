from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, jsonify, Response, stream_with_context, send_file
import os
from datetime import datetime, timedelta
from functools import wraps
from bin.modules.db_manager import DBManager
from bin.modules.file_manager import FileManager
from bin.modules.uploader import Uploader
from bin.modules.downloader import Downloader
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.formparser import parse_form_data
import uuid
import threading
from bin.modules.url_downloader import URLDownloader
from bin.modules.file_sharing import FileSharing
import re
import time
from werkzeug.datastructures import Headers
import io
import mimetypes

# Initialize managers
db = DBManager()
fm = FileManager()
file_sharing = FileSharing(db)

# Create Flask app
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Replace with a secure key

# Dictionary to track URL download tasks
url_download_tasks = {}

# Dictionary to track large file prep jobs
large_file_jobs = {}

# Ensure output directory exists (for merged files)
if not os.path.exists(fm.output_path):
    os.mkdir(fm.output_path)

# ---- Authentication helpers ----
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users = db.get_user_by_username(username)
        if users and users[0][2] == password:
            session["user_id"] = users[0][0]
            session["username"] = users[0][1]
            flash("Logged in successfully.")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        if not username or not password or not confirm:
            flash("Please fill in all fields.")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Passwords do not match.")
            return redirect(url_for("register"))
        try:
            db.add_user(username, password)
            flash("Registration successful. Please log in.")
            return redirect(url_for("login"))
        except Exception as e:
            flash(str(e))
            return redirect(url_for("register"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))

# ---- Main routes ----

@app.route("/")
@login_required
def index():
    user_id = session["user_id"]
    files = db.get_files(user_id=user_id)
    return render_template("index.html", files=files)

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        # Use streaming form parser to avoid buffering the entire file into memory
        environ = request.environ
        stream, form, files = parse_form_data(environ)
        if "file" not in files:
            flash("No file part")
            return redirect(request.url)
        file_storage = files["file"]
        if file_storage.filename == "":
            flash("No selected file")
            return redirect(request.url)
        
        upload_path = os.path.join(fm.base_path, file_storage.filename)
        # Stream the file to disk in small chunks
        with open(upload_path, "wb") as f:
            for chunk in iter(lambda: file_storage.stream.read(4096), b""):
                f.write(chunk)
        
        # Process the upload as before
        uploader = Uploader(upload_path)
        try:
            uploader.run(user_id=session["user_id"])
            flash("File uploaded and processed successfully.")
        except Exception as e:
            flash(str(e))
        return redirect(url_for("index"))
    return render_template("upload.html")

@app.route("/upload_from_url", methods=["POST"])
@login_required
def upload_from_url():
    url = request.form.get("url")
    if not url:
        flash("No URL provided")
        return redirect(url_for("upload"))
    
    # Generate task ID for tracking progress
    task_id = str(uuid.uuid4())
    url_download_tasks[task_id] = {
        "progress": 0,
        "status": "Starting download...",
        "complete": False,
        "success": False
    }
    
    # Start download in background thread
    thread = threading.Thread(
        target=process_url_download,
        args=(url, task_id, session["user_id"])
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"task_id": task_id})

@app.route('/active_tasks')
@login_required
def active_tasks():
    """Return all active tasks for the current user"""
    user_id = session["user_id"]
    user_tasks = {}
    
    # Check for expired/stalled tasks
    current_time = time.time()
    tasks_to_cancel = []
    
    for task_id, task in url_download_tasks.items():
        # Only include tasks for the current user
        if task.get('user_id') == user_id:
            # Deep copy the task to avoid modifying the original
            task_copy = task.copy()
            
            # Check if task is stalled (no progress updates for 5 minutes)
            if not task['complete'] and 'last_update' in task:
                time_since_update = current_time - task['last_update']
                # If no updates for 5 minutes, mark for cancellation
                if time_since_update > 300:  # 5 minutes in seconds
                    tasks_to_cancel.append(task_id)
            
            user_tasks[task_id] = task_copy
    
    # Cancel stalled tasks
    for task_id in tasks_to_cancel:
        _cancel_task(task_id)
        if task_id in user_tasks:
            user_tasks[task_id]['status'] = 'Cancelled (stalled)'
            user_tasks[task_id]['complete'] = True
            user_tasks[task_id]['success'] = False
    
    return jsonify({"tasks": user_tasks})

@app.route('/cancel_task/<task_id>', methods=['POST'])
@login_required
def cancel_task(task_id):
    """Cancel a running task"""
    user_id = session["user_id"]
    
    # Ensure task belongs to current user
    if task_id in url_download_tasks and url_download_tasks[task_id].get('user_id') == user_id:
        success = _cancel_task(task_id)
        return jsonify({"success": success})
        
    return jsonify({"success": False, "error": "Task not found or unauthorized"})

def _cancel_task(task_id):
    """Internal function to cancel a task"""
    if task_id not in url_download_tasks:
        return False
        
    task = url_download_tasks[task_id]
    
    # Cancel based on task type
    if 'controller' in task and task['controller']:
        try:
            task['controller'].abort()
        except:
            pass
            
    # Mark task as cancelled
    task['status'] = 'Cancelled'
    task['complete'] = True
    task['success'] = False
    
    return True

@app.route('/clear_completed_tasks', methods=['POST'])
@login_required
def clear_completed_tasks():
    """Remove completed tasks from the list"""
    user_id = session["user_id"]
    completed_tasks = []
    
    # Find completed tasks for this user
    for task_id, task in url_download_tasks.items():
        if task.get('user_id') == user_id and task.get('complete'):
            completed_tasks.append(task_id)
    
    # Remove the tasks
    for task_id in completed_tasks:
        url_download_tasks.pop(task_id, None)
        
    return jsonify({"success": True, "cleared": len(completed_tasks)})

def process_url_download(url, task_id, user_id):
    try:
        # Initialize task with user_id and timestamps
        url_download_tasks[task_id]["user_id"] = user_id
        url_download_tasks[task_id]["start_time"] = time.time()
        url_download_tasks[task_id]["last_update"] = time.time()
        url_download_tasks[task_id]["status"] = "Downloading from URL..."
        
        # Create an abort controller to allow cancellation
        controller = None
        try:
            from requests import Session
            from requests.adapters import HTTPAdapter
            session = Session()
            session.mount('http://', HTTPAdapter(max_retries=3))
            session.mount('https://', HTTPAdapter(max_retries=3))
            url_download_tasks[task_id]["controller"] = controller
        except ImportError:
            # Fall back if we can't create a controller
            pass
        
        # Download the file
        downloader = URLDownloader(fm.base_path)
        
        def update_progress(progress, status_message=None):
            url_download_tasks[task_id]["progress"] = progress
            url_download_tasks[task_id]["last_update"] = time.time()
            if status_message:
                url_download_tasks[task_id]["status"] = status_message
        
        local_path = downloader.download_from_url(url, progress_callback=update_progress)
        
        # Extract filename from downloaded file
        filename = os.path.basename(local_path)
        url_download_tasks[task_id]["fileName"] = filename
        
        # Update task status
        url_download_tasks[task_id]["status"] = "Processing file and uploading to Telegram..."
        url_download_tasks[task_id]["progress"] = 0
        url_download_tasks[task_id]["last_update"] = time.time()
        
        # Process the downloaded file
        uploader = Uploader(local_path)
        uploader.run(user_id=user_id)
        
        # Complete task
        url_download_tasks[task_id]["status"] = "Complete"
        url_download_tasks[task_id]["progress"] = 100
        url_download_tasks[task_id]["complete"] = True
        url_download_tasks[task_id]["success"] = True
        url_download_tasks[task_id]["last_update"] = time.time()
        
        # Schedule task cleanup after 30 minutes
        def cleanup_task():
            if task_id in url_download_tasks:
                del url_download_tasks[task_id]
                
        scheduler.add_job(
            func=cleanup_task,
            trigger="date",
            run_date=datetime.now() + timedelta(minutes=30)
        )
        
    except Exception as e:
        app.logger.error(f"Error processing URL download: {str(e)}")
        url_download_tasks[task_id]["status"] = f"Error: {str(e)}"
        url_download_tasks[task_id]["complete"] = True
        url_download_tasks[task_id]["success"] = False
        url_download_tasks[task_id]["last_update"] = time.time()

@app.route("/task/progress/<task_id>")
@login_required
def task_progress(task_id):
    if task_id in url_download_tasks:
        return jsonify(url_download_tasks[task_id])
    return jsonify({
        "progress": 0,
        "status": "Task not found",
        "complete": True,
        "success": False,
        "error": "Task ID not found"
    })

@app.route("/download/<file_hash>")
@login_required
def download(file_hash):
    # Get file info from database
    user_id = session["user_id"]
    file_record = next((record for record in db.get_files(user_id=user_id) if record[2] == file_hash), None)
    if not file_record:
        flash("File not found.")
        return redirect(url_for("index"))
        
    file_name = file_record[1]
    
    # Check if the file needs to be assembled from chunks
    output_file = os.path.join(fm.output_path, file_name)
    if not os.path.isfile(output_file):
        downloader = Downloader(file_name)
        output_file = downloader.run()
        if not output_file:
            flash("Failed to assemble file from chunks.")
            return redirect(url_for("index"))
    
    # Use streaming with proper error handling
    return send_file_with_retry(output_file, file_name)

def send_file_with_retry(file_path, filename):
    """Stream a file with better timeout handling and retry support"""
    
    file_size = os.path.getsize(file_path)
    
    # Set a smaller chunk size for more frequent progress updates
    chunk_size = 2 * 1024 * 1024  # 2MB chunks
    
    # Set custom headers optimized for download managers
    headers = Headers()
    headers.add('Content-Disposition', f'attachment; filename="{filename}"')
    headers.add('Content-Length', str(file_size))
    headers.add('Content-Type', 'application/octet-stream')  # Force binary file type
    headers.add('Accept-Ranges', 'bytes')
    headers.add('Cache-Control', 'no-cache, no-store, must-revalidate')
    headers.add('Pragma', 'no-cache')
    headers.add('Expires', '0')
    headers.add('Connection', 'keep-alive')
    
    # Handle range requests for resume capability
    range_header = request.headers.get('Range', None)
    
    if range_header:
        try:
            byte1, byte2 = 0, None
            match = re.search(r'(\d+)-(\d*)', range_header)
            groups = match.groups()
            
            if groups[0]:
                byte1 = int(groups[0])
            if groups[1] and groups[1].strip():
                byte2 = int(groups[1])
                
            if byte2 is None:
                byte2 = file_size - 1
                
            length = byte2 - byte1 + 1
            
            headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
            headers.add('Content-Length', str(length))
            
            resp = Response(
                stream_with_context(generate_file_chunks(file_path, byte1, byte2, chunk_size)),
                status=206,
                headers=headers
            )
            return resp
        except Exception as e:
            app.logger.error(f"Error processing range request: {e}")
            # Fall back to full file
    
    resp = Response(
        stream_with_context(generate_file_chunks(file_path, 0, file_size - 1, chunk_size)),
        headers=headers
    )
    return resp

def generate_file_chunks(file_path, byte1=0, byte2=None, chunk_size=2*1024*1024):
    """Generator that yields file chunks with keep-alive signaling"""
    with open(file_path, 'rb') as fp:
        fp.seek(byte1)
        remaining = byte2 - byte1 + 1
        
        while remaining > 0:
            bytes_to_read = min(chunk_size, remaining)
            data = fp.read(bytes_to_read)
            
            if not data:
                break
                
            yield data
            remaining -= len(data)
            
            # Add a small delay to prevent CPU overutilization
            time.sleep(0.01)

@app.route("/delete/<file_hash>", methods=["POST"])
@login_required
def delete_file(file_hash):
    user_id = session["user_id"]
    file_record = next((record for record in db.get_files(user_id=user_id) if record[2] == file_hash), None)
    if not file_record:
        flash("File not found")
        return redirect(url_for("index"))

    file_name = file_record[1]
    output_file = os.path.join(fm.output_path, file_name)
    if os.path.isfile(output_file):
        try:
            os.remove(output_file)
            app.logger.info(f"Deleted merged file: {output_file}")
        except Exception as e:
            app.logger.error(f"Error deleting merged file: {e}")

    for directory in [fm.base_path, fm.loaded_chunks, fm.split_chunks]:
        if os.path.exists(directory):
            for f in os.listdir(directory):
                if f.startswith(file_hash):
                    file_path = os.path.join(directory, f)
                    try:
                        os.remove(file_path)
                        app.logger.info(f"Deleted chunk file: {file_path}")
                    except Exception as e:
                        app.logger.error(f"Error deleting chunk file {file_path}: {e}")

    try:
        db.delete_file(file_hash)
        flash("File deleted successfully.")
    except Exception as e:
        flash(str(e))
    return redirect(url_for("index"))

@app.route("/share/<file_hash>", methods=["POST"])
@login_required
def create_share(file_hash):
    """Create a public share link for a file"""
    # Get file info for filename
    file_info = next((record for record in db.get_files(user_id=session["user_id"]) if record[2] == file_hash), None)
    if not file_info:
        return jsonify({"error": "File not found"}), 404
        
    file_name = file_info[1]
    
    # Get expiration time (in days)
    expires_days = request.form.get("expires_days")
    
    # Create share link
    share = file_sharing.create_share_link(file_hash, expires_days)
    
    # Generate just one universal URL - using the ultra_raw_download endpoint
    # which works best for both browsers and download managers
    universal_url = url_for('ultra_raw_download', share_id=share["share_id"], filename=file_name, _external=True)
    
    return jsonify({
        "share_id": share["share_id"],
        "universal_url": universal_url,
        "expires_at": share["expires_at"]
    })

@app.route("/s/<share_id>")
@app.route("/s/<share_id>/<filename>")  # Add optional filename path
def shared_download(share_id, filename=None):
    """Public download link - no authentication required"""
    # Check if dl=1 parameter or download manager request
    force_download = request.args.get('dl') == '1' or 'downloadmanager' in request.headers.get('User-Agent', '').lower()
    
    # Get file info from share ID
    file_info = file_sharing.get_shared_file(share_id)
    if not file_info:
        if force_download:
            return Response("Link expired or invalid", status=410)
        flash("This download link is invalid or has expired.")
        return redirect(url_for("login"))
        
    file_hash = file_info["file_hash"]
    file_name = file_info["file_name"]
    
    # Check if file exists in output directory
    output_file = os.path.join(fm.output_path, file_name)
    if not os.path.isfile(output_file):
        downloader = Downloader(file_name)
        output_file = downloader.run()
        
    if not os.path.isfile(output_file):
        if force_download:
            return Response("File unavailable", status=404)
        flash("The requested file could not be assembled.")
        return redirect(url_for("login"))
    
    # Always use optimized streaming for shared links
    return send_file_with_retry(output_file, file_name)

@app.route("/file_shares/<file_hash>")
@login_required
def file_shares(file_hash):
    """Get existing share links for a file"""
    # Verify file belongs to user
    user_id = session["user_id"]
    file_record = next((record for record in db.get_files(user_id=user_id) if record[2] == file_hash), None)
    if not file_record:
        return jsonify({"error": "File not found"}), 404
        
    shares = file_sharing.get_file_shares(file_hash)
    
    # Add full URLs to shares
    for share in shares:
        if not share["is_expired"]:
            share["url"] = url_for('shared_download', share_id=share["share_id"], _external=True)
            
    return jsonify({"shares": shares})
    
@app.route("/revoke_share/<share_id>", methods=["POST"])
@login_required
def revoke_share(share_id):
    """Revoke a share link"""
    file_sharing.delete_share_link(share_id)
    return jsonify({"success": True})

@app.route("/prepare_download/<file_hash>")
@login_required
def prepare_download(file_hash):
    """Start preparing a large file download in the background"""
    user_id = session["user_id"]
    file_record = next((record for record in db.get_files(user_id=user_id) if record[2] == file_hash), None)
    
    if not file_record:
        return jsonify({"error": "File not found"})
        
    file_name = file_record[1]
    job_id = str(uuid.uuid4())
    
    # Start background job for assembly if needed
    output_file = os.path.join(fm.output_path, file_name)
    if not os.path.isfile(output_file):
        large_file_jobs[job_id] = {
            "status": "preparing",
            "progress": 0,
            "file_hash": file_hash,
            "file_name": file_name,
            "start_time": time.time()
        }
        
        # Start background thread to assemble file
        thread = threading.Thread(target=assemble_file, args=(job_id, file_name))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "preparing",
            "job_id": job_id,
            "message": "File is being assembled. Check status for updates."
        })
    else:
        # File already exists
        return jsonify({
            "status": "ready",
            "download_url": url_for('download', file_hash=file_hash)
        })

def assemble_file(job_id, file_name):
    """Background function to assemble a file from chunks"""
    try:
        downloader = Downloader(file_name)
        output_file = downloader.run()
        
        if output_file:
            large_file_jobs[job_id]["status"] = "ready"
            large_file_jobs[job_id]["output_file"] = output_file
        else:
            large_file_jobs[job_id]["status"] = "failed"
            large_file_jobs[job_id]["error"] = "Failed to assemble file"
    except Exception as e:
        large_file_jobs[job_id]["status"] = "failed"
        large_file_jobs[job_id]["error"] = str(e)

@app.route("/check_download/<job_id>")
@login_required
def check_download(job_id):
    """Check status of a large file preparation job"""
    if job_id not in large_file_jobs:
        return jsonify({"error": "Job not found"})
        
    job = large_file_jobs[job_id]
    
    if job["status"] == "ready":
        file_hash = job["file_hash"]
        # Generate download URL when ready
        return jsonify({
            "status": "ready",
            "download_url": url_for('download', file_hash=file_hash)
        })
    
    return jsonify(job)

@app.route("/direct/<share_id>")
def direct_binary_download(share_id):
    """Direct binary download endpoint for download managers - no HTML, only binary data"""
    # Get file info from share ID
    file_info = file_sharing.get_shared_file(share_id)
    if not file_info:
        # Return binary-compatible error response
        resp = Response(b"Link expired or invalid", status=410)
        resp.headers.add('Content-Type', 'application/octet-stream')
        return resp
        
    file_hash = file_info["file_hash"]
    file_name = file_info["file_name"]
    
    # Check if file exists in output directory
    output_file = os.path.join(fm.output_path, file_name)
    if not os.path.isfile(output_file):
        downloader = Downloader(file_name)
        output_file = downloader.run()
        
    if not os.path.isfile(output_file):
        # Return binary-compatible error response
        resp = Response(b"File unavailable", status=404)
        resp.headers.add('Content-Type', 'application/octet-stream')
        return resp
    
    # Send pure binary response with simplified headers
    file_size = os.path.getsize(output_file)
    chunk_size = 2 * 1024 * 1024  # 2MB chunks
    
    headers = Headers()
    headers.add('Content-Disposition', f'attachment; filename="{file_name}"')
    headers.add('Content-Length', str(file_size))
    headers.add('Content-Type', 'application/octet-stream')
    headers.add('Accept-Ranges', 'bytes')
    
    # Handle range requests for resume capability
    range_header = request.headers.get('Range', None)
    
    if range_header:
        try:
            byte1, byte2 = 0, None
            match = re.search(r'(\d+)-(\d*)', range_header)
            groups = match.groups()
            
            if groups[0]:
                byte1 = int(groups[0])
            if groups[1] and groups[1].strip():
                byte2 = int(groups[1])
                
            if byte2 is None:
                byte2 = file_size - 1
                
            length = byte2 - byte1 + 1
            
            headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
            headers.add('Content-Length', str(length))
            
            resp = Response(
                stream_with_context(pure_binary_chunks(output_file, byte1, byte2, chunk_size)),
                status=206,
                headers=headers
            )
            return resp
        except Exception as e:
            app.logger.error(f"Error processing range request: {e}")
    
    resp = Response(
        stream_with_context(pure_binary_chunks(output_file, 0, file_size - 1, chunk_size)),
        headers=headers
    )
    return resp

def pure_binary_chunks(file_path, byte1=0, byte2=None, chunk_size=2*1024*1024):
    """Generator that yields file chunks without any conditionals or error handling"""
    with open(file_path, 'rb') as fp:
        fp.seek(byte1)
        remaining = byte2 - byte1 + 1
        
        while remaining > 0:
            bytes_to_read = min(chunk_size, remaining)
            data = fp.read(bytes_to_read)
            
            if not data:
                break
                
            yield data
            remaining -= len(data)

@app.route("/raw/<share_id>/<filename>")
def raw_binary_download(share_id, filename):
    """Completely raw binary download with no HTML possibility"""
    # Get file info from share ID without any redirects
    file_info = file_sharing.get_shared_file(share_id)
    if not file_info:
        return app.response_class(
            response=b"Link expired",
            status=410,
            mimetype='application/octet-stream'
        )
        
    file_hash = file_info["file_hash"]
    file_name = file_info["file_name"]
    
    # Check if file exists in output directory
    output_file = os.path.join(fm.output_path, file_name)
    if not os.path.isfile(output_file):
        downloader = Downloader(file_name)
        output_file = downloader.run()
        
    if not os.path.isfile(output_file):
        return app.response_class(
            response=b"File unavailable",
            status=404,
            mimetype='application/octet-stream'
        )
    
    # Use Flask's send_file with forced download and binary type
    return send_file(
        output_file,
        as_attachment=True,
        download_name=file_name,
        mimetype='application/octet-stream',
        # Force these headers to ensure binary download
        headers={
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': f'attachment; filename="{file_name}"',
        }
    )

@app.route("/bin/<share_id>/<filename>")
def ultra_raw_download(share_id, filename):
    """Ultra-raw binary download that bypasses Flask's response handling"""
    # Get file info without any Flask redirects or templates
    file_info = file_sharing.get_shared_file(share_id)
    if not file_info:
        return b"Link expired", 410
        
    file_name = file_info["file_name"]
    
    # Check if file exists in output directory
    output_file = os.path.join(fm.output_path, file_name)
    if not os.path.isfile(output_file):
        downloader = Downloader(file_name)
        output_file = downloader.run()
        
    if not os.path.isfile(output_file):
        return b"File unavailable", 404
    
    # Get file size
    file_size = os.path.getsize(output_file)
    
    # Setup basic headers
    headers = {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Content-Length': str(file_size),
        'Accept-Ranges': 'bytes'
    }
    
    # Handle range requests (for resume)
    range_header = request.headers.get('Range', None)
    status_code = 200
    
    start_byte = 0
    end_byte = file_size - 1
    
    if range_header:
        try:
            # Parse range header
            match = re.search(r'(\d+)-(\d*)', range_header)
            groups = match.groups()
            
            if groups[0]:
                start_byte = int(groups[0])
            if groups[1] and groups[1].strip():
                end_byte = min(int(groups[1]), file_size - 1)
            
            # If this is a range request, use 206 Partial Content
            status_code = 206
            headers['Content-Range'] = f'bytes {start_byte}-{end_byte}/{file_size}'
            headers['Content-Length'] = str(end_byte - start_byte + 1)
        except Exception as e:
            app.logger.error(f"Range parsing error: {e}")
            # Continue with full file if range parsing fails
    
    def generate():
        with open(output_file, 'rb') as f:
            f.seek(start_byte)
            bytes_remaining = end_byte - start_byte + 1
            while bytes_remaining > 0:
                # Read in smaller chunks to avoid memory issues
                chunk_size = min(4 * 1024 * 1024, bytes_remaining)  # 4MB chunks
                data = f.read(chunk_size)
                if not data:
                    break
                bytes_remaining -= len(data)
                yield data
    
    return app.response_class(
        generate(),
        status=status_code,
        headers=headers,
        direct_passthrough=True  # Important! Don't buffer the response
    )

def cleanup_old_files():
    now = datetime.now()
    one_day_ago = now - timedelta(days=1)
    directories = [fm.base_path, fm.loaded_chunks, fm.output_path]
    for directory in directories:
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    modification_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if modification_time < one_day_ago:
                        try:
                            os.remove(file_path)
                            app.logger.info(f"Deleted old file: {file_path}")
                        except Exception as e:
                            app.logger.error(f"Error deleting file {file_path}: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_old_files, trigger="interval", hours=24)
scheduler.start()

if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0",port=port,debug=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
