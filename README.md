
# **AI-POWERED ENGAGEMENT AUTOMATION PLATFORM**  

---

## 📝 **Project Description:**  
This platform automates content generation and engagement using AI-powered topic modeling and post creation. It allows users to analyze top discussions, generate platform-specific posts (Blogs, LinkedIn, Twitter), and assess alignment scores based on company style and audience discussions.

---

## ✅ **Key Features:**  
- Analyze subreddit posts to identify top topics.  
- Generate posts tailored to specific platforms using the company's style guide.  
- Edit, regenerate, and copy posts directly from the dashboard.  
- View topic distribution, alignment scores, and top discussions.  

---

## 💻 **System Requirements:**  
- Python 3.10 or higher  
- Flask 2.2 or higher  
- SQLite3 for database management  

---

## 📂 **Folder Structure:**  
```
project-folder
├── app.py
├── topic_modeling.py
├── templates
│   ├── index.html
│   ├── company_setup.html
│   ├── generate_prompt_style.html
│   ├── topic_summary.html
├── static
│   ├── css
│   │   └── style.css
├── data.db
├── requirements.txt
└── README.md
```

---

## ⚙️ **Installation Guide:**  

1. **Clone the Repository:**  
```bash
git clone https://github.com/deepikaksr/ai-marketing-automation-community.git
cd ai-marketing-automation-community
```

2. **Set up the Virtual Environment:**  
```bash
python3 -m venv myenv
source myenv/bin/activate 
```

3. **Install Dependencies:**  
```bash
pip install -r requirements.txt
```

4. **Set Up Database:**  
The database `data.db` is automatically created when you run the application. Ensure SQLite is installed on your system.  

5. **Configure API Keys:**  
Set up your Gemini AI API key as an environment variable:  

---

## 🚀 **Running the Application:**  

1. **Start the Flask Server:**  
```bash
python app.py
```

2. **Access the Dashboard:**  
Open your browser and navigate to:  
```
http://127.0.0.1:5000
```

---

## 🗂 **Using the Platform:**  

1. **Company Setup:**  
- Click on **Company Setup** in the navigation bar.  
- Fill in your company name, profile, blog links, keywords, and communities.  
- Click **Update Details** to save the information.  

2. **Viewing Topics:**  
- The dashboard displays the top 15 topics on the right side.  
- Click on a topic to view its summary and related discussions.  

3. **Generating Posts:**  
- Click **Blogs**, **LinkedIn**, or **Twitter** to generate platform-specific posts.  
- The generated post will appear with its topic and content.  

4. **Editing and Saving Posts:**  
- Click **Edit** to modify the post directly below the content box.  
- Click **Save** to update the content immediately.  
- Use **Regenerate** to create a new post if needed.  

5. **Copying Content:**  
- Click **Copy** to copy the generated post to your clipboard.  

---

## 📊 **Topic Scores:**  
- **Response Alignment Score:** Measures how well the generated post aligns with the company’s style guide.  
- **Discussion Alignment Score:** Measures how closely the post aligns with audience discussions on the chosen topic.  

---
