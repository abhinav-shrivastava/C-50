from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    items = []
    portfolio = db.execute("SELECT * FROM portfolio WHERE user_id = :user_id", user_id=session["user_id"])
    cash = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])[0].get('cash')
    stocks = 0
    for stock in portfolio:
        stock_value = lookup(stock["stock_symbol"]).get('price')
        items.append({'stock_name': stock.get('stock_name'), 'price': stock_value, 'quantity': stock.get('num_stocks'), 'total': stock.get('num_stocks') * stock_value})
        stocks += stock.get('num_stocks') * stock_value
    grand_total = cash + stocks
    return render_template("index.html", items=items, cash=cash, grand_total=grand_total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # ensure stock symbol was submitted
        stock_id = request.form.get("stock_symbol")
        if not stock_id:
            return apology("must provide stock symbol")
        
        # parse quantity
        try:    
            quantity = int(request.form.get("quantity", 0))
        except:
            return apology("not a valid quantity")

        # validate quantity
        if not quantity:
            return apology("must provide quantity")
        elif quantity < 0:
            return apology("must provide positive quantity")
        
        quote = lookup(stock_id)
        if quote:
            # if stock symbol is valid, verify user has enough cash to buy it
            rows = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])
            cash = rows[0].get('cash')
            transaction_amt = quote.get('price') * quantity
            if transaction_amt > cash:
                return apology("Insufficient Funds :/")
            
            # complete the purchase and update the balance
            db.execute("UPDATE users SET cash=:cash WHERE id=:user_id", cash=(cash - transaction_amt), user_id=session["user_id"])
            
            # reflect the purchase in user's stock portfolio
            rows = db.execute("SELECT * FROM portfolio WHERE stock_symbol = :stock_id", stock_id=stock_id)
            if rows:
                db.execute("UPDATE portfolio SET num_stocks=:num_stocks WHERE stock_symbol=:stock_id", num_stocks=quantity + rows[0].get('num_stocks', 0), stock_id=stock_id)
            else:
                db.execute("INSERT INTO portfolio (user_id, stock_symbol, stock_name, num_stocks) VALUES (:user_id, :stock_symbol, :stock_name, :num_stocks)", user_id=session["user_id"], stock_symbol=stock_id, stock_name=quote.get('name'), num_stocks=quantity)

            # add transaction history
            row_id = db.execute("INSERT INTO transactions (user_id,stock_name,price,quantity,action) VALUES (:user_id,:stock_name,:price,:quantity,:action)", user_id=session["user_id"], stock_name=quote.get('name'), price=quote.get('price'), quantity=quantity, action="BUY")
            return render_template("quoted.html", statement="transaction successful")
        else:
            return apology("{} is not a valid stock symbol".format(request.form.get("stock_symbol")))
    
    #  else if user reached route via GET
    return render_template("buy.html")

@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Adds specified amount to the user's account"""
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # validate amount
        amount = request.form.get("amount")
        if not amount:
            return apology("must provide amount")
        try:
            amount = int(amount)
        except:
            return apology("not a number")
        
        # update cash
        cash = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])[0].get('cash')
        db.execute("UPDATE users SET cash=:cash WHERE id=:user_id", cash=(cash + amount), user_id=session["user_id"])
        return index()
    
    #  else if user reached route via GET
    return render_template("add_cash.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    rows = db.execute("SELECT * FROM transactions WHERE user_id = :user_id", user_id=session["user_id"])
    if rows:
        return render_template("history.html", items=rows)
    return apology("No Transactions yet!")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # ensure stock symbol was submitted
        if not request.form.get("stock_symbol"):
            return apology("must provide stock symbol")
        
        quote = lookup(request.form.get("stock_symbol"))
        if quote:
            statement = "One stock of {} is valued at ${}".format(quote.get('name'), quote.get('price'))
        else:
            statement = "{} is not a valid stock symbol".format(request.form.get("stock_symbol"))
        return render_template("quoted.html", statement=statement)
    
    #  else if user reached route via GET
    return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    
    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")
            
        # ensure retype_password was submitted
        elif not request.form.get("retype_password"):
            return apology("must retype password")
            
        # ensure password and retype password fields matches
        elif request.form.get("password") != request.form.get("retype_password"):
            return apology("password and retype password doesn't match!")

        # check if username is not taken
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username doesn't exists
        if len(rows) == 1:
            return apology("Username already taken, try something else!")

        # add username, password hash into database
        row_id = db.execute("INSERT INTO users (username,hash) VALUES (:username,:hash)", username=request.form.get("username"), hash=pwd_context.encrypt(request.form.get("password")))

        # remember which user has logged in
        session["user_id"] = row_id

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # ensure stock symbol was submitted
        stock_id = request.form.get("stock_symbol")
        if not stock_id:
            return apology("must provide stock symbol")
        
        # parse quantity
        try:    
            quantity = int(request.form.get("quantity", 0))
        except:
            return apology("not a valid quantity")

        # validate quantity
        if not quantity:
            return apology("must provide quantity")
        elif quantity < 0:
            return apology("must provide positive quantity")
        
        quote = lookup(stock_id)
        if quote:
            # if stock exists get price
            transaction_amt = quote.get('price') * quantity
            
            # verify user has required number of stocks
            rows = db.execute("SELECT * FROM portfolio WHERE stock_symbol = :stock_id", stock_id=stock_id)
            if rows and rows[0].get('num_stocks', 0) > 0:
                db.execute("UPDATE portfolio SET num_stocks=:num_stocks WHERE stock_symbol=:stock_id", num_stocks=quantity - rows[0].get('num_stocks', 0), stock_id=stock_id)
            else:
                return apology("You don't have that many stocks") if rows else apology("You can't sell what you don't own")

            # complete the sale and reflect the balance
            rows = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])
            db.execute("UPDATE users SET cash=:cash WHERE id=:user_id", cash=(rows[0].get('cash') + transaction_amt), user_id=session["user_id"])
            
            # add transaction history
            row_id = db.execute("INSERT INTO transactions (user_id,stock_name,price,quantity,action) VALUES (:user_id,:stock_name,:price,:quantity,:action)", user_id=session["user_id"], stock_name=quote.get('name'), price=quote.get('price'), quantity=quantity, action="SELL")
            return render_template("quoted.html", statement="transaction successful")
        else:
            return apology("{} is not a valid stock symbol".format(request.form.get("stock_symbol")))
    
    #  else if user reached route via GET
    return render_template("sell.html")
