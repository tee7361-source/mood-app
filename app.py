from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import bcrypt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from itsdangerous import URLSafeTimedSerializer
from threading import Thread

# Import SendGrid แบบ Optional (ไม่ Error ถ้าไม่มี)
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    print("⚠️ SendGrid not installed, using Gmail SMTP")

# โหลดค่าจาก .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Email Configuration
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')  # เพิ่มบรรทัดนี้

# สร้าง Serializer สำหรับ Token
serializer = URLSafeTimedSerializer(app.secret_key)

# ตั้งค่า Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # หน้าที่ redirect ไปถ้ายังไม่ login
login_manager.login_message = 'กรุณาเข้าสู่ระบบก่อนใช้งาน'

# เชื่อมต่อ MongoDB
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)

# เลือก Database และ Collections
db = client['mood_tracker']
moods_collection = db['moods']
users_collection = db['users']  # Collection ใหม่สำหรับเก็บข้อมูลผู้ใช้

# สร้าง index สำหรับ username (ไม่ให้ซ้ำ)
users_collection.create_index('username', unique=True)

# ฟังก์ชันส่งอีเมลแบบ Async (Background Thread)
def send_async_email(app, msg_data):
    """ส่งอีเมลใน Background Thread"""
    with app.app_context():
        try:
            # ตรวจสอบว่ามี Email config หรือไม่
            if not MAIL_USERNAME or not MAIL_PASSWORD:
                print("❌ Email credentials not configured")
                return
            
            # ลองใช้ SendGrid ก่อน (ถ้ามี API Key และติดตั้งแล้ว)
            if SENDGRID_AVAILABLE and SENDGRID_API_KEY:
                try:
                    message = Mail(
                        from_email=MAIL_USERNAME,
                        to_emails=msg_data['to'],
                        subject=msg_data['subject'],
                        html_content=msg_data['html']
                    )
                    sg = SendGridAPIClient(SENDGRID_API_KEY)
                    response = sg.send(message)
                    print(f"✅ Email sent via SendGrid (status: {response.status_code})")
                    return
                except Exception as e:
                    print(f"⚠️ SendGrid failed, falling back to Gmail SMTP: {e}")
            
            # ใช้ Gmail SMTP
            msg = MIMEMultipart('alternative')
            msg['Subject'] = msg_data['subject']
            msg['From'] = MAIL_USERNAME
            msg['To'] = msg_data['to']
            
            part = MIMEText(msg_data['html'], 'html')
            msg.attach(part)
            
            with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as server:
                server.starttls()
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(msg)
            print("✅ Email sent via Gmail SMTP")
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            # ไม่ raise exception เพื่อไม่ให้ Thread crash

# ฟังก์ชันส่งอีเมล
def send_email(subject, recipient, html_content):
    """สร้างและส่งอีเมลแบบ Async"""
    msg_data = {
        'subject': subject,
        'to': recipient,
        'html': html_content
    }
    
    # ส่งอีเมลใน Background Thread
    Thread(target=send_async_email, args=(app, msg_data)).start()
    return True

# ฟังก์ชันส่งอีเมล
def send_reset_email(user_email, reset_url):
    """ส่งอีเมลรีเซ็ตรหัสผ่าน"""
    try:
        # สร้างข้อความอีเมล
        msg = MIMEMultipart('alternative')
        msg['Subject'] = '🔐 รีเซ็ตรหัสผ่าน - Mood Tracker'
        msg['From'] = MAIL_USERNAME
        msg['To'] = user_email
        
        # เนื้อหาอีเมล (HTML)
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
              <h1 style="color: #667eea; text-align: center;">📔 Mood Tracker</h1>
              <h2 style="color: #333;">รีเซ็ตรหัสผ่าน</h2>
              <p style="color: #666; line-height: 1.6;">
                คุณได้ขอรีเซ็ตรหัสผ่าน กรุณาคลิกปุ่มด้านล่างเพื่อตั้งรหัสผ่านใหม่:
              </p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" 
                   style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                          color: white; 
                          padding: 15px 30px; 
                          text-decoration: none; 
                          border-radius: 8px; 
                          font-weight: bold;
                          display: inline-block;">
                  🔓 รีเซ็ตรหัสผ่าน
                </a>
              </div>
              <p style="color: #999; font-size: 14px;">
                ลิงก์นี้จะหมดอายุภายใน <strong>1 ชั่วโมง</strong>
              </p>
              <p style="color: #999; font-size: 14px;">
                ถ้าคุณไม่ได้ขอรีเซ็ตรหัสผ่าน กรุณาเพิกเฉยอีเมลนี้
              </p>
              <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
              <p style="color: #999; font-size: 12px; text-align: center;">
                หรือคัดลอกลิงก์นี้:<br>
                <a href="{reset_url}" style="color: #667eea;">{reset_url}</a>
              </p>
            </div>
          </body>
        </html>
        """
        
        # แนบเนื้อหา HTML
        part = MIMEText(html, 'html')
        msg.attach(part)
        
        # เชื่อมต่อ Gmail SMTP
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()  # เข้ารหัสการเชื่อมต่อ
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# ฟังก์ชันส่งอีเมลยืนยัน
def send_verification_email(user_email, username, verification_url):
    """ส่งอีเมลยืนยันบัญชี"""
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
          <h1 style="color: #667eea; text-align: center;">📔 Mood Tracker</h1>
          <h2 style="color: #333;">ยินดีต้อนรับ {username}! 🎉</h2>
          <p style="color: #666; line-height: 1.6;">
            ขอบคุณที่สมัครสมาชิก! กรุณายืนยันอีเมลของคุณเพื่อเริ่มใช้งานระบบบันทึกความรู้สึก
          </p>
          <div style="text-align: center; margin: 30px 0;">
            <a href="{verification_url}" 
               style="background: linear-gradient(135deg, #51cf66 0%, #37b24d 100%); 
                      color: white; 
                      padding: 15px 30px; 
                      text-decoration: none; 
                      border-radius: 8px; 
                      font-weight: bold;
                      display: inline-block;">
              ✅ ยืนยันอีเมล
            </a>
          </div>
          <p style="color: #999; font-size: 14px;">
            ลิงก์นี้จะหมดอายุภายใน <strong>24 ชั่วโมง</strong>
          </p>
        </div>
      </body>
    </html>
    """
    
    return send_email('✅ ยืนยันอีเมล - Mood Tracker', user_email, html)

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
            'verified': False,  # ยังไม่ได้ยืนยันอีเมล
            'created_at': datetime.now(),
            'verified_at': None
        }
        
        try:
            result = users_collection.insert_one(user_data)
            user_id = str(result.inserted_id)
            
            # สร้าง Token สำหรับยืนยันอีเมล (หมดอายุ 24 ชั่วโมง)
            token = serializer.dumps(email, salt='email-verification')
            
            # สร้าง URL ยืนยันอีเมล
            verification_url = url_for('verify_email', token=token, _external=True)
            
            # ส่งอีเมลยืนยัน
            if send_verification_email(email, username, verification_url):
                flash('สมัครสมาชิกสำเร็จ! กรุณาตรวจสอบอีเมลเพื่อยืนยันบัญชี', 'success')
            else:
                flash('สมัครสมาชิกสำเร็จ แต่ไม่สามารถส่งอีเมลยืนยันได้ กรุณาติดต่อผู้ดูแลระบบ', 'error')
            
            return redirect(url_for('login'))
        except Exception as e:
            flash('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง', 'error')
            return render_template('register.html')
    
    return render_template('register.html')

# หน้าลืมรหัสผ่าน
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('กรุณากรอกอีเมล', 'error')
            return render_template('forgot_password.html')
        
        # หาผู้ใช้จากอีเมล
        user = users_collection.find_one({'email': email})
        
        if user:
            # สร้าง Token (หมดอายุ 1 ชั่วโมง)
            token = serializer.dumps(email, salt='password-reset')
            
            # สร้าง URL รีเซ็ตรหัสผ่าน
            reset_url = url_for('reset_password', token=token, _external=True)
            
            # ส่งอีเมล
            if send_reset_email(email, reset_url):
                flash('ส่งลิงก์รีเซ็ตรหัสผ่านไปยังอีเมลของคุณแล้ว กรุณาตรวจสอบอีเมล', 'success')
            else:
                flash('เกิดข้อผิดพลาดในการส่งอีเมล กรุณาลองใหม่อีกครั้ง', 'error')
        else:
            # ไม่เจออีเมล แต่ไม่บอกผู้ใช้ (ป้องกันการหาอีเมล)
            flash('ส่งลิงก์รีเซ็ตรหัสผ่านไปยังอีเมลของคุณแล้ว กรุณาตรวจสอบอีเมล', 'success')
        
        return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html')

# หน้ารีเซ็ตรหัสผ่าน
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    try:
        # ตรวจสอบ Token (หมดอายุภายใน 1 ชั่วโมง = 3600 วินาที)
        email = serializer.loads(token, salt='password-reset', max_age=3600)
    except:
        flash('ลิงก์รีเซ็ตรหัสผ่านหมดอายุหรือไม่ถูกต้อง กรุณาขอลิงก์ใหม่', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not password or not confirm_password:
            flash('กรุณากรอกรหัสผ่านให้ครบทุกช่อง', 'error')
            return render_template('reset_password.html', token=token)
        
        if len(password) < 6:
            flash('รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร', 'error')
            return render_template('reset_password.html', token=token)
        
        if password != confirm_password:
            flash('รหัสผ่านไม่ตรงกัน', 'error')
            return render_template('reset_password.html', token=token)
        
        # เข้ารหัสรหัสผ่านใหม่
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # อัพเดทรหัสผ่านใน Database
        result = users_collection.update_one(
            {'email': email},
            {'$set': {'password': hashed_password, 'password_reset_at': datetime.now()}}
        )
        
        if result.modified_count > 0:
            flash('รีเซ็ตรหัสผ่านสำเร็จ! กรุณาเข้าสู่ระบบด้วยรหัสผ่านใหม่', 'success')
            return redirect(url_for('login'))
        else:
            flash('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง', 'error')
            return render_template('reset_password.html', token=token)
    
    return render_template('reset_password.html', token=token)

# ยืนยันอีเมล
@app.route('/verify-email/<token>')
def verify_email(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    try:
        # ตรวจสอบ Token (หมดอายุภายใน 24 ชั่วโมง = 86400 วินาที)
        email = serializer.loads(token, salt='email-verification', max_age=86400)
    except:
        flash('ลิงก์ยืนยันอีเมลหมดอายุหรือไม่ถูกต้อง กรุณาขอลิงก์ใหม่', 'error')
        return redirect(url_for('resend_verification'))
    
    # อัพเดทสถานะยืนยันอีเมล
    result = users_collection.update_one(
        {'email': email, 'verified': False},
        {'$set': {'verified': True, 'verified_at': datetime.now()}}
    )
    
    if result.modified_count > 0:
        flash('ยืนยันอีเมลสำเร็จ! ตอนนี้คุณสามารถเข้าสู่ระบบได้แล้ว', 'success')
    else:
        # อาจยืนยันไปแล้ว
        user = users_collection.find_one({'email': email})
        if user and user.get('verified', False):
            flash('อีเมลนี้ได้รับการยืนยันแล้ว กรุณาเข้าสู่ระบบ', 'success')
        else:
            flash('ไม่พบบัญชีที่ตรงกับอีเมลนี้', 'error')
    
    return redirect(url_for('login'))

# ส่งอีเมลยืนยันใหม่
@app.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('กรุณากรอกอีเมล', 'error')
            return render_template('resend_verification.html')
        
        # หาผู้ใช้ที่ยังไม่ได้ยืนยันอีเมล
        user = users_collection.find_one({'email': email, 'verified': False})
        
        if user:
            # สร้าง Token ใหม่
            token = serializer.dumps(email, salt='email-verification')
            verification_url = url_for('verify_email', token=token, _external=True)
            
            # ส่งอีเมลยืนยันใหม่
            if send_verification_email(email, user['username'], verification_url):
                flash('ส่งอีเมลยืนยันใหม่เรียบร้อย กรุณาตรวจสอบอีเมลของคุณ', 'success')
            else:
                flash('เกิดข้อผิดพลาดในการส่งอีเมล กรุณาลองใหม่อีกครั้ง', 'error')
        else:
            # ไม่บอกว่าไม่มีอีเมล หรือยืนยันแล้ว (ป้องกันการหาอีเมล)
            flash('ส่งอีเมลยืนยันใหม่เรียบร้อย กรุณาตรวจสอบอีเมลของคุณ', 'success')
        
        return redirect(url_for('resend_verification'))
    
    return render_template('resend_verification.html')

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
            # ตรวจสอบว่ายืนยันอีเมลหรือยัง
            if not user_data.get('verified', False):
                flash('กรุณายืนยันอีเมลก่อนเข้าสู่ระบบ ตรวจสอบอีเมลของคุณ', 'error')
                return render_template('login.html', unverified_email=user_data.get('email'))
            
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
        'user_id': current_user.id,  # เพิ่ม user_id เพื่อแยกข้อมูลแต่ละคน
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
        'user_id': current_user.id  # ต้องเป็นของคนนี้เท่านั้น
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