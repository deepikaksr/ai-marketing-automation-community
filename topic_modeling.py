from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from umap import UMAP
from hdbscan import HDBSCAN
import sqlite3
import praw
from tqdm import tqdm

# ---------- Function to Ensure the "topic" Column Exists ----------
def ensure_topic_column():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(posts)")
    columns = [row["name"] for row in cur.fetchall()]
    if "topic" not in columns:
        print("Adding 'topic' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN topic TEXT")
        conn.commit()
    conn.close()

# ---------- Function to Clear Old Posts and Reset Auto-Increment ----------
def clear_posts_table():
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    # Delete all rows from posts.
    cur.execute("DELETE FROM posts")
    # Reset the auto-increment counter.
    cur.execute("DELETE FROM sqlite_sequence WHERE name='posts'")
    conn.commit()
    conn.close()
    print("Cleared old posts and reset auto-increment.")

# ---------- Function to Fetch and Store Posts from r/LocalLLaMA ----------
def fetch_and_store_localllama_posts(limit=50):
    reddit = praw.Reddit(
        client_id="Dl22HwxEYEjmVuOhkgB_SA",
        client_secret="wEleoUEeucAANVmEosHtaP4YgU01bQ",
        user_agent="AI Marketing Bot/0.1 by Lucky-Requirement676"
    )
    subreddit = reddit.subreddit("LocalLLaMA")
    posts_data = []
    print("Fetching posts from r/LocalLLaMA...")
    for post in tqdm(subreddit.hot(limit=limit)):
        # Use post.selftext if available; otherwise, use post.title.
        content = post.selftext if post.selftext else post.title
        posts_data.append({
            "post_title": post.title,
            "post_content": content,
            "ai_response": ""  # Initially empty
        })
    
    # Insert fetched posts into the database.
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    # Create the posts table if it doesn't exist.
    cur.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_title TEXT,
            post_content TEXT,
            ai_response TEXT,
            topic TEXT
        )
    ''')
    for post in posts_data:
        cur.execute("INSERT INTO posts (post_title, post_content, ai_response) VALUES (?, ?, ?)",
                    (post["post_title"], post["post_content"], post["ai_response"]))
    conn.commit()
    conn.close()
    print(f"Stored {len(posts_data)} posts from r/LocalLLaMA into the database.")

# ---------- Function to Get Posts from the Database ----------
def get_posts():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    posts = cur.execute("SELECT id, post_title, post_content, ai_response FROM posts").fetchall()
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
    texts = [post["post_content"] for post in posts if post["post_content"]]
    if not texts:
        return None, None
    # Load SentenceTransformer for embeddings.
    sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = sentence_model.encode(texts, show_progress_bar=True)
    # Initialize UMAP and HDBSCAN with custom parameters.
    umap_model = UMAP(n_components=2, random_state=42)
    hdbscan_model = HDBSCAN(min_cluster_size=2, min_samples=1, prediction_data=True)
    # Initialize BERTopic with the custom models.
    topic_model = BERTopic(umap_model=umap_model, hdbscan_model=hdbscan_model)
    topics, _ = topic_model.fit_transform(texts, embeddings)
    return topic_model, topics

# ---------- Main Processing ----------
def main():
    # Clear old posts and reset auto-increment.
    clear_posts_table()
    
    # Fetch and store posts from r/LocalLLaMA.
    fetch_and_store_localllama_posts(limit=50)
    
    # Ensure the posts table has a "topic" column.
    ensure_topic_column()
    
    # Retrieve posts from the database.
    posts = get_posts()
    if not posts:
        print("No posts found in the database.")
        return
    
    # Perform topic modeling.
    topic_model, topics = perform_topic_modeling_on_posts(posts)
    if topic_model is None or topics is None:
        print("No valid text found for topic modeling.")
        return
    
    # Print topic information for inspection.
    print(topic_model.get_topic_info())
    
    # Update each post with its assigned topic.
    for i, post in enumerate(posts):
        if post["post_content"]:
            topic_num = topics[i]
            topic_info = topic_model.get_topic(topic_num)
            if topic_info:
                topic_category = ", ".join([word for word, _ in topic_info[:3]])
            else:
                topic_category = str(topic_num)
            update_topic(post["id"], topic_category)
            print(f"Updated post ID {post['id']} with topic: {topic_category}")

if __name__ == "__main__":
    main()
