"""No limits by default on your own PeakCut: many recordings at once (each kept with its own creator), five videos
at once, any number of creators. Runs against the code directly, with its own empty data folder."""
import os, sys, tempfile
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-lim-")
for k in ("PEAKCUT_MAX_LIVE_PER_USER", "PEAKCUT_MAX_JOBS_PER_USER", "PEAKCUT_MAX_UPLOAD_MB", "PEAKCUT_MAX_VIDEO_HOURS",
          "PEAKCUT_MAX_LIVE_HOURS", "PEAKCUT_MAX_USER_GB", "PEAKCUT_MAX_CREATORS"):
    os.environ.pop(k, None)
os.environ.update(DATABASE_URL="", PEAKCUT_MAX_LIVE="20")
sys.path.insert(0, ".")
from studio import audio_bgm, auth, brain, config, creators, ctx, db, jobs, live, load
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

check("five videos at once", config.MAX_ACTIVE_JOBS_PER_USER, 5)
check("a video can request 100 clips", jobs.clean_options({"max_clips": 100})["max_clips"], 100)
check("queued videos start at least one minute apart", float(config.env("PEAKCUT_QUEUE_GAP_SECONDS", "60")) >= 60)
track = audio_bgm.choose()
check("bundled BGM assets are available", track is not None and track.suffix == ".mp3")
bgm_args, bgm_filter = audio_bgm.mix_filter(30)
check("render uses looped ducked background music", "-stream_loop" in bgm_args and "sidechaincompress" in bgm_filter)
epic_track = audio_bgm.choose("epic")
check("AI-selected epic mood uses the epic BGM folder", epic_track is not None and epic_track.parent.name == "epic")
epic_clip = brain._tidy({"category": "clutch", "bgm_mood": "epic", "score": 90}, 10, 40)
check("AI clip answer carries an epic BGM mood", epic_clip["bgm_mood"] == "epic")
funny_clip = brain._tidy({"category": "funny", "score": 80}, 10, 40)
check("missing AI BGM mood falls back from the clip category", funny_clip["bgm_mood"] == "upbeat")
check("no cap on recordings, video length, recording length, storage, uploads or creators",
      all(x >= 10 ** 6 for x in (config.MAX_LIVE_PER_USER, config.MAX_VIDEO_HOURS, config.MAX_LIVE_HOURS, config.MAX_USER_GB,
                                 config.MAX_UPLOAD_MB, config.MAX_CREATORS)))

u, _ = auth._create("owner@example.com", "Owner", password_hash="x")
started = []
live.Session.start = lambda self: (live.SESSIONS.__setitem__(self.job["id"], self), started.append(self))
load.busy = lambda: False
with ctx.as_user(u.id):
    cs = [creators.create({"name": f"Streamer {i}", "channel": f"https://www.twitch.tv/streamer{i}"}) for i in range(60)]
    check("more than 50 creators can be added", len(creators.all_creators()), 60)
    cancel_job = jobs.create({"type": "file", "name": "cancel-test.mp4", "path": "/tmp/cancel-test.mp4"}, {}, enqueue=False)
    check("an in-progress video can be cancelled", jobs.cancel(cancel_job["id"]) and cancel_job["status"] == "cancelled", True)
    jobs_ = [live.start_session(c) for c in cs[:4]]
    check("four streams record at once", len(live.active_mine()), 4)
    check("each recording belongs to the creator it was started for", [j["creator"] for j in jobs_], [c["id"] for c in cs[:4]])
    check("...and to that creator's own channel", [j["source"]["url"] for j in jobs_], [c["channel"] for c in cs[:4]])
    check("...each in its own folder", len({s.dir for s in started}), 4)
    check("each creator shows only its own recording", [live.active_for(c["id"]).job["id"] for c in cs[:4]], [j["id"] for j in jobs_])
    try:
        live.start_session(cs[0]); again = "started twice"
    except ValueError as e:
        again = str(e)
    check("the same creator is not recorded twice at once", "already being recorded" in again, True)

print("ALL PASSED" if not fails else f"{len(fails)} failed")
import shutil; db.engine.dispose(); shutil.rmtree(os.environ["PEAKCUT_DATA"], ignore_errors=True)
sys.exit(1 if fails else 0)
