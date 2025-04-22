from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

from config import DB_CONFIG

app = Flask(__name__)

app.secret_key = 'your_secret_key_here'  # use a strong secret in production!

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# Routes to exclude from session check
SESSION_EXEMPT_ROUTES = {'welcome', 'reset_session', 'static'}

@app.before_request
def ensure_player_session():
    endpoint = request.endpoint
    print("Before request — endpoint:", endpoint)

    # Exempt certain routes from session check
    if endpoint is None or endpoint in SESSION_EXEMPT_ROUTES:
        return

    if 'player_name' not in session or 'player_merch_id' not in session:
        flash("Session expired. Please enter your name again.")
        return redirect(url_for('welcome'))
    
# Route to reset session in case of access denied issues
@app.route('/reset')
def reset_session():
    session.clear()
    return redirect(url_for('welcome'))

@app.route('/', methods=['GET', 'POST'])
def welcome():
    if request.method == 'POST':
        player_name = request.form['player_name']
        session['player_name'] = player_name

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # 🔍 Check if player already exists
        cursor.execute("""
            SELECT merch_id FROM merchant 
            WHERE name = %s AND category = 'player'
        """, (player_name,))
        existing_player = cursor.fetchone()

        if existing_player:
            # ✅ Reuse existing merch_id
            player_merch_id = existing_player['merch_id']
        else:
            # ➕ Generate new merch_id
            cursor.execute("SELECT MAX(merch_id) AS max_id FROM merchant")
            result = cursor.fetchone()
            player_merch_id = (result['max_id'] or 0) + 1

            # Insert new player merchant
            cursor.execute("""
                INSERT INTO merchant (merch_id, name, level, location, category, balance, hr_open, hr_close)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (player_merch_id, player_name, 1, 'PlayerSpawn', 'player', 100, '00:00', '23:59'))

            # Add starter inventory
            starter_items = [(101, 1), (102, 1)]  # Example: item_id 1 and 3
            for item_id, qty in starter_items:
                cursor.execute("""
                    INSERT INTO inventory (merch_id, item_id, quantity)
                    VALUES (%s, %s, %s)
                """, (player_merch_id, item_id, qty))

        # 🔐 Save player merch_id in session
        session['player_merch_id'] = player_merch_id

        db.commit()
        cursor.close()
        db.close()

        return redirect(url_for('map'))

    return render_template('welcome.html')

@app.route('/map')
def map():
    # Handle session errors
    if 'player_name' not in session:
        return redirect(url_for('welcome'))
    
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

@app.route('/player/inventory', methods=['GET', 'POST'])
def player_inventory():
    merch_id = session.get('player_merch_id')
    if merch_id is None:
        return redirect(url_for('welcome'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Get player merchant row
    cursor.execute("SELECT * FROM merchant WHERE merch_id = %s", (merch_id,))
    merchant = cursor.fetchone()

    # Get player's inventory
    cursor.execute("""
        SELECT i.item_id, i.name, i.description, i.buy_cost, i.sell_price, i.weight,
               i.rarity, i.effect_type, i.effect_value, inv.quantity
        FROM inventory inv
        JOIN item i ON inv.item_id = i.item_id
        WHERE inv.merch_id = %s
    """, (merch_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT item_id, name FROM item")
    all_items = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('player.html', merchant=merchant, items=items, all_items=all_items)

@app.route('/player/modify_inventory', methods=['POST'])
def modify_inventory():
    merch_id = session.get('player_merch_id')
    if merch_id is None:
        return redirect(url_for('welcome'))

    try:
        item_id = int(request.form['item_id'])
        quantity = int(request.form['quantity'])
        action = request.form['action']
    except (ValueError, KeyError):
        print("Invalid form data received.")
        return redirect(url_for('player_inventory'))

    print(f"[MODIFY] merch_id={merch_id}, item_id={item_id}, quantity={quantity}, action={action}")

    db = get_db_connection()
    cursor = db.cursor()

    if action == 'add':
        cursor.execute("""
            INSERT INTO inventory (merch_id, item_id, quantity)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE quantity = quantity + %s
        """, (merch_id, item_id, quantity, quantity))

    elif action == 'remove':
        cursor.execute("""
            SELECT quantity FROM inventory WHERE merch_id = %s AND item_id = %s
        """, (merch_id, item_id))
        result = cursor.fetchone()
        if result:
            current_qty = result[0]
            new_qty = current_qty - quantity
            if new_qty > 0:
                cursor.execute("""
                    UPDATE inventory SET quantity = %s
                    WHERE merch_id = %s AND item_id = %s
                """, (new_qty, merch_id, item_id))
            else:
                cursor.execute("""
                    DELETE FROM inventory
                    WHERE merch_id = %s AND item_id = %s
                """, (merch_id, item_id))

    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for('player_inventory'))


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

