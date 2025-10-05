from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import sys
import os
import json
import random

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET'])
def index():
    with open('index.html', 'r') as f:
        return f.read()

@app.route('/create', methods=['GET'])
def create():
    with open('create.html', 'r') as f:
        return f.read()

@app.route('/getname', methods=['POST'])
def getname():
    data = request.get_json()
    frequency = data.get('frequency', '-1')
    freq_file = f'frequencies/{frequency}.json'
    if os.path.exists(freq_file):
        with open(freq_file, 'r') as f:
            freq_data = json.load(f)
        return jsonify(freq_data), 200
    else:
        return jsonify({'result': 'false'}), 200

@app.route('/launch', methods=['POST'])
def launch():
    data = request.get_json()
    frequency = data.get('frequency', '-1')
    stationname = data.get('stationname', 'Unnamed Station')
    prompt = data.get('param', 'Empty, topicless podcast where we talk about nothing')
    launch_id = random.randint(1, 100000)

    process = subprocess.Popen([
        sys.executable, 
        'launch_station.py',
        frequency,
        stationname,
        prompt,
        str(launch_id),
    ])

    return jsonify({
        'status': 'pending',
        'launch_id': launch_id
    }), 200

@app.route('/status/<launch_id>', methods=['GET'])
def get_status(launch_id):
    status_file = f'status/{launch_id}.json'
    if not os.path.exists(status_file):
        return jsonify({'status': 'pending'}), 200
    
    with open(status_file, 'r') as f:
        status_data = json.load(f)
    
    return jsonify(status_data), 200

if __name__ == "__main__":
    app.run(debug=True)
