from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
from PIL import Image
import io
import logging
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# ตั้งค่า Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security Config - ไม่มี default values
if not os.environ.get('SECRET_KEY'):
    raise ValueError("SECRET_KEY environment variable is required")
if not os.environ.get('ADMIN_PASSWORD'):
    raise ValueError("ADMIN_PASSWORD environment variable is required")

app.secret_key = os.environ.get('SECRET_KEY')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

# File Upload Validation
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

# Cache สำหรับเก็บข้อมูลรูปภาพ
image_cache = {'data': None, 'timestamp': None}
CACHE_DURATION = timedelta(minutes=5)

# ตั้งค่า Cloudinary - ตรวจสอบ required variables
# ในโหมด development จะข้ามการตรวจสอบถ้าไม่มีค่า
if os.environ.get('CLOUD_NAME') and os.environ.get('CLOUD_API_KEY') and os.environ.get('CLOUD_API_SECRET'):
    cloudinary.config(
        cloud_name = os.environ.get('CLOUD_NAME'),
        api_key = os.environ.get('CLOUD_API_KEY'),
        api_secret = os.environ.get('CLOUD_API_SECRET'),
        secure = True
    )
    logger.info("Cloudinary configured successfully")
else:
    logger.warning("Cloudinary credentials not found - running in demo mode")

# Helper Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_file_size(file):
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size <= MAX_FILE_SIZE

def get_cached_images():
    """ดึงข้อมูลรูปจาก cache หรือ Cloudinary"""
    global image_cache
    now = datetime.now()
    
    # ตรวจสอบ cache
    if image_cache['data'] and image_cache['timestamp']:
        if now - image_cache['timestamp'] < CACHE_DURATION:
            logger.info("Using cached image data")
            return image_cache['data']
    
    # ดึงข้อมูลใหม่
    try:
        res_wm = cloudinary.api.resources(type="upload", prefix="menu/watermarked/", max_results=500)
        res_cl = cloudinary.api.resources(type="upload", prefix="menu/clean/", max_results=500)
        res_pm = cloudinary.api.resources(type="upload", prefix="menu/premium/", max_results=500)
        
        data = {
            'watermarked': res_wm.get('resources', []),
            'clean': res_cl.get('resources', []),
            'premium': res_pm.get('resources', [])
        }
        
        # อัปเดต cache
        image_cache['data'] = data
        image_cache['timestamp'] = now
        logger.info("Updated image cache")
        
        return data
    except cloudinary.exceptions.Error as e:
        logger.error(f"Cloudinary API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching images: {e}")
        raise

def clear_cache():
    """ล้าง cache เมื่อมีการเปลี่ยนแปลงข้อมูล"""
    global image_cache
    image_cache['data'] = None
    image_cache['timestamp'] = None
    logger.info("Cache cleared")

# ==========================================
# 🏠 โซนหน้าบ้าน (โชว์เมนู)
# ==========================================
@app.route('/')
def index():
    try:
        data = get_cached_images()
        
        # ดึงรูปโซน "มีลายน้ำ"
        img_watermark = sorted(data['watermarked'], key=lambda x: x['created_at'], reverse=True)
        
        # ดึงรูปโซน "ไม่มีลายน้ำ" (Clean)
        img_clean = sorted(data['clean'], key=lambda x: x['created_at'], reverse=True)
        
        # ดึงรูปโซน "พรีเมี่ยม"
        img_premium = sorted(data['premium'], key=lambda x: x['created_at'], reverse=True)
        
    except cloudinary.exceptions.Error as e:
        logger.error(f"Cloudinary error in index: {e}")
        img_watermark = []
        img_clean = []
        img_premium = []
        flash('เกิดข้อผิดพลาดในการโหลดรูปภาพ', 'error')
    except Exception as e:
        logger.error(f"Unexpected error in index: {e}")
        img_watermark = []
        img_clean = []
        img_premium = []
        flash('เกิดข้อผิดพลาดที่ไม่คาดคิด', 'error')
        
    return render_template('index.html', wm_images=img_watermark, cl_images=img_clean, pm_images=img_premium)

# ==========================================
# 🔐 โซน Login
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('รหัสผ่านไม่ถูกต้อง!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

# ==========================================
# ⚙️ โซน Admin (ระบบซิงค์คู่)
# ==========================================
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # --- ดึงรูปมาจับคู่ (Sync Logic) ---
    try:
        data = get_cached_images()
        
        # 1. ดึงข้อมูลทั้ง 3 โฟลเดอร์
        res_wm = data['watermarked']
        res_cl = data['clean']
        res_pm = data['premium']
        
        # 2. สร้าง Dictionary เพื่อจับคู่
        # Key = ชื่อไฟล์, Value = ข้อมูลครบชุด
        menu_items = {}

        # วนลูปโซนลายน้ำ
        for img in res_wm:
            filename = img['public_id'].split('/')[-1]
            if filename not in menu_items:
                menu_items[filename] = {'name': filename, 'wm': None, 'cl': None, 'pm': None, 'created_at': img['created_at']}
            menu_items[filename]['wm'] = img['secure_url']

        # วนลูปโซนต้นฉบับ
        for img in res_cl:
            filename = img['public_id'].split('/')[-1]
            if filename not in menu_items:
                menu_items[filename] = {'name': filename, 'wm': None, 'cl': None, 'pm': None, 'created_at': img['created_at']}
            menu_items[filename]['cl'] = img['secure_url']

        # วนลูปโซนพรีเมี่ยม
        for img in res_pm:
            filename = img['public_id'].split('/')[-1]
            if filename not in menu_items:
                menu_items[filename] = {'name': filename, 'wm': None, 'cl': None, 'pm': None, 'created_at': img['created_at']}
            menu_items[filename]['pm'] = img['secure_url']

        # 3. เรียงตามวันที่ล่าสุด
        sorted_items = sorted(menu_items.values(), key=lambda x: x['created_at'], reverse=True)

    except cloudinary.exceptions.Error as e:
        logger.error(f"Cloudinary error in admin: {e}")
        sorted_items = []
        flash('เกิดข้อผิดพลาดในการโหลดข้อมูล', 'error')
    except Exception as e:
        logger.error(f"Unexpected error in admin: {e}")
        sorted_items = []
        flash('เกิดข้อผิดพลาดที่ไม่คาดคิด', 'error')
        
    return render_template('admin.html', items=sorted_items)

# --- API อัปโหลดรูป (รับจาก Queue) ---
@app.route('/upload_api', methods=['POST'])
def upload_api():
    if not session.get('logged_in'):
        return {'status': 'error', 'message': 'Unauthorized'}, 401
    
    file = request.files.get('file')
    custom_name = request.form.get('name', '').strip()
    upload_type = request.form.get('type')
    index = request.form.get('index', '0')

    if not file:
        return {'status': 'error', 'message': 'No file'}, 400
    
    # Validate file
    if not allowed_file(file.filename):
        return {'status': 'error', 'message': 'ประเภทไฟล์ไม่ถูกต้อง (รองรับเฉพาะ jpg, png, gif, webp)'}, 400
    
    if not validate_file_size(file):
        return {'status': 'error', 'message': f'ไฟล์ใหญ่เกินไป (สูงสุด {MAX_FILE_SIZE // (1024*1024)}MB)'}, 400

    try:
        # ตั้งชื่อไฟล์
        if custom_name:
            final_name = f"{custom_name}_{index}" if int(index) > 0 else custom_name
        else:
            final_name = os.path.splitext(file.filename)[0]
        
        # Sanitize filename
        final_name = "".join(c for c in final_name if c.isalnum() or c in (' ', '-', '_', 'ก-๙')).strip()

        # Process Image with proper resource management
        with Image.open(file) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.draft('RGB', (2048, 2048))
            if img.width > 2048 or img.height > 2048:
                img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)

            # เลือกโฟลเดอร์ตาม type
            if upload_type == 'watermarked':
                folder = "menu/watermarked"
            elif upload_type == 'premium':
                folder = "menu/premium"
            else:
                folder = "menu/clean"

            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
            img_byte_arr.seek(0)
            
            cloudinary.uploader.upload(img_byte_arr, public_id=f"{folder}/{final_name}")
        
        # ล้าง cache
        clear_cache()
        logger.info(f"Uploaded {final_name} to {folder}")
        
        return {'status': 'success', 'file': final_name}

    except cloudinary.exceptions.Error as e:
        logger.error(f"Cloudinary upload error: {e}")
        return {'status': 'error', 'message': f'เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}'}, 500
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return {'status': 'error', 'message': str(e)}, 500

# --- API เปลี่ยนชื่อแบบแพ็คคู่ (Sync Rename) ---
@app.route('/rename_sync', methods=['POST'])
def rename_sync():
    if not session.get('logged_in'):
        return {'status': 'error', 'message': 'Unauthorized'}, 401
    
    old_name = request.form.get('old_name')
    new_name = request.form.get('new_name', '').strip()

    if not old_name or not new_name:
        return {'status': 'error', 'message': 'ข้อมูลไม่ครบ'}, 400

    try:
        errors = []
        
        # เปลี่ยนชื่อในโซนลายน้ำ
        try:
            cloudinary.uploader.rename(f"menu/watermarked/{old_name}", f"menu/watermarked/{new_name}", overwrite=True)
        except cloudinary.exceptions.Error as e:
            logger.warning(f"Failed to rename watermarked/{old_name}: {e}")
            errors.append(f"watermarked: {str(e)}")

        # เปลี่ยนชื่อในโซนต้นฉบับ
        try:
            cloudinary.uploader.rename(f"menu/clean/{old_name}", f"menu/clean/{new_name}", overwrite=True)
        except cloudinary.exceptions.Error as e:
            logger.warning(f"Failed to rename clean/{old_name}: {e}")
            errors.append(f"clean: {str(e)}")
        
        # เปลี่ยนชื่อในโซนพรีเมี่ยม
        try:
            cloudinary.uploader.rename(f"menu/premium/{old_name}", f"menu/premium/{new_name}", overwrite=True)
        except cloudinary.exceptions.Error as e:
            logger.warning(f"Failed to rename premium/{old_name}: {e}")
            errors.append(f"premium: {str(e)}")

        # ล้าง cache
        clear_cache()
        
        if errors:
            return {'status': 'partial', 'message': 'เปลี่ยนชื่อบางส่วนสำเร็จ', 'errors': errors}
        
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"Rename error: {e}")
        return {'status': 'error', 'message': str(e)}, 500

# --- API แทนที่รูป (Replace Sync) ---
@app.route('/replace_sync', methods=['POST'])
def replace_sync():
    if not session.get('logged_in'):
        return {'status': 'error', 'message': 'Unauthorized'}, 401

    file_wm = request.files.get('file_wm')
    file_cl = request.files.get('file_cl')
    file_pm = request.files.get('file_pm')
    target_name = request.form.get('target_name')

    if not target_name:
        return {'status': 'error', 'message': 'No name provided'}, 400

    try:
        # ทับลายน้ำ
        if file_wm:
            with Image.open(file_wm) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                byte_arr = io.BytesIO()
                img.save(byte_arr, format='JPEG', quality=85, optimize=True)
                byte_arr.seek(0)
                cloudinary.uploader.upload(byte_arr, public_id=f"menu/watermarked/{target_name}", overwrite=True, invalidate=True)

        # ทับต้นฉบับ
        if file_cl:
            with Image.open(file_cl) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                byte_arr = io.BytesIO()
                img.save(byte_arr, format='JPEG', quality=85, optimize=True)
                byte_arr.seek(0)
                cloudinary.uploader.upload(byte_arr, public_id=f"menu/clean/{target_name}", overwrite=True, invalidate=True)
        
        # ทับพรีเมี่ยม
        if file_pm:
            with Image.open(file_pm) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                byte_arr = io.BytesIO()
                img.save(byte_arr, format='JPEG', quality=85, optimize=True)
                byte_arr.seek(0)
                cloudinary.uploader.upload(byte_arr, public_id=f"menu/premium/{target_name}", overwrite=True, invalidate=True)

        # ล้าง cache
        clear_cache()
        logger.info(f"Replaced images for {target_name}")
        
        return {'status': 'success'}
    except cloudinary.exceptions.Error as e:
        logger.error(f"Cloudinary replace error: {e}")
        return {'status': 'error', 'message': str(e)}, 500
    except Exception as e:
        logger.error(f"Replace error: {e}")
        return {'status': 'error', 'message': str(e)}, 500

# --- ลบรูป (ลบเดี่ยว - ใช้ชื่อเต็ม path) ---
@app.route('/delete/<path:public_id>')
def delete_image(public_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        cloudinary.uploader.destroy(public_id, invalidate=True)
        clear_cache()
        flash('🗑️ ลบรูปเรียบร้อยแล้ว')
        logger.info(f"Deleted image: {public_id}")
    except cloudinary.exceptions.Error as e:
        logger.error(f"Cloudinary delete error: {e}")
        flash(f'เกิดข้อผิดพลาด: {e}', 'error')
    except Exception as e:
        logger.error(f"Delete error: {e}")
        flash(f'เกิดข้อผิดพลาด: {e}', 'error')
        
    return redirect(url_for('admin'))

@app.route('/delete_sync/<string:filename>')
def delete_sync(filename):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        errors = []
        
        # 1. ลบโซนลายน้ำ
        try:
            cloudinary.uploader.destroy(f"menu/watermarked/{filename}", invalidate=True)
        except cloudinary.exceptions.Error as e:
            logger.warning(f"Failed to delete watermarked/{filename}: {e}")
            errors.append("watermarked")
        
        # 2. ลบโซนต้นฉบับ
        try:
            cloudinary.uploader.destroy(f"menu/clean/{filename}", invalidate=True)
        except cloudinary.exceptions.Error as e:
            logger.warning(f"Failed to delete clean/{filename}: {e}")
            errors.append("clean")
        
        # 3. ลบโซนพรีเมี่ยม
        try:
            cloudinary.uploader.destroy(f"menu/premium/{filename}", invalidate=True)
        except cloudinary.exceptions.Error as e:
            logger.warning(f"Failed to delete premium/{filename}: {e}")
            errors.append("premium")
        
        # ล้าง cache
        clear_cache()
        
        if errors:
            flash(f'🗑️ ลบเมนู "{filename}" บางส่วน (ไม่พบใน: {", ".join(errors)})')
        else:
            flash(f'🗑️ ลบเมนู "{filename}" ออกจากระบบเรียบร้อยแล้ว')
        
    except Exception as e:
        logger.error(f"Error deleting {filename}: {e}")
        flash(f'เกิดข้อผิดพลาด: {e}', 'error')
        
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)

