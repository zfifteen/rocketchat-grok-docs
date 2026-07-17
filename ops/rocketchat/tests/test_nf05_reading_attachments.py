#!/usr/bin/env python3
"""
NF-SPEC-05 / permanent inbound attachment path tests.

Covers extract/classify (thumb skip, docs), compose inject blocks, SSRF host
guard, rehydrate-before-download contract (mocked), and reply_prompt inbound rule.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WAKE_DIR = ROOT / "wake"
sys.path.insert(0, str(WAKE_DIR))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")


# Live RC 8.6 shape from principal DM 2026-07-11 (IMG_1651 + thumb).
RC_MSG_IMAGE_THUMB = {
    "_id": "HyfhurqfzJ4aq8Bwx",
    "msg": "I attached an image to this message.",
    "file": {
        "_id": "6a52bb56b5a8385468086e39",
        "name": "IMG_1651.jpg",
        "type": "image/jpeg",
        "typeGroup": "image",
    },
    "files": [
        {
            "_id": "6a52bb56b5a8385468086e39",
            "name": "IMG_1651.jpg",
            "type": "image/jpeg",
            "typeGroup": "image",
        },
        {
            "_id": "6a52bb56b5a8385468086e3a",
            "name": "thumb-IMG_1651.jpg",
            "type": "image/jpeg",
            "typeGroup": "thumb",
        },
    ],
    "attachments": [
        {
            "title": "IMG_1651.jpg",
            "title_link": "/file-upload/6a52bb56b5a8385468086e39/IMG_1651.jpg",
            # image_url intentionally points at thumb id (live RC behavior)
            "image_url": "/file-upload/6a52bb56b5a8385468086e3a/IMG_1651.jpg",
            "image_type": "image/jpeg",
            "type": "file",
        }
    ],
}

RC_MSG_SPARSE_WS = {
    "_id": "sparse1",
    "msg": "Can you view this image?",
    # No file / files / attachments — DDP sparse shape
}


class TestExtractAndThumb(unittest.TestCase):
    def test_thumb_skipped_by_name_and_type_group(self) -> None:
        imgs = wl.extract_image_file_candidates(RC_MSG_IMAGE_THUMB)
        self.assertEqual(len(imgs), 1)
        self.assertEqual(imgs[0]["id"], "6a52bb56b5a8385468086e39")
        self.assertFalse(imgs[0]["name"].lower().startswith("thumb"))

    def test_union_dedupes_file_and_attachments(self) -> None:
        all_f = wl.extract_file_candidates(RC_MSG_IMAGE_THUMB)
        ids = [f["id"] for f in all_f]
        self.assertEqual(ids.count("6a52bb56b5a8385468086e39"), 1)

    def test_title_link_preferred_over_image_url_thumb(self) -> None:
        # Attachment-only message where image_url is thumb id
        msg = {
            "attachments": [
                {
                    "title": "photo.jpg",
                    "title_link": "/file-upload/fullid/photo.jpg",
                    "image_url": "/file-upload/thumbid/thumb-photo.jpg",
                    "image_type": "image/jpeg",
                }
            ]
        }
        imgs = wl.extract_image_file_candidates(msg)
        self.assertEqual(len(imgs), 1)
        self.assertEqual(imgs[0]["id"], "fullid")
        self.assertIn("photo.jpg", imgs[0]["title_link"])


class TestDocuments(unittest.TestCase):
    def test_markdown_document(self) -> None:
        msg = {
            "file": {
                "_id": "d1",
                "name": "notes.md",
                "type": "text/markdown",
            }
        }
        docs = wl.extract_document_file_candidates(msg)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["name"], "notes.md")
        self.assertEqual(wl.extract_image_file_candidates(msg), [])

    def test_exe_denylisted(self) -> None:
        msg = {"file": {"_id": "x1", "name": "malware.exe", "type": "application/octet-stream"}}
        self.assertEqual(wl.extract_document_file_candidates(msg), [])
        self.assertTrue(wl._looks_like_binary_skip("malware.exe"))


class TestCompose(unittest.TestCase):
    def test_image_path_block(self) -> None:
        text = wl.compose_wake_user_text(
            "what is this?",
            image_paths=["/tmp/attachments/a.jpg"],
        )
        self.assertIn("what is this?", text)
        self.assertIn("[Image attachment(s)", text)
        self.assertIn("read_file", text)
        self.assertIn("/tmp/attachments/a.jpg", text)

    def test_file_entry_block(self) -> None:
        text = wl.compose_wake_user_text(
            "summarize",
            file_entries=[
                {
                    "path": "/tmp/attachments/n.md",
                    "name": "n.md",
                    "mime": "text/markdown",
                    "bytes": "12",
                }
            ],
        )
        self.assertIn("[File attachment(s)", text)
        self.assertIn("path=/tmp/attachments/n.md", text)
        self.assertIn("read_file", text)

    def test_empty_stub_covers_images_and_docs(self) -> None:
        stub = wl.empty_attachment_wake_stub()
        self.assertIn("image", stub.lower())
        self.assertIn("document", stub.lower())
        self.assertNotEqual(
            stub,
            "(Received a message with an attachment but no text and no "
            "transcribable audio. Re-send as a voice note or with a caption.)",
        )


class TestReplyPromptInbound(unittest.TestCase):
    def test_inbound_rule_present(self) -> None:
        prompt = (WAKE_DIR / "reply_prompt.txt").read_text(encoding="utf-8")
        self.assertIn("Inbound attachments", prompt)
        self.assertIn("read_file", prompt)
        self.assertIn("cannot view Rocket.Chat attachments", prompt)
        self.assertIn("rocketchat.env", prompt)
        self.assertIn("local paths are real files", prompt)


class TestOperatorDownloadPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Load operator only after wake_lib is in sys.modules
        cls.op = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")

    def test_same_host_allows_base(self) -> None:
        op = self.op
        op.BASE_HTTP = "http://127.0.0.1:3000"
        self.assertTrue(op._same_host_as_base("http://127.0.0.1:3000/file-upload/a/b.jpg"))
        self.assertTrue(op._same_host_as_base("http://localhost:3000/file-upload/a/b.jpg"))
        self.assertFalse(op._same_host_as_base("https://evil.example/file"))

    def test_download_rejects_external_host(self) -> None:
        op = self.op
        op.BASE_HTTP = "http://127.0.0.1:3000"
        with self.assertRaises(RuntimeError) as ctx:
            op.download_rc_file(
                "tok",
                "uid",
                title_link="https://evil.example/secret.bin",
                dest_dir=Path(tempfile.mkdtemp()),
            )
        self.assertIn("refusing download", str(ctx.exception).lower())

    def test_resolve_rehydrates_sparse_then_injects_image(self) -> None:
        op = self.op
        op.RC_ATTACH_ENABLED = True
        op.RC_ATTACH_IMAGE = True
        op.RC_ATTACH_DOCS = True
        op.RC_ATTACH_REHYDRATE_ATTEMPTS = 2
        op.RC_ATTACH_REHYDRATE_DELAY_S = 0.0
        op.BASE_HTTP = "http://127.0.0.1:3000"
        tmp = Path(tempfile.mkdtemp())
        op.ATTACHMENTS_DIR = tmp
        op.AUDIO_CACHE_DIR = tmp

        full = dict(RC_MSG_IMAGE_THUMB)
        full["msg"] = "Can you view this image?"

        def fake_fetch(mid: str):
            return full if mid == "sparse1" else None

        jpeg = b"\xff\xd8\xff" + b"\x00" * 64

        def fake_download(token, uid, **kwargs):
            dest_dir = kwargs.get("dest_dir") or tmp
            dest_dir = Path(dest_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            p = dest_dir / "test-IMG_1651.jpg"
            p.write_bytes(jpeg)
            return p

        with mock.patch.object(op, "fetch_message_by_id", side_effect=fake_fetch):
            with mock.patch.object(op, "_operator_auth", return_value=("t", "u")):
                with mock.patch.object(op, "download_rc_file", side_effect=fake_download):
                    text = op.resolve_message_text_for_wake(dict(RC_MSG_SPARSE_WS))

        self.assertIn("Can you view this image?", text)
        self.assertIn("[Image attachment(s)", text)
        self.assertIn("test-IMG_1651.jpg", text)
        self.assertNotIn("thumb-", text)

    def test_resolve_skips_images_when_disabled(self) -> None:
        op = self.op
        op.RC_ATTACH_ENABLED = False
        op.RC_ATTACH_REHYDRATE_ATTEMPTS = 1
        with mock.patch.object(op, "fetch_message_by_id", return_value=RC_MSG_IMAGE_THUMB):
            with mock.patch.object(op, "_operator_auth", return_value=("t", "u")):
                text = op.resolve_message_text_for_wake(dict(RC_MSG_IMAGE_THUMB))
        self.assertEqual(text, "I attached an image to this message.")
        self.assertNotIn("[Image attachment(s)", text)


if __name__ == "__main__":
    unittest.main()
