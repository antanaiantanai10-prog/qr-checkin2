from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import qrcode
import os

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'labai_slapta_fraze_kuri_pakeisk')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    people = Person.query.all()
    return render_template('index.html', people=people)

@app.route('/add', methods=['POST'])
def add_person():
    first_name = request.form['first_name'].strip()
    last_name = request.form['last_name'].strip()
    if first_name and last_name:
        person = Person(first_name=first_name, last_name=last_name)
        db.session.add(person)
        db.session.commit()
        flash(f'Pridėtas: {first_name} {last_name}')
    return redirect(url_for('index'))

@app.route('/generate_qr/<int:person_id>')
def generate_qr(person_id):
    person = Person.query.get_or_404(person_id)
    base_url = request.host_url.rstrip('/')
    url = f"{base_url}/checkin/{person.id}"
    
    qr = qrcode.make(url)
    folder = "static/qrcodes"
    os.makedirs(folder, exist_ok=True)
    qr_path = f"{folder}/{person.id}.png"
    qr.save(qr_path)
    
    flash(f'QR kodas sugeneruotas: {person.first_name} {person.last_name}')
    return redirect(url_for('index'))

@app.route('/checkin/<int:person_id>')
def checkin(person_id):
    person = Person.query.get_or_404(person_id)
    log = ScanLog(person_id=person.id, first_name=person.first_name, last_name=person.last_name)
    db.session.add(log)
    db.session.commit()
    return render_template('success.html', person=person)

@app.route('/logs')
def logs():
    all_logs = ScanLog.query.order_by(ScanLog.scanned_at.desc()).all()
    return render_template('logs.html', logs=all_logs)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)