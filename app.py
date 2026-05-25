from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import qrcode
import os
from zoneinfo import ZoneInfo
import pandas as pd

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'labai_slapta_fraze_kuri_pakeisk')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

db = SQLAlchemy(app)

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

with app.app_context():
    db.create_all()

# ================== ADMIN ==================
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"   

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            flash('Sėkmingai prisijungėte kaip administratorius')
            return redirect(url_for('index'))
        else:
            flash('Neteisingi prisijungimo duomenys')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('Atsijungėte')
    return redirect(url_for('index'))

def is_admin():
    return session.get('admin') == True

# ================== PUSLAPIAI ==================

@app.route('/')
def index():
    if is_admin():
        people = Person.query.order_by(Person.created_at.desc()).all()
    else:
        people = []
    return render_template('index.html', people=people, is_admin=is_admin())

@app.route('/add', methods=['POST'])
def add_person():
    if not is_admin():
        flash('Tik administratorius gali pridėti žmones!')
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
    flash(f'Pridėtas: {person.first_name} {person.last_name}')
    return redirect(url_for('index'))

# === ĮKĖLIMAS IŠ EXCEL / CSV (nauja tvarka) ===
@app.route('/upload', methods=['POST'])
def upload_file():
    if not is_admin():
        flash('Tik administratorius gali įkelti failus!')
        return redirect(url_for('index'))

    if 'file' not in request.files:
        flash('Nepasirinktas failas')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('Nepasirinktas failas')
        return redirect(url_for('index'))

    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        flash('Palaikomi tik .xlsx, .xls ir .csv failai')
        return redirect(url_for('index'))

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        added_count = 0

        for _, row in df.iterrows():
            certificate_number = None
            first_name = None
            last_name = None
            license_number = None
            email = None

            col_map = {str(col).strip().lower(): col for col in df.columns}

            # Pagal stulpelių pavadinimus
            for key in ['pažymėjimo numeris', 'pazyme', 'certificate_number', 'certificate']:
                if key in col_map:
                    certificate_number = str(row[col_map[key]]).strip()
                    break
            if not certificate_number and len(df.columns) > 0:
                certificate_number = str(row.iloc[0]).strip()

            for key in ['vardas', 'first_name', 'name']:
                if key in col_map:
                    first_name = str(row[col_map[key]]).strip()
                    break
            if not first_name and len(df.columns) > 1:
                first_name = str(row.iloc[1]).strip()

            for key in ['pavardė', 'pavarde', 'last_name', 'surname']:
                if key in col_map:
                    last_name = str(row[col_map[key]]).strip()
                    break
            if not last_name and len(df.columns) > 2:
                last_name = str(row.iloc[2]).strip()

            for key in ['licencijos numeris', 'licencija', 'license_number', 'license']:
                if key in col_map:
                    license_number = str(row[col_map[key]]).strip()
                    break
            if not license_number and len(df.columns) > 3:
                license_number = str(row.iloc[3]).strip()

            for key in ['el. paštas', 'el pastas', 'email', 'e-mail']:
                if key in col_map:
                    email = str(row[col_map[key]]).strip()
                    break
            if not email and len(df.columns) > 4:
                email = str(row.iloc[4]).strip()

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
        flash(f'Sėkmingai pridėta {added_count} žmonių iš failo!')
        
    except Exception as e:
        flash(f'Klaida įkeliant failą: {str(e)}')
    
    return redirect(url_for('index'))

# Kitos funkcijos lieka tos pačios...
@app.route('/delete_person/<int:person_id>')
def delete_person(person_id):
    if not is_admin():
        flash('Tik administratorius gali trinti!')
        return redirect(url_for('index'))
    
    person = Person.query.get_or_404(person_id)
    qr_path = f"static/qrcodes/{person.id}.png"
    if os.path.exists(qr_path):
        try:
            os.remove(qr_path)
        except:
            pass
    db.session.delete(person)
    db.session.commit()
    flash(f'Ištrintas: {person.first_name} {person.last_name}')
    return redirect(url_for('index'))

@app.route('/generate_qr/<int:person_id>')
def generate_qr(person_id):
    if not is_admin():
        flash('Tik administratorius gali generuoti QR kodus!')
        return redirect(url_for('index'))
    
    person = Person.query.get_or_404(person_id)
    base_url = request.host_url.rstrip('/')
    url = f"{base_url}/checkin/{person.id}"
    
    qr = qrcode.make(url)
    os.makedirs("static/qrcodes", exist_ok=True)
    qr_path = f"static/qrcodes/{person.id}.png"
    qr.save(qr_path)
    
    flash(f'QR kodas sugeneruotas: {person.first_name} {person.last_name}')
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

    current_time = datetime.now(LT_TIMEZONE)
    
    return render_template('success.html', 
                         person=person, 
                         now=current_time.strftime('%Y-%m-%d %H:%M:%S'),
                         message=message)

@app.route('/logs')
def logs():
    all_logs = ScanLog.query.order_by(ScanLog.scanned_at.desc()).all()
    return render_template('logs.html', logs=all_logs, is_admin=is_admin())

@app.route('/delete_log/<int:log_id>')
def delete_log(log_id):
    if not is_admin():
        flash('Tik administratorius gali trinti įrašus!')
        return redirect(url_for('logs'))
    
    log = ScanLog.query.get_or_404(log_id)
    db.session.delete(log)
    db.session.commit()
    flash('Įrašas ištrintas')
    return redirect(url_for('logs'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)