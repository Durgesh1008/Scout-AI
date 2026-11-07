import requests
from typing import Dict, Any
from app.plugins.base import BasePlugin


class GitHubTrackerPlugin(BasePlugin):
    name = "github_tracker"
    description = "Tracks public commit and event activity for any GitHub user via public API."

    def run(self, username: str = "", **kwargs) -> Dict[str, Any]:
        if not username:
            return {"success": False, "message": "Provide a GitHub username (e.g. run(username='Durgesh1008'))."}

        try:
            url = f"https://api.github.com/users/{username}/events"
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "ScoutAI-Plugin"}
            response = requests.get(url, headers=headers, timeout=12)
            response.raise_for_status()
            events = response.json()

            push_events = [e for e in events if e.get("type") == "PushEvent"]
            return {
                "success": True,
                "username": username,
                "total_recent_events": len(events),
                "recent_pushes": len(push_events),
                "latest_event_type": events[0].get("type") if events else None,
                "latest_event_repo": events[0].get("repo", {}).get("name") if events else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


plugin_instance = GitHubTrackerPlugin()


def run(**kwargs):
    return plugin_instance.run(**kwargs)
