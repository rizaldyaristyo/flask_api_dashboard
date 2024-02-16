from flask import Flask
from flask import request
from flask import jsonify
from flask import render_template
from waitress import serve
import tabulate
import sqlite3
import telebot
import signal
import time
import sys
import os
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
bot = telebot.TeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

@app.route('/send_data', methods=['GET'])
def send_data():
        gas_ppm = float(request.args.get('gas_ppm')) # ppm
        trash_capacity = float(request.args.get('trash_capacity')) # percentage
        trash_can_id = float(request.args.get('trash_can_id'))
        data_date = time.strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect('database.sqlite3')

        last_trash_capacity_raw = conn.cursor().execute("SELECT trash_capacity FROM data WHERE trash_can_id = ? ORDER BY id DESC LIMIT 1", (trash_can_id,)).fetchone()
        last_trash_capacity = 0 if last_trash_capacity_raw is None else float(last_trash_capacity_raw[0])
        if last_trash_capacity != 0:
            percentage_change = ((last_trash_capacity - trash_capacity) / last_trash_capacity) * 100
        else:
            percentage_change = 0
        if percentage_change > 50:
            last_trash_pickup = time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_trash_pickup = None

        conn.cursor().execute("INSERT INTO data (gas_ppm, trash_capacity, last_trash_pickup, trash_can_id, data_date) VALUES (?, ?, ?, ?, ?)", (gas_ppm, trash_capacity, last_trash_pickup, trash_can_id, data_date))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

def data_fetcher(trash_can_id):
    conn = sqlite3.connect('database.sqlite3')
    fetch = conn.cursor().execute("SELECT * FROM data WHERE trash_can_id = ? ORDER BY id DESC LIMIT 16", (trash_can_id,))
    data = fetch.fetchall()
    conn.close()

    ids = [ x[0] for x in data ]
    gas_ppms = [ x[1] for x in data ]
    trash_capacities = [ x[2] for x in data ]
    last_trash_pickups = [x[3] if x[3] is not None else '-' for x in data]
    data_date = [ x[4] for x in data ]

    return ids, gas_ppms, trash_capacities, last_trash_pickups, data_date

@app.route('/get_data')
def get_data():
    trash_can_id = request.args.get('trash_can_id')
    ids, gas_ppms, trash_capacities, last_trash_pickups, data_date = data_fetcher(request.args.get('trash_can_id'))
    return jsonify({'success': True, 'ids': ids, 'gas_ppms': gas_ppms, 'trash_capacities': trash_capacities, 'last_trash_pickups': last_trash_pickups, 'data_date': data_date})

@bot.message_handler(commands=['get_data'])
def get_data(message):
    if message.text == "/get_data":
        bot.reply_to(message, "use /get_data followed by trash can id as in ```/get_data 1```", parse_mode='Markdown')
    else:
        ids, gas_ppms, trash_capacities, last_trash_pickups, data_date = data_fetcher(message.text.split(' ', 1)[1])
        heads = ["ID", "GAS", "CAP", "LAST PICK", "DATE"]
        table_data = list(zip(ids, gas_ppms, trash_capacities, last_trash_pickups, data_date))
        table = tabulate.tabulate(table_data, headers=heads, tablefmt="fancy_grid")

        bot.reply_to(message, f"```{table}```", parse_mode="Markdown")


@app.route('/get_last_trash_pickup')
def get_last_trash_pickup():
    conn = sqlite3.connect('database.sqlite3')
    trash_can_id = request.args.get('trash_can_id')
    fetch = conn.cursor().execute("SELECT last_trash_pickup FROM data WHERE trash_can_id = ? AND last_trash_pickup NOT NULL ORDER BY id DESC LIMIT 1", (trash_can_id,)).fetchone()
    last_trash_pickup = "-" if fetch is None else fetch[0]
    return jsonify({'success': True, 'last_trash_pickup': last_trash_pickup})

def last_trash_pickup_setter(trash_can_id):
    conn = sqlite3.connect('database.sqlite3')

    recent = conn.cursor().execute("SELECT * FROM data WHERE trash_can_id = ? ORDER BY id DESC LIMIT 1", (trash_can_id,))
    data = recent.fetchall()
    gas_ppm = [ x[1] for x in data ][0]
    trash_capacity = [ x[2] for x in data ][0]
    last_trash_pickup = data_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.cursor().execute("INSERT INTO data (gas_ppm, trash_capacity, last_trash_pickup, trash_can_id, data_date) VALUES (?, ?, ?, ?, ?)", (gas_ppm, trash_capacity, last_trash_pickup, trash_can_id, data_date))
    conn.commit()
    conn.close()

@bot.message_handler(commands=['reset_wtp'])
def reset_wtp(message):
    if message.text == "/reset_wtp":
        bot.reply_to(message, "use /reset_wtp followed by trash can id as in ```/reset_wtp 1```", parse_mode='Markdown')
    else:
        last_trash_pickup_setter(message.text.split(' ', 1)[1])
        bot.reply_to(message, "done")

@app.route('/set_last_trash_pickup')
def set_last_trash_pickup():
    trash_can_id = request.args.get('trash_can_id')
    last_trash_pickup_setter(trash_can_id)
    return jsonify({'success': True})

def process_fuzzy_recommendation(trash_can_id):
    conn = sqlite3.connect('database.sqlite3')
    fetch = conn.cursor().execute("SELECT * FROM data WHERE trash_can_id = ? ORDER BY id DESC LIMIT 1", (trash_can_id,))
    data = fetch.fetchall()
    gas_ppm = [ x[1] for x in data ][0] 
    trash_capacity = [ x[2] for x in data ][0]
    last_trash_pickup = conn.cursor().execute("SELECT last_trash_pickup FROM data WHERE trash_can_id = ? AND last_trash_pickup NOT NULL ORDER BY id DESC LIMIT 1", (trash_can_id,)).fetchone()[0]
    last_trash_pickup_delta = abs((datetime.now() - datetime.strptime(last_trash_pickup, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600)

    KTS = "LOW" if trash_capacity <= 75 else "HIGH"
    BS = "LOW" if gas_ppm <= 24 else "HIGH"
    WTP = "RECENT"
    if last_trash_pickup_delta > 8 and last_trash_pickup_delta <= 16:
        WTP = "SEMI_RECENT"
    elif last_trash_pickup_delta > 16:
        WTP = "OLD"

    if WTP == "RECENT":
        if KTS == "LOW" and BS == "LOW":
            return "Safe", "Healthy", "R1", WTP, KTS, BS
        elif KTS == "LOW" and BS == "HIGH":
            return "Moderate", "Need cleaning", "R2", WTP, KTS, BS
        elif KTS == "HIGH" and BS == "LOW":
            return "Moderate", "Need cleaning", "R3", WTP, KTS, BS
        elif KTS == "HIGH" and BS == "HIGH":
            return "Unhealthy", "Immediately clean", "R4", WTP, KTS, BS
    elif WTP == "SEMI_RECENT":
        if KTS == "LOW" and BS == "LOW":
            return "Safe", "Healthy", "R5", WTP, KTS, BS
        elif KTS == "LOW" and BS == "HIGH":
            return "Unhealthy", "Immediately clean", "R6", WTP, KTS, BS
        elif KTS == "HIGH" and BS == "LOW":
            return "Unhealthy", "Immediately clean", "R7", WTP, KTS, BS
        elif KTS == "HIGH" and BS == "HIGH":
            return "Unhealthy", "Immediately clean", "R8", WTP, KTS, BS
    elif WTP == "OLD":
        if KTS == "LOW" and BS == "LOW":
            return "Moderate", "Need cleaning", "R9", WTP, KTS, BS
        elif KTS == "LOW" and BS == "HIGH":
            return "Unhealthy", "Immediately clean", "R10", WTP, KTS, BS
        elif KTS == "HIGH" and BS == "LOW":
            return "Unhealthy", "Immediately clean", "R11", WTP, KTS, BS
        elif KTS == "HIGH" and BS == "HIGH":
            return "Unhealthy", "Immediately clean", "R12", WTP, KTS, BS

@app.route('/get_fuzzy_recommendation')
def get_fuzzy_recommendation():
    status, recommendation, category, WTP, KTS, BS = process_fuzzy_recommendation(request.args.get('trash_can_id'))
    return jsonify({'success': True, 'status': status, 'recommendation': recommendation, 'category':category,'WTP':WTP,'KTS':KTS,'BS':BS})

@bot.message_handler(commands=['status'])
def status(message):
    if message.text == "/status":
        bot.reply_to(message, "use /status followed by trash can id as in ```/status 1```", parse_mode='Markdown')
    else:
        status, recommendation, category, WTP, KTS, BS = process_fuzzy_recommendation(message.text.split(' ', 1)[1])
        if status == "Safe":
            bot.reply_to(message, "Status: Safe\nRecommendation: "+recommendation+"\nCategory: "+category+"\nWTP: "+WTP+"\nKTS: "+KTS+"\nBS: "+BS)
        elif status == "Moderate":
            bot.reply_to(message, "Status: Moderate\nRecommendation: "+recommendation+"\nCategory: "+category+"\nWTP: "+WTP+"\nKTS: "+KTS+"\nBS: "+BS)
        elif status == "Unhealthy":
            bot.reply_to(message, "Status: Unhealthy\nRecommendation: "+recommendation+"\nCategory: "+category+"\nWTP: "+WTP+"\nKTS: "+KTS+"\nBS: "+BS)

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/')
def dashboardv2():
    return render_template('dashboardv2.html')

@bot.message_handler(commands=['start', 'help'])
def tutorial(message):
    bot.reply_to(message, "/status to get recommendation, /get_data to get telemetry, /reset_wtp to set last trash pickup to now")

def start_telegram_bot():
    bot.infinity_polling()

tg_thread = Thread(target=start_telegram_bot).start()
def signal_handler(sig, frame):
    print("Server Shutting Down, Please Wait...")
    bot.stop_polling()
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    print("Server Started")
    # app.run(host='0.0.0.0', port=80, debug=False) # Flask's Development WSGI, dev-note: Setting debug to True will ruin the telegram bot
    serve(app, host='0.0.0.0', port=80) # Waitress Production WSGI