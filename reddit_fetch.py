import praw
import sqlite3
from transformers import pipeline

# Step 1: Initialize Reddit API
reddit = praw.Reddit(
    client_id="Dl22HwxEYEjmVuOhkgB_SA",
    client_secret="wEleoUEeucAANVmEosHtaP4YgU01bQ",
    user_agent="AI Marketing Bot/0.1 by Lucky-Requirement676"
)

# Step 2: Set Up SQLite Database
conn = sqlite3.connect('data.db')
cur = conn.cursor()

cur.execute('''
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_title TEXT,
        post_content TEXT,
        ai_response TEXT,
        approved INTEGER DEFAULT 0
    )
''')
conn.commit()

# Step 3: Initialize GPT-2 for AI Response Generation
generator = pipeline('text-generation', model='gpt2')

def generate_ai_response(post_text):
    """
    Generate an AI response for the given post text using GPT-2.
    If the post text is empty, use the post title instead.
    """
    prompt = f"Write a thoughtful response for: {post_text}"
    # Use max_new_tokens to specify the number of tokens to generate.
    response = generator(prompt, max_new_tokens=50)
    return response[0]['generated_text'].strip()

# Step 4: Fetch Posts from Reddit and Store Data
subreddit = reddit.subreddit("learnpython")
for post in subreddit.hot(limit=5):
    title = post.title
    content = post.selftext  # For self-posts; if empty, it might be a link post

    # Generate an AI response; use title as fallback if content is empty
    ai_response = generate_ai_response(content if content else title)

    cur.execute('''
        INSERT INTO posts (post_title, post_content, ai_response, approved)
        VALUES (?, ?, ?, ?)
    ''', (title, content, ai_response, 0))
    
    print(f"Inserted post: {title}")
    print("AI Response:", ai_response)
    print("-" * 40)

conn.commit()
conn.close()

print("All posts and AI responses have been stored in data.db!")
