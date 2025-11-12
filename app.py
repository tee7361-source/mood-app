from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import json
import os

app = Flask(__name__)

# ไฟล์สำหรับเก็บข้อมูล
DATA_FILE = 'moods.json'

# ฟังก์ชันอ่านข้อมูล
def load_moods():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# ฟังก์ชันบันทึกข้อมูล
def save_moods(moods):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(moods, f, ensure_ascii=False, indent=2)

# หน้าแรก - แสดงฟอร์มและรายการบันทึก
@app.route('/')
def index():
    moods = load_moods()
    return render_template('index.html', moods=moods)

# บันทึกความรู้สึกใหม่
@app.route('/add', methods=['POST'])
def add_mood():
    # รับข้อมูลจากฟอร์ม
    mood_data = {
        'id': datetime.now().strftime('%Y%m%d%H%M%S'),
        'date': request.form['date'],
        'time': request.form['time'],
        'color': request.form['color'],
        'trigger': request.form['trigger'],
        'emotion': request.form['emotion'],
        'detail': request.form['detail'],
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # โหลดข้อมูลเก่า
    moods = load_moods()
    
    # เพิ่มข้อมูลใหม่
    moods.insert(0, mood_data)  # ใส่ไว้ด้านบนสุด
    
    # บันทึกลงไฟล์
    save_moods(moods)
    
    return redirect(url_for('index'))

# ลบบันทึก
@app.route('/delete/<mood_id>')
def delete_mood(mood_id):
    moods = load_moods()
    moods = [m for m in moods if m['id'] != mood_id]
    save_moods(moods)
    return redirect(url_for('index'))

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)