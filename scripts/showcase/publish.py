"""Publish a completed real showcase and refresh only its README block."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "sne11ius/arasaka-kde"))
    args = parser.parse_args()
    directory = args.directory.resolve()
    provenance = json.loads((directory / "provenance.json").read_text())
    source = provenance["source"]
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("invalid recorded source commit")
    for name in ("showcase.mp4", "showcase-inline.mp4", "poster.png", "chapters.json"):
        path = directory / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != provenance["files"][name]:
            raise ValueError(f"recorded file changed: {name}")
    if (directory / "showcase-inline.mp4").stat().st_size > 9_500_000:
        raise ValueError("inline film exceeds the GitHub upload budget")

    media_token = os.environ.get("SHOWCASE_UPLOAD_TOKEN")
    if not media_token:
        raise RuntimeError("set the repository secret SHOWCASE_UPLOAD_TOKEN to enable inline video uploads")
    upload_env = dict(os.environ, GH_TOKEN=media_token)
    repo_env = dict(os.environ, GH_TOKEN=os.environ.get("GITHUB_TOKEN") or media_token)

    def gh(*arguments, upload=False, json_result=False, allow_failure=False):
        result = subprocess.run(["gh", *arguments], env=upload_env if upload else repo_env,
                                cwd=directory, capture_output=True, text=True, timeout=300)
        if result.returncode and not allow_failure:
            raise RuntimeError(result.stderr.strip())
        if allow_failure:
            return result
        return json.loads(result.stdout) if json_result else result.stdout.strip()

    tag = "showcase-" + source[:12]
    release_url = f"https://github.com/{args.repo}/releases/tag/{tag}"
    notes = (f"Automatically recorded from {source}. The MP4 contains the real PLM and Plasma session.\n\n"
             "Interactive Rain adapts BigWings' Heartfelt (CC BY-NC-SA 3.0). "
             f"[Full credits and component licenses](https://github.com/{args.repo}/blob/{source}/ATTRIBUTION.md).")
    if gh("release", "view", tag, "--repo", args.repo, allow_failure=True).returncode:
        gh("release", "create", tag, "--repo", args.repo, "--target", source,
           "--prerelease", "--latest=false", "--title", f"Recorded showcase · {source[:7]}",
           "--notes", notes)
    gh("release", "upload", tag, "--repo", args.repo, "--clobber",
       "showcase.mp4", "showcase-inline.mp4", "poster.png", "chapters.json", "provenance.json")

    marker = "<!-- arasaka-showcase-media -->"
    issues = gh("issue", "list", "--repo", args.repo, "--state", "all", "--limit", "100",
                "--search", '"Automated showcase media" in:title', "--json", "number,body",
                upload=True, json_result=True)
    matches = [issue for issue in issues if marker in issue["body"]]
    if len(matches) > 1:
        raise RuntimeError("multiple managed showcase media issues")
    if matches:
        issue = matches[0]
    else:
        url = gh("issue", "create", "--repo", args.repo, "--title", "Automated showcase media",
                 "--body", marker + "\nCI-generated showcase recordings and provenance.", upload=True)
        issue = {"number": int(url.rsplit("/", 1)[1]), "body": ""}
        gh("issue", "close", str(issue["number"]), "--repo", args.repo, upload=True)
    inline_hash = provenance["files"]["showcase-inline.mp4"]
    url_pattern = r"https://github\.com/user-attachments/assets/[0-9a-f-]+"
    existing_url = re.search(url_pattern, issue["body"])
    if inline_hash in issue["body"] and existing_url:
        video_url = existing_url[0]
    else:
        body = (marker + f"\nRecorded source: `{source}`\n\nInline SHA-256: `{inline_hash}`\n\n"
                f"[Master and provenance]({release_url})\n\n![](./showcase-inline.mp4)\n")
        gh("issue", "edit", str(issue["number"]), "--repo", args.repo, "--body", body,
           "--attach", "./showcase-inline.mp4", upload=True)
        uploaded = gh("issue", "view", str(issue["number"]), "--repo", args.repo,
                      "--json", "body", upload=True, json_result=True)
        match = re.search(url_pattern, uploaded["body"])
        if not match:
            raise RuntimeError("GitHub did not return a native video attachment URL")
        video_url = match[0]

    start, end = "<!-- showcase:start -->", "<!-- showcase:end -->"
    document = gh("api", f"repos/{args.repo}/contents/README.md?ref=main", json_result=True)
    readme = base64.b64decode(document["content"]).decode()
    if readme.count(start) != 1 or readme.count(end) != 1:
        raise ValueError("README must have exactly one managed showcase block")
    block = (f"{start}\n<!-- markdownlint-disable MD034 -->\n\n{video_url}\n\n"
             f"<!-- markdownlint-enable MD034 -->\n\n"
             f"[Watch/download the high-quality film]({release_url}) · "
             f"[Recorded source `{source[:7]}`](https://github.com/{args.repo}/commit/{source})\n\n"
             f"*A real login-to-desktop session, recorded automatically in a disposable VM.*\n{end}")
    before, remainder = readme.split(start)
    _, after = remainder.split(end)
    updated = before + block + after
    if updated != readme:
        gh("api", f"repos/{args.repo}/contents/README.md", "--method", "PUT",
           "-f", "message=docs: refresh recorded showcase [skip ci]", "-f", "branch=main",
           "-f", "sha=" + document["sha"], "-f", "content=" + base64.b64encode(updated.encode()).decode())
    print(video_url)
    print(release_url)


if __name__ == "__main__":
    main()
