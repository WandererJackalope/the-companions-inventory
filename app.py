import logging

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
    player_id = session.get('player_merch_id')
    if player_id is None:
        return redirect(url_for('welcome'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # merchant info + inventory
    cursor.execute("SELECT * FROM merchant WHERE merch_id = %s", (merch_id,))
    merchant = cursor.fetchone()
    cursor.execute("""
        SELECT i.item_id, i.name, i.description, i.buy_cost, i.sell_price, i.weight,
               i.rarity, i.effect_type, i.effect_value, inv.quantity
        FROM inventory inv
        JOIN item i ON inv.item_id = i.item_id
        WHERE inv.merch_id = %s
    """, (merch_id,))
    merchant_items = cursor.fetchall()

    # player info & player inventory
    cursor.execute("SELECT balance, name FROM merchant WHERE merch_id = %s", (player_id,))
    player = cursor.fetchone()
    cursor.execute("""
        SELECT i.item_id, i.name, i.description, i.buy_cost, i.sell_price, i.weight,
               i.rarity, i.effect_type, i.effect_value, inv.quantity
        FROM inventory inv
        JOIN item i ON inv.item_id = i.item_id
        WHERE inv.merch_id = %s
    """, (player_id,))
    player_items = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        'trade.html',
        merchant=merchant,
        items=merchant_items,
        player=player,
        player_items=player_items,
        error=request.args.get('error')    # grab any error
    )
  
@app.route('/trade/<int:merch_id>/transaction', methods=['POST'])
def buy(merch_id):
    error = None
    player_merch_id = session.get('player_merch_id')
    if player_merch_id is None:
        return redirect(url_for('welcome'))
    try:
        # Item id of the item to be bought
        item_id = int(request.form['item_id'])
        # Amount of items in inventory
        item_stock = int(request.form['item_stock'])
        # Amount of items to be bought or sold
        quantity = int(request.form['quantity'])
        # Cost of the item
        buy_sell_amt = float(request.form['buy_sell_amt'])
        # Player's balance
        player_balance = float(request.form['player_balance'])
        # Merchant's balance
        merchant_balance = float(request.form['merchant_balance'])
        # action
        action = request.form['action']
    except (ValueError, KeyError):
        print("Invalid form data received.")
        return redirect(url_for('trade', merch_id=merch_id))

    total_buy_sell_amt: float = buy_sell_amt * quantity
    
    if action == 'buy':
        if total_buy_sell_amt > player_balance:
            error = 'Insufficient funds'
    elif action == 'sell':
        if total_buy_sell_amt > merchant_balance:
            error = 'Merchant has insufficient funds'
            
    if quantity > item_stock:
        error = 'Not enough items in inventory'
    elif quantity <= 0:
        error = 'Invalid quantity'
        
    if action == 'buy' and error is None:
        db = get_db_connection()
        cursor = db.cursor()
        # Update player's balance
        cursor.execute("""
                       UPDATE merchant
                       SET balance = %s
                       WHERE merch_id = %s
                       """, (player_balance - total_buy_sell_amt, player_merch_id))
        # Update merchant's balance
        cursor.execute("""
                       UPDATE merchant
                       SET balance = %s
                       WHERE merch_id = %s
                       """, (merchant_balance + total_buy_sell_amt, merch_id))
        # Update inventory
        if quantity == item_stock:
            cursor.execute("""
                           UPDATE inventory SET merch_id = %s
                           WHERE merch_id = %s AND item_id = %s
                           """, (player_merch_id, merch_id, item_id))
        else:
            cursor.execute("""
                           UPDATE inventory SET quantity = quantity - %s
                           WHERE merch_id = %s AND item_id = %s
                           """, (quantity, merch_id, item_id))
            cursor.execute("""
                           INSERT INTO inventory (merch_id, item_id, quantity)
                           VALUES (%s, %s, %s)
                           ON DUPLICATE KEY UPDATE quantity = quantity + %s
                           """, (player_merch_id, item_id, quantity, quantity))
        db.commit()
        cursor.close()
        db.close()
        
        if action == 'sell' and error is None:
            db = get_db_connection()
            cursor = db.cursor()
            # Update player's balance
            cursor.execute("""
                           UPDATE merchant
                           SET balance = %s
                           WHERE merch_id = %s
                           """, (player_balance + total_buy_sell_amt, player_merch_id))
            # Update merchant's balance
            cursor.execute("""
                           UPDATE merchant
                           SET balance = %s
                           WHERE merch_id = %s
                           """, (merchant_balance - total_buy_sell_amt, merch_id))
            # Update inventory
            if quantity == item_stock:
                cursor.execute("""
                               UPDATE inventory SET merch_id = %s
                               WHERE merch_id = %s AND item_id = %s
                               """, (merch_id, player_merch_id, item_id))
            else:
                cursor.execute("""
                               UPDATE inventory SET quantity = quantity + %s
                               WHERE merch_id = %s AND item_id = %s
                               """, (quantity, merch_id, item_id))
                cursor.execute("""
                               INSERT INTO inventory (merch_id, item_id, quantity)
                               VALUES (%s, %s, %s)
                               ON DUPLICATE KEY UPDATE quantity = quantity - %s
                               """, (player_merch_id, item_id, quantity, quantity))
            db.commit()
            cursor.close()
            db.close()
    
    logging.info(f"[MODIFY] merch_id={merch_id}, item_id={item_id}, quantity={quantity}, total_buy_sell_amt={total_buy_sell_amt}, update_balance={player_balance - total_buy_sell_amt}")
        
    return redirect(url_for('trade', merch_id=merch_id, error=error))
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

@app.route('/merchants/list/')
def merchants_list():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Get player merchant info from database
    player_merch_id = session.get('player_merch_id')
    player = None
    if player_merch_id:
        cursor.execute("SELECT * FROM merchant WHERE merch_id = %s", (player_merch_id,))
        player = cursor.fetchone()

    # Get all npc merchants from database
    cursor.execute("SELECT * FROM merchant WHERE category != 'player'")
    merchants = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('merchants-list.html', player=player, merchants=merchants)

@app.route('/merchant/<int:merch_id>')
def merchant_inventory(merch_id):
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

    # Get all the unique items from database
    cursor.execute("SELECT item_id, name FROM item")
    all_items = cursor.fetchall()

    cursor.close()
    db.close()
    return render_template('merchant.html', merchant=merchant, items=items, all_items=all_items)

@app.route('/merchant/modify_inventory', methods=['POST'])
def modify_merchant_inventory():
    merch_id = request.form.get('merch_id')
    if merch_id is None:
        return redirect(url_for('merchants_list'))

    try:
        item_id = int(request.form['item_id'])
        quantity = int(request.form['quantity'])
        action = request.form['action']
    except (ValueError, KeyError):
        print("Invalid form data received.")
        return redirect(url_for('merchant_inventory', merch_id=merch_id))

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

    return redirect(url_for('merchant_inventory', merch_id=merch_id))

@app.route('/merchant/adjust_balance', methods=['POST'])
def adjust_balance():
    merch_id = request.form.get('merch_id')
    if merch_id is None:
        return redirect(url_for('merchants_list'))
    
    try:
        merch_id = int(request.form['merch_id'])
        amount = float(request.form['amount'])
        action = request.form['action']
    except (ValueError, KeyError):
        print("Invalid form data received.")
        return redirect(url_for('merchants_list'))
    
    print(f"[BALANCE ADJUST] merch_id={merch_id}, amount={amount}, action={action}")
    
    if amount < 0:
        flash("Amount cannot be negative.")
        return redirect(url_for('merchant_inventory', merch_id=merch_id))
    
    db = get_db_connection()
    cursor = db.cursor()

    if action == 'increase':
        cursor.execute("""
            UPDATE merchant SET balance = balance + %s
            WHERE merch_id = %s             
        """, (amount, merch_id))
    elif action == 'decrease':
        cursor.execute("""
            SELECT balance FROM merchant WHERE merch_id = %s
        """, (merch_id,))
        result = cursor.fetchone()

        if result:
            current_balance = result[0]
            if current_balance >= amount:
                cursor.execute("""
                    UPDATE merchant SET balance = balance - %s
                    WHERE merch_id = %s             
                """, (amount, merch_id))
            else:
                flash(f"Cannot decrease by ${amount: .2f}. Merchant only has ${current_balance:.2f}")
                return redirect(url_for('merchant_inventory', merch_id=merch_id))
        else:
            flash("Merchant not found.")
            return redirect(url_for('merchants_list'))
    
    db.commit()
    cursor.close()
    db.close()

    return redirect(url_for('merchant_inventory', merch_id=merch_id))

if __name__ == '__main__':
    app.run(debug=True)
