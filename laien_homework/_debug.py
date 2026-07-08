
import subprocess, json

url = 'https://itunes.apple.com/us/rss/customerreviews/page=1/id=839285684/sortby=mostrecent/json'
cmd = ['curl', '-s', '-L', '--connect-timeout', '20', url]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
data = json.loads(r.stdout)
feed = data.get('feed', {})
entries = feed.get('entry', [])
print(f'ENTRIES={len(entries)}')
print(f'FIRST_KEY={list(entries[0].keys())[:5] if entries else "EMPTY"}')
print(f'HAS_RATING={"im:rating" in entries[0] if entries else "N/A"}')
reviews = [e for e in entries if 'im:rating' in e]
print(f'REVIEWS={len(reviews)}')
