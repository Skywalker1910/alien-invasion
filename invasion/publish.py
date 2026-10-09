"""Publishing a finished run to the portfolio's public leaderboard.

The game itself never talks to a server. In the browser, the portfolio page
that embeds the game owns the public leaderboard: it reviews the gaming name
(OpenAI moderation), stores the score (DynamoDB) and answers through the
origin-pinned bridge. This module is the game's side of that conversation:

  host -> game  host_config        {publicLeaderboard, nameMax, publicationDisclosure}
  game -> host  score_submit       {run_id, name, country, publish: true}
  host -> game  score_publication  {run_id, status: saving|saved|error, message,
                                    name?, country?, score?, masked?, retryable?}

Rules:
  * publishing is only ever started by the player's explicit "Save & publish";
  * one request per click: a pending request blocks another;
  * acknowledgements for any other run are ignored (stale or unrelated);
  * "Saved publicly" is shown only after the host says "saved";
  * a retry re-sends the same run id, name and country.

Pure Python (no pygame) so the rules are easy to test.
"""
from .storage import NAME_MAX

DEFAULT_DISCLOSURE = ("Saving publicly sends your gaming name to the site for review. "
                      "Your reviewed name, country flag and score become public.")
PENDING_TIMEOUT = 45.0          # seconds without any acknowledgement
TEXT_MAX = 400                  # longest host text we display

SENDING = "sending"             # emitted, no acknowledgement yet
SAVING = "saving"               # host is reviewing / saving
SAVED = "saved"
ERROR = "error"


def _text(value, fallback=""):
    return value.strip()[:TEXT_MAX] if isinstance(value, str) and value.strip() else fallback


class HostConfig:
    """What the embedding page supports. Defaults: no public leaderboard."""

    def __init__(self):
        self.public = False
        self.name_max = NAME_MAX
        self.disclosure = ""

    def update(self, cmd):
        self.public = cmd.get("publicLeaderboard") is True
        name_max = cmd.get("nameMax")
        if isinstance(name_max, int) and not isinstance(name_max, bool) and 1 <= name_max <= NAME_MAX:
            self.name_max = name_max
        self.disclosure = _text(cmd.get("publicationDisclosure"), DEFAULT_DISCLOSURE if self.public else "")


class Publication:
    """One completed run's public submission."""

    def __init__(self, run_id, name, country, score):
        self.run_id = run_id
        self.name = name                # what the player asked for (kept for retries)
        self.country = country
        self.score = score
        self.status = None              # None until the first request
        self.message = ""
        self.public_name = None         # reviewed (possibly masked) name from the host
        self.public_country = None
        self.public_score = None
        self.masked = False
        self.retryable = False
        self.waited = 0.0

    @property
    def pending(self):
        return self.status in (SENDING, SAVING)

    @property
    def can_retry(self):
        return self.status == ERROR and self.retryable

    def request(self):
        """The score_submit event to send, or None if one is already pending
        or the score is saved. Calling this is the only way to publish."""
        if self.pending or self.status == SAVED:
            return None
        if self.status == ERROR and not self.retryable:
            return None
        self.status = SENDING
        self.message = "Sending your score to the site…"
        self.retryable = False
        self.waited = 0.0
        return {"type": "score_submit", "run_id": self.run_id, "name": self.name,
                "country": self.country, "publish": True}

    def acknowledge(self, cmd):
        """Apply a score_publication command. Returns True if it was for this
        run and changed what we show."""
        if cmd.get("run_id") != self.run_id or self.status is None:
            return False
        status = cmd.get("status")
        if status not in (SAVING, SAVED, ERROR):
            return False
        if self.status == SAVED:
            return False                # never downgrade a confirmed save
        if status == SAVING and self.status == ERROR:
            return False                # a late "saving" for a request that already failed
        self.status = status
        self.waited = 0.0
        if status == SAVED:
            self.message = _text(cmd.get("message"), "Score saved on the public leaderboard.")
            name = cmd.get("name")
            self.public_name = name if isinstance(name, str) and name else None
            country = cmd.get("country")
            self.public_country = country.lower() if isinstance(country, str) and country else None
            score = cmd.get("score")
            self.public_score = score if isinstance(score, int) and not isinstance(score, bool) else None
            self.masked = cmd.get("masked") is True
            self.retryable = False
        elif status == ERROR:
            self.message = _text(cmd.get("message"), "The score could not be saved publicly.")
            self.retryable = cmd.get("retryable") is True
        else:
            self.message = _text(cmd.get("message"), "Reviewing your gaming name and saving your score…")
        return True

    def update(self, dt):
        """No answer for too long: let the player retry. A retry is safe; the
        host answers a duplicate submission with its earlier result."""
        if self.pending:
            self.waited += dt
            if self.waited >= PENDING_TIMEOUT:
                self.status = ERROR
                self.message = "No confirmation from the site yet. Retry to check again."
                self.retryable = True
