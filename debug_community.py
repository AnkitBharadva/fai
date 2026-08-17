import json
import re
import urllib.request

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def debug_channel():
    url = "https://www.youtube.com/@namaskarprasad/community"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')

    data_match = re.search(r"var\s+ytInitialData\s*=\s*({.+?});</script>", html)
    if not data_match:
        data_match = re.search(r"window\[\"ytInitialData\"\]\s*=\s*({.+?});", html)
    initial_data = json.loads(data_match.group(1)) if data_match else None
    
    key_match = re.search(r'"INNERTUBE_API_KEY":\s*"([^"]+)"', html)
    api_key = key_match.group(1) if key_match else None
    
    context_match = re.search(r'"INNERTUBE_CONTEXT":\s*({.+?})\s*,\s*"INNERTUBE', html)
    context = json.loads(context_match.group(1)) if context_match else None
    
    print(f"API Key: {api_key}")
    
    # Save initial_data for inspection
    with open("debug_initial.json", "w", encoding="utf-8") as f:
        json.dump(initial_data, f, indent=2)
    print("Saved debug_initial.json")

if __name__ == "__main__":
    debug_channel()
