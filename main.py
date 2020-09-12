import os
import traceback

import eyed3
import spotipy
from moviepy.video.io.VideoFileClip import VideoFileClip
from pytube import YouTube as YTDownloader
from spotipy.oauth2 import SpotifyClientCredentials
from youtube_search import YoutubeSearch


SP_CLIENT_ID = "bb7d22c03cab46f09130bacc526d29db"
SP_CLIENT_SECRET = "d99686f18e8743a38e29783523252f90"

SPOTIFY = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=SP_CLIENT_ID,
        client_secret=SP_CLIENT_SECRET,
    )
)


def get_playlist_tracks(playlist_id):
    results = SPOTIFY.playlist_tracks(playlist_id)
    tracks = results["items"]
    while results["next"]:
        results = SPOTIFY.next(results)
        tracks.extend(results["items"])
    tracks = [track["track"] for track in tracks]
    return tracks


def get_track_info(track):
    name = track["name"]
    artists = [artist["name"] for artist in track["artists"]]
    album = track["album"]["name"]
    return name, artists, album


def get_first_youtube_video(name, artists, album):
    query = f"{', '.join(artists)} - {name} Lyrics"
    tries = 0
    while True:
        try:
            print(f"Searching for '{query}'")
            video_id = YoutubeSearch(query, max_results=1).videos[0]["id"]
            return video_id, name, artists, album
        except Exception:
            tries += 1
            if tries >= 3:
                print(f"Could not download {query}:")
                traceback.print_exc()
                print("Skipping track\n")


def download_video(video_id, name, artists, album):
    tries = 0
    while True:
        try:
            print("Downloading first result")
            yt = YTDownloader(f"http://youtube.com/watch?v={video_id}")
            video = yt.streams.filter(subtype="mp4")[0]
            filepath = video.download(os.path.abspath("temp"))
            convert_to_mp3(filepath, name, artists, album)
            return
        except Exception:
            tries += 1
            if tries >= 3:
                print("An error occured:")
                traceback.print_exc()
                print("Skipping track\n")


def convert_to_mp3(filepath, name, artists, album, save_folder=os.path.abspath("download")):
    prevdir = os.getcwd()
    try:
        os.mkdir(save_folder)
    except FileExistsError:
        pass
    os.chdir(save_folder)
    try:
        with VideoFileClip(filepath) as video:
            savepath = os.path.basename(filepath[:-1]) + "3"
            video.audio.write_audiofile(savepath)
            tag_mp3(savepath, name, artists, album)
        os.remove(filepath)
    finally:
        os.chdir(prevdir)


def tag_mp3(path, name, artists, album):
    audiofile = eyed3.load(path)
    audiofile.tag.title = name
    audiofile.tag.artist = "; ".join(artists)
    audiofile.tag.album = album
    audiofile.tag.save()


def main():
    print("SPOTIFY DOWNLOADER v0.1\n")
    print("Type 'exit' to exit. Use Ctrl+C to stop download.\n")
    while True:
        try:
            playlist_url = input("spotify_playlist_link> ")
            print()

            if playlist_url.lower().strip() == "exit":
                break

            tracks = get_playlist_tracks(playlist_url)

            print(f"Found {len(tracks)} track(s).\n")

            skipped_files = []

            for number, track in enumerate(tracks):
                try:
                    print(f"Track {number + 1}/{len(tracks)}")
                    name, artists, album = get_track_info(track)
                    download_video(
                        *get_first_youtube_video(name, artists, album)
                    )
                    print()
                except Exception:
                    print("\nAn error occured during download of this file: ")
                    traceback.print_exc()
                    print("\nSkipping file.\n")
                    skipped_files.append(track["name"])

            print(f"Skipped {len(skipped_files)} file(s):")
            print(skipped_files)
            print()

        except Exception:
            print("\nAn error occured: ")
            traceback.print_exc()
            close_program = input("\nClose program? (y/n): ")[0].lower()
            if close_program == "y":
                break
            print()


main()
