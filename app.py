from flask import Flask, render_template, redirect, url_for, request, session, jsonify
import sqlite3
import json
import random
import plotly.graph_objs as go
from textblob import TextBlob
import requests
import pyperclip
from sentence_transformers import SentenceTransformer, util

import topic_modeling

app = Flask(__name__)
app.secret_key = "your-secret-key"

#############################################
# Database & Helper Functions
#############################################

def get_db_connection():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
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
            communities TEXT,
            style_guide TEXT
        )
    ''')
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

    # Sort by count and get top 15 topics
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:15]

    # Extract topics and counts
    topics = [item[0] for item in sorted_topics]
    counts = [item[1] for item in sorted_topics]

    # Assign colors based on count (same count = same color)
    unique_counts = sorted(set(counts), reverse=True)

    # Predefined colors + random fallback if needed
    predefined_colors = [
        'rgb(26, 118, 255)', 'rgb(255, 153, 51)', 'rgb(0, 204, 102)', 
        'rgb(204, 51, 255)', 'rgb(255, 102, 102)', 'rgb(102, 204, 255)', 
        'rgb(255, 204, 102)', 'rgb(102, 255, 178)', 'rgb(178, 102, 255)', 
        'rgb(255, 178, 102)'
    ]

    while len(predefined_colors) < len(unique_counts):
        predefined_colors.append(
            f'rgb({random.randint(0,255)}, {random.randint(0,255)}, {random.randint(0,255)})'
        )

    color_dict = dict(zip(unique_counts, predefined_colors))
    bar_colors = [color_dict[count] for count in counts]

    # Plotly Bar Chart
    data = [go.Bar(x=topics, y=counts, marker=dict(color=bar_colors))]
    layout = go.Layout(
        title='Top 15 Topics Distribution', 
        xaxis=dict(title='Topic'), 
        yaxis=dict(title='Count')
    )
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
    data = {"contents": [{"parts": [{"text": prompt_text}]}]}
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
# Similarity Score Calculations
#############################################

def calculate_response_alignment_score(generated_post, style_guide):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    gen_embedding = model.encode(generated_post, convert_to_tensor=True)
    style_embedding = model.encode(style_guide, convert_to_tensor=True)
    similarity_score = util.pytorch_cos_sim(gen_embedding, style_embedding).item()
    return round(similarity_score * 100, 2)

def calculate_discussion_alignment_score(generated_post, related_texts):
    model = SentenceTransformer('all-MiniLM-L6-v2')
    gen_embedding = model.encode(generated_post, convert_to_tensor=True)
    discussion_embedding = model.encode(related_texts, convert_to_tensor=True)
    similarity_score = util.pytorch_cos_sim(gen_embedding, discussion_embedding).item()
    return round(similarity_score * 100, 2)

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
    
    return render_template(
        "index.html",
        posts=posts_with_sentiment,
        topic_chart=topic_chart,
        sorted_topics=sorted_topics
    )

@app.route("/generate_post", methods=["POST"])
def generate_post():
    style_guide = get_confirmed_style_guide()
    if not style_guide:
        return jsonify({"error": "No style guide found. Please set up your company profile."}), 400

    platform = request.json.get("platform", "blog")
    platform_instructions = {
        "blog": "Generate a detailed blog post with a clear structure, engaging introduction, and call-to-action.",
        "linkedin": "Generate a professional LinkedIn post that is concise, value-driven, and engaging for professionals.",
        "twitter": "Generate a short and engaging tweet within 280 characters that captures attention quickly."
    }

    # Select the most popular topic
    conn = get_db_connection()
    topic_data = conn.execute("""
        SELECT topic, COUNT(*) as count 
        FROM posts 
        WHERE topic IS NOT NULL 
        GROUP BY topic 
        ORDER BY count DESC 
        LIMIT 1
    """).fetchone()
    conn.close()

    selected_topic = topic_data["topic"] if topic_data else "general"

    # Prepare AI prompt
    prompt = (
        f"Using the following brand style guide:\n{style_guide}\n\n"
        f"Topic: {selected_topic}\n"
        f"Platform: {platform}\n"
        f"{platform_instructions.get(platform, 'Generate a general post.')}\n\n"
        "Response:"
    )

    # Generate AI response
    generated_response = generate_ai_response_with_style(prompt)

    # Calculate Response Alignment Score
    response_alignment_score = calculate_response_alignment_score(generated_response, style_guide)

    # Calculate Discussion Alignment Score
    conn = get_db_connection()
    related_texts = conn.execute("""
        SELECT post_title, post_content, comments 
        FROM posts 
        WHERE topic LIKE ?
    """, ('%' + selected_topic + '%',)).fetchall()
    conn.close()

    discussion_texts = " ".join(
        [f"{post['post_title']} {post['post_content']} {post['comments']}" for post in related_texts]
    )
    discussion_alignment_score = calculate_discussion_alignment_score(generated_response, discussion_texts)

    # Return JSON with both scores
    return jsonify({
        "topic": selected_topic,
        "response": generated_response,
        "response_alignment_score": response_alignment_score,
        "discussion_alignment_score": discussion_alignment_score
    })

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
        communities = request.form["communities"]  # <-- The user enters subreddit(s) here

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

    return render_template(
        "topic_summary.html",
        topic=topic,
        total_posts=total_posts,
        total_upvotes=total_upvotes,
        total_comments=total_comments,
        avg_sentiment=avg_sentiment,
        summary=summary,
        posts=posts
    )

#############################################
# New Route to Run Topic Modeling
#############################################
@app.route("/run_topic_modeling")
def run_topic_modeling_route():
    """
    Reads the last-saved 'communities' from company_details,
    calls run_topic_modeling using that as the subreddit name,
    and returns a simple message or you can redirect to /
    """
    ensure_company_details_table()
    conn = get_db_connection()
    company = conn.execute("SELECT * FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not company:
        return "No company details found. Please set up your company profile first."

    # Assume the user typed something like "LocalLLaMA" or "AskReddit" in the communities field.
    # If multiple communities are listed, take the first one.
    communities_field = company["communities"] or "LocalLLaMA"
    subreddit_name = communities_field.split(",")[0].strip()

    topic_modeling.run_topic_modeling(subreddit_name=subreddit_name, limit=50)
    return "Topic modeling completed successfully! Check the console logs for details."

if __name__ == "__main__":
    app.run(debug=True)
