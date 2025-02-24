from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from umap import UMAP
from hdbscan import HDBSCAN
import sqlite3

# Function to ensure that the "topic" column exists in the "posts" table.
def ensure_topic_column():
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(posts)")
    columns = [info[1] for info in cur.fetchall()]
    if "topic" not in columns:
        print("Adding 'topic' column to posts table.")
        cur.execute("ALTER TABLE posts ADD COLUMN topic TEXT")
        conn.commit()
    conn.close()

# Call the function to ensure the column exists.
ensure_topic_column()

# Fetch posts from the database
def get_posts():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    posts = cur.execute("SELECT id, post_content FROM posts").fetchall()
    conn.close()
    return posts

# Update topic info for a post
def update_topic(post_id, topic_label):
    conn = sqlite3.connect('data.db')
    cur = conn.cursor()
    cur.execute("UPDATE posts SET topic = ? WHERE id = ?", (topic_label, post_id))
    conn.commit()
    conn.close()

posts = get_posts()
# Prepare texts from posts (using post_content)
texts = [post["post_content"] for post in posts if post["post_content"]]

# Load a sentence transformer model to generate embeddings
sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = sentence_model.encode(texts, show_progress_bar=True)

# Initialize UMAP with lower n_components to avoid dimensionality issues
umap_model = UMAP(n_components=2, random_state=42)

# Customize HDBSCAN parameters for small datasets
hdbscan_model = HDBSCAN(min_cluster_size=2, min_samples=1, prediction_data=True)

# Initialize BERTopic with the custom UMAP and HDBSCAN models
topic_model = BERTopic(umap_model=umap_model, hdbscan_model=hdbscan_model)

# Fit the topic model on your texts and embeddings
topics, _ = topic_model.fit_transform(texts, embeddings)

# Print topic information for inspection
print(topic_model.get_topic_info())

# Assign topics back to posts (assuming the order matches)
for i, post in enumerate(posts):
    if post["post_content"]:
        topic_label = str(topics[i])
        update_topic(post["id"], topic_label)
        print(f"Updated post ID {post['id']} with topic {topic_label}")
