from flask import Flask, render_template, request, redirect, url_for, session, flash
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
from PIL import Image
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mysecretkey')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '1234')

# ตั้งค่า Cloudinary
cloudinary.config(
    cloud_name = os.environ.get('CLOUD_NAME'),
    api_key = os.environ.get('CLOUD_API_KEY'),
    api_secret = os.environ.get('CLOUD_API_SECRET'),
    secure = True
)

@app.route('/')
def index():
    try:
        # ดึงรูปโซน "มีลายน้ำ"
        res_watermark = cloudinary.api.resources(type="upload", prefix="menu/watermarked/", max_results=100)
        img_watermark = res_watermark.get('resources', [])
        img_watermark.sort(key=lambda x: x['created_at'], reverse=True)

        # ดึงรูปโซน "ไม่มีลายน้ำ" (Clean)
        res_clean = cloudinary.api.resources(type="upload", prefix="menu/clean/", max_results=100)
        img_clean = res_clean.get('resources', [])
        img_clean.sort(key=lambda x: x['created_at'], reverse=True)
        
    except:
        img_watermark = []
        img_clean = []
        
    return render_template('index.html', wm_images=img_watermark, cl_images=img_clean)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('รหัสผ่านไม่ถูกต้อง!')
    return render_template('login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        files = request.files.getlist('file')
        custom_name = request.form.get('name', '').strip()
        upload_type = request.form.get('type') # รับค่าว่าเลือกโซนไหน
        
        uploaded_count = 0
        
        for i, file in enumerate(files):
            if file:
                try:
                    # ตั้งชื่อไฟล์
                    if custom_name:
                        final_name = f"{custom_name}_{i+1}" if len(files) > 1 else custom_name
                    else:
                        final_name = os.path.splitext(file.filename)[0]

                    # --- ขั้นตอนการย่อรูป (เพื่อไม่ให้ Server ล่ม) ---
                    img = Image.open(file)
                    
                    # แปลงเป็น RGB เสมอ
                    if img.mode != 'RGB': 
                        img = img.convert('RGB')
                    
                    # 1. ย่อแบบหยาบก่อน (Draft) เพื่อลดการกิน RAM ทันทีที่เปิดไฟล์
                    img.draft('RGB', (2048, 2048)) 
                    
                    # 2. ย่อจริงจังอีกทีไม่ให้เกิน 2048px (ชัดระดับ HD)
                    if img.width > 2048 or img.height > 2048: 
                        img.thumbnail((2048, 2048))

                    # --- เลือกโฟลเดอร์ปลายทาง (ไม่มีการวาดลายน้ำแล้ว) ---
                    if upload_type == 'watermarked':
                        folder = "menu/watermarked"
                    else:
                        folder = "menu/clean"

                    # เตรียมไฟล์ส่งขึ้น Cloud
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=85) # บีบอัดเหลือ 85%
                    img_byte_arr.seek(0)
                    
                    # Upload
                    cloudinary.uploader.upload(img_byte_arr, public_id=f"{folder}/{final_name}")
                    uploaded_count += 1
                    
                    # คืนหน่วยความจำ
                    img.close()

                except Exception as e:
                    print(f"Error uploading {file.filename}: {e}")

        if uploaded_count > 0:
            flash(f'✅ อัปโหลดเข้าโซน "{upload_type}" เรียบร้อย {uploaded_count} รูป!')
        
        return redirect(url_for('admin'))

    # ส่วนแสดงรายการรูปล่างสุด (สำหรับลบ)
    try:
        res_wm = cloudinary.api.resources(type="upload", prefix="menu/watermarked/", max_results=50)
        res_cl = cloudinary.api.resources(type="upload", prefix="menu/clean/", max_results=50)
        all_images = res_wm.get('resources', []) + res_cl.get('resources', [])
        all_images.sort(key=lambda x: x['created_at'], reverse=True)
    except:
        all_images = []
        
    return render_template('admin.html', images=all_images)

@app.route('/delete/<path:public_id>')
def delete_image(public_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        cloudinary.uploader.destroy(public_id)
        flash('🗑️ ลบรูปเรียบร้อยแล้ว')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {e}')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
