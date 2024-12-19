from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import requests

app = Flask(__name__)
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
   

@app.route('/nearby-shelters', methods=['POST'])
def nearby_shelters():
    data = request.get_json()
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({"error": "Latitude and Longitude not provided"}), 400

    lat = data['latitude']
    lon = data['longitude']
    shelters = otherfunc.get_nearby_shelters(lat, lon)

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
    disaster_category = otherfunc.get_disaster_prone_category(location)
    first_aid_items = disaster_data.get(disaster_category, disaster_data["general"])

    return jsonify({
        "location": location,
        "disaster_category": disaster_category,
        "first_aid_kit": first_aid_items
    })


if __name__ == "__main__":
    app.run(debug=True)