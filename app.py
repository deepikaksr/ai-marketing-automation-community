from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import plotly.graph_objs as go
import json
import requests

app = Flask(__name__)
app.secret_key = "your-secret-key"  # Replace with a secure key in production

#############################################
# Database & Helper Functions
#############################################

def get_db_connection():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name.
    return conn

def ensure_company_details_table():
    conn = get_db_connection()
    cur = conn.cursor()
    # Create company_details table if it doesn't exist.
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
# Chart Generation
#############################################

def generate_topic_chart_from_counts(topic_counts):
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

def generate_ai_response_with_style(post_content, style_guide):
    prompt = (
        f"Using the following brand style guide:\n{style_guide}\n\n"
        f"Generate a detailed response for the following post:\n{post_content}\n\nResponse:"
    )
    # Use Gemini Flash API with your original API key.
    api_key = "AIzaSyBf-2TifmPe2Y_dyz5YKBInA_XvGases5k"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
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

    posts_to_display = []
    topic_counts = {}
    for post in posts:
        post_dict = dict(post)
        # Split the topic string on comma to count individual topics:
        topic_field = post_dict.get("topic", "")
        if topic_field:
            topics_list = [t.strip() for t in topic_field.split(",") if t.strip()]
        else:
            topics_list = ["miscellaneous"]
        for t in topics_list:
            topic_counts[t] = topic_counts.get(t, 0) + 1
        posts_to_display.append(post_dict)

    # Sort topic_counts by count descending and take the top 15.
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    topics = [t[0] for t in sorted_topics]
    counts = [t[1] for t in sorted_topics]

    # Create a mapping from each unique count to a color.
    unique_counts = sorted(set(counts))
    # Define a palette of colors.
    palette = ['rgb(26, 118, 255)', 'rgb(255, 99, 71)', 'rgb(60, 179, 113)', 'rgb(138, 43, 226)', 'rgb(255, 165, 0)', 'rgb(255, 105, 180)']
    count_to_color = {}
    for i, c in enumerate(unique_counts):
        count_to_color[c] = palette[i % len(palette)]
    # Now assign colors to each bar based on its count.
    bar_colors = [count_to_color[c] for c in counts]

    data = [go.Bar(x=topics, y=counts, marker=dict(color=bar_colors))]
    layout = go.Layout(title='Top 15 Topics Distribution', xaxis=dict(title='Topic'), yaxis=dict(title='Count'))
    topic_chart = json.loads(go.Figure(data=data, layout=layout).to_json())

    return render_template("index.html", posts=posts_to_display,
                           topic_chart=topic_chart, topic_counts=topic_counts)


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
            "Based on the above details, generate a brand style guide and prompt structure that reflects the brand style of writing that will be further used as a prompt to generate content of similar style. So give me detailed instructions based on all the patterns you observe from the written style of these content."
        )
        api_key = "AIzaSyBf-2TifmPe2Y_dyz5YKBInA_XvGases5k"
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": prompt_text}]}]}
        try:
            response = requests.post(endpoint, headers=headers, json=data, timeout=30)
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

@app.route("/edit_style", methods=["GET", "POST"])
def edit_style():
    if request.method == "POST":
        session['style_guide'] = request.form["style_guide"]
        return redirect(url_for('generate_prompt_style'))
    current_style = session.get('style_guide', '')
    return render_template("edit_style.html", style_guide=current_style)

if __name__ == "__main__":
    app.run(debug=True)
