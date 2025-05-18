from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from umap import UMAP
from hdbscan import HDBSCAN
import sqlite3
import praw
from tqdm import tqdm
import nltk
import re
from textblob import TextBlob
import os
from dotenv import load_dotenv

# Download NLTK stopwords if not already downloaded
nltk.download('stopwords')
from nltk.corpus import stopwords

#############################################
# Helper Functions
#############################################

def remove_stop_words(text, stop_words):
    # Lowercase, split text, and filter out stop words.
    words = text.lower().split()
    filtered_words = [w for w in words if w not in stop_words]
    return " ".join(filtered_words)

def preprocess_text(text, stop_words):
    if not text:
        return ""
    text = text.lower()
    # Remove URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    # Remove special characters and numbers
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\d+', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Split and filter stop words (only keep words longer than 2 characters)
    words = text.split()
    filtered = [w for w in words if w not in stop_words and len(w) > 2]
    return " ".join(filtered)

#############################################
# Database Schema Functions
#############################################

def ensure_posts_table_columns():
    """
    Ensure the posts table has the following columns:
      - comments
      - score
      - num_comments
      - topic
    """
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cur.fetchall()]
    if "comments" not in columns:
        print("Adding 'comments' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN comments TEXT")
        conn.commit()
    if "score" not in columns:
        print("Adding 'score' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN score INTEGER")
        conn.commit()
    if "num_comments" not in columns:
        print("Adding 'num_comments' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN num_comments INTEGER")
        conn.commit()
    if "topic" not in columns:
        print("Adding 'topic' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN topic TEXT")
        conn.commit()
    conn.close()

def clear_posts_table():
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM posts")
    cur.execute("DELETE FROM sqlite_sequence WHERE name='posts'")
    conn.commit()
    conn.close()
    print("Cleared old posts and reset auto-increment.")

#############################################
# Fetching Posts from Reddit
#############################################

def fetch_and_store_subreddit_posts(subreddit_name="LocalLLaMA", limit=50):
    """Fetches posts from a given subreddit and stores them in the 'posts' table."""

    load_dotenv()

    # Get credentials from environment variables
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT")

    # Check if the environment variables were loaded
    if not all([client_id, client_secret, user_agent]):
        print("Error: Reddit API credentials not found in .env file or environment variables.")
        print("Please ensure REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT are set.")
        return # Or raise an exception

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        requestor_kwargs={'timeout': 60}
    )
    subreddit = reddit.subreddit(subreddit_name)
    posts_data = []
    print(f"Fetching posts from r/{subreddit_name}...")
    try:
        for post in tqdm(subreddit.hot(limit=limit)):
            content = post.selftext if post.selftext else post.title
            # Fetch top-level comments:
            try:
                post.comments.replace_more(limit=0)
                comments = " ".join([comment.body for comment in post.comments if hasattr(comment, "body")])
            except Exception as e:
                print(f"Error fetching comments for post {post.id}: {e}")
                comments = ""
            posts_data.append({
                "post_title": post.title,
                "post_content": content,
                "comments": comments,
                "ai_response": "",  # Initially empty
                "score": post.score,
                "num_comments": post.num_comments
            })
    except Exception as e:
        print("Error fetching posts from Reddit:", e)
        return

    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    # Create the posts table with all required columns if it doesn't exist.
    cur.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_title TEXT,
            post_content TEXT,
            comments TEXT,
            ai_response TEXT,
            score INTEGER,
            num_comments INTEGER,
            topic TEXT
        )
    ''')
    for post_item in posts_data: # Changed 'post' to 'post_item' to avoid conflict with tqdm 'post'
        # Update the INSERT statement if you added new column
        cur.execute("""
            INSERT INTO posts (post_title, post_content, comments, ai_response, score, num_comments)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (post_item["post_title"], post_item["post_content"], post_item["comments"],
              post_item["ai_response"], post_item["score"], post_item["num_comments"]))
    conn.commit()
    conn.close()
    print(f"Stored {len(posts_data)} posts from r/{subreddit_name} into the database.")

#############################################
# Database Retrieval and Update Functions
#############################################

def get_posts():
    """Retrieve all posts from the 'posts' table."""
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    posts = cur.execute("""
        SELECT id, post_title, post_content, comments, ai_response, score, num_comments, topic
        FROM posts
    """).fetchall()
    conn.close()
    return posts

def update_topic(post_id, topic_label):
    """Update the 'topic' column for a specific post."""
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("UPDATE posts SET topic = ? WHERE id = ?", (topic_label, post_id))
    conn.commit()
    conn.close()

#############################################
# Topic Modeling and Metrics Aggregation
#############################################

def perform_topic_modeling_on_posts(posts):
    """
    Perform topic modeling on the combined text (title, content, comments) of each post.
    Returns the trained BERTopic model, the list of topic IDs, and the list of post IDs.
    """
    # Get NLTK stopwords and add a custom list.
    stop_words = set(stopwords.words('english'))
    custom_stop = {
        "im", "ive", "dont", "cant", "you", "me", "now", "like",
        "the", "open", "local", "translate", "tool", "llms",
        "would", "inference", "think", "implementation", "explores",
        "nice", "integrations", "flux", "get", "got", "using", "use",
        "make", "just", "know", "way", "something", "used", "need",
        "could", "want", "trying", "even", "gonna", "say", "look",
        "every", "much", "working", "500", "time", "day", "really",
        "see", "stuff", "anyone", "tried", "first", "still", "actually",
        "going", "new", "one", "two", "sure", "bit", "of"
    }
    stop_words = stop_words.union(custom_stop)

    texts = []
    post_ids = []
    # Combine title, content, and comments for each post.
    for post in posts:
        combined_text = f"{post['post_title']} {post['post_content']} {post['comments']}"
        processed_text = preprocess_text(combined_text, stop_words)
        if processed_text and len(processed_text.split()) >= 3:
            texts.append(processed_text)
            post_ids.append(post["id"])

    if not texts:
        return None, None, None

    sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = sentence_model.encode(texts, show_progress_bar=True)
    umap_model = UMAP(n_components=5, random_state=42)
    hdbscan_model = HDBSCAN(min_cluster_size=3, min_samples=1, prediction_data=True)
    topic_model = BERTopic(
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        nr_topics="auto",
        top_n_words=10,
        calculate_probabilities=True,
        verbose=True
    )
    topics, _ = topic_model.fit_transform(texts, embeddings)
    topic_model.update_topics(texts, topics, top_n_words=5)
    return topic_model, topics, post_ids

def aggregate_topic_metrics(posts):
    """
    Aggregate metrics for each individual topic word.
    For each topic word (split by commas), calculate:
      - Total upvotes
      - Total posts
      - Total comments
      - Average sentiment (on combined text)
      - A simple summary (first 150 characters of concatenated texts)
    """
    topic_metrics = {}
    for post in posts:
        post_dict = dict(post)
        combined_text = f"{post_dict['post_title']} {post_dict['post_content']} {post_dict['comments']}"
        sentiment = TextBlob(combined_text).sentiment.polarity
        upvotes = post_dict['score'] if post_dict['score'] is not None else 0
        num_comments = post_dict['num_comments'] if post_dict['num_comments'] is not None else 0

        topic_field = post_dict.get("topic") or "miscellaneous"
        topics_list = [t.strip() for t in topic_field.split(",") if t.strip()]
        if not topics_list:
            topics_list = ["miscellaneous"]

        for t in topics_list:
            if t not in topic_metrics:
                topic_metrics[t] = {
                    "total_upvotes": 0,
                    "total_posts": 0,
                    "total_comments": 0,
                    "sentiments": [],
                    "combined_texts": []
                }
            topic_metrics[t]["total_upvotes"] += upvotes
            topic_metrics[t]["total_comments"] += num_comments
            topic_metrics[t]["total_posts"] += 1
            topic_metrics[t]["sentiments"].append(sentiment)
            topic_metrics[t]["combined_texts"].append(combined_text)

    for t, metrics in topic_metrics.items():
        avg_sentiment = sum(metrics["sentiments"]) / len(metrics["sentiments"]) if metrics["sentiments"] else 0
        combined_text = " ".join(metrics["combined_texts"])
        summary = combined_text[:150] + "..." if len(combined_text) > 150 else combined_text
        topic_metrics[t]["avg_sentiment"] = avg_sentiment
        topic_metrics[t]["summary"] = summary
    return topic_metrics

#############################################
# Main Function to Run Topic Modeling
#############################################

def run_topic_modeling(subreddit_name="LocalLLaMA", limit=50):
    """
    Clears the posts table, fetches new posts from the given subreddit,
    runs topic modeling, and prints aggregated metrics to the console.
    """
    clear_posts_table()
    ensure_posts_table_columns()

    fetch_and_store_subreddit_posts(subreddit_name=subreddit_name, limit=limit)
    posts = get_posts()
    if not posts:
        print("No posts found in the database.")
        return

    topic_model, topics, post_ids = perform_topic_modeling_on_posts(posts)
    if topic_model is None or topics is None:
        print("No valid text found for topic modeling.")
        return

    print(topic_model.get_topic_info())

    # Map post IDs to indices for posts included in topic modeling.
    post_id_to_index = {pid: idx for idx, pid in enumerate(post_ids)}

    for post in posts:
        post_dict = dict(post)
        if post_dict.get("post_title"):
            if post_dict["id"] in post_id_to_index:
                i = post_id_to_index[post_dict["id"]]
                topic_num = topics[i]
                topic_info = topic_model.get_topic(topic_num)
                if topic_info:
                    topic_words = [word for word, _ in topic_info[:3] if len(word) > 2]
                    if topic_words:
                        topic_category = ", ".join(topic_words)
                    else:
                        topic_category = "miscellaneous"
                else:
                    topic_category = "miscellaneous"
            else:
                topic_category = "miscellaneous"
            update_topic(post_dict["id"], topic_category)
            print(f"Updated post ID {post_dict['id']} with topic: {topic_category}")

    aggregated_metrics = aggregate_topic_metrics(posts)
    print("\nAggregated Topic Metrics:")
    for topic, metrics in aggregated_metrics.items():
        print(f"Topic: {topic}")
        print(f"  Total Upvotes: {metrics['total_upvotes']}")
        print(f"  Total Posts: {metrics['total_posts']}")
        print(f"  Total Comments: {metrics['total_comments']}")
        print(f"  Average Sentiment: {metrics['avg_sentiment']:.2f}")
        print(f"  Summary: {metrics['summary']}")
        print("-" * 40)
