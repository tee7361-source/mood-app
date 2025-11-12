from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv

# โหลดค่าจาก .env
load_dotenv()

app = Flask(__name__)

# เชื่อมต่อ MongoDB
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)

# เลือก Database และ Collection
db = client['mood_tracker']  # ชื่อ Database
moods_collection = db['moods']  # ชื่อ Collection (เหมือน Table)

# หน้าแรก - แสดงฟอร์มและรายการบันทึก
@app.route('/')
def index():
    # ดึงข้อมูลทั้งหมดจาก MongoDB (เรียงจากใหม่ไปเก่า)
    moods = list(moods_collection.find().sort('created_at', -1))
    return render_template('index.html', moods=moods)

# บันทึกความรู้สึกใหม่
@app.route('/add', methods=['POST'])
def add_mood():
    # รับข้อมูลจากฟอร์ม
    mood_data = {
        'date': request.form['date'],
        'time': request.form['time'],
        'color': request.form['color'],
        'trigger': request.form['trigger'],
        'emotion': request.form['emotion'],
        'detail': request.form['detail'],
        'created_at': datetime.now(),
        'updated_at': None
    }
    
    # บันทึกลง MongoDB
    moods_collection.insert_one(mood_data)
    
    return redirect(url_for('index'))

# แสดงฟอร์มแก้ไข
@app.route('/edit/<mood_id>')
def edit_mood(mood_id):
    # ดึงข้อมูลทั้งหมด
    moods = list(moods_collection.find().sort('created_at', -1))
    
    # หารายการที่ต้องการแก้ไข
    mood_to_edit = moods_collection.find_one({'_id': ObjectId(mood_id)})
    
    if mood_to_edit is None:
        return redirect(url_for('index'))
    
    return render_template('index.html', moods=moods, edit_mood=mood_to_edit)

# อัพเดทรายการที่แก้ไข
@app.route('/update/<mood_id>', methods=['POST'])
def update_mood(mood_id):
    # ข้อมูลใหม่
    updated_data = {
        'date': request.form['date'],
        'time': request.form['time'],
        'color': request.form['color'],
        'trigger': request.form['trigger'],
        'emotion': request.form['emotion'],
        'detail': request.form['detail'],
        'updated_at': datetime.now()
    }
    
    # อัพเดทใน MongoDB
    moods_collection.update_one(
        {'_id': ObjectId(mood_id)},
        {'$set': updated_data}
    )
    
    return redirect(url_for('index'))

# ลบบันทึก
@app.route('/delete/<mood_id>')
def delete_mood(mood_id):
    moods_collection.delete_one({'_id': ObjectId(mood_id)})
    return redirect(url_for('index'))

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)