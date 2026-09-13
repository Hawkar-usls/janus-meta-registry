#!/usr/bin/env python3
"""Blind media extractor and gate runner for JANUS IO D4 prevalence screening.

The human-facing surface is intentionally narrow: it exposes only media bytes under a
neutral local filename and a technical receipt. KYM page HTML, titles, captions, tags,
comments, original media filenames, and raw media URLs are never written to disk or
printed.

This tool DOES NOT decide D4 eligibility. It only enforces frozen order, retrieves one
media object at a time, records an operator's visual PASS/FAIL/OPEN decision, performs
exact-byte dedupe, and stops immediately at 20 PASS decisions.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib

TOOL_SCHEMA = "janus.io.d4_prevalence.kym_blind_media_extractor.v1_0"
STATE_SCHEMA = "janus.io.d4_prevalence.kym_blind_screen_state.v1_0"
FREEZE_SCHEMA = "janus.io.d4_prevalence.kym_sample_freeze.v1_0"
EXPECTED_TARGET_N = 20
EXPECTED_MINIMUM_N = 15
EXPECTED_RANK_RULE = (
    "For each frozen KYM photo ID i, compute SHA256(seed + ':' + decimal(i)); "
    "sort lexicographically ascending by the 64-character lowercase hex digest."
)
PAGE_HOSTS = {"knowyourmeme.com", "www.knowyourmeme.com"}
MEDIA_HOST_SUFFIXES = (".kym-cdn.com",)
MEDIA_HOSTS = {"kym-cdn.com"}
PAGE_MAX_BYTES = 4 * 1024 * 1024
MEDIA_MAX_BYTES = 100 * 1024 * 1024
USER_AGENT = "JANUS-IO-D4-BlindExtractor/1.0 (+research; no-context-screening)"
ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
PASS_REASONS = {"DIRECT_SOURCE_IDENTIFIABLE"}
FAIL_REASONS = {
    "NON_SOURCE_SKELETON",
    "REDRAW_3D_OR_OTHER_REMAKE",
    "OTHER_SOURCE_INELIGIBLE",
    "DUPLICATE_MEDIA",
}
OPEN_REASONS = {"AMBIGUOUS_SOURCE", "RETRIEVAL_ERROR"}


class GateError(RuntimeError):
    """Fail-closed protocol error. Messages must not contain fetched semantic text."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("LOCAL_JSON_READ_ERROR") from exc
    if not isinstance(value, dict):
        raise GateError("LOCAL_JSON_ROOT_NOT_OBJECT")
    return value


def _host_allowed(host: str, *, media: bool) -> bool:
    host = host.lower().rstrip(".")
    if media:
        return host in MEDIA_HOSTS or any(host.endswith(sfx) for sfx in MEDIA_HOST_SUFFIXES)
    return host in PAGE_HOSTS


def _validate_https_url(url: str, *, media: bool) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise GateError("URL_POLICY_REJECTED")
    if not _host_allowed(parsed.hostname, media=media):
        raise GateError("HOST_POLICY_REJECTED")
    if parsed.username or parsed.password:
        raise GateError("URL_CREDENTIALS_REJECTED")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, media: bool):
        super().__init__()
        self.media = media

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        _validate_https_url(newurl, media=self.media)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _MediaMetaParser(HTMLParser):
    """Extract only machine-readable primary-media URL attributes.

    Visible text is deliberately ignored: handle_data is a no-op, and no title/tag/
    description value is retained. Generic <img> elements are ignored to avoid ads,
    avatars, recommendation thumbnails, and other page chrome.
    """

    META_KEYS = {
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
        "og:video",
        "og:video:url",
        "og:video:secure_url",
        "twitter:player:stream",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        amap = {str(k).lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "meta":
            key = (amap.get("property") or amap.get("name") or "").lower()
            if key in self.META_KEYS and amap.get("content"):
                self.candidates.append(amap["content"])
        elif tag == "link":
            rel = {x.lower() for x in amap.get("rel", "").split()}
            if "image_src" in rel and amap.get("href"):
                self.candidates.append(amap["href"])

    def handle_data(self, data: str) -> None:
        # Epistemic firewall: never retain human-readable page text.
        return None


@dataclass(frozen=True)
class MediaReceipt:
    photo_id: int
    rank_position: int
    rank_digest: str
    retrieval_status: str
    media_sha256: str | None = None
    media_url_sha256: str | None = None
    media_mime: str | None = None
    media_bytes: int | None = None
    neutral_file: str | None = None
    error_code: str | None = None

    def as_dict(self) -> dict:
        return {
            "photo_id": self.photo_id,
            "rank_position": self.rank_position,
            "rank_digest": self.rank_digest,
            "retrieval_status": self.retrieval_status,
            "media_sha256": self.media_sha256,
            "media_url_sha256": self.media_url_sha256,
            "media_mime": self.media_mime,
            "media_bytes": self.media_bytes,
            "neutral_file": self.neutral_file,
            "error_code": self.error_code,
        }


def _read_limited(response, limit: int) -> bytes:  # noqa: ANN001
    chunks: list[bytes] = []
    total = 0
    while True:
        block = response.read(min(65536, limit + 1 - total))
        if not block:
            break
        total += len(block)
        if total > limit:
            raise GateError("RESPONSE_TOO_LARGE")
        chunks.append(block)
    return b"".join(chunks)


def _sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in {b"avif", b"avis"}:
            return "image/avif"
        return "video/mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


def _content_type(headers) -> str | None:  # noqa: ANN001
    raw = headers.get("Content-Type", "") if headers is not None else ""
    return raw.split(";", 1)[0].strip().lower() or None


def _download_page_html(photo_id: int) -> tuple[bytes, str]:
    page_url = f"https://knowyourmeme.com/photos/{photo_id}"
    _validate_https_url(page_url, media=False)
    req = Request(page_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    opener = build_opener(_SafeRedirectHandler(media=False))
    try:
        with opener.open(req, timeout=30) as resp:
            _validate_https_url(resp.geturl(), media=False)
            html = _read_limited(resp, PAGE_MAX_BYTES)
    except HTTPError as exc:
        raise GateError("PAGE_HTTP_ERROR") from exc
    except URLError as exc:
        raise GateError("PAGE_NETWORK_ERROR") from exc
    except TimeoutError as exc:
        raise GateError("PAGE_TIMEOUT") from exc
    return html, page_url


def _extract_media_candidates(html: bytes, page_url: str) -> list[str]:
    # Decode only for parser operation; decoded text is never returned/logged/stored.
    text = html.decode("utf-8", errors="replace")
    parser = _MediaMetaParser()
    parser.feed(text)
    del text
    out: list[str] = []
    seen: set[str] = set()
    for raw in parser.candidates:
        url = urljoin(page_url, raw.strip())
        try:
            _validate_https_url(url, media=True)
        except GateError:
            continue
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _download_media(url: str) -> tuple[bytes, str]:
    _validate_https_url(url, media=True)
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,video/*"})
    opener = build_opener(_SafeRedirectHandler(media=True))
    try:
        with opener.open(req, timeout=45) as resp:
            _validate_https_url(resp.geturl(), media=True)
            data = _read_limited(resp, MEDIA_MAX_BYTES)
            declared = _content_type(resp.headers)
    except HTTPError as exc:
        raise GateError("MEDIA_HTTP_ERROR") from exc
    except URLError as exc:
        raise GateError("MEDIA_NETWORK_ERROR") from exc
    except TimeoutError as exc:
        raise GateError("MEDIA_TIMEOUT") from exc
    sniffed = _sniff_mime(data)
    mime = declared if declared in ALLOWED_MIME else sniffed
    if mime not in ALLOWED_MIME:
        raise GateError("MEDIA_TYPE_REJECTED")
    if sniffed is not None and declared in ALLOWED_MIME and sniffed != declared:
        raise GateError("MEDIA_TYPE_MISMATCH")
    return data, mime


def retrieve_blind_media(photo_id: int, rank_position: int, rank_digest: str, screen_dir: Path) -> MediaReceipt:
    """Fetch one KYM object while keeping all semantic page text off the output surface."""
    try:
        html, page_url = _download_page_html(photo_id)
        candidates = _extract_media_candidates(html, page_url)
        del html
        if not candidates:
            raise GateError("NO_MEDIA_CANDIDATE")

        last_error = "NO_VALID_MEDIA_CANDIDATE"
        for media_url in candidates:
            try:
                data, mime = _download_media(media_url)
            except GateError as exc:
                last_error = str(exc)
                continue
            digest = _sha256_bytes(data)
            url_digest = hashlib.sha256(media_url.encode("utf-8")).hexdigest()
            ext = ALLOWED_MIME[mime]
            screen_dir.mkdir(parents=True, exist_ok=True)
            neutral_name = f"screen-{rank_position:04d}{ext}"
            target = screen_dir / neutral_name
            fd, tmp_name = tempfile.mkstemp(prefix="blind-media-", dir=str(screen_dir))
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_name, target)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            return MediaReceipt(
                photo_id=photo_id,
                rank_position=rank_position,
                rank_digest=rank_digest,
                retrieval_status="OK",
                media_sha256=digest,
                media_url_sha256=url_digest,
                media_mime=mime,
                media_bytes=len(data),
                neutral_file=neutral_name,
            )
        raise GateError(last_error)
    except GateError as exc:
        return MediaReceipt(
            photo_id=photo_id,
            rank_position=rank_position,
            rank_digest=rank_digest,
            retrieval_status="OPEN",
            error_code=str(exc),
        )


def _decode_frozen_ids(manifest: dict) -> tuple[list[int], bytes]:
    payload = manifest.get("ordered_id_payload", {})
    if payload.get("encoding") != "zlib+base64":
        raise GateError("MANIFEST_ENCODING_MISMATCH")
    try:
        compressed = base64.b64decode(payload["payload"], validate=True)
        decoded = zlib.decompress(compressed)
    except Exception as exc:
        raise GateError("MANIFEST_PAYLOAD_DECODE_ERROR") from exc
    if len(decoded) != int(payload.get("raw_decoded_length_bytes", -1)):
        raise GateError("MANIFEST_LENGTH_MISMATCH")
    if _sha256_bytes(decoded) != payload.get("decoded_sha256"):
        raise GateError("MANIFEST_SHA256_MISMATCH")
    try:
        ids = [int(x) for x in decoded.decode("ascii").split(",") if x]
    except (UnicodeDecodeError, ValueError) as exc:
        raise GateError("MANIFEST_ID_PARSE_ERROR") from exc
    source = manifest.get("source", {})
    if len(ids) != int(source.get("total_items_observed", -1)):
        raise GateError("MANIFEST_TOTAL_COUNT_MISMATCH")
    if len(set(ids)) != int(source.get("unique_items_observed", -1)):
        raise GateError("MANIFEST_UNIQUE_COUNT_MISMATCH")
    return ids, decoded


def _rank_rows(ids: Iterable[int], seed: str) -> list[dict]:
    rows = []
    for photo_id in ids:
        digest = hashlib.sha256(f"{seed}:{photo_id}".encode("ascii")).hexdigest()
        rows.append({"photo_id": int(photo_id), "rank_digest": digest})
    rows.sort(key=lambda row: row["rank_digest"])
    for pos, row in enumerate(rows, 1):
        row["rank_position"] = pos
    return rows


def _match_ranked_order_checksum(rows: list[dict], expected: str) -> str:
    ids = [str(row["photo_id"]) for row in rows]
    serializations = {
        "comma_separated_decimal_ids": ",".join(ids).encode("ascii"),
        "comma_separated_decimal_ids_newline": (",".join(ids) + "\n").encode("ascii"),
        "newline_separated_decimal_ids": "\n".join(ids).encode("ascii"),
        "compact_json_decimal_ids": json.dumps([int(x) for x in ids], separators=(",", ":")).encode("ascii"),
    }
    matches = [name for name, payload in serializations.items() if _sha256_bytes(payload) == expected]
    if len(matches) != 1:
        raise GateError("RANKED_ORDER_SHA256_MISMATCH")
    return matches[0]


def build_prepared_state(manifest: dict, prereg: dict) -> dict:
    ids, _ = _decode_frozen_ids(manifest)
    sm = prereg.get("sampling_manifest", {})
    if int(sm.get("item_count", -1)) != len(ids) or int(sm.get("unique_item_count", -1)) != len(set(ids)):
        raise GateError("PREREG_FRAME_COUNT_MISMATCH")
    if sm.get("ordered_ids_sha256") != manifest.get("ordered_id_payload", {}).get("decoded_sha256"):
        raise GateError("PREREG_FRAME_SHA256_MISMATCH")

    randomization = prereg.get("deterministic_randomization", {})
    seed = randomization.get("seed")
    if not isinstance(seed, str) or not seed:
        raise GateError("PREREG_SEED_MISSING")
    if _sha256_bytes(seed.encode("utf-8")) != randomization.get("seed_sha256"):
        raise GateError("PREREG_SEED_SHA256_MISMATCH")
    if randomization.get("rank_rule") != EXPECTED_RANK_RULE:
        raise GateError("PREREG_RANK_RULE_MISMATCH")
    rows = _rank_rows(ids, seed)
    expected_ranked_sha = randomization.get("full_ranked_order_sha256")
    if not isinstance(expected_ranked_sha, str):
        raise GateError("PREREG_RANKED_ORDER_SHA256_MISSING")
    serialization = _match_ranked_order_checksum(rows, expected_ranked_sha)

    first_50 = randomization.get("first_50_ids_for_audit")
    if first_50 is not None and [row["photo_id"] for row in rows[: len(first_50)]] != first_50:
        raise GateError("PREREG_FIRST_50_MISMATCH")

    eligibility = prereg.get("eligibility_screen", {})
    if int(eligibility.get("target_n", -1)) != EXPECTED_TARGET_N:
        raise GateError("PREREG_TARGET_N_MISMATCH")
    if int(eligibility.get("minimum_n", -1)) != EXPECTED_MINIMUM_N:
        raise GateError("PREREG_MINIMUM_N_MISMATCH")

    return {
        "schema": STATE_SCHEMA,
        "tool_schema": TOOL_SCHEMA,
        "status": "PREPARED__SCREENING_NOT_STARTED",
        "created_unix": int(time.time()),
        "frame": {
            "item_count": len(ids),
            "ordered_ids_sha256": sm.get("ordered_ids_sha256"),
            "seed_sha256": randomization.get("seed_sha256"),
            "full_ranked_order_sha256": expected_ranked_sha,
            "ranked_order_serialization": serialization,
        },
        "target_n": EXPECTED_TARGET_N,
        "minimum_n": EXPECTED_MINIMUM_N,
        "ranked": rows,
        "cursor": 0,
        "active": None,
        "ledger": [],
        "pass_count": 0,
        "seen_media_sha256": {},
        "epistemic_firewall": {
            "context_coding": "LOCKED",
            "cri": "FORBIDDEN",
            "page_text_exposed_by_tool": False,
            "raw_media_url_exposed_by_tool": False,
        },
    }


def prepare(manifest_path: Path, prereg_path: Path, state_path: Path) -> dict:
    if state_path.exists():
        raise GateError("STATE_ALREADY_EXISTS")
    state = build_prepared_state(_load_json(manifest_path), _load_json(prereg_path))
    _atomic_write_json(state_path, state)
    return {
        "status": state["status"],
        "frame_item_count": state["frame"]["item_count"],
        "full_ranked_order_sha256": state["frame"]["full_ranked_order_sha256"],
        "next_rank_position": 1,
    }


def _public_receipt(entry: dict) -> dict:
    allowed = {
        "photo_id",
        "rank_position",
        "rank_digest",
        "retrieval_status",
        "media_sha256",
        "media_url_sha256",
        "media_mime",
        "media_bytes",
        "neutral_file",
        "error_code",
        "eligibility",
        "visual_reason_code",
    }
    return {k: entry.get(k) for k in allowed if k in entry}


def next_item(state_path: Path, screen_dir: Path) -> dict:
    state = _load_json(state_path)
    if state.get("schema") != STATE_SCHEMA:
        raise GateError("STATE_SCHEMA_MISMATCH")
    if state.get("status") == "SAMPLE_FROZEN__STOP_AT_20":
        raise GateError("GATE_ALREADY_STOPPED_AT_20")
    if state.get("active") is not None:
        raise GateError("ACTIVE_ITEM_MUST_BE_RECORDED_FIRST")
    cursor = int(state.get("cursor", 0))
    ranked = state.get("ranked", [])
    if cursor >= len(ranked):
        state["status"] = "FRAME_EXHAUSTED"
        _atomic_write_json(state_path, state)
        raise GateError("FRAME_EXHAUSTED")

    row = ranked[cursor]
    receipt = retrieve_blind_media(
        photo_id=int(row["photo_id"]),
        rank_position=int(row["rank_position"]),
        rank_digest=str(row["rank_digest"]),
        screen_dir=screen_dir,
    )
    entry = receipt.as_dict()
    if receipt.retrieval_status != "OK":
        entry["eligibility"] = "OPEN"
        entry["visual_reason_code"] = "RETRIEVAL_ERROR"
        state["ledger"].append(entry)
        state["cursor"] = cursor + 1
        state["status"] = "SCREENING_ACTIVE"
        _atomic_write_json(state_path, state)
        return _public_receipt(entry)

    seen = state.get("seen_media_sha256", {})
    if receipt.media_sha256 in seen:
        entry["eligibility"] = "FAIL"
        entry["visual_reason_code"] = "DUPLICATE_MEDIA"
        entry["duplicate_of_rank_position"] = int(seen[receipt.media_sha256])
        if receipt.neutral_file:
            try:
                (screen_dir / receipt.neutral_file).unlink()
            except OSError:
                pass
        state["ledger"].append(entry)
        state["cursor"] = cursor + 1
        state["status"] = "SCREENING_ACTIVE"
        _atomic_write_json(state_path, state)
        return _public_receipt(entry)

    seen[receipt.media_sha256] = receipt.rank_position
    state["seen_media_sha256"] = seen
    state["active"] = entry
    state["status"] = "SCREENING_ACTIVE"
    _atomic_write_json(state_path, state)
    return _public_receipt(entry)


def record_decision(state_path: Path, screen_dir: Path, verdict: str, reason: str) -> dict:
    verdict = verdict.upper()
    reason = reason.upper()
    if verdict == "PASS" and reason not in PASS_REASONS:
        raise GateError("PASS_REASON_REJECTED")
    if verdict == "FAIL" and reason not in FAIL_REASONS - {"DUPLICATE_MEDIA"}:
        raise GateError("FAIL_REASON_REJECTED")
    if verdict == "OPEN" and reason not in OPEN_REASONS - {"RETRIEVAL_ERROR"}:
        raise GateError("OPEN_REASON_REJECTED")

    state = _load_json(state_path)
    active = state.get("active")
    if not isinstance(active, dict):
        raise GateError("NO_ACTIVE_ITEM")
    active["eligibility"] = verdict
    active["visual_reason_code"] = reason
    state["ledger"].append(active)
    state["active"] = None
    state["cursor"] = int(state.get("cursor", 0)) + 1
    if verdict == "PASS":
        state["pass_count"] = int(state.get("pass_count", 0)) + 1

    neutral = active.get("neutral_file")
    if neutral:
        try:
            (screen_dir / neutral).unlink()
        except OSError:
            pass

    if int(state.get("pass_count", 0)) >= EXPECTED_TARGET_N:
        if int(state["pass_count"]) != EXPECTED_TARGET_N:
            raise GateError("PASS_COUNT_OVERSHOOT")
        state["status"] = "SAMPLE_FROZEN__STOP_AT_20"
        state["epistemic_firewall"]["context_coding"] = "LOCKED_UNTIL_FREEZE_ARTIFACT_WRITTEN"
    else:
        state["status"] = "SCREENING_ACTIVE"
    _atomic_write_json(state_path, state)
    return {
        "recorded_rank_position": active["rank_position"],
        "verdict": verdict,
        "reason": reason,
        "pass_count": state["pass_count"],
        "status": state["status"],
    }


def freeze_sample(state_path: Path, output_path: Path) -> dict:
    if output_path.exists():
        raise GateError("FREEZE_OUTPUT_ALREADY_EXISTS")
    state = _load_json(state_path)
    if state.get("status") != "SAMPLE_FROZEN__STOP_AT_20" or int(state.get("pass_count", 0)) != EXPECTED_TARGET_N:
        raise GateError("FREEZE_REQUIRES_EXACTLY_20_PASS")
    passed = [x for x in state.get("ledger", []) if x.get("eligibility") == "PASS"]
    if len(passed) != EXPECTED_TARGET_N:
        raise GateError("FREEZE_LEDGER_PASS_COUNT_MISMATCH")
    sample_ids = [int(x["photo_id"]) for x in passed]
    sample_ids_bytes = ",".join(str(x) for x in sample_ids).encode("ascii")
    ledger = state.get("ledger", [])
    artifact = {
        "schema": FREEZE_SCHEMA,
        "status": "D4_PREVALENCE_KYM_ELIGIBILITY_SCREEN_AND_SAMPLE_FREEZE_GATE__PASS",
        "target_n": EXPECTED_TARGET_N,
        "sample_ids_rank_order": sample_ids,
        "sample_ids_sha256": _sha256_bytes(sample_ids_bytes),
        "screened_item_count": len(ledger),
        "exclusion_count": sum(1 for x in ledger if x.get("eligibility") != "PASS"),
        "ledger_sha256": _sha256_bytes(_canonical_json_bytes(ledger)),
        "frame": state["frame"],
        "epistemic_firewall": [
            "Eligibility decisions precede context coding.",
            "KYM page text and raw media URLs are not emitted by the blind extractor.",
            "This sample estimates only the frozen KYM frame, not internet-wide prevalence.",
            "Context/LRS/LES/CRI remain locked until this freeze artifact is externally committed/sealed.",
        ],
    }
    _atomic_write_json(output_path, artifact)
    state["freeze_artifact_sha256"] = _sha256_bytes(output_path.read_bytes())
    state["status"] = "SAMPLE_FREEZE_ARTIFACT_WRITTEN__AWAIT_EXTERNAL_SEAL"
    _atomic_write_json(state_path, state)
    return {
        "status": state["status"],
        "sample_n": len(sample_ids),
        "sample_ids_sha256": artifact["sample_ids_sha256"],
        "ledger_sha256": artifact["ledger_sha256"],
        "freeze_artifact_sha256": state["freeze_artifact_sha256"],
    }


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JANUS IO D4 blind KYM media extractor")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="verify frozen frame/prereg and initialize state; no network")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--prereg", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)

    p = sub.add_parser("next", help="retrieve exactly the next hash-ranked media object")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--screen-dir", type=Path, required=True)

    p = sub.add_parser("record", help="record visual-only decision for the current object")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--screen-dir", type=Path, required=True)
    p.add_argument("--verdict", choices=["PASS", "FAIL", "OPEN"], required=True)
    p.add_argument(
        "--reason",
        choices=sorted((PASS_REASONS | FAIL_REASONS | OPEN_REASONS) - {"DUPLICATE_MEDIA", "RETRIEVAL_ERROR"}),
        required=True,
    )

    p = sub.add_parser("freeze", help="write sample-freeze artifact after exact stop-at-20")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            _print_json(prepare(args.manifest, args.prereg, args.state))
        elif args.command == "next":
            _print_json(next_item(args.state, args.screen_dir))
        elif args.command == "record":
            _print_json(record_decision(args.state, args.screen_dir, args.verdict, args.reason))
        elif args.command == "freeze":
            _print_json(freeze_sample(args.state, args.output))
        else:
            raise GateError("UNKNOWN_COMMAND")
    except GateError as exc:
        _print_json({"status": "ERROR", "error_code": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
