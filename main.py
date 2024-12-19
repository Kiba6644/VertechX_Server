from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from libretranslatepy import LibreTranslateAPI
import moviepy as mp
import torchaudio
import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline, WhisperProcessor, WhisperForConditionalGeneration
import requests

app = Flask(__name__)
lt = LibreTranslateAPI("https://libretranslate.de/")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dasd'
db = SQLAlchemy(app)

disaster_data = {
    "coastal": ["Waterproof bandages", "Burn cream", "Antibiotic ointment", "Gauze pads", "Emergency thermal blanket"],
    "earthquake-prone": ["Gloves", "Dust masks", "Adhesive bandages", "Pain relievers", "Whistle"],
    "flood-prone": ["Water purification tablets", "Antiseptic wipes", "Adhesive bandages", "Tweezers", "Flashlight"],
    "general": ["Adhesive bandages", "Antibiotic ointment", "Scissors", "Thermometer", "Alcohol wipes"]
}

class Admin_users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    password = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(10))
    age = db.Column(db.Integer)
    gender = db.Column(db.Boolean)  

with app.app_context():
    db.create_all()

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
    
        try:
            url = "https://overpass-api.de/api/interpreter"
            query = f"""
            [out:json];
            node["amenity"="hospital"](around:5000,{lat},{lon});
            out;
            """
            response = requests.get(url, params={"data": query})
            data = response.json()

            hospitals = []
            for element in data.get("elements", []):
                hospitals.append({
                    "name": element.get("tags", {}).get("name", "Unknown Hospital"),
                    "latitude": element["lat"],
                    "longitude": element["lon"],
                    "capacity": element.get("tags", {}).get("capacity", "Unknown")
                })

            return hospitals

        except Exception as e:
            print(f"Error fetching hospitals: {e}")
            return []

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

    def get_nearby_shelters(lat, lon):
        try:
            url = "https://overpass-api.de/api/interpreter"
            query = f"""
            [out:json];
            node["amenity"="shelter"](around:5000,{lat},{lon});
            out;
            """
            response = requests.get(url, params={"data": query})
            data = response.json()

            shelters = []
            for element in data.get("elements", []):
                shelters.append({
                    "name": element.get("tags", {}).get("name", "Unknown Shelter"),
                    "latitude": element["lat"],
                    "longitude": element["lon"],
                    "capacity": element.get("tags", {}).get("capacity", "Unknown")
                })
            return shelters
        except Exception as e:
            print(f"Error fetching shelters: {e}")
            return []
   
    def get_nearby_hospitals(lat, lon):
        try:
            url = "https://overpass-api.de/api/interpreter"
            query = f"""
            [out:json];
            node["amenity"="hospital"](around:5000,{lat},{lon});
            out;
            """
            response = requests.get(url, params={"data": query})
            data = response.json()

            hospitals = []
            for element in data.get("elements", []):
                hospitals.append({
                    "name": element.get("tags", {}).get("name", "Unknown Hospital"),
                    "latitude": element["lat"],
                    "longitude": element["lon"],
                    "capacity": element.get("tags", {}).get("capacity", "Unknown")
                })

            return hospitals

        except Exception as e:
            print(f"Error fetching hospitals: {e}")
            return []

@app.route('/nearby-shelters', methods=['POST'])
def nearby_shelters():
    data = request.get_json()
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({"error": "Latitude and Longitude not provided"}), 400

    lat = data['latitude']
    lon = data['longitude']
    shelters = getloc.get_nearby_shelters(lat, lon)

    return jsonify({
        "latitude": lat,
        "longitude": lon,
        "shelters": shelters
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
    hospitals = getloc.get_nearby_hospitals(lat, lon)

    return jsonify({
        "latitude": lat,
        "longitude": lon,
        "hospitals": hospitals
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

if __name__ == "__main__":
    app.run(debug=True)