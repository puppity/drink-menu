from flask import Flask, render_template, request, redirect, url_for, session, flash
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
from PIL import Image, ImageDraw, ImageFont # เพิ่ม ImageDraw, ImageFont
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

# ฟังก์ชันช่วยวาดลายน้ำ
def add_watermark(image, text="Cha Phranakhon"):
    draw = ImageDraw.Draw(image)
    w, h = image.size
    
    # พยายามโหลดฟอนต์ (ถ้าไม่มีจะใช้ฟอนต์ Default)
    try:
        # บน Render อาจไม่มี Arial ให้ใช้ Default หรืออัปโหลดไฟล์ .ttf ใส่โปรเจกต์
        font = ImageFont.load_default() 
        # หมายเหตุ: ฟอนต์ Default ปรับขนาดไม่ได้ในบางเวอร์ชัน 
        # ถ้าอยากได้สวยๆ ต้องหาไฟล์ font.ttf มาใส่ในโฟลเดอร์
    except:
        font = ImageFont.load_default()

    # คำนวณตำแหน่ง (มุมขวาล่าง)
    # เนื่องจากใช้ font default การคำนวณอาจไม่เป๊ะมากนัก
    x = w - 150 
    y = h - 50

    # วาดพื้นหลังดำจางๆ รองข้อความ
    draw.rectangle([(x-10, y-10), (w, h)], fill=(0,0,0,128))
    # เขียนข้อความสีขาว
    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    
    return image

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
                    # ตั้งชื่อ
                    if custom_name:
                        final_name = f"{custom_name}_{i+1}" if len(files) > 1 else custom_name
                    else:
                        final_name = os.path.splitext(file.filename)[0]

                    # เปิดรูป
                    img = Image.open(file)
                    if img.mode != 'RGB': img = img.convert('RGB')
                    
                    # ย่อรูป
                    if img.width > 2048 or img.height > 2048: 
                        img.thumbnail((2048, 2048))

                    # --- แยกตรรกะตามประเภทที่เลือก ---
                    if upload_type == 'watermarked':
                        folder = "menu/watermarked"
                        # แปะลายน้ำ
                        img = add_watermark(img)
                    else:
                        folder = "menu/clean"
                        # ไม่แปะลายน้ำ (Original)

                    # Save ลง RAM
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=85)
                    img_byte_arr.seek(0)
                    
                    # Upload
                    cloudinary.uploader.upload(img_byte_arr, public_id=f"{folder}/{final_name}")
                    uploaded_count += 1
                except Exception as e:
                    print(f"Error: {e}")

        if uploaded_count > 0:
            flash(f'✅ อัปโหลดเข้าโซน "{upload_type}" เรียบร้อย {uploaded_count} รูป!')
        
        return redirect(url_for('admin'))

    # ดึงข้อมูลมาโชว์ในตารางลบ (รวมทั้ง 2 แบบ)
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
