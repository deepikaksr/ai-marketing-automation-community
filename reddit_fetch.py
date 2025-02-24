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

# Create a table for posts with an additional 'topic' column for future use.
cur.execute('''
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_title TEXT,
        post_content TEXT,
        ai_response TEXT,
        approved INTEGER DEFAULT 0,
        topic TEXT
    )
''')
conn.commit()

# Step 3: Initialize GPT-2 for AI Response Generation
generator = pipeline('text-generation', model='gpt2')

def generate_ai_response(post_text):
    """
    Generate an AI response using advanced prompt engineering.
    The prompt now includes industry-specific instructions to reflect a professional tone.
    """
    prompt = (
        "Act as a marketing expert for a tech startup/SaaS company. "
        "Your response should be authoritative, data-driven, and customer-centric. "
        "Respond thoughtfully to the following discussion:\n\n"
        f"{post_text}\n\n"
        "Response:"
    )
    response = generator(prompt, max_new_tokens=50)
    return response[0]['generated_text'].strip()

# Step 4: Fetch Posts from Reddit and Store Data
subreddit = reddit.subreddit("learnpython")
for post in subreddit.hot(limit=5):
    title = post.title
    content = post.selftext  # For self-posts; if empty, it might be a link post

    # Generate an AI response; use title as fallback if content is empty
    ai_response = generate_ai_response(content if content else title)
    
    # Set a placeholder topic (to be updated later via topic modeling)
    topic_placeholder = "Uncategorized"
    
    cur.execute('''
        INSERT INTO posts (post_title, post_content, ai_response, approved, topic)
        VALUES (?, ?, ?, ?, ?)
    ''', (title, content, ai_response, 0, topic_placeholder))
    
    print(f"Inserted post: {title}")
    print("AI Response:", ai_response)
    print("-" * 40)

conn.commit()
conn.close()

print("All posts and AI responses have been stored in data.db!")
