import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import threading
import time
import os
import json
import pygame
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from spotipy.exceptions import SpotifyException

class HybridPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Hybrid Spotify & Local Music Player")
        self.root.geometry("900x800")
        
        # Spotify config
        self.scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-modify-public playlist-modify-private"
        self.redirect_uri = "http://localhost:8888/callback"
        self.client_id = None
        self.client_secret = None
        self.sp = None
        self.token_cache = ".cache"
        self.current_track_id = None
        
        # Local player init
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        self.local_playlist = []  # File paths
        self.local_current_index = 0
        self.local_volume = 0.5
        pygame.mixer.music.set_volume(self.local_volume)
        self.local_is_playing = False
        
        # GUI: Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Spotify tab
        self.spotify_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.spotify_frame, text="Spotify")
        self.setup_spotify_tab()
        
        # Local tab
        self.local_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.local_frame, text="Local Files")
        self.setup_local_tab()
        
        # Status thread (Spotify)
        self.running = False
        
        # Get creds
        self.get_credentials()
    
    def setup_spotify_tab(self):
        # Search
        search_frame = ttk.Frame(self.spotify_frame)
        search_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_var, width=40).pack(side="left", padx=5)
        ttk.Button(search_frame, text="Search", command=self.search_tracks).pack(side="left")
        
        # Listbox: Multi-select tracks
        self.listbox = tk.Listbox(self.spotify_frame, height=8, selectmode=tk.MULTIPLE)
        self.listbox.pack(pady=10, padx=10, fill="both", expand=True)
        self.listbox.bind("<Double-1>", self.play_selected)
        
        # Controls
        controls_frame = ttk.Frame(self.spotify_frame)
        controls_frame.pack(pady=10)
        for text, cmd in [
            ("Play Selected", self.play_selected), ("Pause", self.pause), ("Next", self.next_track),
            ("Prev", self.previous_track), ("Stop", self.stop_playback), ("Shuffle", self.toggle_shuffle),
            ("Repeat", self.toggle_repeat), ("Create Playlist", self.create_playlist),
            ("Add to Playlist", self.add_to_playlist), ("Export Playlist", self.export_playlist)
        ]:
            ttk.Button(controls_frame, text=text, command=cmd).pack(side="left", padx=5)
        
        # Volume & Seek
        vol_seek_frame = ttk.Frame(self.spotify_frame)
        vol_seek_frame.pack(pady=5)
        ttk.Label(vol_seek_frame, text="Volume:").pack(side="left")
        self.volume_var = tk.DoubleVar(value=50)
        ttk.Scale(vol_seek_frame, from_=0, to=100, variable=self.volume_var, command=self.set_volume).pack(side="left", padx=5)
        
        ttk.Label(vol_seek_frame, text="Seek (s):").pack(side="left", padx=(20,0))
        self.seek_var = tk.StringVar()
        ttk.Entry(vol_seek_frame, textvariable=self.seek_var, width=10).pack(side="left", padx=5)
        ttk.Button(vol_seek_frame, text="Seek", command=self.seek_position).pack(side="left")
        
        # Status
        self.status_var = tk.StringVar(value="Ready - Log in to Spotify")
        ttk.Label(self.spotify_frame, textvariable=self.status_var, relief="sunken", anchor="w").pack(pady=5, padx=10, fill="x")
        
        # Visuals frame
        self.matplot_frame = ttk.Frame(self.spotify_frame)
        self.matplot_frame.pack(pady=10, fill="both", expand=True)
        self.canvas = None
    
    def setup_local_tab(self):
        # Add/Clear
        add_frame = ttk.Frame(self.local_frame)
        add_frame.pack(pady=10, padx=10, fill="x")
        ttk.Button(add_frame, text="Add Local Files", command=self.add_local_files).pack(side="left")
        ttk.Button(add_frame, text="Clear Playlist", command=self.clear_local_playlist).pack(side="left", padx=5)
        
        # Listbox: Files
        self.local_listbox = tk.Listbox(self.local_frame, height=10)
        self.local_listbox.pack(pady=10, padx=10, fill="both", expand=True)
        self.local_listbox.bind("<Double-1>", self.play_local_selected)
        
        # Controls
        local_controls = ttk.Frame(self.local_frame)
        local_controls.pack(pady=10)
        for text, cmd in [
            ("Play Selected", self.play_local_selected), ("Pause", self.local_pause),
            ("Stop", self.local_stop), ("Next", self.local_next), ("Prev", self.local_prev)
        ]:
            ttk.Button(local_controls, text=text, command=cmd).pack(side="left", padx=5)
        
        # Volume
        local_vol_frame = ttk.Frame(self.local_frame)
        local_vol_frame.pack(pady=5)
        ttk.Label(local_vol_frame, text="Local Volume:").pack(side="left")
        self.local_volume_var = tk.DoubleVar(value=50)
        ttk.Scale(local_vol_frame, from_=0, to=100, variable=self.local_volume_var, command=self.local_set_volume).pack(side="left", padx=5)
        
        # Status
        self.local_status_var = tk.StringVar(value="No files loaded")
        ttk.Label(self.local_frame, textvariable=self.local_status_var, relief="sunken", anchor="w").pack(pady=5, padx=10, fill="x")
    
    def get_credentials(self):
        # Prompt for Spotify creds if missing
        if not self.client_id or not self.client_secret:
            self.client_id = simpledialog.askstring("Client ID", "Enter Spotify Client ID:")
            self.client_secret = simpledialog.askstring("Client Secret", "Enter Spotify Client Secret:", show="*")
        if self.client_id and self.client_secret:
            self.init_spotify()
        else:
            messagebox.showerror("Error", "Credentials required!")
            self.root.quit()
    
    def init_spotify(self):
        # Init Spotipy client
        try:
            self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=self.client_id, client_secret=self.client_secret,
                redirect_uri=self.redirect_uri, scope=self.scopes, cache_path=self.token_cache
            ))
            self.status_var.set("Connected to Spotify")
            self.start_status_update()
        except SpotifyException as e:
            messagebox.showerror("Spotify Error", str(e))
            self.root.quit()
    
    def search_tracks(self):
        # Search Spotify tracks
        query = self.search_var.get()
        if not query or not self.sp:
            return
        try:
            results = self.sp.search(q=query, type="track", limit=20)
            self.listbox.delete(0, tk.END)
            self.track_data = []
            for track in results["tracks"]["items"]:
                display = f"{track['name']} - {track['artists'][0]['name']}"
                self.listbox.insert(tk.END, display)
                self.track_data.append(track)
            self.status_var.set(f"Found {len(results['tracks']['items'])} tracks")
        except Exception as e:
            messagebox.showerror("Search Error", str(e))
    
    def play_selected(self, event=None):
        # Play selected track
        selection = self.listbox.curselection()
        if not selection or not self.sp:
            return
        index = selection[0]
        track = self.track_data[index]
        uri = track["uri"]
        try:
            self.sp.start_playback(uris=[uri])
            self.status_var.set(f"Playing: {track['name']}")
            self.current_track_id = track['id']
            self.visualize_audio_features(track['id'])
        except SpotifyException as e:
            import webbrowser
            webbrowser.open(track["external_urls"]["spotify"])
            self.status_var.set(f"Opened in browser: {track['name']}")
    
    def create_playlist(self):
        # Create new playlist from selected
        selection = self.listbox.curselection()
        if not selection or not self.sp:
            return
        selected_tracks = [self.track_data[i] for i in selection]
        if not selected_tracks:
            messagebox.showwarning("Warning", "Select tracks first.")
            return
        name = simpledialog.askstring("Playlist Name", "Enter playlist name:")
        if name:
            try:
                user_id = self.sp.current_user()['id']
                playlist = self.sp.user_playlist_create(user_id, name, public=True)
                uris = [track['uri'] for track in selected_tracks]
                self.sp.playlist_add_items(playlist['id'], uris)
                messagebox.showinfo("Success", f"Created '{name}' with {len(uris)} tracks.")
                self.status_var.set(f"Playlist '{name}' created")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def add_to_playlist(self):
        # Add selected to existing playlist
        selection = self.listbox.curselection()
        if not selection or not self.sp:
            return
        selected_tracks = [self.track_data[i] for i in selection]
        if not selected_tracks:
            messagebox.showwarning("Warning", "Select tracks first.")
            return
        playlist_id = simpledialog.askstring("Playlist ID", "Enter playlist ID:")
        if playlist_id:
            try:
                uris = [track['uri'] for track in selected_tracks]
                self.sp.playlist_add_items(playlist_id, uris)
                messagebox.showinfo("Success", f"Added {len(uris)} tracks to {playlist_id}.")
                self.status_var.set(f"Added to {playlist_id}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def export_playlist(self):
        # Export playlist to JSON
        if not self.sp:
            return
        playlist_id = simpledialog.askstring("Playlist ID", "Enter playlist ID to export:")
        if playlist_id:
            try:
                results = self.sp.playlist_tracks(playlist_id)
                tracks = [{"name": item["track"]["name"], "artist": item["track"]["artists"][0]["name"], "uri": item["track"]["uri"]} 
                          for item in results["items"] if item["track"]]
                filename = f"{playlist_id}_export.json"
                with open(filename, "w") as f:
                    json.dump(tracks, f, indent=4)
                messagebox.showinfo("Success", f"Exported {len(tracks)} tracks to {filename}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def pause(self):
        # Pause Spotify
        if self.sp:
            try:
                self.sp.pause_playback()
                self.status_var.set("Paused")
            except SpotifyException as e:
                messagebox.showerror("Error", str(e))
    
    def next_track(self):
        # Next Spotify track
        if self.sp:
            try:
                self.sp.next_track()
            except SpotifyException as e:
                messagebox.showerror("Error", str(e))
    
    def previous_track(self):
        # Prev Spotify track
        if self.sp:
            try:
                self.sp.previous_track()
            except SpotifyException as e:
                messagebox.showerror("Error", str(e))
    
    def stop_playback(self):
        # Stop Spotify (pause)
        if self.sp:
            try:
                self.sp.pause_playback()
                self.status_var.set("Stopped")
            except SpotifyException as e:
                messagebox.showerror("Error", str(e))
    
    def toggle_shuffle(self):
        # Toggle Spotify shuffle
        if self.sp:
            try:
                current = self.sp.shuffle()["shuffle_state"]
                self.sp.shuffle(not current)
                self.status_var.set(f"Shuffle: {'On' if not current else 'Off'}")
            except SpotifyException as e:
                messagebox.showerror("Error", str(e))
    
    def toggle_repeat(self):
        # Toggle Spotify repeat (context/off)
        if self.sp:
            try:
                current = self.sp.repeat()["repeat_state"]
                new_state = "context" if current == "off" else "off"
                self.sp.repeat(new_state)
                self.status_var.set(f"Repeat: {new_state}")
            except SpotifyException as e:
                messagebox.showerror("Error", str(e))
    
    def set_volume(self, val):
        # Set Spotify volume
        if self.sp:
            try:
                volume = int(float(val))
                self.sp.volume(volume)
                self.status_var.set(f"Volume: {volume}%")
            except SpotifyException as e:
                messagebox.showerror("Error", str(e))
    
    def seek_position(self):
        # Seek Spotify to seconds
        if self.sp:
            try:
                pos_ms = int(self.seek_var.get()) * 1000
                self.sp.seek_track_position(pos_ms)
                self.status_var.set(f"Seeked to {self.seek_var.get()}s")
            except (ValueError, SpotifyException) as e:
                messagebox.showerror("Error", f"Invalid seek: {e}")
    
    def visualize_audio_features(self, track_id):
        # Plot Spotify audio features
        if not self.sp:
            return
        try:
            features = self.sp.audio_features(track_id)[0]
            if features:
                fig, ax = plt.subplots(figsize=(8, 4))
                feats = ['danceability', 'energy', 'speechiness', 'acousticness', 'instrumentalness', 'liveness', 'valence']
                vals = [features[f] for f in feats]
                ax.bar(feats, vals)
                ax.set_title(f"Audio Features: {track_id}")
                ax.set_ylabel("Value (0-1)")
                plt.xticks(rotation=45)
                
                # Embed canvas
                if self.canvas:
                    self.canvas.get_tk_widget().destroy()
                self.canvas = FigureCanvasTkAgg(fig, master=self.matplot_frame)
                self.canvas.draw()
                self.canvas.get_tk_widget().pack(fill="both", expand=True)
        except Exception as e:
            print(f"Vis error: {e}")
    
    def start_status_update(self):
        # Start Spotify status thread
        self.running = True
        self.status_thread = threading.Thread(target=self.update_status, daemon=True)
        self.status_thread.start()
    
    def update_status(self):
        # Update Spotify playback status
        while self.running:
            if self.sp:
                try:
                    playback = self.sp.current_playback()
                    if playback and playback["is_playing"]:
                        track = playback["item"]
                        self.status_var.set(f"Playing: {track['name']} - {track['artists'][0]['name']} | {playback['progress_ms']/1000:.0f}s")
                        if self.current_track_id != track['id']:
                            self.visualize_audio_features(track['id'])
                            self.current_track_id = track['id']
                    elif playback:
                        self.status_var.set("Paused")
                except:
                    pass
            time.sleep(5)
    
    # Local methods
    def add_local_files(self):
        # Add audio files to local playlist
        files = filedialog.askopenfilenames(filetypes=[("Audio", "*.mp3 *.wav *.ogg")])
        for file in files:
            if file not in self.local_playlist:
                self.local_playlist.append(file)
                self.local_listbox.insert(tk.END, os.path.basename(file))
        self.local_status_var.set(f"Playlist: {len(self.local_playlist)} files")
    
    def clear_local_playlist(self):
        # Clear local playlist
        self.local_playlist = []
        self.local_listbox.delete(0, tk.END)
        self.local_status_var.set("Playlist cleared")
    
    def play_local_selected(self, event=None):
        # Play selected local file
        selection = self.local_listbox.curselection()
        if selection:
            self.local_current_index = selection[0]
            self.local_play_current()
    
    def local_play_current(self):
        # Load/play current local file
        if not self.local_playlist:
            return
        file_path = self.local_playlist[self.local_current_index]
        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            self.local_is_playing = True
            self.local_status_var.set(f"Playing: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Load failed: {e}")
    
    def local_pause(self):
        # Toggle local pause
        if self.local_is_playing:
            pygame.mixer.music.pause()
            self.local_is_playing = False
            self.local_status_var.set("Paused")
        else:
            pygame.mixer.music.unpause()
            self.local_is_playing = True
            self.local_status_var.set("Resumed")
    
    def local_stop(self):
        # Stop local playback
        pygame.mixer.music.stop()
        self.local_is_playing = False
        self.local_status_var.set("Stopped")
    
    def local_next(self):
        # Next local track
        if self.local_playlist:
            self.local_current_index = (self.local_current_index + 1) % len(self.local_playlist)
            self.local_stop()
            self.local_play_current()
    
    def local_prev(self):
        # Prev local track
        if self.local_playlist:
            self.local_current_index = (self.local_current_index - 1) % len(self.local_playlist)
            self.local_stop()
            self.local_play_current()
    
    def local_set_volume(self, val):
        # Set local volume
        self.local_volume = float(val) / 100.0
        pygame.mixer.music.set_volume(self.local_volume)
        self.local_status_var.set(f"Volume: {self.local_volume:.1f}")
    
    def on_closing(self):
        # Cleanup on exit
        self.running = False
        pygame.mixer.quit()
        if os.path.exists(self.token_cache):
            os.remove(self.token_cache)
        plt.close('all')
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = HybridPlayer(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
