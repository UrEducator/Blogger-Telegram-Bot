import os
import json
import requests
from difflib import get_close_matches
from flask import Flask, request

app = Flask(__name__)

# Configuration - Load from environment variables
BLOG_ID = os.getenv("BLOG_ID")
API_KEY = os.getenv("BLOGGER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

def send_to_telegram(chat_id, text):
    """Send message to Telegram with error handling"""
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Telegram API Error: {str(e)}")
        return False

def search_blogger_posts(keyword, exact_match=True):
    """Search Blogger posts with exact or fuzzy matching"""
    try:
        if exact_match:
            url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts?labels={keyword}&key={API_KEY}"
            response = requests.get(url, timeout=10).json()
            if "error" in response:
                raise ValueError(response["error"].get("message", "Blogger API Error"))
            return response.get("items", [])
        
        # Fuzzy search fallback
        all_posts_url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts?key={API_KEY}"
        all_posts = requests.get(all_posts_url, timeout=10).json().get("items", [])
        
        matched_posts = []
        for post in all_posts:
            post_labels = [label.lower().strip() for label in post.get("labels", [])]
            if (keyword in " ".join(post_labels) or get_close_matches(keyword, post_labels, n=1, cutoff=0.6):
                matched_posts.append(post)
        
        # Deduplicate results
        return list({post['url']: post for post in matched_posts}.values())
        
    except requests.exceptions.RequestException as e:
        print(f"Blogger API Request Failed: {str(e)}")
        return []

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Main webhook endpoint for Telegram"""
    try:
        update = request.get_json()
        message = update.get("message", update)
        
        if not message or "chat" not in message:
            return {"status": "error", "message": "Invalid message format"}, 400
            
        chat_id = message["chat"]["id"]
        keyword = message.get("text", "").strip().lower()
        
        if not keyword:
            send_to_telegram(chat_id, "ℹ️ Please send a search keyword")
            return {"status": "success"}, 200

        # Try exact match first
        posts = search_blogger_posts(keyword, exact_match=True)
        
        # Fallback to fuzzy search
        if not posts:
            posts = search_blogger_posts(keyword, exact_match=False)
            if posts:
                send_to_telegram(chat_id, f"🎯 Found {len(posts)} related matches:")
            else:
                send_to_telegram(chat_id, "❌ No matches found. Try different keywords.")
                return {"status": "success"}, 200
        else:
            send_to_telegram(chat_id, f"🔍 Found {len(posts)} exact matches:")
        
        # Send results (limit to 5 to prevent flooding)
        for post in posts[:5]:
            send_to_telegram(chat_id, f"📖 *{post['title']}*\n{post['url']}")
            
        return {"status": "success"}, 200
        
    except Exception as e:
        error_msg = f"⚠️ Error: {str(e)}"
        print(error_msg)
        if 'chat_id' in locals():
            send_to_telegram(chat_id, error_msg)
        return {"status": "error", "message": str(e)}, 500

def set_telegram_webhook():
    """Configure Telegram webhook on startup"""
    webhook_url = f"https://{os.getenv('RAILWAY_STATIC_URL')}/webhook"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            json={"url": webhook_url}
        )
        print(f"Webhook set to: {webhook_url}")
    except Exception as e:
        print(f"Failed to set webhook: {str(e)}")

if __name__ == '__main__':
    set_telegram_webhook()
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 3000)))