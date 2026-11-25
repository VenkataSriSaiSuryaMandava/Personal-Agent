"""Normalize untrusted public job-board responses.

No network requests, HTML rendering or application execution
are performed by this module.
"""

import json
import re
import unicodedata

from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from aegis.schemas.discovery import (
    JobSourceInput,
    JobListing,
    MAX_LISTINGS_PER_SOURCE,
    MAX_RESPONSE_BYTES,
)


class SourceResponseRejected(ValueError):
    pass


class BoardLimitExceeded(SourceResponseRejected):
    pass


ALLOWED_LINK_HOSTS = {
    "greenhouse": frozenset({
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "boards.eu.greenhouse.io",
        "job-boards.eu.greenhouse.io",
    }),
    "lever": frozenset({
        "jobs.lever.co",
        "jobs.eu.lever.co",
    }),
    "ashby": frozenset({
        "jobs.ashbyhq.com",
    }),
}


def clean_text(value, limit, multiline=False):
    if not isinstance(value, str):
        return ""

    value.encode("utf-8", errors="strict")

    result = "".join(
        character
        for character in value
        if (
            unicodedata.category(character)
            not in {"Cc", "Cf"}
            or character in "\n\r\t"
        )
    )

    if multiline:
        result = "\n".join(
            " ".join(line.split())
            for line in result.splitlines()
        )
    else:
        result = " ".join(result.split())

    return result.strip()[:limit]


class PlainTextParser(HTMLParser):
    BLOCKS = {
        "p", "div", "br", "li", "ul", "ol",
        "h1", "h2", "h3", "h4", "h5",
        "section", "tr",
    }

    SUPPRESSED = {
        "script", "style", "iframe",
        "object", "svg", "template",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SUPPRESSED:
            self.suppressed.append(tag)

        if not self.suppressed and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.suppressed:
            if self.suppressed[-1] == tag:
                self.suppressed.pop()
            return

        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def html_to_text(value):
    if not isinstance(value, str):
        return ""

    parser = PlainTextParser()
    parser.feed(value)
    parser.close()

    return clean_text(
        "".join(parser.parts),
        30000,
        multiline=True,
    )


def safe_link(
    value, provider, board=None, external_id=None,
):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 2000
        or "\\" in value
        or any(
            char.isspace()
            or unicodedata.category(char) in {"Cc", "Cf"}
            for char in value
        )
    ):
        return ""

    try:
        url = urlsplit(value)

        if (
            url.scheme != "https"
            or url.username is not None
            or url.password is not None
            or url.port is not None
            or not url.path.startswith("/")
            or url.path.startswith("//")
        ):
            return ""

        if (
            provider == "greenhouse"
            and board == "stripe"
            and url.netloc.lower() == "stripe.com"
            and isinstance(external_id, str)
            and re.fullmatch(r"[0-9]{1,20}", external_id)
            and url.path == "/jobs/search"
            and url.query == "gh_jid=" + external_id
            and not url.fragment
        ):
            return (
                "https://stripe.com/jobs/search?gh_jid="
                + external_id
            )

        if url.netloc.lower() in ALLOWED_LINK_HOSTS[provider]:
            return value

        # Explicit employer-specific browser link exception.
        # This never authorizes backend network requests.
        if (
            provider == "greenhouse"
            and board == "stripe"
            and url.netloc.lower() == "stripe.com"
            and isinstance(external_id, str)
            and re.fullmatch(r"[0-9]{1,20}", external_id)
            and not url.fragment
            and re.fullmatch(
                r"/careers/listing/[A-Za-z0-9-]+/"
                + external_id + r"/?",
                url.path,
            )
        ):
            # Strip tracking parameters from custom employer links.
            return "https://stripe.com" + url.path

    except (ValueError, KeyError):
        return ""

    return ""


def timestamp(value):
    if not isinstance(value, str):
        return None

    try:
        date = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if date.tzinfo is None:
            return None

        result = int(date.timestamp())

        if 0 <= result <= 253402300799:
            return result

    except (ValueError, OverflowError, OSError):
        pass

    return None


def milliseconds(value):
    if (
        type(value) is int
        and 0 <= value <= 253402300799999
    ):
        return value // 1000

    return None


def work_mode(value):
    if not isinstance(value, str):
        return "unknown"

    return {
        "remote": "remote",
        "hybrid": "hybrid",
        "onsite": "onsite",
        "on-site": "onsite",
    }.get(
        value.strip().lower(),
        "unknown",
    )


def identifier(value):
    if type(value) is int:
        value = str(value)

    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 200
        or any(
            char.isspace()
            or unicodedata.category(char) in {"Cc", "Cf"}
            for char in value
        )
    ):
        raise SourceResponseRejected(
            "Invalid listing identifier"
        )

    value.encode("utf-8", errors="strict")
    return value


def object_value(value):
    return value if isinstance(value, dict) else {}


def greenhouse_description(value):
    if not isinstance(value, str):
        return ""

    # Decode bounded layers of provider-escaped markup.
    # The result still passes through the plain-text parser.
    for _ in range(2):
        if "<" in value:
            break

        decoded = unescape(value)

        if decoded == value:
            break

        value = decoded

    return html_to_text(value)


def normalize_greenhouse(item, board=None):
    location = object_value(item.get("location"))

    departments = item.get("departments")

    department = ""

    if isinstance(departments, list):
        department = ", ".join(
            clean_text(entry.get("name"), 160)
            for entry in departments
            if isinstance(entry, dict)
        )

    external_id = identifier(item.get("id"))

    url = safe_link(
        item.get("absolute_url"),
        "greenhouse",
        board,
        external_id,
    )

    return JobListing(
        external_id=external_id,
        title=clean_text(item.get("title"), 160),
        location=clean_text(location.get("name"), 500),
        department=clean_text(department, 300),
        description=greenhouse_description(item.get("content")),
        posting_url=url,
        apply_url=url,
        published_at=timestamp(
            item.get("first_published")
        ),
    )


def normalize_lever(item):
    categories = object_value(item.get("categories"))

    description = item.get("descriptionPlain")

    if not isinstance(description, str):
        description = html_to_text(
            item.get("description")
        )

    sections = [description]

    lists = item.get("lists")

    if isinstance(lists, list):
        for section in lists:
            if isinstance(section, dict):
                sections.append(
                    clean_text(section.get("text"), 500)
                )
                sections.append(
                    html_to_text(section.get("content"))
                )

    sections.append(
        clean_text(
            item.get("additionalPlain"),
            30000,
            multiline=True,
        )
        or html_to_text(item.get("additional"))
    )

    return JobListing(
        external_id=identifier(item.get("id")),
        title=clean_text(item.get("text"), 160),
        location=clean_text(
            categories.get("location"), 500,
        ),
        department=clean_text(
            categories.get("team")
            or categories.get("department"),
            300,
        ),
        employment_type=clean_text(
            categories.get("commitment"), 100,
        ),
        description=clean_text(
            "\n".join(sections),
            30000,
            multiline=True,
        ),
        work_mode=work_mode(
            item.get("workplaceType")
        ),
        posting_url=safe_link(
            item.get("hostedUrl"), "lever",
        ),
        apply_url=safe_link(
            item.get("applyUrl"), "lever",
        ),
        published_at=milliseconds(
            item.get("createdAt")
        ),
    )


def normalize_ashby(item):
    description = item.get("descriptionPlain")

    if not isinstance(description, str):
        description = html_to_text(
            item.get("descriptionHtml")
        )

    mode = work_mode(item.get("workplaceType"))

    url = safe_link(
        item.get("jobUrl"), "ashby",
    )

    # Ashby's public response may not expose a separate ID.
    # Use the final job URL path component in that case.
    external_id = item.get("id")

    if external_id is None and url:
        external_id = urlsplit(url).path.rstrip(
            "/"
        ).rsplit("/", 1)[-1]

    return JobListing(
        external_id=identifier(external_id),
        title=clean_text(item.get("title"), 160),
        location=clean_text(item.get("location"), 500),
        department=clean_text(
            item.get("department")
            or item.get("team"),
            300,
        ),
        description=clean_text(
            description, 30000,
            multiline=True,
        ),
        employment_type=clean_text(
            item.get("employmentType"), 100,
        ),
        work_mode=mode,
        posting_url=url,
        apply_url=safe_link(
            item.get("applyUrl"), "ashby",
        ),
        published_at=timestamp(
            item.get("publishedAt")
        ),
    )


def unique_object(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise SourceResponseRejected(
                "Duplicate JSON key"
            )

        result[key] = value

    return result


def reject_constant(value):
    raise SourceResponseRejected(
        "Invalid JSON constant"
    )


def normalize_response(source, raw):
    source = JobSourceInput.model_validate(
        source.model_dump()
    )

    if (
        not isinstance(raw, bytes)
        or not 1 <= len(raw) <= MAX_RESPONSE_BYTES
    ):
        raise SourceResponseRejected(
            "Invalid response size"
        )

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )

        if source.provider == "lever":
            rows = payload
            normalize = normalize_lever

        elif source.provider == "greenhouse":
            rows = object_value(payload).get("jobs")
            normalize = lambda item: normalize_greenhouse(item, source.board)

        else:
            rows = object_value(payload).get("jobs")
            normalize = normalize_ashby

        if not isinstance(rows, list):
            raise SourceResponseRejected(
                "Invalid provider response"
            )

        if source.provider == "greenhouse":
            meta = object_value(payload.get("meta"))

            if "meta" in payload:
                total = meta.get("total")

                if type(total) is not int or total != len(rows):
                    raise SourceResponseRejected(
                        "Incomplete Greenhouse snapshot"
                    )

        if len(rows) > MAX_LISTINGS_PER_SOURCE:
            raise BoardLimitExceeded(
                "Board exceeds listing limit"
            )

        listings = {}

        for item in rows:
            if not isinstance(item, dict):
                raise SourceResponseRejected(
                    "Invalid listing"
                )

            if (
                source.provider == "ashby"
                and item.get("isListed") is False
            ):
                continue

            listing = normalize(item)

            previous = listings.get(
                listing.external_id
            )

            if previous is not None and previous != listing:
                raise SourceResponseRejected(
                    "Conflicting duplicate listing"
                )

            listings[listing.external_id] = listing

        return list(listings.values())

    except BoardLimitExceeded:
        raise

    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ):
        raise SourceResponseRejected(
            "Provider response rejected"
        ) from None
