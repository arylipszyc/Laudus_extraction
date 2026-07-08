"""Tests del writer JSONL append-only de comentarios + persistencia bajo lock — Story 7.0 (AC1, AC6)."""
import subprocess

from pipeline.importers import owner_comments_writer as ocw

ANCHOR = {
    "tx_id": "abc123def456",
    "ledger_git_sha": "deadbeef",
    "anchor_key": "0011223344ff",
    "tx_snapshot": {"date": "2026-04-05", "amount": -300.0, "currency": "CLP",
                    "account": "Liabilities:EAG:TC:Real:TestCard", "narration": "COMPRA X"},
}


def _init_git_repo(path):
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@test"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "commit.gpgsign", "false"], check=True)


def test_build_comment_shape():
    c = ocw.build_comment(anchor=ANCHOR, author_email="ary@x.cl", author_role="family",
                          body="¿esto qué es?", ts="2026-07-08T10:00:00Z")
    assert c["type"] == "comment"
    assert c["thread_id"] == c["comment_id"]  # el raíz define el thread
    assert c["anchor"] == ANCHOR
    assert c["author_role"] == "family"
    assert c["schema_version"] == ocw.SCHEMA_VERSION


def test_round_trip_thread_folding(tmp_path):
    """Escribir raíz + 2 respuestas + resolución → read_threads reconstruye el hilo (AC1/AC8)."""
    path = tmp_path / "_meta" / "owner-comments.jsonl"  # _meta no existe aún → append lo crea
    root = ocw.build_comment(anchor=ANCHOR, author_email="ary@x.cl", author_role="family",
                             body="pregunta", ts="2026-07-08T10:00:00Z")
    tid = root["thread_id"]
    ocw.append_comment(root, path)
    ocw.append_reply(tid, {"author_email": "val@x.cl", "author_role": "contador",
                           "body": "es una compra", "ts": "2026-07-08T11:00:00Z"}, path)
    ocw.append_reply(tid, {"author_email": "ary@x.cl", "author_role": "family",
                           "body": "ok gracias", "ts": "2026-07-08T12:00:00Z"}, path)
    ocw.append_resolution(tid, {"action": "resolved", "resolved_by": "ary@x.cl",
                                "resolved_at": "2026-07-08T12:05:00Z"}, path)

    threads = ocw.read_threads(path)
    assert len(threads) == 1
    t = threads[0]
    assert t["thread_id"] == tid
    assert t["root"]["body"] == "pregunta"
    assert [r["body"] for r in t["replies"]] == ["es una compra", "ok gracias"]
    assert t["replies"][0]["author_role"] == "contador"
    assert t["resolution"]["action"] == "resolved"


def test_last_resolution_wins(tmp_path):
    """Append-only: una segunda resolución gana sobre la primera (última acción gana)."""
    path = tmp_path / "owner-comments.jsonl"
    root = ocw.build_comment(anchor=ANCHOR, author_email="a@x", author_role="family",
                             body="b", ts="t")
    tid = root["thread_id"]
    ocw.append_comment(root, path)
    ocw.append_resolution(tid, {"action": "resolved", "resolved_by": "a@x"}, path)
    ocw.append_resolution(tid, {"action": "reopened", "resolved_by": "v@x"}, path)
    t = ocw.read_threads(path)[0]
    assert t["resolution"]["action"] == "reopened"


def test_read_threads_filter_and_multithread(tmp_path):
    path = tmp_path / "owner-comments.jsonl"
    c1 = ocw.build_comment(anchor=ANCHOR, author_email="a@x", author_role="family", body="1", ts="t")
    c2 = ocw.build_comment(anchor=ANCHOR, author_email="a@x", author_role="family", body="2", ts="t")
    ocw.append_comment(c1, path)
    ocw.append_comment(c2, path)
    assert len(ocw.read_threads(path)) == 2
    only = ocw.read_threads(path, thread_id=c2["thread_id"])
    assert len(only) == 1 and only[0]["root"]["body"] == "2"


def test_read_threads_missing_file(tmp_path):
    assert ocw.read_threads(tmp_path / "nope.jsonl") == []


def test_persist_and_commit_under_lock_no_git(tmp_path, monkeypatch):
    """persist_and_commit toma el lock, appendea y NO corre bean-check; git no-op sin IMPORTER_GIT_ENABLED."""
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    root = tmp_path / "ledger"
    root.mkdir()
    comment = ocw.build_comment(anchor=ANCHOR, author_email="a@x", author_role="family",
                                body="hola", ts="t")

    sha = ocw.persist_and_commit(lambda p: ocw.append_comment(comment, p),
                                 "test: comentario", ledger_root=root)

    assert sha is None  # git deshabilitado → no-op
    threads = ocw.read_threads(ocw.default_jsonl_path(root))
    assert len(threads) == 1 and threads[0]["root"]["body"] == "hola"
    assert (root / "_meta" / "owner-comments.jsonl").exists()
    assert not (root / ".import.lock").exists()  # lock liberado


def test_persist_and_commit_commits_with_git(tmp_path, monkeypatch):
    """Con IMPORTER_GIT_ENABLED el helper commitea el JSONL (reusa git_commit_push, sin bean-check)."""
    monkeypatch.setenv("IMPORTER_GIT_ENABLED", "true")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    (repo / "seed").write_text("x")  # un commit inicial para que HEAD exista
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "seed"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "push", "origin", "main"], check=True, capture_output=True)
    root = repo / "ledger"
    root.mkdir()
    comment = ocw.build_comment(anchor=ANCHOR, author_email="a@x", author_role="family",
                                body="git", ts="t")

    sha = ocw.persist_and_commit(lambda p: ocw.append_comment(comment, p),
                                 "test: comentario git", ledger_root=root)

    assert sha  # commiteó
    tracked = subprocess.run(["git", "-C", str(repo), "ls-files"],
                             capture_output=True, text=True, check=True).stdout
    assert "ledger/_meta/owner-comments.jsonl" in tracked
