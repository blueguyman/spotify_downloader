import multiprocessing as mp
import os
import queue
import time

import eyed3
import progressbar
import spotipy
from moviepy.video.io.VideoFileClip import VideoFileClip
from pytube import YouTube
from spotipy.oauth2 import SpotifyClientCredentials
from youtube_search import YoutubeSearch

import api_keys

SAVE_FOLDER = "_download"
TEMP_FOLDER = "_download"
TIMEOUT = 30


def format_track(track):
    track = track["track"]
    formatted_track = {}
    formatted_track["title"] = track["name"]
    formatted_track["artists"] = [artist["name"] for artist in track["artists"]]
    formatted_track["album"] = track["album"]["name"]
    formatted_track["album_artists"] = [
        artist["name"] for artist in track["album"]["artists"]
    ]
    formatted_track["track_number"] = track["track_number"]
    formatted_track["total_tracks"] = track["album"]["total_tracks"]

    return formatted_track


def get_playlist_tracks(sp, playlist_id):
    results = sp.playlist_tracks(playlist_id)

    tracks = results["items"]
    while results["next"]:
        results = sp.next(results)
        tracks.extend(results["items"])
    tracks = [format_track(track) for track in tracks]

    return tracks


def get_yt_link(progress_queue, track):
    query = f"{', '.join(track['artists'])} - {track['title']} Lyrics"
    video = YoutubeSearch(query, max_results=1).videos[0]
    progress_queue.put("")
    return track, video


def download_mp4(progress_queue, track, video_info):
    while True:
        tries = 0
        try:
            yt = YouTube(f"http://youtube.com/watch?v={video_info['id']}")
            video = yt.streams.filter(subtype="mp4")[0]

            filepath = video.download(os.path.abspath(TEMP_FOLDER))
            progress_queue.put("")
            return track, filepath
        except KeyError:
            tries += 1
            if tries >= 3:
                break


def convert_to_mp3(progress_queue, track, filepath):
    try:
        os.mkdir(SAVE_FOLDER)
    except FileExistsError:
        pass

    prevdir = os.getcwd()
    os.chdir(SAVE_FOLDER)

    try:
        with VideoFileClip(filepath) as video:
            savepath = os.path.basename(filepath[:-1]) + "3"
            video.audio.write_audiofile(savepath, verbose=False, logger=None)
    finally:
        os.chdir(prevdir)

    os.remove(filepath)
    progress_queue.put("")
    return track, savepath


def tag_mp3(progress_queue, track, path):
    prevdir = os.getcwd()
    os.chdir(SAVE_FOLDER)

    try:
        audiofile = eyed3.load(path)
        audiofile.tag.title = track["title"]
        audiofile.tag.artist = "; ".join(track["artists"])
        audiofile.tag.album = track["album"]
        audiofile.tag.album_artist = "; ".join(track["album_artists"])
        audiofile.tag.track_num = (track["track_number"], track["total_tracks"])
        audiofile.tag.save()
    finally:
        os.chdir(prevdir)
    progress_queue.put("")


def show_progress(progress_queue, tracks):
    total_progress = len(tracks) * 4
    progress = 0
    last_get = time.time()

    widgets = [
        "[Progress: ",
        progressbar.Percentage(),
        "] ",
        progressbar.Bar("█"),
        " [",
        progressbar.Timer(),
        "] [",
        progressbar.ETA(),
        "]",
    ]

    bar = progressbar.ProgressBar(max_value=total_progress, widgets=widgets).start()

    while True:
        try:
            message = progress_queue.get(block=False)
            last_get = time.time()
            progress += 1
        except queue.Empty:
            # This may or may not work. I haven't encountered an issue like this yet.
            if time.time() - last_get > TIMEOUT:
                break

        bar.update(progress)

        if progress == total_progress:
            break

    bar.finish()


def add_queue_to_args(queue, iterable, nested=True):
    if nested:
        return [(queue, *item) for item in iterable]
    return [(queue, item) for item in iterable]


def main():
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=api_keys.CLIENT_ID,
            client_secret=api_keys.CLIENT_SECRET,
        )
    )

    print("Spotify Downloader v1.0\n")
    print("Commands:")
    print("exit -> Close program")
    print()

    while True:
        playlist = input("playlist_link> ")
        print()

        if playlist.lower() == "exit":
            break

        try:
            tracks = get_playlist_tracks(sp, playlist)
        except spotipy.SpotifyException:
            print()
            continue

        print(f"{len(tracks)} track(s) found in playlist.")

        manager = mp.Manager()
        progress_queue = manager.Queue()

        pr_progressbar = mp.Process(target=show_progress, args=(progress_queue, tracks))
        pr_progressbar.start()

        with mp.Pool(os.cpu_count() // 2) as pool:

            videos = pool.starmap(
                get_yt_link, add_queue_to_args(progress_queue, tracks, nested=False)
            )
            mp4_files = pool.starmap(
                download_mp4, add_queue_to_args(progress_queue, videos)
            )
            mp3_files = pool.starmap(
                convert_to_mp3, add_queue_to_args(progress_queue, mp4_files)
            )
            pool.starmap(tag_mp3, add_queue_to_args(progress_queue, mp3_files))

        print(f"Your tracks were downloaded to the {SAVE_FOLDER} folder.\n")


if __name__ == "__main__":
    mp.freeze_support()
    main()
