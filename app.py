from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
from PIL import Image
import io

app = Flask(__name__)
# ใช้ Config เดิมของคุณ
app.secret_key = os.environ.get('SECRET_KEY', 'mysecretkey')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '1234')

# ตั้งค่า Cloudinary (ใช้ Config เดิมของคุณ)
cloudinary.config(
    cloud_name = os.environ.get('CLOUD_NAME'),
    api_key = os.environ.get('CLOUD_API_KEY'),
    api_secret = os.environ.get('CLOUD_API_SECRET'),
    secure = True
)

# ==========================================
# 🏠 โซนหน้าบ้าน (โชว์เมนู)
# ==========================================
@app.route('/')
def index():
    try:
        # ดึงรูปโซน "มีลายน้ำ"
        res_watermark = cloudinary.api.resources(type="upload", prefix="menu/watermarked/", max_results=500, direction="desc")
        img_watermark = sorted(res_watermark.get('resources', []), key=lambda x: x['created_at'], reverse=True)

        # ดึงรูปโซน "ไม่มีลายน้ำ" (Clean)
        res_clean = cloudinary.api.resources(type="upload", prefix="menu/clean/", max_results=500, direction="desc")
        img_clean = sorted(res_clean.get('resources', []), key=lambda x: x['created_at'], reverse=True)
        
    except:
        img_watermark = []
        img_clean = []
        
    return render_template('index.html', wm_images=img_watermark, cl_images=img_clean)

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
        # 1. ดึงข้อมูลทั้ง 2 โฟลเดอร์ (Max 500 รูป)
        res_wm = cloudinary.api.resources(type="upload", prefix="menu/watermarked/", max_results=500)
        res_cl = cloudinary.api.resources(type="upload", prefix="menu/clean/", max_results=500)
        
        # 2. สร้าง Dictionary เพื่อจับคู่
        # Key = ชื่อไฟล์, Value = ข้อมูลครบชุด
        menu_items = {}

        # วนลูปโซนลายน้ำ
        for img in res_wm.get('resources', []):
            filename = img['public_id'].split('/')[-1]
            if filename not in menu_items:
                menu_items[filename] = {'name': filename, 'wm': None, 'cl': None, 'created_at': img['created_at']}
            menu_items[filename]['wm'] = img['secure_url']

        # วนลูปโซนต้นฉบับ
        for img in res_cl.get('resources', []):
            filename = img['public_id'].split('/')[-1]
            if filename not in menu_items:
                menu_items[filename] = {'name': filename, 'wm': None, 'cl': None, 'created_at': img['created_at']}
            menu_items[filename]['cl'] = img['secure_url']

        # 3. เรียงตามวันที่ล่าสุด
        sorted_items = sorted(menu_items.values(), key=lambda x: x['created_at'], reverse=True)

    except Exception as e:
        print(f"Error fetching images: {e}")
        sorted_items = []
        
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

    if file:
        try:
            # ตั้งชื่อไฟล์
            if custom_name:
                final_name = f"{custom_name}_{index}" if int(index) > 0 else custom_name
            else:
                final_name = os.path.splitext(file.filename)[0]

            # Process Image
            img = Image.open(file)
            if img.mode != 'RGB': img = img.convert('RGB')
            img.draft('RGB', (2048, 2048))
            if img.width > 2048 or img.height > 2048: 
                img.thumbnail((2048, 2048))

            folder = "menu/watermarked" if upload_type == 'watermarked' else "menu/clean"

            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            img_byte_arr.seek(0)
            
            cloudinary.uploader.upload(img_byte_arr, public_id=f"{folder}/{final_name}")
            img.close()
            
            return {'status': 'success', 'file': final_name}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500
            
    return {'status': 'error', 'message': 'No file'}, 400

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
        # เปลี่ยนชื่อในโซนลายน้ำ
        try:
            cloudinary.uploader.rename(f"menu/watermarked/{old_name}", f"menu/watermarked/{new_name}", overwrite=True)
        except: pass

        # เปลี่ยนชื่อในโซนต้นฉบับ
        try:
            cloudinary.uploader.rename(f"menu/clean/{old_name}", f"menu/clean/{new_name}", overwrite=True)
        except: pass

        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500

# --- API แทนที่รูป (Replace Sync) ---
@app.route('/replace_sync', methods=['POST'])
def replace_sync():
    if not session.get('logged_in'):
        return {'status': 'error', 'message': 'Unauthorized'}, 401

    file_wm = request.files.get('file_wm')
    file_cl = request.files.get('file_cl')
    target_name = request.form.get('target_name')

    if not target_name:
        return {'status': 'error', 'message': 'No name provided'}, 400

    try:
        # ทับลายน้ำ
        if file_wm:
            img = Image.open(file_wm)
            if img.mode != 'RGB': img = img.convert('RGB')
            img.thumbnail((2048, 2048))
            byte_arr = io.BytesIO()
            img.save(byte_arr, format='JPEG', quality=85)
            byte_arr.seek(0)
            cloudinary.uploader.upload(byte_arr, public_id=f"menu/watermarked/{target_name}", overwrite=True, invalidate=True)

        # ทับต้นฉบับ
        if file_cl:
            img = Image.open(file_cl)
            if img.mode != 'RGB': img = img.convert('RGB')
            img.thumbnail((2048, 2048))
            byte_arr = io.BytesIO()
            img.save(byte_arr, format='JPEG', quality=85)
            byte_arr.seek(0)
            cloudinary.uploader.upload(byte_arr, public_id=f"menu/clean/{target_name}", overwrite=True, invalidate=True)

        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500

# --- ลบรูป (ลบเดี่ยว - ใช้ชื่อเต็ม path) ---
@app.route('/delete/<path:public_id>')
def delete_image(public_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        cloudinary.uploader.destroy(public_id, invalidate=True)
        flash('🗑️ ลบรูปเรียบร้อยแล้ว')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {e}')
        
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
