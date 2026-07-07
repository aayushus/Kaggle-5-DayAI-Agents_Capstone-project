import subprocess
import sys
from pathlib import Path

def extract_frame(video_path: str, timestamp: str, output_path: str):
    """
    Extracts a frame at a specific timestamp (e.g. '00:01:30') using ffmpeg.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", timestamp,
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"✓ Extracted frame at {timestamp} -> {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to extract frame at {timestamp}: {e.stderr.decode()}", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_screenshots.py <path_to_video.mkv>", file=sys.stderr)
        sys.exit(1)
        
    video_path = sys.argv[1]
    if not Path(video_path).exists():
        print(f"Error: Video file '{video_path}' does not exist.", file=sys.stderr)
        sys.exit(1)
        
    output_dir = Path("screenshots")
    output_dir.mkdir(exist_ok=True)
    
    # Standard timestamps for the 5-minute video pitch:
    timestamps = {
        "00:00:10": "screenshots/intro_dashboard.png",
        "00:01:15": "screenshots/architecture_overview.png",
        "00:02:30": "screenshots/live_research_results.png",
        "00:03:45": "screenshots/customer_advisory_board.png",
        "00:04:30": "screenshots/competitor_war_room.png"
    }
    
    print(f"Processing '{video_path}'...")
    for ts, out in timestamps.items():
        extract_frame(video_path, ts, out)
    print("Done! Screenshots saved in 'screenshots/' folder.")

if __name__ == "__main__":
    main()
