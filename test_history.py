import subprocess
import re
import json
import sys

def get_gh_response_headers_and_body(endpoint):
    # gh api -i returns headers, blank line, body
    cmd = ["gh", "api", "-i", endpoint]
    try:
        output = subprocess.check_output(cmd, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error calling gh api: {e}")
        return None, None

    parts = output.split("\n\n", 1)
    if len(parts) < 2:
        return output, ""
    return parts[0], parts[1]

def parse_link_header(headers):
    # Find Link: header (case insensitive)
    for line in headers.splitlines():
        if line.lower().startswith("link:"):
            return line[5:].strip()
    return None

def get_last_page(link_header):
    if not link_header:
        return 1
    # <url>; rel="next", <url>; rel="last"
    # match references
    matches = re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', link_header)
    for url, rel in matches:
        if rel == "last":
            # Extract page param
            # usually ...?page=X...
            m = re.search(r'[?&]page=(\d+)', url)
            if m:
                return int(m.group(1))
    return 1

def main():
    path = "Casks/1/1password-cli.rb"
    repo = "Homebrew/homebrew-cask"
    endpoint = f"/repos/{repo}/commits?path={path}&per_page=1"

    print(f"Fetching first page for {path}...")
    headers, body = get_gh_response_headers_and_body(endpoint)
    if not headers:
        print("Failed to get response")
        return

    link_header = parse_link_header(headers)
    print(f"Link Header: {link_header}")

    last_page = get_last_page(link_header)
    print(f"Last Page: {last_page}")

    if last_page > 1:
        print(f"Fetching last page {last_page}...")
        endpoint_last = f"{endpoint}&page={last_page}"
        # No need for headers this time
        out = subprocess.check_output(["gh", "api", endpoint_last], text=True)
        data = json.loads(out)
    else:
        data = json.loads(body)

    if isinstance(data, list) and len(data) > 0:
        commit = data[-1] # Should be only 1 if per_page=1, but generic safety
        date = commit['commit']['committer']['date']
        print(f"Oldest Commit Date: {date}")
        print(f"Commit SHA: {commit['sha']}")
    else:
        print("No commits found.")

if __name__ == "__main__":
    main()
