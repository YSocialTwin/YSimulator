import ast
from pathlib import Path


def test_project_uses_sqlalchemy_for_db_access():
    repo_root = Path(__file__).resolve().parents[2]
    ysim_root = repo_root / "YSimulator"
    violations = []

    for py_file in ysim_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        if py_file.name == "test_sqlalchemy_only_db_access.py":
            continue

        source = py_file.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "sqlite3":
                        violations.append(f"{py_file}: imports sqlite3")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "sqlite3":
                    violations.append(f"{py_file}: imports from sqlite3")
            elif isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "connect"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "sqlite3"
                ):
                    violations.append(f"{py_file}: calls sqlite3.connect(...)")

    assert not violations, "Found non-SQLAlchemy DB access patterns:\n" + "\n".join(violations)
