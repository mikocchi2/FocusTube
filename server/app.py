# app.py

import json
import os
from dotenv import load_dotenv
from flask import Flask, redirect, url_for, render_template, request, jsonify
from flask_dance.consumer import OAuth2ConsumerBlueprint
from flask_login import LoginManager, login_user, logout_user, current_user, UserMixin
from flask_cors import CORS
from googleapiclient.discovery import build
from gpt import askGpt

app = Flask(__name__)
CORS(app)

load_dotenv()
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
app.secret_key = os.getenv('SECRET_KEY')

print(CLIENT_SECRET)

# OAuth2 Configuration
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Remove this in production
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


google_bp = OAuth2ConsumerBlueprint(
    "google", __name__,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    scope=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile'],
    base_url="https://www.googleapis.com/oauth2/v2/",
    authorization_url="https://accounts.google.com/o/oauth2/auth",
    token_url="https://accounts.google.com/o/oauth2/token",
    redirect_url='/login/google/authorized'
)
app.register_blueprint(google_bp, url_prefix='/login')

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)

# Define User class
class User(UserMixin):
    def __init__(self, email):
        self.id = email

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


youtube_api_key = os.getenv('YOUTUBE_API_KEY')
if not youtube_api_key:
    raise EnvironmentError("Error: YOUTUBE_API_KEY is not set in environment variables.")

youtube = build('youtube', 'v3', developerKey=youtube_api_key)

# In-memory store for search results
recent_search = {
    'query': None,
    'results': []
}

# Load and save JSON Data
def load_json(filename, key):
    file_path = os.path.join(BASE_DIR, filename)
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data.get(key, [])
    except FileNotFoundError:
        return []

def save_json(filename, key, items):
    data = {key: items}
    file_path = os.path.join(BASE_DIR, filename)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)


# Allowed filters for query validation
FILTERS = (
    "computer science, programming, software engineering, anything I'd study at the Faculty of Organizational Sciences "
    "in Belgrade (operations research, management, IT-related topics), learning guitar. "
    "Basically anything that has to do with tech, science, learning to play guitar, music in general, ex-yu rock is good"
)

def validate_query(query: str) -> bool:
    """
    Validates the query using GPT to determine if it matches the allowed filters.
    
    Args:
        query (str): The search query to validate.
        
    Returns:
        bool: True if the query is allowed, False otherwise.
    """
    init_prompt = (
        "I will be sending you YouTube query requests for my focus YouTube wrapper, then a filter, "
        "then the query to test. You need to respond with ALLOW if you think the query should run or DENY if the query "
        "doesn't match the filters. Below I will provide the filters. "
        "The query must only be about:"
    )

    full_prompt = f"{init_prompt} {FILTERS} Query: {query}"

    try:
        gpt_response = askGpt(full_prompt)
        return gpt_response == 'ALLOW'
    except Exception as e:
        print(f"GPT validation failed: {e}")
        return False

def perform_youtube_search(query: str):
    """
    Performs a YouTube search using the YouTube Data API.
    
    Args:
        query (str): The search query.
        
    Returns:
        list: A list of dictionaries containing video IDs and titles.
    """
    try:
        request = youtube.search().list(
            part='snippet',
            q=query,
            type='video',
            maxResults=10  # Adjust as needed
        )
        response = request.execute()
        results = [
            {
                'videoId': item['id']['videoId'],
                'title': item['snippet']['title']
            }
            for item in response.get('items', [])
        ]
        return results
    except Exception as e:
        print(f"YouTube search failed: {e}")
        return []










# Routes
@app.route('/')
def index():
    return redirect(url_for('admin'))

@app.route('/admin')
def admin():
    if not google_bp.session.authorized:
        return redirect(url_for('google.login'))

    resp = google_bp.session.get('/oauth2/v2/userinfo')
    if not resp.ok:
        return 'Could not fetch your information from Google.', 500
    email = resp.json()['email']

    if email != ADMIN_EMAIL:
        return 'Access denied', 403

    user = User(email)
    login_user(user)

    playlists = load_json('playlists.json', 'playlists')
    channels = load_json('channels.json', 'channels')

    return render_template('admin.html', playlists=playlists, channels=channels, email=email)




@app.route('/add_playlist', methods=['POST'])
def add_playlist():
    if not current_user.is_authenticated:
        return redirect(url_for('google.login'))

    name = request.form.get('name')
    playlist_id = request.form.get('playlist_id')

    if not name or not playlist_id:
        return 'Name and Playlist ID are required', 400

    playlists = load_json('playlists.json', 'playlists')
    # Check for duplication
    if not any(p['id'] == playlist_id for p in playlists):
        playlists.append({'name': name, 'id': playlist_id})
        save_json('playlists.json', 'playlists', playlists)

    return redirect(url_for('admin'))

@app.route('/remove_playlist', methods=['POST'])
def remove_playlist():
    if not current_user.is_authenticated:
        return redirect(url_for('google.login'))

    playlist_id = request.form.get('playlist_id')
    playlists = load_json('playlists.json', 'playlists')
    updated_playlists = [p for p in playlists if p['id'] != playlist_id]
    save_json('playlists.json', 'playlists', updated_playlists)
    return redirect(url_for('admin'))




@app.route('/add_channel', methods=['POST'])
def add_channel():
    if not current_user.is_authenticated:
        return redirect(url_for('google.login'))

    channel_name = request.form.get('channel_name')
    channel_id = request.form.get('channel_id')

    if not channel_name or not channel_id:
        return 'Channel Name and Channel ID are required', 400

    channels = load_json('channels.json', 'channels')
    # Check for duplication
    if not any(c['channel_id'] == channel_id for c in channels):
        channels.append({'name': channel_name, 'channel_id': channel_id})
        save_json('channels.json', 'channels', channels)

    return redirect(url_for('admin'))

@app.route('/remove_channel', methods=['POST'])
def remove_channel():
    if not current_user.is_authenticated:
        return redirect(url_for('google.login'))

    channel_id = request.form.get('channel_id')
    channels = load_json('channels.json', 'channels')
    updated_channels = [c for c in channels if c['channel_id'] != channel_id]
    save_json('channels.json', 'channels', updated_channels)
    return redirect(url_for('admin'))

@app.route('/api/search', methods=['GET'])
def search():
    """
    Endpoint to handle search requests.
    
    Expects a query parameter:
    /api/search?query=your+search+query
    
    Returns:
        JSON response indicating success or an error message.
    """
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Missing or empty "query" parameter.'}), 400

    if not validate_query(query):
        return jsonify({'error': 'Query does not match the allowed filters.'}), 403

    results = perform_youtube_search(query)
    if not results:
        return jsonify({'error': 'No results found or an error occurred during the search.'}), 500

    # Update the recent search with the current query and its results
    recent_search['query'] = query
    recent_search['results'] = results

    return jsonify({'message': 'Search successful.', 'query': query, 'number_of_results': len(results)}), 200

@app.route('/api/searchresults', methods=['GET'])
def get_search_results():
    """
    Endpoint to retrieve the most recent search results.
    
    Returns:
        JSON response with video IDs and titles, or an error message if no search has been performed.
    """
    if not recent_search['query']:
        return jsonify({'error': 'No search has been performed yet.'}), 404

    return jsonify({
        'query': recent_search['query'],
        'results': recent_search['results']
    }), 200




@app.route('/api/playlists')
def api_playlists():
    playlists = load_json('playlists.json', 'playlists')
    return jsonify(playlists)

@app.route('/api/channels')
def api_channels():
    channels = load_json('channels.json', 'channels')
    return jsonify(channels)

@app.route('/api/search')
def get_search_query():
    query = request.args.get('query', '')
    
    return jsonify([])



@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('google.logout'))

if __name__ == '__main__':
    app.run(debug=True)