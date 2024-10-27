# app.py

import json
import os
import re
from dotenv import load_dotenv
from urllib.parse import urlparse
from flask import Flask, redirect, url_for, render_template, request, jsonify
from flask_dance.consumer import OAuth2ConsumerBlueprint
from flask_login import LoginManager, login_user, logout_user, current_user, UserMixin
from flask_cors import CORS
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


app = Flask(__name__)       # first we instantiate the Flask object    
CORS(app)

load_dotenv()
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
app.secret_key = os.getenv('SECRET_KEY')    # select a secret key (safeguard against cookie forgery)


# OAuth2 Configuration
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  
#                                                   Remove this in production, allows HTTP, unsafe
#                                                   environmental variables : key value config pairs 
#                                                   that moderate OS - processes interactions
#                                                   by defaul same for a process and all children, 
#                                                   a process can change its own

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# says it all in the docs
google_bp = OAuth2ConsumerBlueprint(        
    "google", 
    __name__,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    scope=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile'],
    base_url="https://www.googleapis.com/oauth2/v2/",
    authorization_url="https://accounts.google.com/o/oauth2/auth",
    token_url="https://accounts.google.com/o/oauth2/token",
    redirect_url='/login/google/authorized' # redirect user here on dance complete
)
app.register_blueprint(google_bp, url_prefix='/login')



# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)

# Define User class, what the Users table looks like in the db, more configs exist for more complex tables
class User(UserMixin):
    def __init__(self, email):
        self.id = email

# necessary boilerplate for session mgmt, gets complex as data models expands
@login_manager.user_loader  
def load_user(user_id):
    return User(user_id)




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






#!                                              BAD + DOESNT DO SHIT
# Extract channel ID from YouTube link
import requests
from bs4 import BeautifulSoup

def get_channel_id_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        html = response.text

        soup = BeautifulSoup(html, 'html.parser')
        # Find the canonical link
        link = soup.find('link', rel='canonical')
        if link:
            canonical_url = link['href']
            # The canonical URL should be in the format https://www.youtube.com/channel/CHANNEL_ID
            parsed_canonical = urlparse(canonical_url)
            if '/channel/' in parsed_canonical.path:
                channel_id = parsed_canonical.path.split('/channel/')[-1].split('/')[0]
                return channel_id
    except Exception as e:
        print(f'Error fetching channel ID from URL: {e}')
        return None

def extract_channel_id(url):
    parsed_url = urlparse(url)
    path = parsed_url.path

    if '/channel/' in path:
        # Standard channel URL
        channel_id = path.split('/channel/')[-1].split('/')[0]
        return channel_id
    elif '/user/' in path:
        # Legacy username URL
        username = path.split('/user/')[-1].split('/')[0]
        return get_channel_id_by_username(username)
    else:
        # Attempt to fetch the channel ID by requesting the URL and parsing the HTML
        channel_id = get_channel_id_from_url(url)
        return channel_id

def get_channel_id_by_username(username):
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request = youtube.channels().list(part='id', forUsername=username)
        response = request.execute()
        items = response.get('items')
        if items:
            return items[0]['id']
    except HttpError:
        return None

def get_channel_id_by_custom_name(custom_name):
    return get_channel_id_by_search_query(custom_name)

def get_channel_id_by_handle(handle):
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request = youtube.channels().list(
            part='id',
            handle=handle
        )
        response = request.execute()
        items = response.get('items')
        if items:
            return items[0]['id']
        else:
            return None
    except HttpError as e:
        print(f'YouTube API Error: {e}')
        return None

def get_channel_id_by_search_query(query):
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request = youtube.search().list(
            part='snippet',
            q=query,
            type='channel',
            maxResults=1
        )
        response = request.execute()
        items = response.get('items')
        if items:
            return items[0]['snippet']['channelId']
    except HttpError:
        return None




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

    channel_link = request.form.get('channel_link')
    if not channel_link:
        return 'No channel link provided', 400

    # Extract channel ID from the link
    channel_id = extract_channel_id(channel_link)
    if not channel_id:
        return 'Invalid channel link', 400

    # Fetch channel name using YouTube API
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request_ = youtube.channels().list(part='snippet', id=channel_id)
        response = request_.execute()
        items = response.get('items')
        if items:
            channel_name = items[0]['snippet']['title']
            channels = load_json('channels.json', 'channels')
            # Check for duplication
            if not any(c['channel_id'] == channel_id for c in channels):
                channels.append({'name': channel_name, 'channel_id': channel_id})
                save_json('channels.json', 'channels', channels)
        else:
            return 'Channel not found', 404
    except HttpError as e:
        return f'YouTube API Error: {e}', 500

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

@app.route('/api/playlists')
def api_playlists():
    playlists = load_json('playlists.json', 'playlists')
    return jsonify(playlists)

@app.route('/api/channels')
def api_channels():
    channels = load_json('channels.json', 'channels')
    return jsonify(channels)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('google.logout'))

if __name__ == '__main__':
    app.run(debug=True)