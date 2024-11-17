from pymongo import MongoClient
import jwt
import hashlib
from flask import Flask, render_template, jsonify, request, redirect, url_for, make_response, flash, session
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from os.path import join, dirname
from dotenv import load_dotenv
from bson import ObjectId
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_KEGIATAN'] = './static/kegiatan'
app.config['UPLOAD_PROFILE'] = './static/profile'

SECRET_KEY = 'SPARTA'
TOKEN_KEY = 'mytoken'

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME =  os.environ.get("DB_NAME")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

admin_name = "admin"
admin_password = "admin"
pw_hash = hashlib.sha256(admin_password.encode("utf-8")).hexdigest()

if db.users.count_documents({"name": admin_name}) == 0:
    db.users.insert_one({
        "name": admin_name,
        "address": "Admin Address",
        "role": "admin",
        "password": pw_hash
    })

@app.context_processor
def cookies():
    token_receive = request.cookies.get(TOKEN_KEY)
    logged_in = False
    is_admin = False

    if token_receive:
        try:
            payload = jwt.decode(token_receive, SECRET_KEY, algorithms=['HS256'])
            user_info = db.users.find_one({"name": payload["id"]})
            if user_info:
                logged_in = True
                is_admin = user_info.get("role") == "admin"
        except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError):
            pass

    return {'logged_in': logged_in, 'is_admin': is_admin}

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get(TOKEN_KEY)
        if not token:
            return jsonify({"message": "Token is missing!"}), 403
        
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            if data.get("id") != admin_name:
                return jsonify({"message": "Admin access required!"}), 403
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({"message": "Invalid token!"}), 403

        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def main():
    return render_template('homepage.html')

@app.route('/logout', methods=['GET'])
def logout():
    response = make_response(redirect(url_for('main')))
    response.delete_cookie(TOKEN_KEY)
    return response

@app.route('/signin')
def signin():
    error_message = request.args.get('error_message', None)
    if cookies().get('logged_in'):
        return redirect(url_for('main'))
    else:
        return render_template('login.html', error_message=error_message)

@app.route('/sign_in', methods=['POST'])
def sign_in():
    name = request.form["name"]
    password = request.form["password"]
    pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    
    if name == admin_name and pw_hash == hashlib.sha256(admin_password.encode("utf-8")).hexdigest():
        payload = {
            "id": name,
            "exp": datetime.utcnow() + timedelta(seconds=60 * 60 * 24),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        response = make_response(jsonify({'success': True, 'message': 'Berhasil Login'}))
        response.set_cookie(TOKEN_KEY, token)
        return response
    else:
        return jsonify({'success': False, 'message': 'Username atau Password Salah'})
    
@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/edit', methods=['POST'])
def edit_kegiatan():
    if not cookies().get('logged_in'):
        return redirect(url_for('signin'))
        
    doct_id = request.form.get('dokumentasi_id')  
    judul_kegiatan = request.form.get('judul_kegiatan')
    deskripsi_kegiatan = request.form.get('deskripsi_kegiatan')

    existing_filename = request.form.get('existing_foto_kegiatan', 'default.jpg')
    filename = existing_filename

    if 'foto_kegiatan' in request.files:
        foto_kegiatan = request.files['foto_kegiatan']
        if foto_kegiatan.filename != '':
            file_extension = foto_kegiatan.filename.rsplit('.', 1)[1].lower() if '.' in foto_kegiatan.filename else 'jpg'
            filename = secure_filename(f"{doct_id}.{file_extension}")
            foto_kegiatan.save(os.path.join(app.config['UPLOAD_KEGIATAN'], filename))

    db.dokumentasi.update_one(
        {'_id': ObjectId(doct_id)},
        {'$set': {
                'judul_kegiatan': judul_kegiatan,
                'deskripsi_kegiatan': deskripsi_kegiatan,
                'foto_kegiatan': filename if filename != existing_filename else existing_filename
            }
        }
    )

    return redirect(url_for('show_postingan'))  

@app.route('/add', methods=['POST'])
def add_kegiatan():
    judul_kegiatan = request.form.get('judul_kegiatan')
    deskripsi_kegiatan = request.form.get('deskripsi_kegiatan')

    os.makedirs(app.config['UPLOAD_KEGIATAN'], exist_ok=True)

    foto_kegiatan = request.files['foto_kegiatan'] if 'foto_kegiatan' in request.files else None

    if foto_kegiatan and foto_kegiatan.filename != '':
        file_extension = foto_kegiatan.filename.rsplit('.', 1)[1].lower() if '.' in foto_kegiatan.filename else 'jpg'
        filename = secure_filename(f"{judul_kegiatan}.{file_extension}")
        foto_kegiatan.save(os.path.join(app.config['UPLOAD_KEGIATAN'], filename))
        print(f"File saved as: {filename}") 
    else:
        filename = 'default.jpg'

    current_datetime = datetime.now()

    doc_data = {
        'judul_kegiatan': judul_kegiatan,
        'foto_kegiatan': filename,
        'deskripsi_kegiatan': deskripsi_kegiatan,
        'tanggal_kegiatan': current_datetime,
        'tanggal_kegiatan_display': current_datetime.strftime('%B %d, %Y')
    }

    db.dokumentasi.insert_one(doc_data)

    return redirect(url_for('show_postingan'))

@app.route('/delete', methods=['POST'])
def delete_kegiatan():
    doct_id = request.form['doc_id']  
    db.dokumentasi.delete_one({'_id': ObjectId(doct_id)})  

    return redirect(url_for('show_postingan')) 


@app.route('/search', methods=['GET'])
def search_postingan():
    query = request.args.get('query', '').strip()
    
    if query:
        postingan_list = db.dokumentasi.find({
            "$or": [
                {"judul_kegiatan": {"$regex": query, "$options": "i"}}, 
                {"tanggal_kegiatan_display": {"$regex": query, "$options": "i"}}
            ]
        }).sort('_id', -1)  
    else:
        postingan_list = db.dokumentasi.find().sort('_id', -1)  

    return render_template('postingan.html', postingan_list=postingan_list)

@app.route('/staf')
def staf():
    return render_template('staf.html')

@app.route('/kkn')
def kkn():
    return render_template('kkn.html')

@app.route('/lembaga_adat')
def lembaga_adat():
    return render_template('lembaga_adat.html')

@app.route('/karta')
def karta():
    return render_template('karta.html')

@app.route('/remas')
def remas():
    return render_template('remas.html')

@app.route('/adat')
def adat():
    return render_template('adat.html')


@app.route('/kesenian')
def kesenian():
    return render_template('kesenian.html')

@app.route('/bejango_beleq')
def bejango_beleq():
    return render_template('bejango_beleq.html')

@app.route('/bejariq_minyak')
def bejariq_minyak():
    return render_template('bejariq_minyak.html')

@app.route('/postingan')
def show_postingan():
    postingan_list = db.dokumentasi.find().sort('_id', -1)  
    return render_template('postingan.html', postingan_list=postingan_list)

@app.route('/sejarah-masjid')
def sejarah_masjid():
    return render_template('sejarah-masjid.html')

@app.route('/sejarah-songak')
def sejarah_songak():
    return render_template('sejarah-songak.html')


if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)