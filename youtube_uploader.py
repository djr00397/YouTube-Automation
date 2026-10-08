import os, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


def _service():
    # scopes ইচ্ছা করেই নেই: টোকেনে যা আছে তা-ই ব্যবহার হবে (invalid_scope এরর এড়াতে)
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"])
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def check_auth():
    items = _service().channels().list(part="id", mine=True).execute().get("items", [])
    if not items:
        raise RuntimeError("this token has no YouTube channel")
    want = os.getenv("YT_CHANNEL_ID")
    if want and items[0]["id"] != want:
        print(f"WARNING: token channel {items[0]['id']} != YT_CHANNEL_ID {want}")
    print("YouTube auth OK")


def recent_titles(n=40):
    try:
        yt = _service()
        up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        r = yt.playlistItems().list(part="snippet", playlistId=up, maxResults=min(50, n)).execute()
        titles = [i["snippet"]["title"] for i in r.get("items", [])]
        print(f"recent uploads checked: {len(titles)}")
        return titles
    except Exception as e:
        print("recent titles skipped:", repr(e)[:150])
        return []


def _status(level):
    st = {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    if level <= 2:
        st.update({"embeddable": True, "publicStatsViewable": True, "license": "youtube"})
    if level <= 1:
        st["containsSyntheticMedia"] = True
    if level == 0:
        st["paidProductPlacementDetails"] = {"hasPaidProductPlacement": False}
    return st


def _insert(yt, video, meta, level):
    body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"], "categoryId": meta["categoryId"],
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"}, "status": _status(level)}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=16 * 1024 * 1024, resumable=True, mimetype="video/mp4"))
    resp, retries = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st:
                print(f"upload {int(st.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 8:
                retries += 1
                time.sleep(5 * retries)
            else:
                raise
        except (ConnectionError, TimeoutError, OSError):
            if retries >= 8:
                raise
            retries += 1
            time.sleep(5 * retries)
    return resp["id"]


def upload(video, thumb, meta, srt=None):
    yt = _service()
    vid, last = None, None
    for level in (0, 1, 2, 3):
        try:
            vid = _insert(yt, video, meta, level)
            break
        except HttpError as e:
            last = e
            if e.resp.status != 400:
                raise
            print(f"upload rejected at level {level}, retrying with fewer optional fields:", str(e)[:200])
    if not vid:
        raise last
    if thumb:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as e:
            print("thumbnail failed:", e)
    if srt:
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "en", "name": "English", "isDraft": False}},
                                 media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
        except Exception as e:
            print("captions skipped:", e)
    try:
        st = yt.videos().list(part="status", id=vid).execute()["items"][0]["status"]
        print("UPLOADED: https://youtu.be/" + vid, "| privacy:", st.get("privacyStatus"), "| processing:", st.get("uploadStatus"))
    except Exception:
        print("UPLOADED: https://youtu.be/" + vid)
    return vid
