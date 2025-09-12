# Name: web_server.py
# Quick Desc: Web server for Spotify DWN
# Author: w1l238
# Project Link: https://github.com/w1l238/CLI-Spotify-Downloader 
# Desc:
#   Backend web server for Spotify Downloader
#   Program is able to:
#    - Search a song
#    - Display results
#    - Download a song
#    - Import a file to mass download songs
#    - Show live terminal results
#    - Edit API keys and path(s)

# Import statements
import eventlet
import eventlet.wsgi
from spotdl import Spotdl
from urllib.parse import quote_plus
from flask_socketio import SocketIO, emit
from flask import Flask, request, render_template, redirect, url_for, flash, get_flashed_messages, jsonify, session
from dotenv import load_dotenv
from user_agents import parse
import requests
import subprocess
import os
import re
import sys
import json

# Flask app setup
app = Flask(__name__)

# Load key from .env
app.secret_key = os.getenv("FLASK_SECRET", "SECRET")

# Start the socketIO server to provide terminal output in webviewer
socketio = SocketIO(app)

#=================
# Helper Functions
#=================

# Get API token using Client ID and Client Secret
# If found return the access token
# If not found return 'None'
def generate_token(CLIENT_ID, CLIENT_SECRET):
    auth_response = requests.post('https://accounts.spotify.com/api/token', data={
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    })
    try:
        access_token = auth_response.json()['access_token']
        return access_token
    except:
        return None


# Searches spotify song after taking name and artist as input with spotify API access token generated from generate token function
# If song is found return the track artist, album name, track name, and track url
# If song not found return 'None'
def search_spotify_song(access_token, song_name, artist_name, limit):
    # Pass access token for auth using spotify API
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    # Query the search
    query = f"track:{song_name} artist:{artist_name}"
    # Filter the search to a track
    params = {
        "q": query,
        "type": "track",
        "limit": limit
    }
    # Spotify API endpoint
    search_url = "https://api.spotify.com/v1/search"

    # Store the response from API
    response = requests.get(search_url, headers=headers, params=params)
    
    # If the response fails return 'None'
    if response.status_code != 200:
        print(f"Spotify API search failed: {response.status_code} {response.text}")
        return []

    # Store results in json
    results = response.json()
    
    # Grab the needed data from the json
    tracks = results.get("tracks", {}).get("items", [])
    
    # If the needed data isn't found in the json from the API return 'None'
    if not tracks:
        print(f"No matching tracks found for '{song_name}' by '{artist_name}'.")
        return []

    # Store each part of the json in different variables
    # Track Name
    # Track Artist
    # Album Name
    # Track URL (Spotify's URL)
    # 
    track_list = [] # Dictionary of metadata for each track
    for track in tracks:
        images = track["album"].get("images", [])
        albumn_artwork_url = images[0]["url"] if images else None
        track_info = {
            "song": track["name"],
            "artist": ", ".join(artist["name"] for artist in track["artists"]),
            "album": track["album"]["name"],
            "url": track["external_urls"]["spotify"],
            "artwork": albumn_artwork_url,
            "track_id": track["id"]
        }
        track_list.append(track_info) # Append to dictionary array
    # Print that the song was found
    print(f"Found {len(track_list)} tracks for '{song_name}' by '{artist_name}'.")

    # Return the data
    return track_list

# Set the destination path using the path the user requests
# Return the newly made folder or return the already valid folder
def set_folder(givn_folder):
    
    # If folder doesn't exist. Make it and return the path
    if not os.path.exists(givn_folder): 
        os.makedirs(givn_folder)
        print(f"\nCreating folder '{givn_folder}'...")
        return givn_folder
    
    # If the folder already exists then return it
    else:
        return givn_folder


# Create song folder structure function given song, album, and artist
def create_song_folder_structure(dest_path, artist, playlist, song_name):

    # Remove any spaces or illegal characters the playlists/artists used
    safe_artist = sanitize_filename(artist)
    safe_playlist = sanitize_filename(playlist)

    # Create the folder structure using the legal characters 
    artist_folder = os.path.join(dest_path, safe_artist)
    playlist_folder = os.path.join(artist_folder, safe_playlist)
    os.makedirs(playlist_folder, exist_ok=True)
    
    # Return the path to the playlist folder
    return playlist_folder


# Removes illegal characters to create a valid path for the OS
# Returns the legal path that the OS can use
def sanitize_filename(name):
    
    # Remove illegal characters for file/folder names
    return re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name).strip()

# Download a specific song given the song's Spotify URL and the output path
# If song is found then download it using spotdl
# Falls back to yt-dlp if spotdl is unable to download due to audio provider error
# Falls back to yt-dlp if spotdl is unable to download due to audio provider error
# If spotfl throws error then output that an error occured
def download_spotify_url(spotify_url, output_folder):
        
    # Returns the folder where this script is stored
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Split path into parts
    parts = current_dir.split(os.sep)

    # Find index of the target folder
    try:
        idx = parts.index('CLI-Spotify-Downloader')
        # Rebuild path up to and including target folder
        current_dir = os.sep.join(parts[:idx + 1])
    except ValueError:
        # 'CLI-Spotify-Downloader' not found, keep current_dir as is or handle error
        pass


    # Local FFmpeg path in VENV (as spotdl doesn't place it correctly when downloading it)
    ffmpeg_path = "C:\\Users\\w1l\\dev\\CLI-Spotify-Downloader\\venv\\Scripts\\ffmpeg.exe"

    # Spotdl's command to download a song using Spotify's song url
    command = [sys.executable, "-u", "-m", "spotdl", "--ffmpeg", ffmpeg_path, spotify_url]
    
    # Set the output folder for spotdl to use
    if output_folder:
        command.extend(["--output", output_folder])
    
    # Call spotdl to download the song
    try:
        # spotdl has it's own output here showing a progress bar and if it downloaded successfully etc.
        # Using popen to capture stdout to pass to front end web viewer
        spotdl_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

        all_output = ""

        # Output stdout to terminal and variable
        try:
            # read and show the command's stdout in real time
            for line in spotdl_process.stdout:
                # emit it back to the client (front end)
                print(line, end='')
                socketio.emit('stdout', {'data': line})
                socketio.sleep(0)
                all_output += line
                

            # Close the stream
            spotdl_process.stdout.close()

            # Get the return code
            return_code = spotdl_process.wait()

            # # If Spotdl encounters a audioprovider error then download using yt-dlp using yt URL
            # if "AudioProviderError" in all_output:
            yt_URL = re.search(r"AudioProviderError:.*-\s*(https?://\S+)", all_output) # Extract the URL

            if yt_URL:
                fallback_url = yt_URL.group(1)
                print(f"\nUsing fallback URL: {fallback_url}")

                # Local FFmpeg path in VENV (as spotdl doesn't place it correctly)
                print("[OS] Scanning Device Operating System...")
                if os.name == 'nt': # Windows
                    print("[OS] Device running Windows.")
                    ffmpeg_path = os.path.join(current_dir, 'venv', 'Scripts', 'ffmpeg.exe')
                elif os.name != 'nt': # Default to linux if not windows
                    print("[OS] Device running UNIX")
                    ffmpeg_path = os.path.join(current_dir, 'venv', 'bin', 'ffmpeg')

                # Check if ffmpeg path is valid
                if os.path.isfile(ffmpeg_path) or os.access(ffmpeg_path, os.X_OK):
                    # Download using yt-dlp and convert to mp3 using ffmpeg
                    yt_dlp_command = ["yt-dlp", fallback_url, "-P", output_folder, "-x", "--audio-format", "mp3", "--ffmpeg-location", ffmpeg_path]
                else:
                    # Warn user that ffmpeg isn't found
                    print("[WARN] ffmpeg package not found. Continuing to download without ffmpeg...")
           
                    # Download using yt-dlp and attempt to convert to mp3 without ffmpeg 
                    yt_dlp_command = ["yt-dlp", fallback_url, "-P", output_folder, "-x", "--audio-format", "mp3"]
                    
                # Call yt-dlp and stream the output to the wbe viewer
                yt_process = subprocess.Popen(yt_dlp_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

                # read and show the command's stdout in real time
                for line in yt_process.stdout:
                    # emit it back to the client (front end)
                    print(line, end='')
                    socketio.emit('stdout', {'data': line})
                    socketio.sleep(0)

                # Close the stream
                yt_process.stdout.close()
            
                # Get the return code
                return_code = yt_process.wait()
            # Get the return code
            return_code = spotdl_process.wait()

            # # If Spotdl encounters a audioprovider error then download using yt-dlp using yt URL
            # if "AudioProviderError" in all_output:
            yt_URL = re.search(r"AudioProviderError:.*-\s*(https?://\S+)", all_output) # Extract the URL

            if yt_URL:
                fallback_url = yt_URL.group(1)
                print(f"\nUsing fallback URL: {fallback_url}")

                # Download using yt-dlp and convert to mp3 using ffmpeg
                yt_dlp_command = ["yt-dlp", fallback_url, "-P", output_folder, "--ffmpeg-location", ffmpeg_path, "-x", "--audio-format", "mp3", ]
                    
                # Call yt-dlp and stream the output to the wbe viewer
                yt_process = subprocess.Popen(yt_dlp_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

                # read and show the command's stdout in real time
                for line in yt_process.stdout:
                    # emit it back to the client (front end)
                    print(line, end='')
                    socketio.emit('stdout', {'data': line})
                    socketio.sleep(0)

                # Close the stream
                yt_process.stdout.close()
            
                # Get the return code
                return_code = yt_process.wait()
            # Get the return code
            return_code = spotdl_process.wait()

            # # If Spotdl encounters a audioprovider error then download using yt-dlp using yt URL
            # if "AudioProviderError" in all_output:
            yt_URL = re.search(r"AudioProviderError:.*-\s*(https?://\S+)", all_output) # Extract the URL

            if yt_URL:
                fallback_url = yt_URL.group(1)
                print(f"\nUsing fallback URL: {fallback_url}")

                # Download using yt-dlp and convert to mp3 using ffmpeg
                yt_dlp_command = ["yt-dlp", fallback_url, "-P", output_folder, "-x", "--audio-format", "mp3", "--ffmpeg-location", ffmpeg_path]
                    
                # Call yt-dlp and stream the output to the wbe viewer
                yt_process = subprocess.Popen(yt_dlp_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

                # read and show the command's stdout in real time
                for line in yt_process.stdout:
                    # emit it back to the client (front end)
                    print(line, end='')
                    socketio.emit('stdout', {'data': line})
                    socketio.sleep(0)

                # Close the stream
                yt_process.stdout.close()
            
                # Get the return code
                return_code = yt_process.wait()
        
            # If the call fails show that to the front end
            if return_code != 0:
                # emit a error message to web viewer client
                socketio.emit('stdout', {'data': f"Download failed with code {return_code}."})
            else:
                socketio.emit('download_complete', {'message': 'Download completed successfully!'})

        except Exception as e:
            socketio.emit('download_error', {'message': f"Error during download: {e}"})

    # If the calling of the command throws an error print it
    except subprocess.CalledProcessError as e: 
        print(f"Error during download: {e}")
        flash("Error during download. Please try again.")

# Imports and parses json file given the file's path
# Returns download path and each song in the json file
def parse_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['download_path'], [(s['song_name'], s['artist_name']) for s in data['songs']]

# Function that gets new releases from spotify's API to display for the browse feature
def get_new_releases(access_token, country_code="US", limit=20):
    """Gets a list of new album releases on Spotify."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"country": country_code, "limit": limit}
    browse_url = "https://api.spotify.com/v1/browse/new-releases"
    
    response = requests.get(browse_url, headers=headers, params=params)
    
    if response.status_code == 200:
        # The result is a list of album objects
        return response.json().get('albums', {}).get('items', [])
    
    print(f"Failed to get new releases: {response.status_code} {response.text}")
    return None

# Function
def get_browse_categories(access_token, country_code="US", limit=50):
    """Gets a list of available genre categories."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"country": country_code, "limit": limit}
    browse_url = "https://api.spotify.com/v1/browse/categories"
    
    response = requests.get(browse_url, headers=headers, params=params)
    
    if response.status_code == 200:
        # The result is a list of category objects, each with an 'id' and 'name'
        return response.json().get('categories', {}).get('items', [])
    
    return None


def get_category_playlists(access_token, category_id, country_code="US", limit=20):
    """Gets playlists for a specific category."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"country": country_code, "limit": limit}
    browse_url = f"https://api.spotify.com/v1/browse/categories/{category_id}/playlists"
    
    response = requests.get(browse_url, headers=headers, params=params)
    
    if response.status_code == 200:
        # The result is a list of playlist objects
        return response.json().get('playlists', {}).get('items', [])
        
    return None

def get_track_details(access_token, track_id):
    """Gets detailed information for a single track."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/tracks/{track_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    print(f"Failed to get track details: {response.status_code} {response.text}")
    return None

def get_album_details(access_token, album_id):
    """Gets detailed information for a single album."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/albums/{album_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    print(f"Failed to get album details: {response.status_code} {response.text}")
    return None

def get_album_tracks(access_token, album_id):
    """Gets all tracks from a Spotify album, handling pagination."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
    tracks = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to get album tracks: {response.status_code} {response.text}")
            return None
        data = response.json()
        tracks.extend(data.get('items', []))
        url = data.get('next')
    return tracks

def get_artist_details(access_token, artist_id):
    """Gets detailed information for a single artist."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/artists/{artist_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    print(f"Failed to get artist details: {response.status_code} {response.text}")
    return None

# Function to get a playlist name, cover image, and description
def get_playlist_details(access_token, playlist_id):
    """Gets metadata for a specific playlist."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    print(f"Failed to get playlist details: {response.status_code} {response.text}")
    return None

# Function to get a playlist's tracks (All of them for a list view)
def get_playlist_tracks(access_token, playlist_id):
    """Gets all tracks from a Spotify playlist, handling pagination."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    tracks = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to get playlist tracks: {response.status_code} {response.text}")
            return None
        data = response.json()
        tracks.extend(data.get('items', []))
        url = data.get('next')  # Get URL for the next page of results, or None if it's the last page
    return tracks
    

#====================
# App Route Functions
#====================

# Backend logic for root page (index.html)
@app.route("/", methods=["GET", "POST"])
def index():

    #  Added mobile template html path based on device's User Agent
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    if user_agent.is_mobile:
        template = "mobile/index.html"
        result_template = "mobile/results.html"
    else:
        template = "index.html"
        result_template = "results.html"
    # Flash to user's screen type of device for debugging
    # flash(f"User-Agent: {ua_string}, Selected template: {template}")


    # flash((f"Detected User-Agent: {request.headers.get('User-Agent')}"))
    # flash(f"Rendering template: {template}")

    # When user submits the form (AKA searching for a song)
    if request.method == "POST":

        # Load env variables
        load_dotenv(override=True)

        # Spotify API Client Credentials
        CLIENT_ID = os.getenv("CLIENT_ID")
        CLIENT_SECRET = os.getenv("CLIENT_SECRET")
        print(f"ID and Secret: {CLIENT_ID}, {CLIENT_SECRET}")

        # Store user input as variables
        song_name = request.form.get("song_Name")
        artist_name = request.form.get("artist_Name")
        

        # Try to search for the song
        try:
            # Generate the token
            token = generate_token(CLIENT_ID,CLIENT_SECRET)
                
            if not token:
                flash("Unable to acquire token. Please check API credentials.", "error")
                return render_template(template)

            # Search for the spotify song
            song_data = search_spotify_song(token, song_name, artist_name, 5) # USE ONE FOR TESTING. WILL DEFAULT TO 5
                

            if not song_data or len(song_data) == 0:
                flash("No songs found. Please try a different title or artist.", "error")
                return redirect(url_for('index'))

            valid_tracks = [track for track in song_data if track.get("url")]
            if not valid_tracks:
                flash("No valid song URLs found in results.", "error")
                return redirect(url_for('index'))
            
            # Return the data
            return render_template(result_template, tracks=valid_tracks, query=f"{song_name} by {artist_name}")
        
        # If the song is unable to be searched for then print error and loop back to main menu
        except Exception as e:
            # Optionally log exception e somewhere for debugging
            flash("Error: Please check your API keys and try again.", "error")
            flash(f"Error Message Code: {e}")
            return redirect(url_for('index'))

        # Else throw error and tell user and return
        else:
            flash("Song not found. Please try a different title or artist.", "error")
            return redirect(url_for('index'))

    return render_template(template)

# Import page logic for import.html
@app.route('/import', methods=["GET", "POST"])
def import_page():
    
    #  Added mobile template html path based on device's User Agent
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    if user_agent.is_mobile:
        template = "mobile/import.html"
    else:
        template = "import.html"
    # Flash to user's screen type of device for debugging
    # flash(f"User-Agent: {ua_string}, Selected template: {template}")

    # On form submission run this if block
    if request.method == "POST":
        print("GOT POST STARTING...")

        # Load env variables
        load_dotenv(override=True)

        # Spotify API Client Credentials
        CLIENT_ID = os.getenv("CLIENT_ID")
        CLIENT_SECRET = os.getenv("CLIENT_SECRET")
        print(f"ID and Secret: {CLIENT_ID}, {CLIENT_SECRET}")

        # Store path from user
        import_file_path = request.form.get("import_Path")
        print(import_file_path)

        try:
            path, songs = parse_json_file(import_file_path)
            print(songs)
        
        except FileNotFoundError:
            flash(f"\nUnable to find import file with path '{import_file_path}' provided.")
            songs = []  # To avoid reference error
        
        except Exception as e:
            flash(f"Error found: '{e}'")
            songs = []

        song_data_list = [] # List to send to JS

        for song_name, artist_name in songs:
            # Generate token for Spotify's API
            token = generate_token(CLIENT_ID, CLIENT_SECRET)

            if token is None:
                flash("Unable to acquire token. Check your API keys.")
                return render_template("import_page.html")

            try:
                song_data = search_spotify_song(token, song_name, artist_name, 1)
                if not song_data:
                    flash(f"No data found for {song_name} by {artist_name}.")
                    continue

                track = song_data[0]

                if "url" in track and track["url"]:
                    # Define artist, album, song, url for folder creation and download
                    artist = track.get("artist")
                    album = track.get("album")
                    song = track.get("song")
                    url = track.get("url")

                    try:
                        dest_path = set_folder(path)
                    except OSError as e:
                        flash(f"Failed to create or access folder: {e}")
                        continue  # Skip this song on folder error

                    song_path = create_song_folder_structure(dest_path, artist, album, song)

                    #socketio.start_background_task(download_spotify_url, url, song_path)

                    # List of data to return
                    song_info = {
                        'track_url': url,
                        'download_path': song_path,
                        'song': song,
                        'album': album,
                        'artist': artist
                    }

                else:
                    flash(f"URL missing for track {track.get('song', 'unknown')} by {track.get('artist', 'unknown')}.")

            except Exception as e:
                flash(f"An error occurred: {e}")
                continue  # Continue looping over remaining songs

            # Append the song info
            if song_info:
                song_data_list.append(song_info)
                session['song_data_list'] = song_data_list
                print(f"Appending songs:\n {song_data_list}")

        print("Sending songs_data_list to front-end")
        return render_template(template)

    return render_template(template)


# Search results page logic (results.html)
@app.route('/results', methods=["GET", "POST"])
def results():

    #  Added mobile template html path based on device's User Agent
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    if user_agent.is_mobile:
        template = "mobile/results.html"
    else:
        template = "results.html"
    # Flash to user's screen type of device for debugging
    # flash(f"User-Agent: {ua_string}, Selected template: {template}")    

    # If the user selects to download a song
    if request.method == "POST":
        
        track_url = request.form.get("track_url")
        song = request.form.get("song")
        album = request.form.get("album")
        artist = request.form.get("artist")

        # Grab download path from .env
        DWN_PATH = os.getenv("DWN_PATH")

        # Make path if not already there
        os.makedirs(DWN_PATH, exist_ok=True)

        try:
            dest_path = set_folder(DWN_PATH)
        except OSError as e:
            flash(f"Failed to create or access folder: {e}")

        song_path = create_song_folder_structure(dest_path, artist, album, song)

        if not track_url:
            # Tell user that the URL can't be found
            flash("Download URL can't be found/isn't provided", "error")
            return render_template(template)
        
        # List of data to return
        song_info = {
            'track_url': track_url,
            'download_path': song_path,
            'song': song,
            'album': album,
            'artist': artist
        }

        session['song_info'] = song_info

        return redirect(url_for('download_page'))
    
    return render_template(template)

# Download backend logic (download.html)
@app.route('/download', methods=["GET", "POST"])
def download_page():

    #  Added mobile template html path based on device's User Agent
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    if user_agent.is_mobile:
        template = "mobile/download.html"
    else:
        template = "download.html"
    # Flash to user's screen type of device for debugging
    # flash(f"User-Agent: {ua_string}, Selected template: {template}")

    # Grab song info (array of everything needed from the song to download)
    song_info = session.get('song_info', [])

    # Extract the track url from the song array
    track_url = song_info.get("track_url")

    # If track not found flash error & return
    if not track_url:
        flash("No track URL provided to download", "error")
        return render_template(template)
    
    # Else return the page and proceed to download
    return render_template(template, track_url=track_url)

# Settings backend logic (settings.html)
@app.route('/settings', methods=["GET", "POST"])
def settings_page():

    #  Added mobile template html path based on device's User Agent
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    if user_agent.is_mobile:
        template = "mobile/settings.html"
    else:
        template = "settings.html"
    # Flash to user's screen type of device for debugging
    # flash(f"User-Agent: {ua_string}, Selected template: {template}")

    # Load env variables
    load_dotenv(override=True)

    # Spotify API Client Credentials
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    DWN_PATH = os.getenv("DWN_PATH")
    print(f"ID and Secret: {CLIENT_ID}, {CLIENT_SECRET}, Download Path: {DWN_PATH}")

    # When user hits save button
    if request.method == "POST":
        # Store input as temp variables
        form_id = request.form.get("client-id")
        form_secret = request.form.get("client-secret")
        form_dwn = request.form.get("dwn_path")

        print(f"Form's ID: {form_id}")
        print(f"Form Secret: {form_secret}")
        print(f"Form Dwn Path: {form_dwn}")

        # Check if form data differs from current env values
        updated = False
        new_values = {}

        if form_id and form_id != CLIENT_ID:
            new_values["CLIENT_ID"] = form_id
            updated = True
        if form_secret and form_secret != CLIENT_SECRET:
            new_values["CLIENT_SECRET"] = form_secret
            updated = True
        if form_dwn and form_dwn != DWN_PATH:
            new_values["DWN_PATH"] = form_dwn
            updated = True

        if updated:
            # Read existing lines from .env
            env_path = ".env"
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()
            
            # Update lines with new values or add them
            for key, val in new_values.items():
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith(f"{key}="):
                        lines[i] = f'{key}="{val}"\n'
                        found = True
                        break
                if not found:
                    lines.append(f'{key}="{val}"\n')
            
            # Write back updated .env
            with open(env_path, "w") as f:
                f.writelines(lines)

            # Reload the environment variables after updating .env
            load_dotenv(override=True)

            # Optionally flash a message or redirect after saving
            flash("Saved Successfully.", "message")

        # Update current values for rendering after possible save
        CLIENT_ID = form_id
        CLIENT_SECRET = form_secret
        DWN_PATH = form_dwn

    # Render template, passing current values to pre-fill inputs
    return render_template(
        template,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        dwn_path=DWN_PATH
    )


# Browse logic
@app.route('/browse', methods=["GET", "POST"])
def browse():
    #  Added mobile template html path based on device's User Agent
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    if user_agent.is_mobile:
        template = "mobile/browse.html"
    else:
        template = "browse.html"


    # Load env variables
    load_dotenv(override=True)

    # Spotify API Client Credentials
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    print(f"ID and Secret: {CLIENT_ID}, {CLIENT_SECRET}")

    # Generate the token
    token = generate_token(CLIENT_ID, CLIENT_SECRET)
        
    if not token:
        flash("Unable to acquire token. Please check API credentials.", "error")
        return render_template(template)

    # --- Process New Releases ---
    new_releases = get_new_releases(token)
    release_data = []
    if new_releases:
        for release in new_releases:
            album_name = release.get("name")
            artists = ", ".join(artist["name"] for artist in release.get("artists", []))
            release_url = release.get("external_urls", {}).get("spotify")
            images = release.get("images", [])
            artwork_url = images[0]["url"] if images else None
            album_id = release.get("id")

            release_data.append({
                "album": album_name,
                "artist": artists,
                "url": release_url,
                "artwork": artwork_url,
                "album_id": album_id
            })
    else:
        flash("Could not fetch new releases.", "error")

    # --- Process Browse Categories ---
    browse_categories = get_browse_categories(token)
    category_data = []
    if browse_categories:
        for category in browse_categories:
            # The API returns a list of icons, we'll take the first one.
            icons = category.get("icons", [])
            icon_url = icons[0]["url"] if icons else None
            category_data.append({
                "id": category.get("id"),
                "name": category.get("name"),
                "icon": icon_url
            })
    else:
        flash("Could not fetch browse categories.", "error")

    return render_template(
        template, 
        new_releases=release_data,
        browse_categories=category_data
    )

@app.route('/about/<track_id>', methods=["GET", "POST"])
def about(track_id=None):
    #  Added mobile template html path based on device's User Agent
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    if user_agent.is_mobile:
        template = "mobile/about.html"
    else:
        template = "about.html"

    # Load env variables
    load_dotenv(override=True)

    # Spotify API Client Credentials
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")

    # Generate the token
    token = generate_token(CLIENT_ID, CLIENT_SECRET)
        
    if not token:
        flash("Unable to acquire token. Please check API credentials.", "error")
        return redirect(url_for('index'))

    # Fetch track details
    track_details = get_track_details(token, track_id)

    if not track_details:
        flash("Could not find details for this track.", "error")
        return redirect(url_for('index'))

    # Extract album and artist IDs
    album_id = track_details.get('album', {}).get('id')
    artist_ids = [artist.get('id') for artist in track_details.get('artists', [])]
    primary_artist_id = artist_ids[0] if artist_ids else None

    # Fetch album and artist details
    album_details = None
    if album_id:
        album_details = get_album_details(token, album_id)

    artist_details = None
    if primary_artist_id:
        artist_details = get_artist_details(token, primary_artist_id)

    # Combine all data to pass to the template
    about_data = {
        'track': track_details,
        'album': album_details,
        'artist': artist_details
    }

    return render_template(template, data=about_data)

@app.route('/playlist/<playlist_id>')
def playlist_page(playlist_id=None):
    # Detect device for mobile/desktop template
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    template = "mobile/playlist.html" if user_agent.is_mobile else "playlist.html"

    # Load ENV and get API token
    load_dotenv(override=True)
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    token = generate_token(CLIENT_ID, CLIENT_SECRET)
    if not token:
        flash("Unable to acquire token. Please check API credentials.", "error")
        return redirect(url_for('index'))

    # Fetch playlist details and all tracks
    playlist_details = get_playlist_details(token, playlist_id)
    raw_tracks = get_playlist_tracks(token, playlist_id)

    if not playlist_details or not raw_tracks:
        flash("Unable to retrieve playlist information.", "error")
        return render_template(template) # Render HTML to show error

    # Process track data into clean format for HTML
    track_list = []
    for item in raw_tracks:
        track = item.get('track')
        if not track:
            continue # Skip the rest

        images = track["album"].get("images", [])
        artwork_url = images[0]["url"] if images else None
        track_info = {
            "song": track["name"],
            "artist": ", ".join(artist["name"] for artist in track["artists"]),
            "album": track["album"]["name"],
            "url": track["external_urls"]["spotify"],
            "artwork": artwork_url,
            "track_id": track["id"]
        }
        track_list.append(track_info)
    
    return render_template(template, playlist=playlist_details, tracks=track_list)

@app.route('/album/<album_id>')
def album_page(album_id):
    # Detect device for mobile/desktop template
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)
    # Re-use playlist.html as requested
    template = "mobile/playlist.html" if user_agent.is_mobile else "playlist.html"

    # Standard procedure to get API token
    load_dotenv(override=True)
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    token = generate_token(CLIENT_ID, CLIENT_SECRET)
    if not token:
        flash("Unable to acquire token. Please check API credentials.", "error")
        return redirect(url_for('index'))

    # Fetch album details and all its tracks
    album_details = get_album_details(token, album_id)
    raw_tracks = get_album_tracks(token, album_id)

    if not album_details or not raw_tracks:
        flash("Could not retrieve album information.", "error")
        return redirect(url_for('browse'))

    # Create a "pseudo-playlist" object from album details to fit the playlist.html template
    pseudo_playlist_object = {
        "name": album_details.get("name"),
        "images": album_details.get("images", []),
        "description": f"Album by {', '.join(artist['name'] for artist in album_details.get('artists', []))}",
        "owner": {"display_name": album_details.get("label", "N/A")},
        "tracks": {"total": album_details.get("total_tracks", 0)}
    }

    # Process the raw track data. Album tracks are "simplified" objects.
    track_list = []
    album_artwork = album_details.get("images", [{}])[0].get("url") if album_details.get("images") else None
    for track in raw_tracks:
        if not track:
            continue
        
        track_info = {
            "song": track.get("name"),
            "artist": ", ".join(artist["name"] for artist in track.get("artists", [])),
            "album": album_details.get("name"), # Add album name from parent
            "url": track.get("external_urls", {}).get("spotify"),
            "artwork": album_artwork, # Use the same album artwork for all tracks
            "track_id": track.get("id")
        }
        track_list.append(track_info)

    return render_template(template, playlist=pseudo_playlist_object, tracks=track_list)

#=================
# Socket IO routes
# ================

# Start download (passed from js in 'download.html')
@socketio.on('start_download')
def handle_start_download(data):
    
    # Grab track url passed in
    track_url = data.get("track_url")

    # If url found then proceed to download
    if track_url:

        # Grab data passed in
        song = data.get("song")
        artist = data.get("artist")
        album = data.get("album")
        download_path = data.get("download_path")
        
        # Print artist, album, and song
        print(f"Artist: {artist}, Album: {album}, Song: {song}")

        # Start download using socketio
        socketio.start_background_task(download_spotify_url, track_url, download_path)
        
        # Emit download task started
        flash("Download task started, please wait...", "message")
    else:
        # Emit download error no URL provided
        flash("No track URL provided to start download", "error")

# Start loop download (called inside a for loop in import.html's JS)
@socketio.on('start_loop_download')
def handle_loop_download(data):

    # Grab track url passed in
    track_url = data.get("track_url")

    # Grab download path passed in
    download_path = data.get("download_path")

    # print(f"Track URL passed in and Download_path is: {track_url} && {download_path}")
    socketio.start_background_task(download_spotify_url, track_url, download_path)


# ==========
# API Routes
# ==========

# API to jsonify all songs that querys from 'import.html'
@app.route('/api/songs')
def get_songs_api():
    songs = session.get('song_data_list', [])
    return jsonify(songs)

# API to jsonify one song that querys from 'download.html' (which is the song selected from 'results.html')
@app.route('/api/song_info')
def get_song_info():
    song_info = session.get('song_info')
    if song_info is None:
        return jsonify({'error': 'No song info found'}), 404
    else:
        return jsonify(song_info)

# API to clear backend session (to prevent page reload on 'download.html/import.html'to rerun command)
@app.route('/api/clear-songs', methods=['POST'])
def clear_songs():
    print("Clearing import session...")
    session.pop('song_data_list', None)
    return '', 204


if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
