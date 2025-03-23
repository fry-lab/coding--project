import sqlite3
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Path to the shared database
DATABASE_PATH = "c:/path/to/shared/library.db"

# Base URL of the other library system's API
OTHER_LIBRARY_API_BASE_URL = "http://other-library-system.com/api"

def get_books():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, author, copies FROM books")
    books = cursor.fetchall()
    conn.close()
    return books

@app.route('/')
def home():
    books = get_books()
    return render_template('index.html', books=books)

def borrow_book_in_db(book_id, borrow_date, return_date):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE books SET copies = copies - 1 WHERE id = ? AND copies > 0",
        (book_id,)
    )
    if cursor.rowcount > 0:
        cursor.execute(
            "INSERT INTO borrowed_books (book_id, borrow_date, return_date) VALUES (?, ?, ?)",
            (book_id, borrow_date, return_date)
        )
        conn.commit()
        success = True
    else:
        success = False
    conn.close()
    return success

@app.route('/borrow_book', methods=['POST'])
def borrow_book():
    book_id = request.form['book_id']
    borrow_date = request.form['borrow_date']
    return_date = request.form['return_date']

    # Send borrow request to the other system
    response = requests.post(f"{OTHER_LIBRARY_API_BASE_URL}/borrow", json={
        "book_id": book_id,
        "borrow_date": borrow_date,
        "return_date": return_date
    })

    if response.status_code == 200:
        if borrow_book_in_db(book_id, borrow_date, return_date):
            return jsonify({"message": "Book borrowed successfully!"})
        else:
            return jsonify({"message": "Failed to borrow book!"}), 400
    else:
        return jsonify({"message": "Failed to borrow book!"}), 400

def check_outstanding_books(first_name, last_name):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM borrowed_books
        WHERE student_first_name = ? AND student_last_name = ? AND return_date IS NULL
    """, (first_name, last_name))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

@app.route('/check_outstanding_books', methods=['POST'])
def check_outstanding_books_route():
    data = request.get_json()
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    has_outstanding_books = check_outstanding_books(first_name, last_name)
    return jsonify({"has_outstanding_books": has_outstanding_books})

def get_borrowed_books(first_name, last_name):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.title, bb.borrow_date, bb.return_date,
               DATE(bb.borrow_date, '+7 days') AS due_date,
               CASE
                   WHEN julianday('now') - julianday(DATE(bb.borrow_date, '+7 days')) > 0
                   THEN ROUND((julianday('now') - julianday(DATE(bb.borrow_date, '+7 days'))) * 0.5, 2)
                   ELSE 0
               END AS fees
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
        WHERE bb.student_first_name = ? AND bb.student_last_name = ?
    """, (first_name, last_name))
    books = [
        {
            "id": row[0],
            "title": row[1],
            "borrow_date": row[2],
            "return_date": row[3],
            "due_date": row[4],
            "fees": f"${row[5]:.2f}" if row[5] > 0 else None
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return books

@app.route('/get_borrowed_books', methods=['POST'])
def get_borrowed_books_route():
    data = request.get_json()
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    books = get_borrowed_books(first_name, last_name)
    return jsonify(books)

def return_book_in_db(first_name, last_name, book_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE borrowed_books
        SET return_date = DATE('now')
        WHERE student_first_name = ? AND student_last_name = ? AND book_id = ? AND return_date IS NULL
    """, (first_name, last_name, book_id))
    success = cursor.rowcount > 0
    if success:
        cursor.execute("UPDATE books SET copies = copies + 1 WHERE id = ?", (book_id,))
        conn.commit()
    conn.close()
    return success

@app.route('/return_book', methods=['POST'])
def return_book_route():
    data = request.get_json()
    book_title = data.get('book_title')

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Fetch the book and student details
    cursor.execute("""
        SELECT bb.student_first_name, bb.student_last_name, bb.book_id
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
        WHERE b.title = ? AND bb.return_date IS NULL
    """, (book_title,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Book not found or already returned!"})

    student_first_name, student_last_name, book_id = row

    # Update the borrowed_books table to mark the book as returned
    cursor.execute("""
        UPDATE borrowed_books
        SET return_date = DATE('now')
        WHERE book_id = ? AND student_first_name = ? AND student_last_name = ?
    """, (book_id, student_first_name, student_last_name))

    # Update the books table to increment the available copies
    cursor.execute("UPDATE books SET copies = copies + 1 WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"Book '{book_title}' returned successfully!"})

def get_all_borrowed_books():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.title, bb.student_first_name, bb.student_last_name, bb.borrow_date, bb.return_date
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
    """)
    books = [
        {
            "title": row[0],
            "student_first_name": row[1],
            "student_last_name": row[2],
            "borrow_date": row[3],
            "return_date": row[4]
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    return books

@app.route('/borrowed_books')
def borrowed_books():
    borrowed_books = get_all_borrowed_books()
    return render_template('borrowed_books.html', borrowed_books=borrowed_books)

def get_book_borrow_details(book_title):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.title, bb.student_first_name, bb.student_last_name, bb.borrow_date,
               DATE(bb.borrow_date, '+7 days') AS due_date,
               CASE
                   WHEN julianday('now') - julianday(DATE(bb.borrow_date, '+7 days')) > 0
                   THEN ROUND((julianday('now') - julianday(DATE(bb.borrow_date, '+7 days'))) * 0.5, 2)
                   ELSE 0
               END AS fees
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
        WHERE b.title = ? AND bb.return_date IS NULL
    """, (book_title,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "title": row[0],
            "student_first_name": row[1],
            "student_last_name": row[2],
            "borrow_date": row[3],
            "due_date": row[4],
            "fees": f"${row[5]:.2f}" if row[5] > 0 else None
        }
    return None

@app.route('/get_book_borrow_details', methods=['POST'])
def get_book_borrow_details_route():
    data = request.get_json()
    book_title = data.get('book_title')

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.title, bb.student_first_name, bb.student_last_name, bb.borrow_date,
               DATE(bb.borrow_date, '+7 days') AS due_date,
               CASE
                   WHEN julianday('now') - julianday(DATE(bb.borrow_date, '+7 days')) > 0
                   THEN ROUND((julianday('now') - julianday(DATE(bb.borrow_date, '+7 days'))) * 0.5, 2)
                   ELSE 0
               END AS fees
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
        WHERE b.title = ? AND bb.return_date IS NULL
    """, (book_title,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return jsonify({
            "title": row[0],
            "student_first_name": row[1],
            "student_last_name": row[2],
            "borrow_date": row[3],
            "due_date": row[4],
            "fees": f"${row[5]:.2f}" if row[5] > 0 else None
        })
    return jsonify(None)

if __name__ == '__main__':
    app.run(debug=True)
