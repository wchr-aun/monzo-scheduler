"""Reject credential files and SQLite databases in the Git index without printing contents."""

from pathlib import PurePosixPath
import subprocess
import sys


def check_index() -> list[str]:
    names = (
        subprocess.check_output(["git", "ls-files", "--cached", "-z"])
        .decode()
        .split("\0")
    )
    rejected = []
    for name in filter(None, names):
        path = PurePosixPath(name)
        credential_file = (
            path.name.startswith(".env") and path.name != ".env.example"
        ) or path.suffix in {".pem", ".key"}
        database_file = any(
            path.name.endswith(suffix) or f"{suffix}-" in path.name
            for suffix in (".db", ".sqlite", ".sqlite3")
        )
        content = subprocess.check_output(["git", "show", f":{name}"])
        if (
            credential_file
            or database_file
            or content.startswith(b"SQLite format 3\x00")
            or any(
                marker in content
                for marker in (
                    b"-----BEGIN " + b"PRIVATE KEY-----",
                    b"-----BEGIN RSA " + b"PRIVATE KEY-----",
                    b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
                )
            )
        ):
            rejected.append(name)
    return rejected


if __name__ == "__main__":
    rejected = check_index()
    if rejected:
        print(
            "Sensitive files must not be committed:\n" + "\n".join(rejected),
            file=sys.stderr,
        )
        sys.exit(1)
