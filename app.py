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
        # ดึงรูปมาแสดง 100 รูปล่าสุด
        result = cloudinary.api.resources(type="upload", prefix="menu/", max_results=100)
        images = result.get('resources', [])
        # เรียงลำดับจากใหม่ไปเก่า (created_at)
        images.sort(key=lambda x: x['created_at'], reverse=True)
    except:
        images = []
    return render_template('index.html', images=images)

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
        # รับไฟล์แบบ List (หลายไฟล์)
        files = request.files.getlist('file')
        custom_name = request.form.get('name', '').strip()
        
        uploaded_count = 0
        
        # วนลูปทำทีละรูป
        for i, file in enumerate(files):
            if file:
                try:
                    # --- ตั้งชื่อรูป ---
                    if custom_name:
                        # ถ้าคนกรอกชื่อมา
                        if len(files) > 1:
                            # ถ้าอัปหลายไฟล์ ให้เติมเลขต่อท้าย เช่น "Coffee_1", "Coffee_2"
                            final_name = f"{custom_name}_{i+1}"
                        else:
                            final_name = custom_name
                    else:
                        # ถ้าไม่กรอกชื่อ -> ใช้ชื่อไฟล์เดิม (ตัด .jpg ออก)
                        final_name = os.path.splitext(file.filename)[0]

                    # --- บีบอัดรูป (Code เดิม) ---
                    img = Image.open(file)
                    if img.mode != 'RGB': img = img.convert('RGB')
                    if img.width > 2048 or img.height > 2048: img.thumbnail((2048, 2048))
                    
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=85)
                    img_byte_arr.seek(0)
                    
                    # อัปโหลด
                    cloudinary.uploader.upload(img_byte_arr, public_id=f"menu/{final_name}")
                    uploaded_count += 1
                    
                except Exception as e:
                    print(f"Error uploading {file.filename}: {e}")

        flash(f'✅ อัปโหลดเรียบร้อยทั้งหมด {uploaded_count} รูป!')
        return redirect(url_for('admin'))
            
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(debug=True)
