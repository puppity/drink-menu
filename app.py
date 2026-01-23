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
    
    # --- ส่วนรับรูปภาพ (เหมือนเดิม) ---
    if request.method == 'POST':
        files = request.files.getlist('file')
        custom_name = request.form.get('name', '').strip()
        upload_type = request.form.get('type')
        
        uploaded_count = 0
        
        for i, file in enumerate(files):
            if file:
                try:
                    if custom_name:
                        final_name = f"{custom_name}_{i+1}" if len(files) > 1 else custom_name
                    else:
                        final_name = os.path.splitext(file.filename)[0]

                    img = Image.open(file)
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img.draft('RGB', (2048, 2048)) 
                    if img.width > 2048 or img.height > 2048: 
                        img.thumbnail((2048, 2048))

                    if upload_type == 'watermarked':
                        folder = "menu/watermarked"
                    else:
                        folder = "menu/clean"

                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=85)
                    img_byte_arr.seek(0)
                    
                    cloudinary.uploader.upload(img_byte_arr, public_id=f"{folder}/{final_name}")
                    uploaded_count += 1
                    img.close()
                except Exception as e:
                    print(f"Error uploading {file.filename}: {e}")

        if uploaded_count > 0:
            flash(f'✅ อัปโหลดเข้าโซน "{upload_type}" เรียบร้อย {uploaded_count} รูป!')
        
        return redirect(url_for('admin'))

    # --- 🔥 ส่วนที่แก้ไข: ดึงรูปมาแสดง (เพิ่มจำนวน + เรียงใหม่) ---
    try:
        # 1. เพิ่ม max_results เป็น 500 (Cloudinary ให้สูงสุด 500 ต่อครั้ง)
        # 2. ใส่ direction="desc" เพื่อบอกให้เอา "รูปล่าสุด" ขึ้นก่อนเสมอ
        
        res_wm = cloudinary.api.resources(
            type="upload", 
            prefix="menu/watermarked/", 
            max_results=500, 
            direction="desc" 
        )
        
        res_cl = cloudinary.api.resources(
            type="upload", 
            prefix="menu/clean/", 
            max_results=500, 
            direction="desc"
        )
        
        # รวมรายการ
        all_images = res_wm.get('resources', []) + res_cl.get('resources', [])
        
        # เรียงใน Python อีกรอบเพื่อความชัวร์ (ใหม่สุดอยู่บนสุด)
        all_images.sort(key=lambda x: x['created_at'], reverse=True)
        
    except Exception as e:
        print(f"Error fetching images: {e}")
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

