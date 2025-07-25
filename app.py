from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_mail import Mail, Message
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = 'mysecretkey123'

# Mail configuration (configure your email/password)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_email_password'
mail = Mail(app)

# Initialize DB
def init_db():
    with sqlite3.connect('library.db') as con:
        cur = con.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    email TEXT,
    password TEXT,
    role TEXT
)
''')
        cur.execute('''CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            author TEXT,
            category TEXT,
            available INTEGER DEFAULT 1
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS issued_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            book_id INTEGER,
            issue_date TEXT,
            due_date TEXT,
            returned INTEGER DEFAULT 0
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS book_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            book_title TEXT,
            request_date TEXT
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS contact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            message TEXT
        )''')
        cur.execute("SELECT * FROM users WHERE role = 'admin'")
        admin_exists = cur.fetchone()
        
        # If no admin user, create one with default credentials
        if not admin_exists:
            default_admin = ('admin', 'admin@example.com', 'admin123', 'admin')
            cur.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)", default_admin)
            con.commit()
            print("Default admin user created: email='admin@example.com', password='admin123'")

init_db()

# Home page
@app.route('/')
def landing():
    return render_template('landing.html')

# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        with sqlite3.connect('library.db') as con:
            cur = con.cursor()

            # Check if email already exists
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            existing_user = cur.fetchone()

            if existing_user:
                flash('User already exists. Please login to continue.', 'warning')
                return redirect('/login')

            # Insert new user
            cur.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                        (username, email, password, role))
            con.commit()
            flash('Registration successful. Please login.', 'success')
            return redirect('/login')

    return render_template('register.html')


# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        with sqlite3.connect('library.db') as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM users WHERE email=? AND password=? AND role=?", (email, password, role))
            user = cur.fetchone()
            if user:
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[4]
                return redirect('/dashboard')
            else:
                flash('Invalid credentials')
    return render_template('login.html')

# Dashboard (role-based)
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('dashboard.html')
# Manage Books (Admin)
@app.route('/manage-books', methods=['GET', 'POST'])
def manage_books():
    if session.get('role') != 'admin':
        return redirect('/dashboard')
    with sqlite3.connect('library.db') as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        if request.method == 'POST':
            title = request.form['title']
            author = request.form['author']
            category = request.form['category']
            cur.execute("INSERT INTO books (title, author, category) VALUES (?, ?, ?)", (title, author, category))
            con.commit()
            flash('Book added successfully', 'success')
        cur.execute("SELECT * FROM books")
        books = cur.fetchall()
    return render_template('manage_books.html', books=books)

# Delete book route
@app.route('/delete-book/<int:book_id>')
def delete_book(book_id):
    if session.get('role') != 'admin':
        return redirect('/dashboard')
    with sqlite3.connect('library.db') as con:
        cur = con.cursor()
        # Optional: Also delete issued_books related to this book?
        cur.execute("DELETE FROM books WHERE id=?", (book_id,))
        con.commit()
    flash('Book deleted successfully', 'success')
    return redirect(url_for('manage_books'))

# Issue & Return Books (Admin)
@app.route('/issue-return', methods=['GET', 'POST'])
def issue_return():
    if session.get('role') != 'admin':
        return redirect('/dashboard')

    with sqlite3.connect('library.db') as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        if request.method == 'POST':
            username = request.form['username']
            book_id = request.form['book_id']
            action = request.form['action']
            issue_date_str = request.form['issue_date']

            # Lookup user_id by username
            cur.execute("SELECT id FROM users WHERE username=?", (username,))
            user = cur.fetchone()
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for('issue_return'))
            user_id = user['id']

            # Check if book exists and availability
            cur.execute("SELECT available FROM books WHERE id=?", (book_id,))
            book = cur.fetchone()
            if not book:
                flash("Book not found.", "danger")
                return redirect(url_for('issue_return'))

            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()

            if action == 'issue':
                if book['available'] == 0:
                    flash("Book is currently not available.", "warning")
                    return redirect(url_for('issue_return'))

                due_date = issue_date + timedelta(days=14)
                cur.execute("INSERT INTO issued_books (user_id, book_id, issue_date, due_date, returned) VALUES (?, ?, ?, ?, 0)",
                            (user_id, book_id, issue_date.isoformat(), due_date.isoformat()))
                cur.execute("UPDATE books SET available=0 WHERE id=?", (book_id,))
                con.commit()
                flash("Book issued successfully.", "success")

            elif action == 'return':
                # Find the issued_books entry that is not returned yet
                cur.execute("""SELECT id FROM issued_books
                               WHERE user_id=? AND book_id=? AND returned=0""",
                            (user_id, book_id))
                issued_book = cur.fetchone()
                if not issued_book:
                    flash("No issued record found for this user and book.", "warning")
                    return redirect(url_for('issue_return'))

                issued_book_id = issued_book['id']
                return_date = issue_date.isoformat()
                cur.execute("UPDATE issued_books SET returned=1 WHERE id=?", (issued_book_id,))
                cur.execute("UPDATE books SET available=1 WHERE id=?", (book_id,))
                con.commit()
                flash("Book returned successfully.", "success")

        # Show all issued books with user and book details
        cur.execute("""
            SELECT i.id, u.username, b.title, i.issue_date, i.due_date, i.returned
            FROM issued_books i
            JOIN users u ON i.user_id = u.id
            JOIN books b ON i.book_id = b.id
        """)
        issued = cur.fetchall()

    return render_template('issue_return.html', issued=issued, datetime=datetime)

# Reports (Admin)
@app.route('/reports', methods=['GET', 'POST'])
def reports():
    if session.get('role') != 'admin':
        return redirect('/dashboard')

    report_type = 'daily'  # default
    today = datetime.now().date()

    with sqlite3.connect('library.db') as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        if request.method == 'POST':
            report_type = request.form.get('report_type', 'daily')

        if report_type == 'daily':
            start_date = today
        elif report_type == 'weekly':
            start_date = today - timedelta(days=7)
        elif report_type == 'monthly':
            start_date = today - timedelta(days=30)
        else:
            start_date = today

        cur.execute("""
            SELECT u.username, b.title, i.issue_date, 
                   CASE WHEN i.returned=1 THEN i.due_date ELSE NULL END as return_date
            FROM issued_books i
            JOIN users u ON i.user_id = u.id
            JOIN books b ON i.book_id = b.id
            WHERE i.issue_date >= ?
            ORDER BY i.issue_date DESC
        """, (start_date.isoformat(),))
        reports = cur.fetchall()

    return render_template('reports.html', reports=reports, report_type=report_type)

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# Book Gallery
@app.route('/book_gallery')
def book_gallery():
    categories = [
        {
            'name': 'Mathematics',
            'image': 'math.jpg',
            'description': 'Books related to mathematics and problem solving.'
        },
        {
            'name': 'Programming',
            'image': 'programming.webp',
            'description': 'Coding, algorithms, and software development books.'
        },
        {
            'name': 'Self-help',
            'image': 'selfhelp.jpg',
            'description': 'Books for personal growth and motivation.'
        },
        {
            'name': 'Aptitude',
            'image': 'aptitude.jpg',
            'description': 'Books for clearing competitive exams.'
        },
        {
            'name': 'Physics',
            'image': 'physics.avif',
            'description': 'Explore Physics books here'
        },
        {
            'name': 'Chemistry',
            'image': 'chemistry.avif',
            'description': 'Explore Chemistry books here'
        },
        {
            'name' : 'Electrical',
            'image': 'electrical.jpg',
            'description': 'Explore Electrical books here'
        },
        {
            'name': 'Fiction',
            'image': 'fiction.jpg',
            'description': 'Explore Physics books here'
        },
        {
            'name' : 'Geography',
            'image' : 'geography.png',
            'description': 'Explore Geography books here'
        },
        {
            'name' : 'Mythology',
            'image' : 'mythology.jpg',
            'description' : 'Explore Mythology books here'
        },
        {
            'name' : 'History',
            'image' : 'history.jpg',
            'description' : 'Explore History books here'
        },
        {
            'name' : 'Comic',
            'image' : 'comic.png',
            'description' : 'Explore Comic books here'

        },
        {
            'name' : 'Fairy Tale',
            'image' : 'fairy tale.webp',
            'description' : 'Explore Fairy Tale books here'

        },
        {
            'name' : 'Zoology',
            'image' : 'zoology.avif',
            'description' : 'Explore Zoology books here'

        }
    ]

        
    return render_template('book_gallery.html', categories=categories)


# Manage Books (Admin)
# @app.route('/manage-books', methods=['GET', 'POST'])
# def manage_books():
#     if session.get('role') != 'admin':
#         return redirect('/dashboard')
#     with sqlite3.connect('library.db') as con:
#         cur = con.cursor()
#         if request.method == 'POST':
#             title = request.form['title']
#             author = request.form['author']
#             category = request.form['category']
#             cur.execute("INSERT INTO books (title, author, category) VALUES (?, ?, ?)", (title, author, category))
#             con.commit()
#         cur.execute("SELECT * FROM books")
#         books = cur.fetchall()
#     return render_template('manage_books.html', books=books)

# # Issue & Return Books (Admin)
# @app.route('/issue-return', methods=['GET', 'POST'])
# def issue_return():
#     if session.get('role') != 'admin':
#         return redirect('/dashboard')
#     with sqlite3.connect('library.db') as con:
#         cur = con.cursor()
#         if request.method == 'POST':
#             user_id = request.form['user_id']
#             book_id = request.form['book_id']
#             issue_date = datetime.now().date()
#             due_date = issue_date + timedelta(days=14)
#             cur.execute("INSERT INTO issued_books (user_id, book_id, issue_date, due_date) VALUES (?, ?, ?, ?)",
#                         (user_id, book_id, issue_date.isoformat(), due_date.isoformat()))
#             cur.execute("UPDATE books SET available=0 WHERE id=?", (book_id,))
#             con.commit()
#         cur.execute("SELECT * FROM issued_books")
#         issued = cur.fetchall()
#     return render_template('issue_return.html', issued=issued)

# # View Issued Books (User)
@app.route('/my-books')
def my_books():
    if session.get('role') not in ['student', 'faculty']:
        return redirect('/dashboard')

    user_id = session['user_id']
    con = sqlite3.connect('library.db')
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute('''
        SELECT b.title, i.issue_date, i.due_date, i.returned
        FROM issued_books i
        JOIN books b ON i.book_id = b.id
        WHERE i.user_id = ?
    ''', (user_id,))
    issued_books = cur.fetchall()

    cur.execute('''
        SELECT book_title AS title, request_date
        FROM book_requests
        WHERE user_id = ?
    ''', (user_id,))
    requested_books = cur.fetchall()
    con.close()

    return render_template('my_books.html', issued_books=issued_books, requested_books=requested_books)

# # Reports (Admin)
# @app.route('/reports')
# def reports():
#     if session.get('role') != 'admin':
#         return redirect('/dashboard')
#     today = datetime.now().date()
#     with sqlite3.connect('library.db') as con:
#         cur = con.cursor()
#         cur.execute("SELECT * FROM issued_books WHERE issue_date=?", (today.isoformat(),))
#         daily = cur.fetchall()
#         cur.execute("SELECT * FROM issued_books WHERE issue_date >= ?", ((today - timedelta(days=7)).isoformat(),))
#         weekly = cur.fetchall()
#         cur.execute("SELECT * FROM issued_books WHERE issue_date >= ?", ((today - timedelta(days=30)).isoformat(),))
#         monthly = cur.fetchall()
#     return render_template('reports.html', daily=daily, weekly=weekly, monthly=monthly)

# Request a Book (User)
@app.route('/request-book', methods=['GET', 'POST'])
def request_book():
    if session.get('role') not in ['student', 'faculty']:
        return redirect('/dashboard')
    if request.method == 'POST':
        book_title = request.form['book_title']
        with sqlite3.connect('library.db') as con:
            cur = con.cursor()
            cur.execute("INSERT INTO book_requests (user_id, book_title, request_date) VALUES (?, ?, ?)",
                        (session['user_id'], book_title, datetime.now().date()))
            con.commit()
        flash("Book request sent!")
    return render_template('request_book.html')

# Contact
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        with sqlite3.connect('library.db') as con:
            cur = con.cursor()
            cur.execute("INSERT INTO contact (name, email, message) VALUES (?, ?, ?)", (name, email, message))
            con.commit()
        flash("Message sent successfully!")
    return render_template('contact.html')
@app.route('/books/<category>', methods=['GET', 'POST'])
def view_books_by_category(category):
    category_key = category.replace('-', ' ').lower()

    books_by_category = {
        "mathematics": [
            {"title": "Calculus Made Easy", "author": "Silvanus P. Thompson", "image": "calculus.jpg"},
            {"title": "Linear Algebra Done Right", "author": "Sheldon Axler", "image": "linear_algebra.jpg"}
        ],
        "programming": [
            {"title": "Python Crash Course", "author": "Eric Matthes", "image": "python_crash.jpg"},
            {"title": "The Complete Reference Book Java", "author": "Herbert Schildt", "image": "java.jpg"},
            {"title": "Data Science : A Modern Approach for Analytics with Python", "author": "C Sudheer Kumar", "image": "data_analytics.jpg"}
        ],
        "self help": [
            {"title": "Atomic Habits", "author": "James Clear", "image": "atomic_habits.webp"},
            {"title": "The Power of Now", "author": "Eckhart Tolle", "image": "power_now.jpg"}
        ],
        "aptitude": [
            {"title": "Quantitative Aptitude", "author": "R.S. Aggarwal", "image": "aptitude.jpg"}
        ],
        "physics": [
            {"title": "Concepts of Physics", "author": "H.C. Verma", "image": "concepts_physics.jpg"}
        ],
        "chemistry": [
            {"title": "Organic Chemistry", "author": "Paula Y. Bruice", "image": "organic_chem.jpg"}
        ],
        "electrical": [
            {"title": "Basic Electrical Engineering", "author": "V.K. Mehta", "image": "electrical_basics.jpg"}
        ],
        "fiction": [
            {"title": "The Great Gatsby", "author": "F. Scott Fitzgerald", "image": "gatsby.jpg"}
        ],
        "geography": [
            {"title": "Geography of India", "author": "Majid Husain", "image": "geography_india.jpeg"}
        ],
        "mythology": [
            {"title": "Indian Mythology", "author": "Devdutt Pattanaik", "image": "indian_myth.jpg"}
        ],
        "history": [
            {"title": "A People's History of the United States", "author": "Howard Zinn", "image": "us_history.jpg"}
        ],
        "comic": [
            {"title": "Watchmen", "author": "Alan Moore", "image": "watchmen.webp"}
        ],
        "fairy tale": [
            {"title": "Grimm's Fairy Tales", "author": "Brothers Grimm", "image": "grimm.jpg"}
        ],
        "zoology": [
            {"title": "Secret world of Animals", "author": "Smithsonian", "image": "zoology_animals.jpg"}
        ]
    }

    books = books_by_category.get(category_key, [])

    if request.method == 'POST':
        if 'user_id' in session:
            book_title = request.form['book_title']
            with sqlite3.connect('library.db') as con:
                cur = con.cursor()
                cur.execute("INSERT INTO book_requests (user_id, book_title, request_date) VALUES (?, ?, ?)",
                            (session['user_id'], book_title, datetime.now().date()))
                con.commit()
            flash('Thank you for submitting your request!')
            return redirect(request.url)
        else:
            flash("You must be logged in to request a book.")
            return redirect(url_for('login'))

    return render_template('books_by_category.html', category=category_key.title(), books=books)




if __name__ == '__main__':
    app.run(debug=True)
