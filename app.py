from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import bcrypt

# โหลดค่าจาก .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# ตั้งค่า Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'กรุณาเข้าสู่ระบบก่อนใช้งาน'

# เชื่อมต่อ MongoDB
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)

# เลือก Database และ Collections
db = client['mood_tracker']
moods_collection = db['moods']
users_collection = db['users']

# สร้าง index สำหรับ username (ไม่ให้ซ้ำ)
users_collection.create_index('username', unique=True)

# คลาส User สำหรับ Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data.get('email', '')

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

# หน้าแรก - redirect ไปหน้า login
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# หน้า Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # ตรวจสอบข้อมูล
        if not username or not email or not password:
            flash('กรุณากรอกข้อมูลให้ครบทุกช่อง', 'error')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('รหัสผ่านไม่ตรงกัน', 'error')
            return render_template('register.html')
        
        # เช็คว่า username ซ้ำไหม
        if users_collection.find_one({'username': username}):
            flash('ชื่อผู้ใช้นี้ถูกใช้งานแล้ว', 'error')
            return render_template('register.html')
        
        # เช็คว่า email ซ้ำไหม
        if users_collection.find_one({'email': email}):
            flash('อีเมลนี้ถูกใช้งานแล้ว', 'error')
            return render_template('register.html')
        
        # เข้ารหัสรหัสผ่าน
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # สร้างผู้ใช้ใหม่
        user_data = {
            'username': username,
            'email': email,
            'password': hashed_password,
            'created_at': datetime.now()
        }
        
        try:
            users_collection.insert_one(user_data)
            flash('สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง', 'error')
            return render_template('register.html')
    
    return render_template('register.html')

# หน้า Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('กรุณากรอกชื่อผู้ใช้และรหัสผ่าน', 'error')
            return render_template('login.html')
        
        # หาผู้ใช้ใน Database
        user_data = users_collection.find_one({'username': username})
        
        if user_data and bcrypt.checkpw(password.encode('utf-8'), user_data['password']):
            # Login สำเร็จ
            user = User(user_data)
            login_user(user, remember=True)
            flash(f'ยินดีต้อนรับ {username}!', 'success')
            
            # ไปหน้าที่ต้องการก่อนหน้า หรือ dashboard
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('dashboard'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

# ออกจากระบบ
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ออกจากระบบเรียบร้อย', 'success')
    return redirect(url_for('login'))

# หน้า Dashboard (ต้อง Login ก่อน)
@app.route('/dashboard')
@login_required
def dashboard():
    # ดึงเฉพาะข้อมูลของผู้ใช้คนนี้
    moods = list(moods_collection.find({'user_id': current_user.id}).sort('created_at', -1))
    return render_template('dashboard.html', moods=moods)

# บันทึกความรู้สึกใหม่
@app.route('/add', methods=['POST'])
@login_required
def add_mood():
    mood_data = {
        'user_id': current_user.id,
        'username': current_user.username,
        'date': request.form['date'],
        'time': request.form['time'],
        'color': request.form['color'],
        'trigger': request.form['trigger'],
        'emotion': request.form['emotion'],
        'detail': request.form['detail'],
        'created_at': datetime.now(),
        'updated_at': None
    }
    
    moods_collection.insert_one(mood_data)
    flash('บันทึกความรู้สึกสำเร็จ!', 'success')
    return redirect(url_for('dashboard'))

# แสดงฟอร์มแก้ไข
@app.route('/edit/<mood_id>')
@login_required
def edit_mood(mood_id):
    # ดึงข้อมูลของผู้ใช้คนนี้
    moods = list(moods_collection.find({'user_id': current_user.id}).sort('created_at', -1))
    
    # หารายการที่ต้องการแก้ไข และเช็คว่าเป็นของผู้ใช้คนนี้
    mood_to_edit = moods_collection.find_one({
        '_id': ObjectId(mood_id),
        'user_id': current_user.id
    })
    
    if mood_to_edit is None:
        flash('ไม่พบรายการที่ต้องการแก้ไข', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('dashboard.html', moods=moods, edit_mood=mood_to_edit)

# อัพเดทรายการที่แก้ไข
@app.route('/update/<mood_id>', methods=['POST'])
@login_required
def update_mood(mood_id):
    # เช็คว่ารายการนี้เป็นของผู้ใช้คนนี้
    mood = moods_collection.find_one({
        '_id': ObjectId(mood_id),
        'user_id': current_user.id
    })
    
    if not mood:
        flash('ไม่สามารถแก้ไขรายการนี้ได้', 'error')
        return redirect(url_for('dashboard'))
    
    updated_data = {
        'date': request.form['date'],
        'time': request.form['time'],
        'color': request.form['color'],
        'trigger': request.form['trigger'],
        'emotion': request.form['emotion'],
        'detail': request.form['detail'],
        'updated_at': datetime.now()
    }
    
    moods_collection.update_one(
        {'_id': ObjectId(mood_id), 'user_id': current_user.id},
        {'$set': updated_data}
    )
    
    flash('แก้ไขบันทึกสำเร็จ!', 'success')
    return redirect(url_for('dashboard'))

# ลบบันทึก
@app.route('/delete/<mood_id>')
@login_required
def delete_mood(mood_id):
    # ลบเฉพาะถ้าเป็นของผู้ใช้คนนี้
    result = moods_collection.delete_one({
        '_id': ObjectId(mood_id),
        'user_id': current_user.id
    })
    
    if result.deleted_count > 0:
        flash('ลบบันทึกสำเร็จ!', 'success')
    else:
        flash('ไม่สามารถลบรายการนี้ได้', 'error')
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)