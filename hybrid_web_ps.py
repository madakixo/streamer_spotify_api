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
        
        # Shared Spotify setup
        self.scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-modify-public playlist-modify-private"
        self.redirect_uri = "http://localhost:8888/callback"
        self.client_id = None
        self.client_secret = None
        self.sp = None
        self.token_cache = ".cache"
        self.current_track_id = None
        
        # Local Player setup
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        self.local_playlist = []  # List of file paths
        self.local_current_index = 0
        self.local_volume = 0.5
        pygame.mixer.music.set_volume(self.local_volume)
        self.local_stream_file = None
        self.local_is_playing = False
        
        # GUI: Notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Spotify Tab
        self.spotify_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.spotify_frame, text="Spotify")
        self.setup_spotify_tab()
        
        # Local Tab
        self.local_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.local_frame, text="Local Files")
        self.setup_local_tab()
        
        # Status update thread (Spotify only)
        self.status_thread = None
        self.running = False
        
        # Prompt for credentials
        self.get_credentials()
    
    def setup_spotify_tab(self):
        # Search Frame
        search_frame = ttk.Frame(self.spotify_frame)
        search_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side="left", padx=5)
        ttk.Button(search_frame, text="Search", command=self.search_tracks).pack(side="left")
        
        # Results Listbox (multi-select)
        self.listbox = tk.Listbox(self.spotify_frame, height=8, selectmode=tk.MULTIPLE)
        self.listbox.pack(pady=10, padx=10, fill="both", expand=True)
        self.listbox.bind("<Double-1>", self.play_selected)
        
        # Controls Frame
        controls_frame = ttk.Frame(self.spotify_frame)
        controls_frame.pack(pady=10)
        ttk.Button(controls_frame, text="Play Selected", command=self.play_selected).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Pause", command=self.pause).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Next", command=self.next_track).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Prev", command=self.previous_track).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Stop", command=self.stop_playback).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Shuffle", command=self.toggle_shuffle).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Repeat", command=self.toggle_repeat).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Create Playlist", command=self.create_playlist).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Add to Playlist", command=self.add_to_playlist).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Export Playlist", command=self.export_playlist).pack(side="left", padx=5)
        
        # Volume & Seek
        vol_seek_frame = ttk.Frame(self.spotify_frame)
        vol_seek_frame.pack(pady=5)
        ttk.Label(vol_seek_frame, text="Volume:").pack(side="left")
        self.volume_var = tk.DoubleVar(value=50)
        volume_scale = ttk.Scale(vol_seek_frame, from_=0, to=100, orient="horizontal", variable=self.volume_var, command=self.set_volume)
        volume_scale.pack(side="left", padx=5)
        
        ttk.Label(vol_seek_frame, text="Seek (s):").pack(side="left", padx=(20,0))
        self.seek_var = tk.StringVar()
        seek_entry = ttk.Entry(vol_seek_frame, textvariable=self.seek_var, width=10)
        seek_entry.pack(side="left", padx=5)
        ttk.Button(vol_seek_frame, text="Seek", command=self.seek_position).pack(side="left")
        
        # Status
        self.status_var = tk.StringVar(value="Ready - Log in to Spotify")
        status_label = ttk.Label(self.spotify_frame, textvariable=self.status_var, relief="sunken", anchor="w")
        status_label.pack(pady=5, padx=10, fill="x")
        
        # Matplotlib Frame
        self.matplot_frame = ttk.Frame(self.spotify_frame)
        self.matplot_frame.pack(pady=10, fill="both", expand=True)
        self.canvas = None
    
    def setup_local_tab(self):
        # Add Files Button
        add_frame = ttk.Frame(self.local_frame)
        add_frame.pack(pady=10, padx=10, fill="x")
        ttk.Button(add_frame, text="Add Local Files", command=self.add_local_files).pack(side="left")
        ttk.Button(add_frame, text="Clear Playlist", command=self.clear_local_playlist).pack(side="left", padx=5)
        
        # Local Listbox
        self.local_listbox = tk.Listbox(self.local_frame, height=10)
        self.local_listbox.pack(pady=10, padx=10, fill="both", expand=True)
        self.local_listbox.bind("<Double-1>", self.play_local_selected)
        
        # Local Controls
        local_controls = ttk.Frame(self.local_frame)
        local_controls.pack(pady=10)
        ttk.Button(local_controls, text="Play Selected", command=self.play_local_selected).pack(side="left", padx=5)
        ttk.Button(local_controls, text="Pause", command=self.local_pause).pack(side="left", padx=5)
        ttk.Button(local_controls, text="Stop", command=self.local_stop).pack(side="left", padx=5)
        ttk.Button(local_controls, text="Next", command=self.local_next).pack(side="left", padx=5)
        ttk.Button(local_controls, text="Prev", command=self.local_prev).pack(side="left", padx=5)
        
        # Local Volume
        local_vol_frame = ttk.Frame(self.local_frame)
        local_vol_frame.pack(pady=5)
        ttk.Label(local_vol_frame, text="Local Volume:").pack(side="left")
        self.local_volume_var = tk.DoubleVar(value=50)
        local_volume_scale = ttk.Scale(local_vol_frame, from_=0, to=100, orient="horizontal", variable=self.local_volume_var, command=self.local_set_volume)
        local_volume_scale.pack(side="left", padx=5)
        
        # Local Status
        self.local_status_var = tk.StringVar(value="No files loaded")
        local_status = ttk.Label(self.local_frame, textvariable=self.local_status_var, relief="sunken", anchor="w")
        local_status.pack(pady=5, padx=10, fill="x")
    
    def get_credentials(self):
        if not self.client_id or not self.client_secret:
            self.client_id = simpledialog.askstring("Client ID", "Enter Spotify Client ID:")
            self.client_secret = simpledialog.askstring("Client Secret", "Enter Spotify Client Secret:", show="*")
        if self.client_id and self.client_secret:
            self.init_spotify()
        else:
            messagebox.showerror("Error", "Credentials required!")
            self.root.quit()
    
    def init_spotify(self):
        try:
            self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=self.client_id, client_secret=self.client_secret, redirect_uri=self.redirect_uri, scope=self.scopes, cache_path=self.token_cache))
            self.status_var.set("Connected to Spotify")
            self.start_status_update()
        except SpotifyException as e:
            messagebox.showerror("Spotify Error", str(e))
            self.root.quit()
    
    # Spotify Methods (unchanged from previous, except export)
    def search_tracks(self):
        # ... (same as before)
        pass  # Omitted for brevity; copy from prior version
    
    def play_selected(self, event=None):
        # ... (same)
        pass
    
    def create_playlist(self):
        # ... (same)
        pass
    
    def add_to_playlist(self):
        # ... (same)
        pass
    
    def export_playlist(self):
        if not self.sp:
            return
        playlist_id = simpledialog.askstring("Playlist ID", "Enter playlist ID to export:")
        if playlist_id:
            try:
                results = self.sp.playlist_tracks(playlist_id)
                tracks = [{"name": item["track"]["name"], "artist": item["track"]["artists"][0]["name"], "uri": item["track"]["uri"]} for item in results["items"] if item["track"]]
                with open(f"{playlist_id}_export.json", "w") as f:
                    json.dump(tracks, f, indent=4)
                messagebox.showinfo("Success", f"Exported {len(tracks)} tracks to {playlist_id}_export.json")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def pause(self):
        # ... (same)
        pass
    
    # ... (other Spotify methods: next_track, etc., same as before)
    
    def visualize_audio_features(self, track_id):
        # ... (same as before)
        pass
    
    def start_status_update(self):
        # ... (same)
        pass
    
    def update_status(self):
        # ... (same)
        pass
    
    # Local Methods
    def add_local_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Audio files", "*.mp3 *.wav *.ogg")])
        for file in files:
            if file not in self.local_playlist:
                self.local_playlist.append(file)
                self.local_listbox.insert(tk.END, os.path.basename(file))
        self.local_status_var.set(f"Playlist: {len(self.local_playlist)} files")
    
    def clear_local_playlist(self):
        self.local_playlist = []
        self.local_listbox.delete(0, tk.END)
        self.local_status_var.set("Playlist cleared")
    
    def play_local_selected(self, event=None):
        selection = self.local_listbox.curselection()
        if selection:
            self.local_current_index = selection[0]
            self.local_play_current()
    
    def local_play_current(self):
        if not self.local_playlist:
            return
        file_path = self.local_playlist[self.local_current_index]
        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            self.local_is_playing = True
            self.local_status_var.set(f"Playing: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load {file_path}: {e}")
    
    def local_pause(self):
        if self.local_is_playing:
            pygame.mixer.music.pause()
            self.local_is_playing = False
            self.local_status_var.set("Paused")
        else:
            pygame.mixer.music.unpause()
            self.local_is_playing = True
            self.local_status_var.set("Resumed")
    
    def local_stop(self):
        pygame.mixer.music.stop()
        self.local_is_playing = False
        self.local_status_var.set("Stopped")
    
    def local_next(self):
        if self.local_playlist:
            self.local_current_index = (self.local_current_index + 1) % len(self.local_playlist)
            self.local_stop()
            self.local_play_current()
    
    def local_prev(self):
        if self.local_playlist:
            self.local_current_index = (self.local_current_index - 1) % len(self.local_playlist)
            self.local_stop()
            self.local_play_current()
    
    def local_set_volume(self, val):
        self.local_volume = float(val) / 100.0
        pygame.mixer.music.set_volume(self.local_volume)
        self.local_status_var.set(f"Local Volume: {self.local_volume:.1f}")
    
    # Note: For range requests in local, Pygame loads full file; extend with custom loader for partial if needed
    
    def on_closing(self):
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
