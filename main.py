import multiprocessing as mp
import os
import queue
import sys

import eyed3
import spotipy
from moviepy.video.io.VideoFileClip import VideoFileClip
from pytube import YouTube
from spotipy.oauth2 import SpotifyClientCredentials
from youtube_search import YoutubeSearch

import api_keys

TIMEOUT = 15
SAVE_FOLDER = "download"
DEBUG = False
LOCK = mp.Lock()


def main():
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=api_keys.CLIENT_ID,
            client_secret=api_keys.CLIENT_SECRET,
        )
    )

    print("SPOTIFY DOWNLOADER v0.2\n")
    print("Type 'exit' to exit.\n")
    while True:
        playlist_url = input("spotify_playlist_link> ")
        print()

        if playlist_url.lower().strip() == "exit":
            break

        downloader(sp, playlist_url)


def downloader(sp, playlist_id):
    try:
        tracks = get_playlist_tracks(sp, playlist_id)
    except spotipy.SpotifyException:
        print("Invalid playlist link.\n")
        return

    track_queue = mp.Queue()
    yt_link_queue = mp.Queue()
    mp4_file_queue = mp.Queue()
    mp3_file_queue = mp.Queue()

    pr_queue_tracks = mp.Process(target=queue_tracks, args=(tracks, track_queue))
    pr_queue_tracks.start()

    pr_queue_video_links = mp.Process(
        target=get_video_links, args=(track_queue, yt_link_queue, len(tracks))
    )
    pr_queue_video_links.start()

    pr_queue_mp4_files = mp.Process(
        target=download_mp4_files,
        args=(yt_link_queue, mp4_file_queue, len(tracks)),
    )
    pr_queue_mp4_files.start()

    pr_queue_mp3_files = mp.Process(
        target=convert_mp4_files_to_mp3,
        args=(mp4_file_queue, mp3_file_queue, len(tracks)),
    )
    pr_queue_mp3_files.start()

    pr_tag_mp3s = mp.Process(target=tag_mp3_files, args=(mp3_file_queue, len(tracks)))
    pr_tag_mp3s.start()

    pr_queue_tracks.join()
    pr_queue_video_links.join()
    pr_queue_mp4_files.join()
    pr_queue_mp3_files.join()
    pr_tag_mp3s.join()

    print("\nDownload completed.\n")


def mp_print(*args, sep=" ", end="\n", file=sys.stdout, flush=False, debug_only=True):
    if debug_only and not DEBUG:
        return
    LOCK.acquire()
    print(*args, sep=sep, end=end, file=file, flush=flush)
    LOCK.release()


def get_playlist_tracks(sp, playlist_id):
    results = sp.playlist_tracks(playlist_id)

    tracks = results["items"]
    while results["next"]:
        results = sp.next(results)
        tracks.extend(results["items"])
    tracks = [format_track(track) for track in tracks]

    return tracks


def format_track(track):
    track = track["track"]
    formatted_track = {}
    formatted_track["title"] = track["name"]
    formatted_track["artists"] = [artist["name"] for artist in track["artists"]]
    formatted_track["album"] = track["album"]["name"]
    formatted_track["album_artists"] = [
        artist["name"] for artist in track["album"]["artists"]
    ]
    formatted_track["year"] = track["album"]["release_date"][:4]
    formatted_track["track_number"] = track["track_number"]
    formatted_track["total_tracks"] = track["album"]["total_tracks"]

    return formatted_track


def queue_tracks(tracks, output_queue):
    mp_print(f"Found {len(tracks)} tracks in playlist.\n", debug_only=False)
    for track in tracks:
        output_queue.put(track)
    output_queue.close()


def get_video_links(track_queue, output_queue, total_tracks):
    tracks_found = 0
    while track_queue.empty():
        pass
    while True:
        try:
            track = track_queue.get(timeout=TIMEOUT)

            query = f"{', '.join(track['artists'])} - {track['title']} Lyrics"
            mp_print("INFO:", f"Searching for '{query}'")

            video = YoutubeSearch(query, max_results=1).videos[0]
            tracks_found += 1
            mp_print(
                "INFO:",
                f"Found '{video['title']}' at https://www.youtube.com/watch?v={video['id']}",
                f"[{tracks_found}/{total_tracks}]",
            )
            output_queue.put((track, video))

            if tracks_found == total_tracks:
                break
        except queue.Empty:
            break

    mp_print("COMPLETED:", f"Found {tracks_found} tracks on YouTube")
    output_queue.close()


def download_mp4_files(yt_link_queue, output_queue, total_tracks):
    tracks_downloaded = 0
    while yt_link_queue.empty():
        pass
    while True:
        try:
            track, video_info = yt_link_queue.get(timeout=TIMEOUT)

            while True:
                tries = 0
                try:
                    yt = YouTube(f"http://youtube.com/watch?v={video_info['id']}")
                    video = yt.streams.filter(subtype="mp4")[0]

                    mp_print("INFO:", f"Downloading '{video_info['title']}'")
                    filepath = video.download(os.path.abspath("temp"))
                    tracks_downloaded += 1
                    mp_print(
                        "INFO:",
                        f"Finished downloading '{video_info['title']}'",
                        f"[{tracks_downloaded}/{total_tracks}]",
                    )
                    output_queue.put((track, filepath))
                    break
                except KeyError as err:
                    tries += 1
                    if tries >= 3:
                        mp_print(
                            "ERROR:",
                            f"An error occured during download of '{video_info['title']}':",
                            err,
                        )
                        break
            if tracks_downloaded == total_tracks:
                break

        except queue.Empty:
            break

    mp_print("COMPLETED:", f"Downloaded {tracks_downloaded} tracks from YouTube")
    output_queue.close()


def convert_mp4_files_to_mp3(mp4_file_queue, output_queue, total_tracks):
    tracks_converted = 0
    prevdir = os.getcwd()
    while mp4_file_queue.empty():
        pass

    while True:
        try:
            track, filepath = mp4_file_queue.get(timeout=TIMEOUT)

            try:
                os.mkdir(SAVE_FOLDER)
            except FileExistsError:
                pass

            os.chdir(SAVE_FOLDER)

            try:
                with VideoFileClip(filepath) as video:
                    mp_print("INFO:", f"Converting {filepath} to mp3")
                    savepath = os.path.basename(filepath[:-1]) + "3"
                    video.audio.write_audiofile(savepath, verbose=False, logger=None)
                    tracks_converted += 1
                    mp_print(
                        "INFO:",
                        f"Saved {savepath}",
                        f"[{tracks_converted}/{total_tracks}]",
                    )
                    output_queue.put((track, savepath))
            finally:
                os.chdir(prevdir)

            os.remove(filepath)

            if tracks_converted == total_tracks:
                break

        except queue.Empty:
            break
        finally:
            os.chdir(prevdir)

    mp_print("COMPLETED:", f"Converted {tracks_converted} tracks to mp3")
    output_queue.close()


def tag_mp3_files(mp3_file_queue, total_tracks):
    tracks_tagged = 0
    prevdir = os.getcwd()
    while mp3_file_queue.empty():
        pass
    while True:
        try:
            try:
                os.mkdir(SAVE_FOLDER)
            except FileExistsError:
                pass

            os.chdir(SAVE_FOLDER)

            try:
                track, path = mp3_file_queue.get(timeout=TIMEOUT)

                audiofile = eyed3.load(path)
                audiofile.tag.title = track["title"]
                audiofile.tag.artist = "; ".join(track["artists"])
                audiofile.tag.album = track["album"]
                audiofile.tag.album_artist = "; ".join(track["album_artists"])
                audiofile.tag.track_num = (track["track_number"], track["total_tracks"])
                audiofile.tag.save()

                tracks_tagged += 1
                mp_print(
                    "INFO:",
                    f"Tagged file {path}",
                    f"[{tracks_tagged}/{total_tracks}]",
                )
                mp_print(
                    f"Progress: {tracks_tagged}/{total_tracks} tracks. [{track['title']}]",
                    debug_only=False,
                )

                if tracks_tagged == total_tracks:
                    break
            finally:
                os.chdir(prevdir)

        except queue.Empty:
            break
        finally:
            os.chdir(prevdir)

    mp_print("COMPLETED:", f"Tagged {tracks_tagged} mp3 files")


if __name__ == "__main__":
    mp.freeze_support()
    main()
