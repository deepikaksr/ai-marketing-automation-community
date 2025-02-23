from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from textblob import TextBlob  # Import TextBlob for sentiment analysis

app = Flask(__name__)

# Helper function to get a connection to the database.
def get_db_connection():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row  # This allows us to access columns by name.
    return conn

# Function to calculate the sentiment of a given text.
def get_sentiment(text):
    # Returns a polarity value between -1 (negative) and 1 (positive)
    return TextBlob(text).sentiment.polarity

# Route for the home page that lists all posts with sentiment info.
@app.route("/")
def index():
    conn = get_db_connection()
    posts = conn.execute("SELECT * FROM posts").fetchall()
    conn.close()

    # Convert each post to a dictionary and add sentiment data.
    posts_with_sentiment = []
    for post in posts:
        post_dict = dict(post)
        if post_dict.get("ai_response"):
            post_dict["sentiment"] = get_sentiment(post_dict["ai_response"])
        else:
            post_dict["sentiment"] = None
        posts_with_sentiment.append(post_dict)
    
    return render_template("index.html", posts=posts_with_sentiment)

# Route to approve a post (updates the approved status in the database).
@app.route("/approve/<int:post_id>", methods=["POST"])
def approve(post_id):
    conn = get_db_connection()
    conn.execute("UPDATE posts SET approved = 1 WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

# Route to edit a post's AI response.
@app.route("/edit/<int:post_id>", methods=["GET", "POST"])
def edit(post_id):
    conn = get_db_connection()
    if request.method == "POST":
        new_response = request.form["ai_response"]
        conn.execute("UPDATE posts SET ai_response = ? WHERE id = ?", (new_response, post_id))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    else:
        post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        conn.close()
        return render_template("edit.html", post=post)

if __name__ == "__main__":
    app.run(debug=True)
