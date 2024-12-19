from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from libretranslatepy import LibreTranslateAPI
import moviepy as mp
from flask_socketio import SocketIO, emit
import torchaudio
import os
import geopy.distance
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline, WhisperProcessor, WhisperForConditionalGeneration
import requests


lis = []
app = Flask(__name__)
lt = LibreTranslateAPI("https://libretranslate.de/")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dasd'
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
disaster_data = {
    "coastal": ["Waterproof bandages", "Burn cream", "Antibiotic ointment", "Gauze pads", "Emergency thermal blanket"],
    "earthquake-prone": ["Gloves", "Dust masks", "Adhesive bandages", "Pain relievers", "Whistle"],
    "flood-prone": ["Water purification tablets", "Antiseptic wipes", "Adhesive bandages", "Tweezers", "Flashlight"],
    "general": ["Adhesive bandages", "Antibiotic ointment", "Scissors", "Thermometer", "Alcohol wipes"]
}
#Admin users
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    password = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(10))
    age = db.Column(db.Integer)
    gender = db.Column(db.Boolean)  

class itemtracker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    update = db.Column(db.String(200))  

with app.app_context():
    db.create_all()

@socketio.on('connect')
def handle_connect():
    print("Client connected")
    emit('server_message', {'message': 'Welcome! You are connected to the notification server.'})

class otherfunc():
    def download_video(video_url, save_path="temp_video.mp4"):
        response = requests.get(video_url, stream=True)
        with open(save_path, "wb") as video_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    video_file.write(chunk)
        return save_path
    
    def extract_audio(video_path, audio_path):
        video = mp.VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path)     
 
    def transcribe_audio(audio_path, model_name="openai/whisper-tiny"):
        processor = WhisperProcessor.from_pretrained(model_name)
        model = WhisperForConditionalGeneration.from_pretrained(model_name)

        waveform, rate = torchaudio.load(audio_path)
        if rate != 16000:
            waveform = torchaudio.transforms.Resample(orig_freq=rate, new_freq=16000)(waveform)
        inputs = processor(waveform.squeeze().numpy(), return_tensors="pt", sampling_rate=16000)
        predicted_ids = model.generate(inputs["input_features"])
        transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
        return transcription
    
    def summarize_text(text, model_name="t5-small"):
        summarizer = pipeline("summarization", model=model_name)
        max_chunk = 512  # T5 models have a token limit
        chunks = [text[i:i + max_chunk] for i in range(0, len(text), max_chunk)]
        summarized_chunks = [
            summarizer(chunk, max_length=50, min_length=10, do_sample=False)[0]["summary_text"]
            for chunk in chunks
        ]
        return " ".join(summarized_chunks)

    def translate_text(text, target_language="fr"):
        model_name = f"Helsinki-NLP/opus-mt-en-{target_language}"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        
        inputs = tokenizer(text, return_tensors="pt", truncation=True)
        outputs = model.generate(**inputs)
        translated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return translated_text
    
    def get_amenities_by_city(city_name, amenity_type):
        base_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json];
        area[name="{city_name}"]->.searchArea;
        (
        node["amenity"="{amenity_type}"](area.searchArea);
        way["amenity"="{amenity_type}"](area.searchArea);
        relation["amenity"="{amenity_type}"](area.searchArea);
        );
        out body;
        >;
        out skel qt;
        """
        response = requests.get(base_url, params={"data": query})
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return []
        
        data = response.json()
        facilities = []
        
        for element in data.get("elements", []):
            name = element.get("tags", {}).get("name", "Unnamed")
            address = element.get("tags", {}).get("addr:full", "No address")
            lat = element.get("lat", None)
            lon = element.get("lon", None)
            sector_id = element.get("tags", {}).get("addr:suburb", "Unknown")
            facilities.append({
                "name": name, "address": address, "lat": lat, "lon": lon, "sector_id": sector_id
            })
        
        return facilities
    
    def calculate_city_score(city_name):
        hospitals = otherfunc.get_amenities_by_city(city_name, "hospital")
        police_stations = otherfunc.get_amenities_by_city(city_name, "police")
        fire_stations = otherfunc.get_amenities_by_city(city_name, "fire_station")
        score = 0
        score += len(hospitals) * 3 
        score += len(police_stations) * 2 
        score += len(fire_stations) * 1
        
        return {
            "total_score": score,
            "facilities": {
                "hospitals": len(hospitals),
                "police_stations": len(police_stations),
                "fire_stations": len(fire_stations),
            }
        }
    
    def get_weakest_sector(city_name):
        hospitals = otherfunc.get_amenities_by_city(city_name, "hospital")
        police_stations = otherfunc.get_amenities_by_city(city_name, "police")
        fire_stations = otherfunc.get_amenities_by_city(city_name, "fire_station")

        all_facilities = hospitals + police_stations + fire_stations
        sector_count = {}
        for facility in all_facilities:
            sector_id = facility.get("sector_id", None)
            if not sector_id:
                continue
            
            sector_count[sector_id] = sector_count.get(sector_id, 0) + 1
        
        if not sector_count:
            return {"weakest_sector_name": "No data", "facility_count": 0}

        weakest_sector_id = min(sector_count, key=sector_count.get)
        weakest_count = sector_count[weakest_sector_id]
        
        facilities_in_weakest_sector = [facility for facility in all_facilities if facility.get("sector_id") == weakest_sector_id]
        
        sector_name = weakest_sector_id 
        return {
            "weakest_sector_id": weakest_sector_id,
            "weakest_sector_name": sector_name, 
            "facility_count": weakest_count,
            "facilities": facilities_in_weakest_sector
        }

class getloc():
    def get_disaster_prone_category(city):
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"
            response = requests.get(url)
            data = response.json()

            if not data:
                return "general"
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])

            #mock data
            if 10 <= lat <= 20 and 75 <= lon <= 85:
                return "flood-prone"
            elif 25 <= lat <= 35 and 80 <= lon <= 90:
                return "earthquake-prone"
            else:
                return "general"

        except Exception as e:
            print(f"Error fetching data: {e}")
            return "general"
   
    def get_ameni(lat, lon, radius=10000, max_results=20, type="hospital"):
        base_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json];
        node["amenity"="{type}"](around:{radius},{lat},{lon});
        out body;
        """
        
        response = requests.get(base_url, params={"data": query})
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return []
        
        data = response.json()
        hospitals = []
        
        for element in data.get("elements", []):
            hospital_name = element.get("tags", {}).get("name", "Unnamed")
            hospital_lat = element.get("lat")
            hospital_lon = element.get("lon")
            
            if hospital_lat is None or hospital_lon is None:
                continue
            
            distance = geopy.distance.distance((lat, lon), (hospital_lat, hospital_lon)).km
            hospitals.append({
                "name": hospital_name,
                "lat": hospital_lat,
                "lon": hospital_lon,
                "distance": distance
            })
        hospitals_sorted = sorted(hospitals, key=lambda x: x['distance'])
        return hospitals_sorted[:max_results]

@app.route('/nearby-shelters', methods=['POST'])
def nearby_shelters():
    data = request.get_json()
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({"error": "Latitude and Longitude not provided"}), 400

    lat = data['latitude']
    lon = data['longitude']

    shelter = getloc.get_ameni(lat, lon, type='shelter')
    if not shelter:
        return jsonify({"message": "No nearby shelters found"}), 404
    
    return jsonify({
        "shelters": [
            {"name": shelter["name"], "latitude": shelter["lat"], "longitude": shelter["lon"], "distance": shelter["distance"]}
            for hospital in shelter
        ]
    })

@app.route('/first-aid-kit', methods=['POST'])
def first_aid_kit():
    data = request.get_json()
    if not data or 'location' not in data:
        return jsonify({"error": "Location not provided"}), 400

    location = data['location']
    disaster_category = getloc.get_disaster_prone_category(location)
    first_aid_items = disaster_data.get(disaster_category, disaster_data["general"])

    return jsonify({
        "location": location,
        "disaster_category": disaster_category,
        "first_aid_kit": first_aid_items
    })

@app.route('/nearby-hospitals', methods=['POST'])
def nearby_hospitals():
    data = request.get_json()
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({"error": "Latitude and Longitude not provided"}), 400

    lat = data['latitude']
    lon = data['longitude']

    hospitals = getloc.get_ameni(lat, lon)
    if not hospitals:
        return jsonify({"message": "No nearby hospitals found"}), 404
    
    return jsonify({
        "hospitals": [
            {"name": hospital["name"], "latitude": hospital["lat"], "longitude": hospital["lon"], "distance": hospital["distance"]}
            for hospital in hospitals
        ]
    })

@app.route('/video', methods=['POST'])
def transcribe_video():
    data = request.get_json()
    name = data.get('name')
    lang = data.get('lang')

    video_path = "temp_video.mp4"
    audio_path = "temp_audio.wav"
    otherfunc.download_video(data.get('url'), video_path)

    otherfunc.extract_audio(video_path, audio_path)

    transcribed_text = otherfunc.transcribe_audio(audio_path)

    summary = otherfunc.summarize_text(transcribed_text)

    translated_summary = otherfunc.translate_text(summary, lang)

    os.remove(video_path)
    os.remove(audio_path)
    print(summary, translated_summary)
    return jsonify(summary, translated_summary)

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    if not data or not data.get('name') or not data.get('password'):
        return jsonify({"message": "name and password are required"}), 400

    password = data.get('password')
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    age = data.get('age')
    gender = data.get('gender')

    existing_user = User.query.filter_by(name=name).first()
    if existing_user:
        return jsonify({"message": "Username already exists"}), 400
    new_user = User(
        password=password,
        name=name,
        email=email,
        phone=phone,
        age=age,
        gender=gender,
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 200

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"message": "Username and password are required"}), 400

    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    if not user.password == password:
        return jsonify({"message": "Invalid password"}), 401

    return jsonify({"message": "Login successful", "name": user.name}), 200

@app.route('/sos', methods=['POST'])
def sos():
    global lis
    data = request.get_json()
    lat = data['latitude']
    lon = data['longitude']
    lis.append({lat,lon})
    emit('notification', f'A person requested for help at {lat,lon}!', broadcast=True)

@app.route('/track', methods=['POST'])
def track():
    updates = itemtracker.query.all()
    fresponse_list = [
            {
                "id": updates.id,
                "type": updates.type,
                "msg": updates.update,
            }
            for i in updates
        ]
    return itemtracker.query.all()

app.route("/trackupdate", methods=['POST'])
def updatetracker():
    data = request.get_json()
    type = data.get('type')
    msg = data.get('msg')

    new_update = itemtracker(
        type=type,
        update=msg,
    )
    db.session.add(new_update)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 200

@app.route('/get_disasters', methods=['GET'])
def get_disasters():
    try:
        disasters = []
        storm_url = f"https://api.openweathermap.org/data/2.5/onecall?lat=0&lon=0&exclude=hourly,daily&appid=7a5d287cea04cae8cf65b769d7dcab48"
        storm_response = requests.get(storm_url)
        if storm_response.status_code == 200:
            storm_data = storm_response.json()
            for alert in storm_data.get("alerts", []):
                disasters.append({
                    "disaster_type": "Storm",
                    "name": alert.get("event"),
                    "latitude": alert.get("lat"),
                    "longitude": alert.get("lon"),
                    "description": alert.get("description"),
                    "severity": alert.get("severity")
                })

        earthquake_response = requests.get("https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&limit=5")
        if earthquake_response.status_code == 200:
            earthquake_data = earthquake_response.json()
            for feature in earthquake_data.get("features", []):
                earthquake_properties = feature.get("properties", {})
                earthquake_geometry = feature.get("geometry", {})
                magnitude = earthquake_properties.get("mag")
                place = earthquake_properties.get("place")
                latitude = earthquake_geometry.get("coordinates", [])[1]
                longitude = earthquake_geometry.get("coordinates", [])[0]
                disasters.append({
                    "disaster_type": "Earthquake",
                    "name": place,
                    "latitude": latitude,
                    "longitude": longitude,
                    "magnitude": magnitude
                })

        wildfire_response = requests.get("https://firms.modaps.eosdis.nasa.gov/api/active_fire/v2")
        if wildfire_response.status_code == 200:
            wildfire_data = wildfire_response.json()
            for fire in wildfire_data.get("activeFire", []):
                disasters.append({
                    "disaster_type": "Wildfire",
                    "name": fire.get("name"),
                    "latitude": fire.get("latitude"),
                    "longitude": fire.get("longitude"),
                    "intensity": fire.get("intensity")
                })

        return jsonify({"disasters": disasters}), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/broadcast', methods=['POST'])
def broadca():
    data = request.get_json()
    msg = data.get('msg')
    emit('notification', data, broadcast=True)

@app.route('/cityscore', methods=['POST'])
def scorec():
    data = request.get_json()
    city_name = data.get('city')
    
    city_score_data = otherfunc.calculate_city_score(city_name)

    result = {
        "city_score": city_score_data['total_score'],
        "facilities_count": city_score_data['facilities'],
    }
    
    weakest_sector_data = otherfunc.get_weakest_sector(city_name)
    result["weakest_sector"] = {
        "weakest_sector_name": weakest_sector_data['weakest_sector_name'],
        "facility_count": weakest_sector_data['facility_count'],
        "facilities": weakest_sector_data['facilities']
    }
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True)