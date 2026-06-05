import json
import base64
import logging
import requests
import pandas as pd
import os
from logic.constants import AppConstants

logger = logging.getLogger(__name__)


class WebPublisher:
    """
    Handles the synchronization of schedule data from the local desktop application
    to a remote GitHub Pages repository for web viewing.
    """

    @staticmethod
    def publish_schedule(df: pd.DataFrame, config: dict) -> bool:
        """
        Minimizes the schedule dataframe, filtering specifically for the Custom Team,
        and pushes it as a formatted JSON payload to a configured GitHub repository.

        Args:
            df (pd.DataFrame): The raw schedule dataframe containing engineering tasks.
            config (dict): Application configuration dictionary containing GitHub credentials.

        Returns:
            bool: True if the publishing was successful, False otherwise.
        """
        gh_config = config.get("github") or {}

        # Priority 1: Environment Variable (most secure)
        # Priority 2: Local ignored app_config.json file
        token = os.environ.get("MYGANTT_GITHUB_TOKEN") or gh_config.get("token")
        repo = gh_config.get("repo")
        path = gh_config.get("data_path", "data/schedule.json")
        branch = gh_config.get("branch", "main")

        if not token or not repo:
            logger.warning("Web publishing skipped: GitHub credentials or target repository mapping missing.")
            return False

        if df.empty:
            logger.warning("Web publishing skipped: Schedule dataframe is empty.")
            return False

        try:
            # 1. Enforce Application Custom Team Filter
            # Reference the global constants to isolate only Custom Team lines
            if 'TYPE' in df.columns:
                df = df[df['TYPE'].isin(AppConstants.CUSTOM_LINE_TYPES)]

            if df.empty:
                logger.warning("Web publishing skipped: No Custom Team lines found to publish.")
                return False

            # 2. Minimize Data Footprint
            target_cols = [
                'SMART_ID', 'PROJECT_ID', 'ASSIGNED TO', 'EST START DATE', 'EST END DATE',
                'EST DAYS', 'STATUS', 'REQUIREMENT', 'QUOTE NO', 'PROJECT NAME', 'ENG DUE DATE'
            ]

            available_cols = [c for c in target_cols if c in df.columns]

            publish_df = df[available_cols].copy()
            publish_df = publish_df.fillna("")

            records = publish_df.to_dict(orient='records')
            json_payload = json.dumps(records, indent=4)

            # --- Save Local Copy for PyCharm Testing ---
            local_path = os.path.join(AppConstants.get_data_dir(), "schedule.json")
            try:
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(json_payload)
            except Exception as e:
                logger.warning(f"Could not save local schedule.json: {e}")

            # 3. Prepare GitHub REST API Details
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }

            # 4. Check for Existing File to Retrieve required SHA blob identifier
            sha = None
            try:
                response = requests.get(url, headers=headers, params={"ref": branch}, timeout=10)
                if response.status_code == 200:
                    sha = response.json().get("sha")
            except requests.exceptions.RequestException as req_e:
                logger.warning(f"Failed to fetch existing file SHA from GitHub: {req_e}")

            # 5. Encode and Transmit Payload
            content_bytes = json_payload.encode("utf-8")
            content_b64 = base64.b64encode(content_bytes).decode("utf-8")

            payload = {
                "message": "Automated Custom Team schedule sync from MyGantt",
                "content": content_b64,
                "branch": branch
            }
            if sha:
                payload["sha"] = sha

            put_response = requests.put(url, headers=headers, json=payload, timeout=10)

            if put_response.status_code in [200, 201]:
                logger.info("Successfully pushed Custom Team schedule to GitHub web interface.")
                return True
            else:
                logger.error(
                    f"GitHub API update failed with status code {put_response.status_code}: {put_response.text}")
                return False

        except Exception as e:
            logger.exception(f"Unhandled exception during web scheduling export: {e}")
            return False