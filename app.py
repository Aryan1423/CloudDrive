from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
import os
from datetime import datetime, timedelta
from functools import wraps
from bin.modules.db_manager import DBManager
from bin.modules.file_manager import FileManager
from bin.modules.uploader import Uploader
from bin.modules.downloader import Downloader
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.formparser import parse_form_data

# Initialize managers
db = DBManager()
fm = FileManager()

# Create Flask app
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Replace with a secure key

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

@app.route("/download/<file_hash>")
@login_required
def download(file_hash):
    # Find file record by file hash; ensure the file belongs to the logged-in user
    user_id = session["user_id"]
    file_record = next((record for record in db.get_files(user_id=user_id) if record[2] == file_hash), None)
    if not file_record:
        flash("File not found")
        return redirect(url_for("index"))

    file_name = file_record[1]
    output_file = os.path.join(fm.output_path, file_name)
    if not os.path.isfile(output_file):
        downloader = Downloader(file_name)
        downloader.run()

    if not os.path.isfile(output_file):
        flash("Merged file not found after processing.")
        return redirect(url_for("index"))

    return send_from_directory(fm.output_path, file_name, as_attachment=True)

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
