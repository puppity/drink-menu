from flask import Flask, render_template, request, redirect, url_for, session, flash
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mysecretkey')

# ตั้งค่ารหัสผ่านสำหรับเข้าหน้า Admin (เดี๋ยวไปตั้งใน Render)
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
    # ดึงรูปทั้งหมดจาก Cloudinary ในโฟลเดอร์ 'menu'
    try:
        result = cloudinary.api.resources(
            type="upload", 
            prefix="menu/", 
            max_results=100
        )
        images = result.get('resources', [])
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
        file = request.files['file']
        name = request.form['name']
        if file and name:
            # อัปโหลดรูปขึ้น Cloudinary ใส่โฟลเดอร์ menu
            cloudinary.uploader.upload(file, public_id=f"menu/{name}")
            flash('อัปโหลดเรียบร้อย!')
            return redirect(url_for('admin'))
            
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(debug=True)
