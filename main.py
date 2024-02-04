from flask import Flask
from flask import render_template
from flask import request
from flask import jsonify
import sqlite3
import time

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_data', methods=['GET'])
def send_data():
        # data = request.args.get('data')
        gas_ppm = request.args.get('gas_ppm') # ppm
        trash_capacity = request.args.get('trash_capacity') # percentage
        trash_can_id = request.args.get('trash_can_id')
        data_date = time.strftime("%Y-%m-%d %H:%M:%S")
        # return render_template('dashboard.html', gas_ppm=str(gas_ppm), trash_capacity=trash_capacity, data_date=data_date)
        
        conn = sqlite3.connect('database.sqlite3')
        conn.cursor().execute("INSERT INTO data (gas_ppm, trash_capacity, trash_can_id, data_date) VALUES (?, ?, ?, ?)", (gas_ppm, trash_capacity, trash_can_id, data_date))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/get_data')
def get_data():
    conn = sqlite3.connect('database.sqlite3')
    fetch = conn.cursor().execute("SELECT * FROM data ORDER BY id DESC LIMIT 32")
    data = fetch.fetchall()
    # print(data)
    ids = [ x[0] for x in data ]
    gas_ppms = [ x[1] for x in data ]
    trash_capacities = [ x[2] for x in data ]
    last_trash_pickups = [x[3] if x[3] is not None else '-' for x in data]
    data_date = [ x[4] for x in data ]
    print(ids)
    print(gas_ppms)
    print(trash_capacities)
    print(last_trash_pickups)
    print(data_date)
    return jsonify({'success': True, 'ids': ids, 'gas_ppms': gas_ppms, 'trash_capacities': trash_capacities, 'last_trash_pickups': last_trash_pickups, 'data_date': data_date})

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

app.run(host='0.0.0.0', port=80, debug=True)