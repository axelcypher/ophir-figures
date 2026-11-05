"""Fetching what a user pasted a link to: a product page (link_import.py) or a picture (images.py).

The server makes these requests on a user's behalf, so they are kept to the public internet:
only http(s), only hosts that resolve to public addresses (no loopback, private network,
link-local or the like -- the app must not become a way to look into the network it runs in),
every redirect checked the same way, a size limit and a timeout.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "Mozilla/5.0 (compatible; OphirFigures/1.0; +https://github.com/axelcypher/ophir-figures)"
TIMEOUT_SECONDS = 15
MAX_REDIRECTS = 5


class FetchError(Exception):
    """A fetch that did not bring a usable answer; the message is shown to the user (German).
    `blocked`: the site refused an automatic request (bot protection, throttling), so reading the
    page in the user's own browser (the bookmarklet) is the way to go."""

    def __init__(self, message, blocked=False):
        super().__init__(message)
        self.blocked = blocked


def public_address(host):
    """Whether every address the host resolves to is a public one."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise FetchError("Die Adresse ist nicht erreichbar (Name unbekannt).")
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global or address.is_multicast:
            return False
    return bool(infos)


def check_url(url):
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FetchError("Nur http- und https-Links können abgerufen werden.")
    if not public_address(parsed.hostname):
        raise FetchError("Adressen im lokalen Netz werden nicht abgerufen.")
    return parsed.geturl()


def fetch(url, max_bytes, accept="*/*", session=None):
    """(final url, content type, body bytes). Raises FetchError."""
    http = session or requests
    current = check_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = http.get(current, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "de,en;q=0.8,ja;q=0.6"},
                                timeout=TIMEOUT_SECONDS, allow_redirects=False, stream=True)
        except requests.RequestException as error:
            raise FetchError(f"Die Seite antwortet nicht ({type(error).__name__}).")
        try:
            if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise FetchError("Die Seite leitet ins Leere weiter.")
                current = check_url(urljoin(current, location))
                continue
            if response.status_code == 429:
                raise FetchError("Die Seite bremst automatische Abrufe gerade aus (429). Versuch es später noch einmal, "
                                 "oder öffne sie im Browser und nutze das Lesezeichen „Zu Ophir Figures“.", blocked=True)
            if response.status_code in (401, 403, 503):
                raise FetchError("Die Seite lässt keinen automatischen Abruf zu (Schutz vor Bots). "
                                 "Öffne sie im Browser und nutze das Lesezeichen „Zu Ophir Figures“ oder trage die Daten von Hand ein.", blocked=True)
            if response.status_code >= 400:
                raise FetchError(f"Die Seite antwortet mit Fehler {response.status_code}.")
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise FetchError("Die Antwort ist zu groß.")
            return current, (response.headers.get("Content-Type") or "").split(";")[0].strip().lower(), bytes(body)
        finally:
            response.close()
    raise FetchError("Zu viele Weiterleitungen.")
