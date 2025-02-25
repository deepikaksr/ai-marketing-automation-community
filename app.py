from flask import Flask, render_template, redirect, url_for, request, session, jsonify
import sqlite3
import json
import plotly.graph_objs as go
from textblob import TextBlob
import requests
import pyperclip

app = Flask(__name__)
app.secret_key = "your-secret-key"  # Replace with a secure key in production

#############################################
# Database & Helper Functions
#############################################

def get_db_connection():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row  # Access columns by name.
    return conn

def ensure_company_details_table():
    conn = get_db_connection()
    cur = conn.cursor()
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
    # Ensure the style_guide column exists.
    cur.execute("PRAGMA table_info(company_details)")
    columns = [row["name"] for row in cur.fetchall()]
    if "style_guide" not in columns:
        cur.execute("ALTER TABLE company_details ADD COLUMN style_guide TEXT")
        conn.commit()
    conn.close()

#############################################
# Sentiment and Chart Generation
#############################################

def get_sentiment(text):
    return TextBlob(text).sentiment.polarity

def generate_topic_chart(posts):
    topic_counts = {}
    for post in posts:
        topic = post.get("topic") or "miscellaneous"
        topics_list = [t.strip() for t in topic.split(",") if t.strip()]
        if not topics_list:
            topics_list = ["miscellaneous"]
        for t in topics_list:
            topic_counts[t] = topic_counts.get(t, 0) + 1
    topics = list(topic_counts.keys())
    counts = list(topic_counts.values())
    data = [go.Bar(x=topics, y=counts, marker=dict(color='rgb(26, 118, 255)'))]
    layout = go.Layout(title='Topic Distribution', xaxis=dict(title='Topic'), yaxis=dict(title='Count'))
    fig = go.Figure(data=data, layout=layout)
    return json.loads(fig.to_json())

#############################################
# AI Response Generation using Gemini Flash
#############################################

def get_confirmed_style_guide():
    conn = get_db_connection()
    company = conn.execute("SELECT style_guide FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if company and company["style_guide"]:
        return company["style_guide"]
    return None

def generate_ai_response_with_style(prompt_text):
    api_key = "AIzaSyBf-2TifmPe2Y_dyz5YKBInA_XvGases5k"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }]
    }
    try:
        response = requests.post(endpoint, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        candidates = result.get("candidates", [])
        if candidates:
            return candidates[0]["content"]["parts"][0]["text"]
        else:
            return "No response generated."
    except Exception as e:
        print("Error generating AI response:", e)
        return f"Error: {e}"

#############################################
# Routes
#############################################

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
    
    topic_chart = generate_topic_chart(posts_with_sentiment)
    
    topic_counts = {}
    for post in posts_with_sentiment:
        topic_field = post.get("topic") or "miscellaneous"
        topics_list = [t.strip() for t in topic_field.split(",") if t.strip()]
        if not topics_list:
            topics_list = ["miscellaneous"]
        for t in topics_list:
            topic_counts[t] = topic_counts.get(t, 0) + 1
    
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    
    return render_template("index.html", posts=posts_with_sentiment,
                           topic_chart=topic_chart, sorted_topics=sorted_topics)

@app.route("/generate_post", methods=["POST"])
def generate_post():
    style_guide = get_confirmed_style_guide()
    if not style_guide:
        return "No style guide found. Please set up your company profile."
    
    topic = request.form.get("topic", "general")
    platform = request.form.get("platform", "blog")

    platform_instructions = {
        "blog": "Generate a detailed blog post with a clear structure, engaging introduction, and call-to-action.",
        "linkedin": "Generate a professional LinkedIn post that is concise, value-driven, and engaging for professionals.",
        "twitter": "Generate a short and engaging tweet within 280 characters that captures attention quickly."
    }

    prompt = (
        f"Using the following brand style guide:\n{style_guide}\n\n"
        f"Topic: {topic}\n"
        f"Platform: {platform}\n"
        f"{platform_instructions.get(platform, 'Generate a general post.')}\n\n"
        "Response:"
    )

    generated_response = generate_ai_response_with_style(prompt)
    return jsonify({"response": generated_response})


@app.route("/copy_post", methods=["POST"])
def copy_post():
    content = request.form.get("content", "")
    if content:
        pyperclip.copy(content)
        return jsonify({"message": "Content copied to clipboard"})
    else:
        return jsonify({"error": "No content to copy"}), 400


@app.route("/edit_post", methods=["POST"])
def edit_post():
    content = request.form.get("content", "")
    return jsonify({"response": content})


@app.route("/company_setup", methods=["GET", "POST"])
def company_setup():
    ensure_company_details_table()
    conn = get_db_connection()
    company = conn.execute("SELECT * FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
    if request.method == "POST":
        company_name = request.form["company_name"]
        company_profile = request.form["company_profile"]
        blogs = request.form["blogs"]
        keywords = request.form["keywords"]
        communities = request.form["communities"]
        if company:
            conn.execute('''
                UPDATE company_details
                SET company_name = ?, company_profile = ?, blogs = ?, keywords = ?, communities = ?
                WHERE id = ?
            ''', (company_name, company_profile, blogs, keywords, communities, company["id"]))
        else:
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


@app.route("/generate_prompt_style", methods=["GET", "POST"])
def generate_prompt_style():
    ensure_company_details_table()
    if request.method == "POST":
        style = session.get('style_guide', '')
        conn = get_db_connection()
        company = conn.execute("SELECT * FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
        if company:
            conn.execute("UPDATE company_details SET style_guide = ? WHERE id = ?", (style, company["id"]))
            conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
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
            "Based on the above details, generate a brand style guide that reflects the brand style of writing."
        )
        
        style_guide = generate_ai_response_with_style(prompt_text)
        session['style_guide'] = style_guide

    return render_template("generate_prompt_style.html", style_guide=style_guide)


@app.route("/edit_style", methods=["GET", "POST"])
def edit_style():
    if request.method == "POST":
        session['style_guide'] = request.form["style_guide"]
        return redirect(url_for('generate_prompt_style'))
    current_style = session.get('style_guide', '')
    return render_template("edit_style.html", style_guide=current_style)


@app.route("/topic_summary/<topic>")
def topic_summary(topic):
    conn = get_db_connection()
    cur = conn.cursor()
    posts = cur.execute("SELECT * FROM posts WHERE topic LIKE ?", ('%' + topic + '%',)).fetchall()
    conn.close()
    posts = [dict(post) for post in posts]
    
    if not posts:
        return f"No posts found for topic: {topic}"
    
    total_posts = len(posts)
    total_upvotes = sum(post["score"] if post["score"] is not None else 0 for post in posts)
    total_comments = sum(post["num_comments"] if post["num_comments"] is not None else 0 for post in posts)
    
    combined_texts = " ".join([post["post_title"] + " " + (post["post_content"] or "") + " " + (post["comments"] or "") for post in posts])
    avg_sentiment = TextBlob(combined_texts).sentiment.polarity if combined_texts else 0
    summary = combined_texts[:150] + "..." if len(combined_texts) > 150 else combined_texts

    return render_template("topic_summary.html", topic=topic, total_posts=total_posts,
                           total_upvotes=total_upvotes, total_comments=total_comments,
                           avg_sentiment=avg_sentiment, summary=summary, posts=posts)


if __name__ == "__main__":
    app.run(debug=True)
