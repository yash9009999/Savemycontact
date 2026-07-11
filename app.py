import os
import re
import csv
import hashlib
import shutil
import psutil
from datetime import datetime
from functools import wraps
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from flask import Flask, request, render_template, redirect, url_for, send_file, flash, session as flask_session
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Flask Setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'supersecretkey123')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
app.config['CSV_ARCHIVE_FOLDER'] = 'csv_archive/'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp'}

# Admin credentials - change these!
# Password is hashed with SHA-256 for security
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASSWORD_HASH = hashlib.sha256(
    os.environ.get('ADMIN_PASS', 'admin@5001').encode()
).hexdigest()

# Database Setup
Base = declarative_base()
engine = create_engine('sqlite:///images.db', echo=False)
Session = sessionmaker(bind=engine)
db_session = Session()


class ImageRecord(Base):
    __tablename__ = 'images'
    id = Column(Integer, primary_key=True)
    original_name = Column(String, nullable=False)
    renamed_name = Column(String, nullable=False)
    extracted_text = Column(String, nullable=True)
    contacts = Column(String, nullable=True)


class CsvArchive(Base):
    __tablename__ = 'csv_archives'
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    base_name = Column(String, nullable=False)
    contact_count = Column(Integer, default=0)
    created_at = Column(String, nullable=False)


Base.metadata.create_all(engine)


def login_required(f):
    """Decorator to protect admin routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not flask_session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Country code rules based on number length (digits only, without country code)
# Map: number_of_digits -> country_code
COUNTRY_CODE_MAP = {
    10: '+91',   # India (10 digits)
    11: '+1',    # USA/Canada (11 digits including country code 1 + 10 digits)
    12: '+92',   # Pakistan (12 digits including country code)
}

# Known country code prefixes (digits after removing +)
KNOWN_COUNTRY_PREFIXES = {
    '1': '+1',      # USA/Canada
    '7': '+7',      # Russia
    '20': '+20',    # Egypt
    '27': '+27',    # South Africa
    '30': '+30',    # Greece
    '31': '+31',    # Netherlands
    '33': '+33',    # France
    '34': '+34',    # Spain
    '39': '+39',    # Italy
    '44': '+44',    # UK
    '49': '+49',    # Germany
    '55': '+55',    # Brazil
    '61': '+61',    # Australia
    '62': '+62',    # Indonesia
    '63': '+63',    # Philippines
    '64': '+64',    # New Zealand
    '65': '+65',    # Singapore
    '66': '+66',    # Thailand
    '81': '+81',    # Japan
    '82': '+82',    # South Korea
    '86': '+86',    # China
    '90': '+90',    # Turkey
    '91': '+91',    # India
    '92': '+92',    # Pakistan
    '93': '+93',    # Afghanistan
    '94': '+94',    # Sri Lanka
    '95': '+95',    # Myanmar
    '98': '+98',    # Iran
    '121': '+121',  # Custom/reserved
    '212': '+212',  # Morocco
    '234': '+234',  # Nigeria
    '254': '+254',  # Kenya
    '255': '+255',  # Tanzania
    '256': '+256',  # Uganda
    '263': '+263',  # Zimbabwe
    '353': '+353',  # Ireland
    '355': '+355',  # Albania
    '358': '+358',  # Finland
    '370': '+370',  # Lithuania
    '371': '+371',  # Latvia
    '372': '+372',  # Estonia
    '375': '+375',  # Belarus
    '380': '+380',  # Ukraine
    '420': '+420',  # Czech Republic
    '421': '+421',  # Slovakia
    '880': '+880',  # Bangladesh
    '886': '+886',  # Taiwan
    '960': '+960',  # Maldives
    '961': '+961',  # Lebanon
    '962': '+962',  # Jordan
    '963': '+963',  # Syria
    '964': '+964',  # Iraq
    '965': '+965',  # Kuwait
    '966': '+966',  # Saudi Arabia
    '967': '+967',  # Yemen
    '968': '+968',  # Oman
    '971': '+971',  # UAE
    '972': '+972',  # Israel
    '973': '+973',  # Bahrain
    '974': '+974',  # Qatar
    '975': '+975',  # Bhutan
    '976': '+976',  # Mongolia
    '977': '+977',  # Nepal
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def detect_country_code(phone_digits):
    """
    Detect and add the appropriate country code to a phone number.
    If the number already has a country code prefix, format it properly.
    Otherwise, assign based on digit length.
    """
    # Check if number already starts with a known country code
    for prefix_len in [3, 2, 1]:
        prefix = phone_digits[:prefix_len]
        if prefix in KNOWN_COUNTRY_PREFIXES:
            # Number already has country code, format it
            country_code = KNOWN_COUNTRY_PREFIXES[prefix]
            local_number = phone_digits[prefix_len:]
            if len(local_number) >= 7:  # Valid local number
                return f"{country_code} {local_number}"

    # No known prefix found - assign country code based on digit count
    num_digits = len(phone_digits)

    if num_digits == 10:
        # Most likely Indian number
        return f"+91 {phone_digits}"
    elif num_digits == 11:
        # Could be US/Canada (1 + 10 digits) or other
        if phone_digits.startswith('0'):
            # Local format with leading 0, likely Indian landline
            return f"+91 {phone_digits[1:]}"
        else:
            return f"+1 {phone_digits[1:]}"
    elif num_digits == 12:
        # Check first 2 digits for country code
        if phone_digits.startswith('91'):
            return f"+91 {phone_digits[2:]}"
        elif phone_digits.startswith('92'):
            return f"+92 {phone_digits[2:]}"
        elif phone_digits.startswith('44'):
            return f"+44 {phone_digits[2:]}"
        else:
            return f"+{phone_digits[:2]} {phone_digits[2:]}"
    elif num_digits == 13:
        # 3-digit country code + 10 digits
        if phone_digits.startswith('091'):
            return f"+91 {phone_digits[3:]}"
        else:
            return f"+{phone_digits[:3]} {phone_digits[3:]}"
    elif num_digits < 10 and num_digits >= 7:
        # Short number, assume local Indian
        return f"+91 {phone_digits}"
    else:
        # Unknown format, return as-is with +
        return f"+{phone_digits}"


def preprocess_image(image_path):
    """Preprocess image for better OCR accuracy."""
    image = Image.open(image_path)
    image = image.convert("L")  # Grayscale
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = ImageEnhance.Sharpness(image).enhance(2.0)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    return image


def extract_phone_numbers(text):
    """Extract phone numbers from OCR text and add country codes."""
    # Multiple patterns to catch different phone number formats
    patterns = [
        r'\+?\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}',
        r'\b\d{10,13}\b',
        r'\b\d{3,5}[-.\s]\d{3,5}[-.\s]\d{3,5}\b',
        r'\(\d{2,4}\)\s?\d{3,4}[-.\s]?\d{3,4}',
    ]

    found_numbers = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Extract only digits
            digits = re.sub(r'[^\d]', '', match)
            if 7 <= len(digits) <= 15:
                found_numbers.add(digits)

    # Add country codes and format
    formatted_numbers = []
    for digits in found_numbers:
        formatted = detect_country_code(digits)
        formatted_numbers.append(formatted)

    return formatted_numbers


def process_single_image(image_path):
    """Process an image: OCR extraction + phone number detection with country codes."""
    processed_image = preprocess_image(image_path)
    extracted_text = pytesseract.image_to_string(
        processed_image, config='--oem 3 --psm 6'
    )
    phone_numbers = extract_phone_numbers(extracted_text)
    return extracted_text.strip(), phone_numbers


def cleanup_uploads():
    """Remove uploaded files and DB image records (not the CSV)."""
    db_session.query(ImageRecord).delete()
    db_session.commit()

    upload_folder = app.config['UPLOAD_FOLDER']
    if os.path.exists(upload_folder):
        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)


@app.route('/')
def upload_form():
    return render_template('upload.html')


@app.route('/', methods=['POST'])
def upload_images():
    base_name = request.form.get('base_name', 'Contact').strip()
    if not base_name:
        base_name = 'Contact'

    files = request.files.getlist('images')
    if not files or files[0].filename == '':
        flash('No files selected.', 'error')
        return redirect(url_for('upload_form'))

    all_contacts = []

    for file in files[:100]:
        if not allowed_file(file.filename):
            continue

        original_name = secure_filename(file.filename)
        renamed_name = f"img_{original_name}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], renamed_name)
        file.save(file_path)

        extracted_text, phone_numbers = process_single_image(file_path)
        all_contacts.extend(phone_numbers)

        new_image = ImageRecord(
            original_name=original_name,
            renamed_name=renamed_name,
            extracted_text=extracted_text,
            contacts=", ".join(phone_numbers) if phone_numbers else "No contacts found"
        )
        db_session.add(new_image)
        db_session.commit()

    # Check if any contacts were found
    unique_contacts = list(set(all_contacts))
    if not unique_contacts:
        cleanup_uploads()
        flash('No phone numbers found in the uploaded images. Try clearer images.', 'error')
        return redirect(url_for('upload_form'))

    # Generate CSV
    csv_filename = 'extracted_contacts.csv'
    with open(csv_filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Phone"])
        for i, contact in enumerate(unique_contacts, start=1):
            writer.writerow([f"{base_name} {i}", contact])

    # Archive the CSV
    os.makedirs(app.config['CSV_ARCHIVE_FOLDER'], exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_name = f"{base_name}_{timestamp}.csv"
    archive_path = os.path.join(app.config['CSV_ARCHIVE_FOLDER'], archive_name)
    shutil.copy2(csv_filename, archive_path)

    archive_record = CsvArchive(
        filename=archive_name,
        base_name=base_name,
        contact_count=len(unique_contacts),
        created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    db_session.add(archive_record)
    db_session.commit()

    # Store CSV filename and results in session for download page
    flask_session['pending_csv'] = csv_filename
    flask_session['contact_count'] = len(unique_contacts)
    return redirect(url_for('download_page'))


@app.route('/download')
def download_page():
    csv_file = flask_session.get('pending_csv', None)
    if not csv_file or not os.path.exists(csv_file):
        flash('No CSV available. Please upload images first.', 'error')
        return redirect(url_for('upload_form'))
    contact_count = flask_session.get('contact_count', 0)
    images = db_session.query(ImageRecord).all()
    return render_template('download.html', csv_file=csv_file, contact_count=contact_count, images=images)


@app.route('/download/csv')
def download_csv():
    csv_file = flask_session.pop('pending_csv', None)
    flask_session.pop('contact_count', None)
    if csv_file and os.path.exists(csv_file):
        response = send_file(csv_file, as_attachment=True)
        # Clean up everything after sending
        @response.call_on_close
        def full_cleanup():
            cleanup_uploads()
            if os.path.exists(csv_file):
                os.remove(csv_file)
        return response
    flash('No CSV available. Please upload images first.', 'error')
    return redirect(url_for('upload_form'))


# ==================== ADMIN PANEL ====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        if username == ADMIN_USERNAME and password_hash == ADMIN_PASSWORD_HASH:
            flask_session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.', 'error')
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    flask_session.pop('admin_logged_in', None)
    return redirect(url_for('upload_form'))


@app.route('/admin')
@login_required
def admin_dashboard():
    archives = db_session.query(CsvArchive).order_by(CsvArchive.id.desc()).all()
    return render_template('admin_dashboard.html', archives=archives)


@app.route('/admin/download/<int:archive_id>')
@login_required
def admin_download_csv(archive_id):
    archive = db_session.query(CsvArchive).filter_by(id=archive_id).first()
    if archive:
        file_path = os.path.join(app.config['CSV_ARCHIVE_FOLDER'], archive.filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=archive.filename)
    return "File not found", 404


@app.route('/admin/delete/<int:archive_id>', methods=['POST'])
@login_required
def admin_delete_csv(archive_id):
    archive = db_session.query(CsvArchive).filter_by(id=archive_id).first()
    if archive:
        file_path = os.path.join(app.config['CSV_ARCHIVE_FOLDER'], archive.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        db_session.delete(archive)
        db_session.commit()
        flash('Archive deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/download-all')
@login_required
def admin_download_all():
    """Download all archived CSVs as a single merged CSV."""
    archives = db_session.query(CsvArchive).all()
    merged_path = 'all_contacts_merged.csv'
    with open(merged_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Phone", "Source File", "Date"])
        for archive in archives:
            file_path = os.path.join(app.config['CSV_ARCHIVE_FOLDER'], archive.filename)
            if os.path.exists(file_path):
                with open(file_path, 'r') as csvfile:
                    reader = csv.reader(csvfile)
                    next(reader, None)  # Skip header
                    for row in reader:
                        writer.writerow(row + [archive.filename, archive.created_at])
    if os.path.exists(merged_path):
        return send_file(merged_path, as_attachment=True, download_name='all_contacts_merged.csv')
    return "No archives found", 404


@app.route('/admin/stats')
@login_required
def admin_stats():
    """Return server stats as JSON for the admin dashboard."""
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()

    # Memory
    mem = psutil.virtual_memory()
    mem_total_gb = round(mem.total / (1024 ** 3), 2)
    mem_used_gb = round(mem.used / (1024 ** 3), 2)
    mem_percent = mem.percent

    # Disk
    disk = psutil.disk_usage('/')
    disk_total_gb = round(disk.total / (1024 ** 3), 2)
    disk_used_gb = round(disk.used / (1024 ** 3), 2)
    disk_free_gb = round(disk.free / (1024 ** 3), 2)
    disk_percent = disk.percent

    # Uptime
    import time
    uptime_seconds = int(time.time() - psutil.boot_time())
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    uptime_str = f"{days}d {hours}h {minutes}m"

    # Network
    net = psutil.net_io_counters()
    net_sent_mb = round(net.bytes_sent / (1024 ** 2), 1)
    net_recv_mb = round(net.bytes_recv / (1024 ** 2), 1)

    from flask import jsonify
    return jsonify({
        'cpu_percent': cpu_percent,
        'cpu_count': cpu_count,
        'mem_total_gb': mem_total_gb,
        'mem_used_gb': mem_used_gb,
        'mem_percent': mem_percent,
        'disk_total_gb': disk_total_gb,
        'disk_used_gb': disk_used_gb,
        'disk_free_gb': disk_free_gb,
        'disk_percent': disk_percent,
        'uptime': uptime_str,
        'net_sent_mb': net_sent_mb,
        'net_recv_mb': net_recv_mb,
    })


if __name__ == "__main__":
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CSV_ARCHIVE_FOLDER'], exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
