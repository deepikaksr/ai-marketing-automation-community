from flask import Flask, render_template, redirect, url_for, request, session, jsonify
import sqlite3
import json
import plotly.graph_objs as go
from textblob import TextBlob
import requests
import pyperclip

app = Flask(__name__)
app.secret_key = "your-secret-key"


#############################################
# Database & Helper Functions
#############################################

def get_db_connection():
    """Establishes a database connection and sets row_factory for named columns."""
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    return conn


def get_most_popular_topic():
    """Returns the most popular topic from posts."""
    conn = get_db_connection()
    posts = conn.execute("SELECT topic FROM posts").fetchall()
    conn.close()

    topic_counts = {}
    for post in posts:
        topic_field = post["topic"] or "miscellaneous"
        topics_list = [t.strip() for t in topic_field.split(",") if t.strip()]
        for t in topics_list:
            topic_counts[t] = topic_counts.get(t, 0) + 1

    return max(topic_counts, key=topic_counts.get) if topic_counts else "miscellaneous"


def get_topic_details(topic):
    """Returns aggregated details for the chosen topic."""
    conn = get_db_connection()
    posts = conn.execute("SELECT * FROM posts WHERE topic LIKE ?", ('%' + topic + '%',)).fetchall()
    conn.close()

    posts = [dict(post) for post in posts]
    combined_texts = " ".join([post["post_title"] + " " + (post["post_content"] or "") for post in posts])
    avg_sentiment = TextBlob(combined_texts).sentiment.polarity if combined_texts else 0
    summary = combined_texts[:150] + "..." if len(combined_texts) > 150 else combined_texts

    return {
        "total_posts": len(posts),
        "summary": summary,
        "avg_sentiment": avg_sentiment
    }


def get_confirmed_style_guide():
    """Returns the confirmed style guide from the company details."""
    conn = get_db_connection()
    company = conn.execute("SELECT style_guide FROM company_details ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return company["style_guide"] if company and company["style_guide"] else None


def generate_ai_response_with_style(prompt_text):
    """Generates an AI response using Gemini API with the provided prompt."""
    api_key = "AIzaSyBf-2TifmPe2Y_dyz5YKBInA_XvGases5k"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt_text}]}]}

    try:
        response = requests.post(endpoint, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        candidates = result.get("candidates", [])
        return candidates[0]["content"]["parts"][0]["text"] if candidates else "No response generated."
    except Exception as e:
        print("Error generating AI response:", e)
        return f"Error: {e}"


def get_sentiment(text):
    """Returns the sentiment polarity of the given text."""
    return TextBlob(text).sentiment.polarity


def generate_topic_chart(posts):
    """Generates a bar chart for topic distribution."""
    topic_counts = {}
    for post in posts:
        topic = post.get("topic") or "miscellaneous"
        topics_list = [t.strip() for t in topic.split(",") if t.strip()]
        for t in topics_list:
            topic_counts[t] = topic_counts.get(t, 0) + 1

    topics = list(topic_counts.keys())
    counts = list(topic_counts.values())
    data = [go.Bar(x=topics, y=counts, marker=dict(color='rgb(26, 118, 255)'))]
    layout = go.Layout(title='Topic Distribution', xaxis=dict(title='Topic'), yaxis=dict(title='Count'))
    fig = go.Figure(data=data, layout=layout)
    return json.loads(fig.to_json())

#############################################
# Routes
#############################################

@app.route("/")
def index():
    """Main dashboard page."""
    conn = get_db_connection()
    posts = conn.execute("SELECT * FROM posts").fetchall()
    conn.close()

    posts_with_sentiment = []
    for post in posts:
        post_dict = dict(post)
        post_dict["sentiment"] = get_sentiment(post_dict["ai_response"]) if post_dict.get("ai_response") else None
        posts_with_sentiment.append(post_dict)

    topic_chart = generate_topic_chart(posts_with_sentiment)

    topic_counts = {}
    for post in posts_with_sentiment:
        topic_field = post.get("topic") or "miscellaneous"
        topics_list = [t.strip() for t in topic_field.split(",") if t.strip()]
        for t in topics_list:
            topic_counts[t] = topic_counts.get(t, 0) + 1

    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:15]

    return render_template("index.html", posts=posts_with_sentiment, topic_chart=topic_chart, sorted_topics=sorted_topics)


@app.route("/generate_post/<platform>", methods=["GET"])
def generate_post(platform):
    """Generates platform-specific posts using the most popular topic."""
    style_guide = get_confirmed_style_guide()
    if not style_guide:
        return jsonify({"response": "No style guide found. Please set up your company profile."})

    topic = get_most_popular_topic()
    topic_details = get_topic_details(topic)

    platform_instructions = {
        "blog": "Generate a detailed blog post with a clear structure, engaging introduction, and call-to-action.",
        "linkedin": "Generate a professional LinkedIn post that is concise, value-driven, and engaging.",
        "twitter": "Generate a short and engaging tweet within 280 characters."
    }

    prompt = (
        f"Using the following brand style guide:\n{style_guide}\n\n"
        f"Topic: {topic}\n"
        f"Summary: {topic_details['summary']}\n"
        f"Average Sentiment: {topic_details['avg_sentiment']}\n"
        f"{platform_instructions.get(platform, 'Generate a general post.')}\n\n"
        "Response:"
    )

    generated_response = generate_ai_response_with_style(prompt)
    return jsonify({"topic": topic, "response": generated_response})


@app.route("/copy_post", methods=["POST"])
def copy_post():
    """Copies the generated post to clipboard."""
    content = request.form.get("content", "")
    if content:
        pyperclip.copy(content)
        return jsonify({"message": "Content copied to clipboard"})
    else:
        return jsonify({"error": "No content to copy"}), 400


@app.route("/regenerate_post/<platform>", methods=["POST"])
def regenerate_post(platform):
    """Re-generates platform-specific posts using the most popular topic."""
    return generate_post(platform)


@app.route("/edit_post", methods=["POST"])
def edit_post():
    content = request.json.get("content", "")
    if content:
        return jsonify({"response": content, "status": "success"})
    else:
        return jsonify({"error": "No content to update", "status": "error"}), 400



@app.route("/topic_summary/<topic>")
def topic_summary(topic):
    """Displays topic summary with aggregated metrics."""
    conn = get_db_connection()
    posts = conn.execute("SELECT * FROM posts WHERE topic LIKE ?", ('%' + topic + '%',)).fetchall()
    conn.close()

    posts = [dict(post) for post in posts]
    total_posts = len(posts)
    total_upvotes = sum(post["score"] if post["score"] is not None else 0 for post in posts)
    total_comments = sum(post["num_comments"] if post["num_comments"] is not None else 0 for post in posts)

    combined_texts = " ".join([post["post_title"] + " " + (post["post_content"] or "") + " " + (post["comments"] or "") for post in posts])
    avg_sentiment = TextBlob(combined_texts).sentiment.polarity if combined_texts else 0
    summary = combined_texts[:150] + "..." if len(combined_texts) > 150 else combined_texts

    return render_template("topic_summary.html", topic=topic, total_posts=total_posts,
                           total_upvotes=total_upvotes, total_comments=total_comments,
                           avg_sentiment=avg_sentiment, summary=summary, posts=posts)


@app.route("/company_setup", methods=["GET", "POST"])
def company_setup():
    """Handles company setup and saves company details."""
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
    """Generates a brand style guide based on company details."""
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
    """Allows editing of the brand style guide."""
    if request.method == "POST":
        session['style_guide'] = request.form["style_guide"]
        return redirect(url_for('generate_prompt_style'))
    current_style = session.get('style_guide', '')
    return render_template("edit_style.html", style_guide=current_style)


if __name__ == "__main__":
    app.run(debug=True)
