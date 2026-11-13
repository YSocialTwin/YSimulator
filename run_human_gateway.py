"""Human gateway entry of YSimulator (microblogging, HPC): one JSON request on stdin, one JSON answer on stdout.

Usage: python run_human_gateway.py <config_dir>      (stdin: {"op": "ensure"|"state"|"actions", "body": {...}})

The same operations as the human gateways of the other runtimes, applied to the database of the experiment under a file
lock; it works with the server running or stopped. Answer: the body of the operation plus ``status``."""

import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    config_dir = Path(argv[0]).resolve()
    try:
        config = json.loads((config_dir / "server_config.json").read_text())
        request = json.loads(sys.stdin.read() or "{}")
        assert isinstance(request, dict)
    except (OSError, ValueError, AssertionError):
        print(json.dumps({"ok": False, "status": 400, "code": "invalid_request"}))
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from YSimulator.YServer.federation.humans import HumanGateway, handle
    from YSimulator.utils.init_db import create_database_engine

    db_config = json.loads(json.dumps(config.get("database") or {"type": "sqlite", "sqlite": {"filename": "simulation.db"}}))
    if "database_file" in config:
        db_config = {"type": "sqlite", "sqlite": {"filename": config["database_file"]}}
    # the same database the server uses (run_server.py makes the name unique per server)
    if db_config.get("type", "sqlite") == "sqlite":
        db_config.setdefault("sqlite", {})["filename"] = "database_server.db"
    elif db_config.get("type") in ("postgresql", "mysql"):
        section = db_config.setdefault(db_config["type"], {})
        section["database"] = f"{section.get('database', 'ysimulator')}_{config.get('server_name', 'orchestrator_server')}"
    federation = config.get("federation") or {}
    gw = HumanGateway(create_database_engine(db_config, config_dir), federation.get("crosspost_mode", "coordinator_rule"),
                      federation.get("member"))
    status, body = handle(config_dir / "server_config.human.lock", gw, str(request.get("op", "")), request.get("body") or {})
    print(json.dumps({**body, "status": status}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
