from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from umap import UMAP
from hdbscan import HDBSCAN
import sqlite3
import praw
from tqdm import tqdm
import nltk
import re
from sklearn.feature_extraction.text import CountVectorizer

# Download stopwords if not already downloaded
nltk.download('stopwords')
from nltk.corpus import stopwords

# ---------- Helper Function to Remove Stop Words ----------
def remove_stop_words(text, stop_words):
    # Lowercase and split text, then filter out stop words.
    words = text.lower().split()
    filtered_words = [w for w in words if w not in stop_words]
    return " ".join(filtered_words)

# ---------- Function to Ensure Required Columns in the "posts" Table ----------
def ensure_posts_table_columns():
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cur.fetchall()]  # Extract column names
    if "comments" not in columns:
        print("Adding 'comments' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN comments TEXT")
        conn.commit()
    if "topic" not in columns:
        print("Adding 'topic' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN topic TEXT")
        conn.commit()
    conn.close()

# ---------- Function to Clear Old Posts and Reset Auto-Increment ----------
def clear_posts_table():
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM posts")
    cur.execute("DELETE FROM sqlite_sequence WHERE name='posts'")
    conn.commit()
    conn.close()
    print("Cleared old posts and reset auto-increment.")

# ---------- Function to Fetch and Store Posts from r/LocalLLaMA ----------
def fetch_and_store_localllama_posts(limit=50):
    reddit = praw.Reddit(
        client_id="Dl22HwxEYEjmVuOhkgB_SA",
        client_secret="wEleoUEeucAANVmEosHtaP4YgU01bQ",
        user_agent="AI Marketing Bot/0.1 by Lucky-Requirement676",
        requestor_kwargs={'timeout': 60}
    )
    subreddit = reddit.subreddit("LocalLLaMA")
    posts_data = []
    print("Fetching posts from r/LocalLLaMA...")
    try:
        for post in tqdm(subreddit.hot(limit=limit)):
            content = post.selftext if post.selftext else post.title
            # Fetch top-level comments.
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
                "ai_response": ""  # Initially empty
            })
    except Exception as e:
        print("Error fetching posts from Reddit:", e)
        return

    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    # Create the posts table if it doesn't exist, including comments and topic columns.
    cur.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_title TEXT,
            post_content TEXT,
            comments TEXT,
            ai_response TEXT,
            topic TEXT
        )
    ''')
    for post in posts_data:
        cur.execute("INSERT INTO posts (post_title, post_content, comments, ai_response) VALUES (?, ?, ?, ?)",
                    (post["post_title"], post["post_content"], post["comments"], post["ai_response"]))
    conn.commit()
    conn.close()
    print(f"Stored {len(posts_data)} posts from r/LocalLLaMA into the database.")

# ---------- Function to Get Posts from the Database ----------
def get_posts():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    posts = cur.execute("SELECT id, post_title, post_content, comments, ai_response FROM posts").fetchall()
    conn.close()
    return posts

# ---------- Function to Update Topic for a Post ----------
def update_topic(post_id, topic_label):
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("UPDATE posts SET topic = ? WHERE id = ?", (topic_label, post_id))
    conn.commit()
    conn.close()

# ---------- Helper Function to Perform Topic Modeling on Posts ----------
def perform_topic_modeling_on_posts(posts):
    # Get NLTK stop words and add custom stop words.
    stop_words = set(stopwords.words('english'))
    custom_stop = {
        "im", "ive", "dont", "cant", "you", "me", "now", "like", 
        "research", "open", "local", "translate", "tool", "llms", 
        "would", "inference", "think", "implementation", "explores",
        "nice", "integrations", "flux", "get", "got", "using", "use",
        "make", "just", "know", "way", "something", "used", "need",
        "could", "want", "trying", "even", "gonna", "say", "look",
        "every", "much", "working", "500", "time", "day", "really",
        "see", "stuff", "anyone", "tried", "first", "still", "actually",
        "going", "new", "one", "two", "sure", "bit", "of", "the"
    }
    stop_words = stop_words.union(custom_stop)
    
    texts = []
    post_ids = []
    # Combine title, content, and comments for modeling.
    for post in posts:
        combined_text = post["post_title"] + " " + (post["post_content"] or "") + " " + (post["comments"] or "")
        processed_text = remove_stop_words(combined_text, stop_words)
        if processed_text and len(processed_text.split()) >= 3:
            texts.append(processed_text)
            post_ids.append(post["id"])
    
    if not texts:
        return None, None, None
    
    sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = sentence_model.encode(texts, show_progress_bar=True)
    umap_model = UMAP(n_components=5, random_state=42)
    hdbscan_model = HDBSCAN(min_cluster_size=3, min_samples=1, prediction_data=True)
    topic_model = BERTopic(umap_model=umap_model, hdbscan_model=hdbscan_model,
                           nr_topics="auto", top_n_words=10, calculate_probabilities=True, verbose=True)
    topics, _ = topic_model.fit_transform(texts, embeddings)
    topic_model.update_topics(texts, topics, top_n_words=5)
    return topic_model, topics, post_ids

# ---------- Main Processing ----------
def main():
    clear_posts_table()
    ensure_posts_table_columns()  # Ensure table has 'comments' and 'topic'
    fetch_and_store_localllama_posts(limit=50)
    posts = get_posts()
    if not posts:
        print("No posts found in the database.")
        return
    
    topic_model, topics, post_ids = perform_topic_modeling_on_posts(posts)
    if topic_model is None or topics is None:
        print("No valid text found for topic modeling.")
        return
    
    print(topic_model.get_topic_info())
    
    # Create mapping from post IDs to their indices in the modeling list.
    post_id_to_index = {pid: idx for idx, pid in enumerate(post_ids)}
    
    for post in posts:
        if post["post_content"]:
            if post["id"] in post_id_to_index:
                i = post_id_to_index[post["id"]]
                topic_num = topics[i]
                topic_info = topic_model.get_topic(topic_num)
                if topic_info:
                    topic_words = [word for word, _ in topic_info[:3] if len(word) > 2]
                    if topic_words:
                        # Join each topic word with a comma delimiter.
                        topic_category = ", ".join(topic_words)
                    else:
                        topic_category = "miscellaneous"
                else:
                    topic_category = "miscellaneous"
            else:
                topic_category = "miscellaneous"
            update_topic(post["id"], topic_category)
            print(f"Updated post ID {post['id']} with topic: {topic_category}")

if __name__ == "__main__":
    main()
