from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

from config import DB_CONFIG

app = Flask(__name__)

app.secret_key = 'your_secret_key_here'  # use a strong secret in production!

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

@app.route('/', methods=['GET', 'POST'])
def welcome():
    if request.method == 'POST':
        session['player_name'] = request.form['player_name']
        return redirect(url_for('map'))

    return render_template('welcome.html')

@app.route('/map')
def map():
    # Get list of cities like before
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT DISTINCT location AS name FROM merchant")
    cities = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('map.html', cities=cities, player=session.get('player_name'))

@app.route('/trade/<int:merch_id>')
def trade(merch_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Get merchant info
    cursor.execute("SELECT * FROM merchant WHERE merch_id = %s", (merch_id,))
    merchant = cursor.fetchone()

    # Get merchant's inventory + item details
    cursor.execute("""
        SELECT i.item_id, i.name, i.description, i.buy_cost, i.sell_price, i.weight, 
               i.rarity, i.effect_type, i.effect_value, inv.quantity
        FROM inventory inv
        JOIN item i ON inv.item_id = i.item_id
        WHERE inv.merch_id = %s
    """, (merch_id,))
    items = cursor.fetchall()

    cursor.close()
    db.close()
    return render_template('trade.html', merchant=merchant, items=items)

@app.route('/city/<location>')
def city(location):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Get all merchants from this location
    cursor.execute("SELECT * FROM merchant WHERE location = %s", (location,))
    merchants = cursor.fetchall()

    cursor.close()
    db.close()
    return render_template('city.html', location=location, merchants=merchants)


if __name__ == '__main__':
    app.run(debug=True)

