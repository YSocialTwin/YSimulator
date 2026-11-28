"""The human gateway of the microblogging HPC runtime, as YSocial's World Simulation talks to it.

The server is a Ray actor with no HTTP surface: every request goes through the runtime's script
(``run_human_gateway.py``), which works with the server running or stopped.
"""

from __future__ import annotations

from y_web.sdk import HumanGatewayTraits


def ensure_body(key, username, human_id, language):
    return {
        "human_key": key,
        "username": username,
        "language": language,
        "human_id": human_id,
    }


def actions_request(account_id, username, key, actions):
    return None, {"account_id": str(account_id), "actions": actions}


def offline_ensure(paths, body):
    return [str(paths.folder)], {"op": "ensure", "body": body}


def offline_actions(paths, path, body):
    return [str(paths.folder)], {"op": "actions", "body": body}


def post(text, targets):
    return {"type": "post", "text": text, "crosspost_to": targets}


def share(post_id, text, targets):
    return {"type": "share", "post_id": post_id, "text": text, "crosspost_to": targets}


def build_action(text, targets, post_id=None, community=None):
    return share(post_id, text, targets) if post_id else post(text, targets)


HUMAN_GATEWAY = HumanGatewayTraits(
    repo="YSimulator",
    script="run_human_gateway.py",
    http=False,
    ensure_body=ensure_body,
    actions_request=actions_request,
    offline_ensure=offline_ensure,
    offline_actions=offline_actions,
    build_action=build_action,
)
