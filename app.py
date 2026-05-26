from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from datetime import datetime
import qrcode
import os
from zoneinfo import ZoneInfo
import pandas as pd
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageDraw, ImageFont
import zipfile

app = Flask(__name__)

# SAUGUMO KONFIGŪRACIJA
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'labai_slapta_fraze_kuri_pakeisk_2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

LT_TIMEZONE = ZoneInfo("Europe/Vilnius")

# ================== MODELIAI ==================
class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    license_number = db.Column(db.String(50))
    certificate_number = db.Column(db.String(50))
    email = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(LT_TIMEZONE))

class ScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    scanned_at = db.Column(db.DateTime, default=lambda: datetime.now(LT_TIMEZONE))

class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

with app.app_context():
    db.create_all()
    
    if not AdminUser.query.filter_by(username="admin").first():
        admin = AdminUser(
            username="admin",
            password_hash=generate_password_hash("admin123")
        )
        db.session.add(admin)
        db.session.commit()

# ================== PAGALBINĖS FUNKCIJOS ==================
def is_admin():
    return session.get('admin') == True

def generate_qr_with_name(person):
    base_url = request.host_url.rstrip('/')
    url = f"{base_url}/checkin/{person.id}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    width, height = qr_img.size
    new_height = height + 70
    combined = Image.new('RGB', (width, new_height), color='white')
    combined.paste(qr_img, (0, 0))
    
    draw = ImageDraw.Draw(combined)
    
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
        except:
            font = ImageFont.load_default()
    
    full_name = f"{person.first_name} {person.last_name}"
    text_width = draw.textlength(full_name, font=font)
    text_x = (width - text_width) // 2
    text_y = height + 20
    
    draw.text((text_x, text_y), full_name, fill="black", font=font)
    
    os.makedirs("static/qrcodes", exist_ok=True)
    qr_path = f"static/qrcodes/{person.id}.png"
    combined.save(qr_path)
    return qr_path

# ================== VIENO QR ATSISIUNTIMAS ==================
@app.route('/download_qr/<int:person_id>')
def download_qr(person_id):
    if not is_admin():
        flash('Tik administratorius gali atsisiųsti QR!', 'danger')
        return redirect(url_for('index'))
    
    person = Person.query.get_or_404(person_id)
    qr_path = f"static/qrcodes/{person.id}.png"
    
    if not os.path.exists(qr_path):
        flash('QR kodas dar nesugeneruotas!', 'danger')
        return redirect(url_for('index'))
    
    filename = f"{person.first_name}_{person.last_name}.png".replace(" ", "_")
    return send_file(qr_path, as_attachment=True, download_name=filename)

# ================== VISŲ QR ATSISIUNTIMAS KAIP ZIP ==================
@app.route('/download_all_qr', methods=['POST'])
def download_all_qr():
    if not is_admin():
        flash('Tik administratorius gali atsisiųsti!', 'danger')
        return redirect(url_for('index'))

    person_ids = request.form.getlist('person_ids')
    if not person_ids:
        flash('Nepasirinktas nė vienas žmogus!', 'danger')
        return redirect(url_for('index'))

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for pid_str in person_ids:
            try:
                person = Person.query.get(int(pid_str))
                if not person:
                    continue
                
                qr_path = f"static/qrcodes/{person.id}.png"
                if not os.path.exists(qr_path):
                    generate_qr_with_name(person)
                
                if os.path.exists(qr_path):
                    filename = f"{person.first_name}_{person.last_name}.png".replace(" ", "_")
                    zf.write(qr_path, filename)
            except:
                pass

    memory_file.seek(0)
    return send_file(memory_file, 
                     mimetype='application/zip',
                     as_attachment=True, 
                     download_name=f'QR_kodai_{datetime.now().strftime("%Y-%m-%d_%H-%M")}.zip')

# ================== LOGIN ==================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        admin = AdminUser.query.filter_by(username=username).first()
        
        if admin and check_password_hash(admin.password_hash, password):
            session['admin'] = True
            flash('Sėkmingai prisijungėte kaip administratorius', 'success')
            return redirect(url_for('index'))
        else:
            flash('Neteisingi prisijungimo duomenys', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('Atsijungėte sėkmingai', 'info')
    return redirect(url_for('index'))

# ================== PAGRINDINIS PUSLAPIS ==================
@app.route('/')
def index():
    if is_admin():
        people = Person.query.order_by(Person.created_at.desc()).all()
    else:
        people = []
    return render_template('index.html', people=people, is_admin=is_admin())

# ================== PRIDĖTI VIENĄ ==================
@app.route('/add', methods=['POST'])
def add_person():
    if not is_admin():
        flash('Tik administratorius gali pridėti žmones!', 'danger')
        return redirect(url_for('index'))
    
    person = Person(
        first_name=request.form['first_name'].strip(),
        last_name=request.form['last_name'].strip(),
        certificate_number=request.form.get('certificate_number', '').strip(),
        license_number=request.form.get('license_number', '').strip(),
        email=request.form.get('email', '').strip()
    )
    db.session.add(person)
    db.session.commit()
    flash(f'Pridėtas: {person.first_name} {person.last_name}', 'success')
    return redirect(url_for('index'))

# ================== EXCEL ĮKĖLIMAS ==================
@app.route('/upload', methods=['POST'])
def upload_file():
    if not is_admin():
        flash('Tik administratorius gali įkelti failus!', 'danger')
        return redirect(url_for('index'))

    if 'file' not in request.files:
        flash('Nepasirinktas failas', 'danger')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('Nepasirinktas failas', 'danger')
        return redirect(url_for('index'))

    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        flash('Palaikomi tik .xlsx, .xls ir .csv failai', 'danger')
        return redirect(url_for('index'))

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        added_count = 0
        for _, row in df.iterrows():
            certificate_number = str(row.iloc[0] if len(df.columns) > 0 else '').strip()
            first_name = str(row.iloc[1] if len(df.columns) > 1 else '').strip()
            last_name = str(row.iloc[2] if len(df.columns) > 2 else '').strip()
            license_number = str(row.iloc[3] if len(df.columns) > 3 else '').strip()
            email = str(row.iloc[4] if len(df.columns) > 4 else '').strip()

            if first_name and last_name and first_name.lower() != 'nan' and last_name.lower() != 'nan':
                person = Person(
                    first_name=first_name,
                    last_name=last_name,
                    certificate_number=certificate_number if certificate_number and certificate_number.lower() != 'nan' else None,
                    license_number=license_number if license_number and license_number.lower() != 'nan' else None,
                    email=email if email and email.lower() != 'nan' else None
                )
                db.session.add(person)
                added_count += 1

        db.session.commit()
        flash(f'Sėkmingai pridėta {added_count} žmonių iš failo!', 'success')
        
    except Exception as e:
        flash(f'Klaida įkeliant failą: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

# ================== MASINIAI VEIKSMAI ==================
@app.route('/bulk_action', methods=['POST'])
def bulk_action():
    if not is_admin():
        flash('Tik administratorius gali atlikti masinius veiksmus!', 'danger')
        return redirect(url_for('index'))

    action = request.form.get('action')
    person_ids = request.form.getlist('person_ids')

    if not person_ids:
        flash('Nepasirinktas nė vienas žmogus!', 'danger')
        return redirect(url_for('index'))

    if action == 'download_all_qr':
        return download_all_qr()

    success_count = 0

    for pid_str in person_ids:
        try:
            person_id = int(pid_str)
            person = Person.query.get(person_id)
            if not person:
                continue

            if action == 'generate_qr':
                generate_qr_with_name(person)
                success_count += 1

            elif action == 'delete_qr':
                qr_path = f"static/qrcodes/{person.id}.png"
                if os.path.exists(qr_path):
                    os.remove(qr_path)
                    success_count += 1

            elif action == 'delete_person':
                qr_path = f"static/qrcodes/{person.id}.png"
                if os.path.exists(qr_path):
                    os.remove(qr_path)
                db.session.delete(person)
                success_count += 1

        except:
            pass

    db.session.commit()
    flash(f'Sėkmingai atlikta {success_count} veiksmų.', 'success')
    return redirect(url_for('index'))

# ================== KITI ROUTES ==================
@app.route('/logs')
def logs():
    all_logs = ScanLog.query.order_by(ScanLog.scanned_at.desc()).all()
    total_people = Person.query.count()
    people_with_qr = sum(1 for p in Person.query.all() if os.path.exists(f"static/qrcodes/{p.id}.png"))
    total_registrations = len(all_logs)
    unique_registered = len(set(log.person_id for log in all_logs))
    
    return render_template('logs.html', 
                         logs=all_logs, 
                         is_admin=is_admin(),
                         total_people=total_people,
                         people_with_qr=people_with_qr,
                         total_registrations=total_registrations,
                         unique_registered=unique_registered)

@app.route('/export_logs')
def export_logs():
    if not is_admin():
        flash('Tik administratorius gali eksportuoti!', 'danger')
        return redirect(url_for('logs'))

    logs = ScanLog.query.order_by(ScanLog.scanned_at.desc()).all()
    data = []
    for log in logs:
        person = Person.query.get(log.person_id)
        data.append({
            'Pažymėjimo numeris': person.certificate_number if person else '',
            'Vardas': log.first_name,
            'Pavardė': log.last_name,
            'Licencijos numeris': person.license_number if person else '',
            'El. paštas': person.email if person else '',
            'Skenavimo laikas': log.scanned_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'registracijos_{datetime.now().strftime("%Y-%m-%d")}.xlsx')

@app.route('/generate_qr/<int:person_id>')
def generate_qr(person_id):
    if not is_admin():
        flash('Tik administratorius gali generuoti QR!', 'danger')
        return redirect(url_for('index'))
    person = Person.query.get_or_404(person_id)
    generate_qr_with_name(person)
    flash(f'QR sugeneruotas: {person.first_name} {person.last_name}', 'success')
    return redirect(url_for('index'))

@app.route('/delete_qr/<int:person_id>')
def delete_qr(person_id):
    if not is_admin():
        flash('Tik administratorius gali trinti!', 'danger')
        return redirect(url_for('index'))
    person = Person.query.get_or_404(person_id)
    qr_path = f"static/qrcodes/{person.id}.png"
    if os.path.exists(qr_path):
        os.remove(qr_path)
        flash(f'Ištrintas QR kodas: {person.first_name} {person.last_name}', 'success')
    return redirect(url_for('index'))

@app.route('/delete_person/<int:person_id>')
def delete_person(person_id):
    if not is_admin():
        flash('Tik administratorius gali trinti!', 'danger')
        return redirect(url_for('index'))
    person = Person.query.get_or_404(person_id)
    qr_path = f"static/qrcodes/{person.id}.png"
    if os.path.exists(qr_path):
        os.remove(qr_path)
    db.session.delete(person)
    db.session.commit()
    flash(f'Žmogus visiškai ištrintas: {person.first_name} {person.last_name}', 'success')
    return redirect(url_for('index'))

@app.route('/checkin/<int:person_id>')
def checkin(person_id):
    person = Person.query.get_or_404(person_id)
    today = datetime.now(LT_TIMEZONE).date()
    existing = ScanLog.query.filter(
        ScanLog.person_id == person.id,
        db.func.date(ScanLog.scanned_at) == today
    ).first()
    
    if existing:
        message = f'{person.first_name} {person.last_name} jau užsiregistravo šiandien!'
    else:
        log = ScanLog(person_id=person.id, first_name=person.first_name, last_name=person.last_name)
        db.session.add(log)
        db.session.commit()
        message = f'Sėkmingai užsiregistravote!'

    now = datetime.now(LT_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
    return render_template('success.html', person=person, now=now, message=message)

@app.route('/delete_log/<int:log_id>')
def delete_log(log_id):
    if not is_admin():
        flash('Tik administratorius gali trinti!', 'danger')
        return redirect(url_for('logs'))
    log = ScanLog.query.get_or_404(log_id)
    db.session.delete(log)
    db.session.commit()
    flash('Įrašas ištrintas', 'success')
    return redirect(url_for('logs'))

if __name__ == '__main__':
    os.makedirs("static/qrcodes", exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    print(f"✅ Serveris paleistas: http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)