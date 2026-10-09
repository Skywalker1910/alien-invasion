"""In-game public score flow: host_config -> score_submit -> score_publication."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from invasion.menu import BOARD, ENTRY, PUBLISH  # noqa: E402
from invasion.publish import (ERROR, PENDING_TIMEOUT, SAVED, SAVING, SENDING,  # noqa: E402
                              HostConfig, Publication)
from tests.test_app import RecordingBridge, make_app, press  # noqa: E402
from tests.test_story_and_leaderboard import end_run, type_text  # noqa: E402

DISCLOSURE = ("Saving publicly sends your gaming name to OpenAI for review. Your reviewed name, "
              "country flag, and score appear on the public leaderboard for up to 180 days.")
HOST_CONFIG = {"type": "host_config", "publicLeaderboard": True, "nameMax": 20,
               "publicationDisclosure": DISCLOSURE}


def public_app(score=1200, config=HOST_CONFIG):
    app = make_app()
    app.bridge = bridge = RecordingBridge([dict(config)] if config else [])
    press(app, pygame.K_RETURN)                    # Play (also delivers host_config)
    end_run(app, score)
    assert app.menu.screen == ENTRY
    return app, bridge


def fill_form(app, name="NovaPilot", query="ind"):
    form = app.menu.form
    form.name = ""
    form.field = "name"
    type_text(app, name)
    press(app, pygame.K_TAB)
    type_text(app, query)
    press(app, pygame.K_RETURN)                    # pick the first match, focus -> buttons
    return form


def submits(bridge):
    return [e for e in bridge.sent if e["type"] == "score_submit"]


def ack(app, **fields):
    app.bridge.commands.append({"target": "alien-invasion", "type": "score_publication", **fields})
    app.frame(1 / 60)


# ----------------------------------------------------------------------
# Choosing to publish
# ----------------------------------------------------------------------
def test_public_host_offers_save_and_publish_with_disclosure():
    app, _ = public_app()
    form = app.menu.form
    assert form.public and form.disclosure == DISCLOSURE
    assert [label for label, _ in form.buttons()] == ["Save & publish", "Save locally", "Skip"]


def test_without_a_compatible_host_only_local_saving_is_offered():
    app, bridge = public_app(config=None)
    form = app.menu.form
    assert not form.public
    assert [a for _, a in form.buttons()] == ["save", "skip"]
    fill_form(app)
    app.act("publish")                             # not offered: ignored
    assert submits(bridge) == [] and app.menu.screen == ENTRY
    press(app, pygame.K_RETURN)                    # "Save locally"
    assert app.menu.screen == BOARD and app.store.top(1)[0]["name"] == "NovaPilot"


def test_save_locally_is_never_public_consent():
    app, bridge = public_app()
    fill_form(app)
    press(app, pygame.K_RIGHT)                     # "Save locally"
    press(app, pygame.K_RETURN)
    assert submits(bridge) == []
    saved = [e for e in bridge.sent if e["type"] == "score_saved"]
    assert saved and saved[0]["publish"] is False
    assert app.menu.screen == BOARD and app.publication is None
    # The host's "device only" answer for that run is ignored, not shown.
    ack(app, run_id=app.game.run_id, status="error", message="Saved on this device only.", retryable=False)
    assert app.menu.screen == BOARD


def test_save_and_publish_emits_one_submit_for_the_finished_run():
    app, bridge = public_app()
    fill_form(app)
    press(app, pygame.K_RETURN)                    # "Save & publish"
    assert app.menu.screen == PUBLISH
    events = submits(bridge)
    assert events == [{"type": "score_submit", "run_id": app.game.run_id, "name": "NovaPilot",
                       "country": "in", "publish": True}]
    assert app.store.top(1)[0]["name"] == "NovaPilot"          # also saved locally
    # Repeated clicks / retries while pending send nothing more.
    app.act("publish")
    app.act("retry")
    assert len(submits(bridge)) == 1


def test_publishing_needs_a_name_and_a_country():
    app, bridge = public_app()
    form = app.menu.form
    form.name, form.country = "", "in"
    app.act("publish")
    assert form.error and form.field == "name"
    form.name, form.country = "Nova", ""
    app.act("publish")
    assert "country" in form.error.lower() and form.field == "country"
    assert submits(bridge) == []


def test_gaming_names_are_limited_to_20_plain_characters():
    app, _ = public_app()
    form = app.menu.form
    form.name = ""
    form.field = "name"
    type_text(app, "Nova<Pilot>!!")
    assert form.name == "NovaPilot"                # only letters, digits, space _ . -
    type_text(app, "X" * 30)
    assert len(form.name) == 20
    app.bridge.commands.append({**HOST_CONFIG, "nameMax": 12})
    app.frame(1 / 60)
    assert form.name_max == 12 and len(form.name) == 12


def test_host_config_can_arrive_while_the_form_is_open():
    app, _ = public_app(config=None)
    assert not app.menu.form.public
    app.bridge.commands.append(dict(HOST_CONFIG))
    app.frame(1 / 60)
    assert app.menu.form.public and app.menu.form.buttons()[0][1] == "publish"
    app.bridge.commands.append({**HOST_CONFIG, "publicLeaderboard": False})
    app.frame(1 / 60)
    assert not app.menu.form.public


def test_zero_scores_can_be_published():
    app, bridge = public_app(score=0)
    fill_form(app)
    press(app, pygame.K_RETURN)
    assert submits(bridge)[0]["run_id"] == app.game.run_id


# ----------------------------------------------------------------------
# Acknowledgements
# ----------------------------------------------------------------------
def published_app():
    app, bridge = public_app()
    fill_form(app)
    press(app, pygame.K_RETURN)
    return app, bridge, app.publication


def test_saving_then_saved_shows_the_reviewed_name_and_flag():
    app, _, pub = published_app()
    assert pub.status == SENDING
    ack(app, run_id=pub.run_id, status="saving", message="Reviewing your gaming name…")
    assert pub.status == SAVING
    ack(app, run_id=pub.run_id, status="saved", message="Score saved as NovaPilot.",
        name="NovaPilot", country="in", score=1200, masked=False, retryable=False)
    assert pub.status == SAVED and pub.public_name == "NovaPilot" and pub.public_country == "in"
    assert ("Retry", "retry") not in app.menu.items()


def test_masked_names_keep_their_stars():
    app, _, pub = published_app()
    ack(app, run_id=pub.run_id, status="saved", message="Score saved. Your public gaming name is *********.",
        name="*********", country="in", score=1200, masked=True)
    assert pub.public_name == "*********" and pub.masked


def test_saved_acknowledgement_without_name_fields():
    app, _, pub = published_app()
    ack(app, run_id=pub.run_id, status="saved", message="This round is already saved on the public leaderboard.")
    assert pub.status == SAVED and pub.public_name is None
    assert "already saved" in pub.message


def test_retryable_error_offers_retry_with_the_same_inputs():
    app, bridge, pub = published_app()
    ack(app, run_id=pub.run_id, status="error", message="Name review is unavailable.", retryable=True)
    assert pub.status == ERROR and ("Retry", "retry") in app.menu.items()
    app.menu.index = 0
    press(app, pygame.K_RETURN)                    # Retry
    events = submits(bridge)
    assert len(events) == 2 and events[0] == events[1]
    assert pub.status == SENDING
    ack(app, run_id=pub.run_id, status="saved", message="Score saved as NovaPilot.", name="NovaPilot",
        country="in", score=1200, masked=False)
    assert pub.status == SAVED


def test_non_retryable_error_offers_no_retry_but_edit_keeps_inputs():
    app, bridge, pub = published_app()
    ack(app, run_id=pub.run_id, status="error", message="Use letters, numbers, spaces…", retryable=False)
    actions = [a for _, a in app.menu.items()]
    assert "retry" not in actions and "edit" in actions
    app.act("retry")
    assert len(submits(bridge)) == 1               # nothing re-sent
    app.act("edit")
    assert app.menu.screen == ENTRY and app.menu.form.name == "NovaPilot" and app.menu.form.country == "in"


def test_stale_and_unrelated_acknowledgements_are_ignored():
    app, _, pub = published_app()
    ack(app, run_id="999-9", status="saved", message="Another run", name="Other", country="us")
    assert pub.status == SENDING
    ack(app, run_id=pub.run_id, status="saved", message="Score saved as NovaPilot.", name="NovaPilot",
        country="in", score=1200)
    ack(app, run_id=pub.run_id, status="error", message="late duplicate", retryable=True)
    ack(app, run_id=pub.run_id, status="saving", message="late duplicate")
    assert pub.status == SAVED                     # never downgraded


def test_a_new_run_never_inherits_the_old_acknowledgement():
    app, bridge, pub = published_app()
    old_run = pub.run_id
    app.act("play")                                # start another run while pending
    assert app.publication is None and app.game.run_id != old_run
    ack(app, run_id=old_run, status="saved", message="Score saved as NovaPilot.", name="NovaPilot")
    assert app.publication is None and app.menu.screen is None


def test_no_answer_becomes_a_retryable_error():
    pub = Publication("5-1", "Nova", "in", 10)
    assert pub.request()["run_id"] == "5-1"
    pub.update(PENDING_TIMEOUT + 0.1)
    assert pub.status == ERROR and pub.can_retry
    assert pub.request() is not None               # retry allowed


def test_publication_rules_without_the_app():
    pub = Publication("7-1", "Nova", "in", 10)
    assert not pub.acknowledge({"run_id": "7-1", "status": "saved"})   # nothing requested yet
    assert pub.request() and pub.request() is None                      # one request per click
    assert not pub.acknowledge({"run_id": "7-1", "status": "bogus"})
    host = HostConfig()
    host.update({"publicLeaderboard": "yes", "nameMax": 99})
    assert host.public is False and host.name_max == 20
