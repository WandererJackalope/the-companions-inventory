from flask import Flask, render_template, request
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

@app.route('/')
def index():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT merch_id, name, location, category FROM merchant")
    merchants = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('index.html', merchants=merchants)

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

if __name__ == '__main__':
    app.run(debug=True)

