from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from textblob import TextBlob
import plotly.graph_objs as go
import json
import requests

app = Flask(__name__)
app.secret_key = "your-secret-key"  # Replace with a secure key in production

# Helper function to get a connection to the database.
def get_db_connection():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name.
    return conn

# Helper function to ensure the company_details table exists and has the style_guide column.
def ensure_company_details_table():
    conn = get_db_connection()
    cur = conn.cursor()
    # Create table if not exists.
    cur.execute('''
        CREATE TABLE IF NOT EXISTS company_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            company_profile TEXT,
            blogs TEXT,
            keywords TEXT,
            communities TEXT
        )
    ''')
    # Check if style_guide column exists.
    cur.execute("PRAGMA table_info(company_details)")
    columns = [row["name"] for row in cur.fetchall()]
    if "style_guide" not in columns:
        cur.execute("ALTER TABLE company_details ADD COLUMN style_guide TEXT")
        conn.commit()
    conn.close()

# Function to calculate the sentiment of a given text.
def get_sentiment(text):
    return TextBlob(text).sentiment.polarity

# Generate a Plotly chart for topic distribution.
def generate_topic_chart(posts):
    topic_counts = {}
    for post in posts:
        topic = post.get("topic", "N/A")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    topics = list(topic_counts.keys())
    counts = list(topic_counts.values())
    data = [go.Bar(x=topics, y=counts, marker=dict(color='rgb(26, 118, 255)'))]
    layout = go.Layout(
        title='Topic Distribution',
        xaxis=dict(title='Topic'),
        yaxis=dict(title='Count')
    )
    fig = go.Figure(data=data, layout=layout)
    return json.loads(fig.to_json())

# Generate a Plotly chart for sentiment distribution.
def generate_sentiment_chart(posts):
    sentiments = [post["sentiment"] for post in posts if post.get("sentiment") is not None]
    data = [go.Histogram(x=sentiments, nbinsx=10, marker=dict(color='rgb(255, 100, 102)'))]
    layout = go.Layout(
        title='Sentiment Distribution',
        xaxis=dict(title='Sentiment Score'),
        yaxis=dict(title='Frequency')
    )
    fig = go.Figure(data=data, layout=layout)
    return json.loads(fig.to_json())

# Route for the home page (dashboard).
@app.route("/")
def index():
    conn = get_db_connection()
    posts = conn.execute("SELECT * FROM posts").fetchall()
    conn.close()

    posts_with_sentiment = []
    for post in posts:
        post_dict = dict(post)
        if post_dict.get("ai_response"):
            post_dict["sentiment"] = get_sentiment(post_dict["ai_response"])
        else:
            post_dict["sentiment"] = None
        posts_with_sentiment.append(post_dict)
    
    sentiment_chart = generate_sentiment_chart(posts_with_sentiment)
    topic_chart = generate_topic_chart(posts_with_sentiment)
    
    return render_template("index.html", posts=posts_with_sentiment,
                           sentiment_chart=sentiment_chart, topic_chart=topic_chart)

# Route to approve a post.
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

# Route for company setup (or editing existing details).
@app.route("/company_setup", methods=["GET", "POST"])
def company_setup():
    ensure_company_details_table()  # Ensure table exists with style_guide column.
    conn = get_db_connection()
    # Retrieve the most recent company details (if they exist)
    company = conn.execute("SELECT * FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
    if request.method == "POST":
        company_name = request.form["company_name"]
        company_profile = request.form["company_profile"]
        blogs = request.form["blogs"]
        keywords = request.form["keywords"]
        communities = request.form["communities"]

        if company:
            # Update the existing record.
            conn.execute('''
                UPDATE company_details
                SET company_name = ?, company_profile = ?, blogs = ?, keywords = ?, communities = ?
                WHERE id = ?
            ''', (company_name, company_profile, blogs, keywords, communities, company["id"]))
        else:
            # Insert new company details.
            conn.execute('''
                INSERT INTO company_details (company_name, company_profile, blogs, keywords, communities)
                VALUES (?, ?, ?, ?, ?)
            ''', (company_name, company_profile, blogs, keywords, communities))
        conn.commit()
        conn.close()
        session.pop('style_guide', None)
        return redirect(url_for('generate_prompt_style'))
    conn.close()
    return render_template("company_setup.html", company=company)

# Route to generate and display prompt style using company details and an LLM API.
@app.route("/generate_prompt_style", methods=["GET", "POST"])
def generate_prompt_style():
    ensure_company_details_table()  # Ensure table structure is up-to-date.
    
    if request.method == "POST":
        # "Set Style" button clicked; save style permanently in the DB.
        style = session.get('style_guide', '')
        conn = get_db_connection()
        company = conn.execute("SELECT * FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
        if company:
            conn.execute("UPDATE company_details SET style_guide = ? WHERE id = ?", (style, company["id"]))
            conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    # If a style guide is already in session, use it.
    if 'style_guide' in session:
        style_guide = session['style_guide']
    else:
        conn = get_db_connection()
        company = conn.execute("SELECT * FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        if not company:
            return "No company details found. Please set up your company profile first."
    
        prompt_text = (
            f"Company Name: {company['company_name']}\n"
            f"Company Profile: {company['company_profile']}\n"
            f"Blogs: {company['blogs']}\n"
            f"Keywords: {company['keywords']}\n"
            f"Communities: {company['communities']}\n\n"
            "Based on the above details, generate a brand style guide and prompt structure that reflects the brand style of writing that will be further used as a prompt to generate content of similar style. So give me detailed instructions based on all the patterns you observe from the written style of these content."
        )
        
        # Use your actual API key and endpoint for the LLM.
        api_key = "AIzaSyBf-2TifmPe2Y_dyz5YKBInA_XvGases5k"  # Replace with your actual API key.
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{
                "parts": [{"text": prompt_text}]
            }]
        }
        
        try:
            response = requests.post(endpoint, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            candidates = result.get("candidates", [])
            if candidates:
                style_guide = candidates[0]["content"]["parts"][0]["text"]
            else:
                style_guide = "No style generated. Please check your prompt or API configuration."
        except requests.exceptions.RequestException as e:
            style_guide = f"Error generating style guide: {e}"
            print("API error:", e)
        
        session['style_guide'] = style_guide

    return render_template("generate_prompt_style.html", style_guide=style_guide)

# Route to edit the generated style guide.
@app.route("/edit_style", methods=["GET", "POST"])
def edit_style():
    if request.method == "POST":
        # Save the edited style text to session.
        session['style_guide'] = request.form["style_guide"]
        return redirect(url_for('generate_prompt_style'))
    # On GET, pre-populate the form with the current style guide.
    current_style = session.get('style_guide', '')
    return render_template("edit_style.html", style_guide=current_style)

if __name__ == "__main__":
    app.run(debug=True)
