import re
import subprocess
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
VERSION_RE = r'version\s*=\s*"(\d+\.\d+\.\d+)"'


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_commits() -> list[str]:
    try:
        tag = git("describe", "--tags", "--abbrev=0")
        return git("log", "--pretty=format:%s", f"{tag}..HEAD").splitlines()
    except subprocess.CalledProcessError:
        return git("log", "--pretty=format:%s").splitlines()


def get_bump_level(commits: list[str]) -> str | None:
    if any("BREAKING CHANGE" in c for c in commits):
        return "major"
    if any(c.startswith("feat") for c in commits):
        return "minor"
    if any(c.startswith("fix") for c in commits):
        return "patch"
    return None


def bump(version: str, level: str) -> str:
    major, minor, patch = map(int, version.split("."))
    match level:
        case "major":
            return f"{major + 1}.0.0"
        case "minor":
            return f"{major}.{minor + 1}.0"
        case _:
            return f"{major}.{minor}.{patch + 1}"


def main() -> None:
    content = PYPROJECT.read_text()

    if not (m := re.search(VERSION_RE, content)):
        return
    if not (commits := get_commits()):
        return
    if not (level := get_bump_level(commits)):
        return

    new_version = bump(m.group(1), level)
    PYPROJECT.write_text(re.sub(VERSION_RE, f'version = "{new_version}"', content))
    print(new_version)


if __name__ == "__main__":
    main()
