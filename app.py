from flask import Flask, render_template, send_from_directory
import os

app = Flask(__name__)
# กำหนดโฟลเดอร์รูปภาพ
IMAGE_FOLDER = 'static/images'

@app.route('/')
def index():
    # อ่านชื่อไฟล์รูปภาพทั้งหมดในโฟลเดอร์
    images = []
    if os.path.exists(IMAGE_FOLDER):
        images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    return render_template('index.html', images=images)

if __name__ == '__main__':
    app.run(debug=True)