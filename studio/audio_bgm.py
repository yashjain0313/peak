"""Mandatory background-music selection and FFmpeg mixing for rendered clips."""
import random
from pathlib import Path


BGM_VOLUME = 0.25
BGM_DIR = Path(__file__).resolve().parent.parent / "bgm"
BGM_MOODS = ("chill", "epic", "sad", "suspense", "upbeat")


def choose(mood: str = "chill") -> Path | None:
    """Pick one track for the reel's AI-selected mood, with fallback across every bundled mood."""
    mood = mood if mood in BGM_MOODS else "chill"
    preferred = (mood, "chill", *BGM_MOODS)
    for folder_name in preferred:
        folder = BGM_DIR / folder_name
        if folder.is_dir():
            tracks = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".mp3")
            if tracks:
                return random.choice(tracks)
    tracks = sorted(p for p in BGM_DIR.rglob("*.mp3") if p.is_file())
    return random.choice(tracks) if tracks else None


def mix_filter(duration: float, mood: str = "chill") -> tuple[list[str], str]:
    """Build a looped, ducked BGM mix for the clip audio."""
    track = choose(mood)
    if track is None:
        return [], ("[0:a:0]loudnorm=I=-14:TP=-1.5:LRA=11,"
                    "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo")

    vocal = ("[0:a:0]loudnorm=I=-14:TP=-1.5:LRA=11,"
             "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
             "volume=1.2[voc]")
    bgm = ("[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
           f"atrim=duration={duration:.3f},volume={BGM_VOLUME}[bgm]")
    filter_complex = (
        f"{vocal};{bgm};"
        "[voc]asplit=2[voc_sc][voc_mix];"
        "[bgm][voc_sc]sidechaincompress=threshold=0.08:ratio=5:attack=100:release=1000[bgm_ducked];"
        "[voc_mix][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
    )
    return ["-stream_loop", "-1", "-i", str(track)], filter_complex
