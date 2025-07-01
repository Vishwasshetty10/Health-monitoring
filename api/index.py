from flask import Flask, jsonify, redirect, render_template_string, request, send_file, session, url_for
import os
import json
from PyPDF2 import PdfReader
import google.generativeai as genai
import io
import re
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)

app.secret_key = 'fax2003'

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id='214872427334-bo8sm6de7sfk90t4rpthc5tvd00265je.apps.googleusercontent.com',
    client_secret='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',
    redirect_uri='https://fax-ai.vercel.app/authorize',
    client_kwargs={'scope': 'openid profile email'},
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
)

@app.route('/login')
def login():
    if 'user_info' in session:
        return redirect(url_for('profile'))

    nonce = request.headers.get('X-Request-Nonce', 'default-nonce') 
    session['nonce'] = nonce
    return google.authorize_redirect(
        redirect_uri=url_for('authorized', _external=True),
        nonce=nonce
    )

@app.route('/logout')
def logout():
    session.pop('google_token', None)
    session.pop('user_info', None)
    return redirect(url_for('index'))

@app.route('/authorize')
def authorized():
    try:
        token = google.authorize_access_token()
        if not token:
            error_reason = request.args.get('error_reason', 'unknown')
            error_description = request.args.get('error_description', 'No description provided')
            return f'Access denied: reason={error_reason} error={error_description}'

        nonce = session.pop('nonce', None)
        user_info = google.parse_id_token(token, nonce=nonce)
        session['google_token'] = token
        session['user_info'] = user_info
        return redirect(url_for('profile'))

    except Exception as e:
        app.logger.error(f'Error parsing ID token: {str(e)}')
        return 'An error occurred during authentication. Please try again later.', 500

@app.route('/profile')
def profile():
    user_info = session.get('user_info')
    if not user_info:
        return redirect(url_for('login'))

    profile_html = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="shortcut icon" type="image/png" href="https://i.ibb.co/DGGw2MD/image.png" />
    <title>FAX Profile</title>
    <style>
        body {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: linear-gradient(180deg, #10121B 0%, #060606 100%);
            color: #ffffff;
            text-align: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            height: 100vh;
            margin: 0;
        }
        .profile-container {
            padding: 20px;
            border-radius: 30px;
            background-color: #ffffff;
        }
        .profile-image {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            cursor: pointer;
            border: 3px solid #ffffff;
        }

        .username {
            margin-top: 20px;
            font-size: 20px;
            font-weight: bold;
            color: #000000;
        }
        a {
            display: inline-block;
            margin-top: 20px;
            padding: 10px;
            color: #ffffff;
            text-decoration: none;
            font-weight: bold;
            background: linear-gradient(85deg, #ff2a86, #ff9900);
            border-radius: 10px;
            font-size: 15px;
        }
    </style>
</head>
<body>
    <div class="profile-container">
        <img src="{{ picture }}" alt="Profile Image" class="profile-image" onclick="showUsername()">
        <div class="username">Welcome, {{ name }}.</div>
        <a href="{{ url_for('logout') }}">Logout</a><br>
        <a href="i.html">Move to Dashboard</a>
    </div>
</body>
<style>.c{display:none;position:fixed;bottom:0;left:0;right:0;background:#ff5555;color:#fff;align-items:center;justify-content:center}.spinner{width:20px;height:20px;border:2px solid transparent;border-top:2px solid #fff;border-radius:50%;animation:spin 1s linear infinite;margin-right:10px}@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style></head>
  <body><div class="c" id="no-internet-card"><div class="spinner"></div><h4>Failed to load data, retrying....</h4></div><script>function updateOnlineStatus(){document.getElementById('no-internet-card').style.display=navigator.onLine?'none':'flex'}window.addEventListener('online',updateOnlineStatus);window.addEventListener('offline',updateOnlineStatus);updateOnlineStatus();</script></body>  
</html>
    '''
    return render_template_string(
        profile_html,
        picture=user_info['picture'],
        name=user_info['name']
    )

def load_json_file(file_name):
    file_path = os.path.join(os.path.dirname(__file__), file_name)
    with open(file_path, "r") as file:
        return json.load(file)

questions_data = load_json_file("c.json")
diseases_data = load_json_file("fax.json")
medicines_data = load_json_file("drug.json")
track_data = load_json_file("track.json")

def calculate_probability(symptoms, diseases):
    probability = {}
    
    for disease, info in diseases.items():
        disease_symptoms = info['symptoms'].split(', ')
        matching_symptoms = len(set(symptoms) & set(disease_symptoms))
        probability[disease] = (matching_symptoms / len(disease_symptoms)) * 100
    
    return probability

@app.route('/analyze', methods=['POST'])
def analyze():
    input_data = request.json
    symptoms = input_data.get('symptoms', [])
    
    if not symptoms or not isinstance(symptoms, list):
        return jsonify({"error": "Invalid symptoms data. Please provide a list of symptoms."}), 400
    
    probability = calculate_probability(symptoms, diseases_data)
    
    fully_matched_diseases = {}
    partially_matched_diseases = {}
    
    for disease, prob in probability.items():
        disease_symptoms = diseases_data[disease]['symptoms'].split(', ')
        if set(symptoms).issubset(set(disease_symptoms)):
            fully_matched_diseases[disease] = prob
        else:
            partially_matched_diseases[disease] = prob

    sorted_partially_matched = sorted(partially_matched_diseases.items(), key=lambda x: x[1], reverse=True)
    sorted_probabilities = list(fully_matched_diseases.items()) + sorted_partially_matched
    top_10_diseases = dict(sorted_probabilities[:10])
    return jsonify(top_10_diseases)

@app.route('/symptoms', methods=['GET'])
def get_symptoms():
    symptoms = set()
    for disease_info in diseases_data.values():
        symptoms.update(disease_info['symptoms'].split(', '))
    return jsonify(sorted(symptoms))

@app.route('/disease_info', methods=['GET'])
def disease_info():
    disease_name = request.args.get('disease')
    disease_info = diseases_data.get(disease_name, None)
    
    if disease_info is None:
        return jsonify({"error": "Disease not found"}), 404
    
    disease_info['name'] = disease_name
    return jsonify(disease_info)

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/w.html')
def dashboard():
    return send_file('w.html')

@app.route('/<page>.html')
def render_html(page):
    allowed_pages = ['w', 'i', 'account', 'fax', 'da', 'd', 'a', 'c', 'doc', 'v', 'fph', 'm', 'p', 'f']
    
    if 'user_info' in session:
        if page == 'account':
            return redirect(url_for('profile'))
        if page in allowed_pages:
            try:
                return send_file(f'{page}.html')
            except FileNotFoundError:
                return "Page not found", 404
    else:
        if page == 'profile':
            return redirect(url_for('render_html', page='account'))
        if page in allowed_pages:
            try:
                return send_file(f'{page}.html')
            except FileNotFoundError:
                return "Page not found", 404
    return "Page not found", 404

@app.route('/fax.json')
def fax_data():
    return send_file('fax.json', as_attachment=True, mimetype='application/json')

GOOGLE_API_KEY = 'AIzaSyBVywbpZnCBDqUwca2oebNPVC4G1gYBOfo'
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
def clean_markdown(text):
    text = text.replace('**', '') 
    text = text.replace('##', '')  
    text = text.replace('* ', '') 
    text = text.replace('```', '') 
    text = text.replace('\n', ' ')
    return text.strip()

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')

        if message in questions_data:
            response = questions_data[message]
        else:
            words = message.split()
            last_two_words = " ".join(words[-2:])

            matched_key = next((key for key in questions_data.keys() if last_two_words.lower() in key.lower()), None)
            if matched_key:
                response = questions_data[matched_key]
            else:
                last_word = words[-1]
                matched_key = next((key for key in questions_data.keys() if last_word.lower() in key.lower()), None)
                if matched_key:
                    response = questions_data[matched_key]
                else:
                    try:
                        ai_response = model.generate_content(message)
                        response = ai_response.text
                    except Exception as e:
                        response = "Sorry, I couldn't find a response related to your query."
        formatted_response = clean_markdown(response)
        return jsonify({"response": formatted_response})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/get_medicines', methods=['POST'])
def get_medicines():
    symptom = request.json.get('symptom', '').strip().lower()
    for item in medicines_data:
        if item['symptom'].strip().lower() == symptom:
            sorted_medicines = sorted(item['medicines'], key=lambda med: med['severity'] == 'high')
            return jsonify({'symptom': item['symptom'], 'medicines': sorted_medicines})
    return jsonify({'error': 'Symptom not found'}), 404

@app.route('/get_related_symptoms', methods=['POST'])
def get_related_symptoms():
    symptom_input = request.json.get('symptom', '').lower()
    related_symptoms = {entry['symptom'] for entry in medicines_data if symptom_input in entry['symptom'].lower()}
    return jsonify({'relatedSymptoms': list(related_symptoms)})

ALLOWED_EXTENSIONS = {'pdf'}
HIGHLIGHT_WORDS = ['important', 'highlight', 'key']  

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def highlight_text(text, words):
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    for word in words:
        text = re.sub(rf'\b{re.escape(word)}\b', f'<span class="highlight">{word}</span>', text, flags=re.IGNORECASE)
    return text

def allowed_file(filename):
    return filename.lower().endswith('.pdf')

def remove_special_symbols(text):
    return re.sub(r'[\*\#]', '', text)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        try:
            pdf_file = io.BytesIO(file.read())
            reader = PdfReader(pdf_file)
            text = ''.join(page.extract_text() for page in reader.pages)
            response = model.generate_content(text)
            summarized_text = remove_special_symbols(response.text)

            result_text = f"Uploaded PDF Summary: {summarized_text}"
            return jsonify({'text': result_text}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    name = data.get('name')
    age = data.get('age')
    gender = data.get('gender')
    weight = float(data.get('weight', 0))
    height = float(data.get('height', 0))
    bp_systolic = float(data.get('bp_systolic', 0))
    bp_diastolic = float(data.get('bp_diastolic', 0))
    inhale = float(data.get('inhale', 0))
    exhale = float(data.get('exhale', 0))

    original_data = next((item for item in track_data if item["age"] == age and item["gender"] == gender), None)

    if not original_data:
        return jsonify({"error": "No matching data found"}), 404

    entered_data = {
        "name": name,
        "age": age,
        "gender": gender,
        "weight": weight,
        "height": height,
        "bp_systolic": bp_systolic,
        "bp_diastolic": bp_diastolic,
        "inhale": inhale,
        "exhale": exhale
    }

    def calculate_difference(original, entered):
        if original == 0:
            return 0
        return abs((entered - original) / original) * 100

    weight_diff = calculate_difference(original_data['weight'], weight)
    height_diff = calculate_difference(original_data['height'], height)
    bp_systolic_diff = calculate_difference(int(original_data['bp'].split('/')[0]), bp_systolic)
    bp_diastolic_diff = calculate_difference(int(original_data['bp'].split('/')[1]), bp_diastolic)
    inhale_diff = calculate_difference(original_data['inhale'], inhale)
    exhale_diff = calculate_difference(original_data['exhale'], exhale)

    all_match = (weight_diff == 0 and height_diff == 0 and 
                 bp_systolic_diff == 0 and bp_diastolic_diff == 0 and 
                 inhale_diff == 0 and exhale_diff == 0)

    if all_match:
        weight_diff = height_diff = bp_systolic_diff = bp_diastolic_diff = inhale_diff = exhale_diff = 100

    total_diff = (weight_diff + height_diff + bp_systolic_diff + bp_diastolic_diff + inhale_diff + exhale_diff) / 6

    report = f"Hello {name}, <br/>here is your health report:<br/><br/>"
    if all_match:
        report += "Your health parameters are within the normal range.<br/><br/>"
    else:
        report += f"Weight difference: {weight_diff:.2f}%<br/>"
        report += f"Height difference: {height_diff:.2f}%<br/>"
        report += f"Blood Pressure Systolic difference: {bp_systolic_diff:.2f}%<br/>"
        report += f"Blood Pressure Diastolic difference: {bp_diastolic_diff:.2f}%<br/>"
        report += f"Inhale time difference: {inhale_diff:.2f}%<br/>"
        report += f"Exhale time difference: {exhale_diff:.2f}%<br/><br/>"
        report += f"Overall Health Comparison: {total_diff:.2f}%"

        health_tips = ""
        if weight_diff < 50:
            health_tips += "Consider consulting a nutritionist for weight management.<br/>"
        if height_diff < 50:
            health_tips += "Ensure proper posture and consult a specialist if height issues persist.<br/>"
        if bp_systolic_diff < 50:
            health_tips += "Monitor your blood pressure regularly and consult a healthcare provider.<br/>"
        if bp_diastolic_diff < 50:
            health_tips += "Regular exercise and a balanced diet can help manage blood pressure.<br/>"
        if inhale_diff < 50:
            health_tips += "Practice breathing exercises to improve lung capacity.<br/>"
        if exhale_diff < 50:
            health_tips += "Breathing techniques can enhance lung function and overall health.<br/>"

        if health_tips:
            report += "<br/><br/>Health Tips:<br/>" + health_tips

    response = {
        "original_data": original_data,
        "entered_data": entered_data,
        "report": report,
        "percentage_difference": total_diff
    }

    return jsonify(response)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://default:1QYEWuax8BTr@ep-soft-union-a46sh4wp.us-east-1.aws.neon.tech:5432/verceldb?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    issue = db.Column(db.Text, nullable=False)
    feedback_rating = db.Column(db.Integer, nullable=False)

def create_tables():
    with app.app_context():
        db.create_all()

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        name = data.get('name')
        email = data.get('email')
        issue = data.get('issue')
        feedback_rating = data.get('feedback_rating')

        try:
            feedback_rating = int(feedback_rating)
        except ValueError:
            return jsonify({'error': 'Invalid feedback rating'}), 400

        if not name or not email or not issue or feedback_rating not in [1, 2, 3, 4, 5]:
            return jsonify({'error': 'Invalid input'}), 400

        feedback = Feedback(name=name, email=email, issue=issue, feedback_rating=feedback_rating)
        db.session.add(feedback)
        db.session.commit()

        return jsonify({'message': 'Feedback submitted successfully!'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    app.run()