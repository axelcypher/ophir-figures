"""Filling in a figure from a product page: a shop, a manufacturer's page, a database entry.

Two ways in, one way out. Both turn the page into a *snapshot* -- its meta tags (OpenGraph and
the like), its JSON-LD blocks and the label/value pairs it shows (definition lists, two-column
table rows, MyFigureCollection's data fields) -- and extract() maps a snapshot onto figure fields:

- POST /api/figures/link-import {url}: the server fetches the page (fetch.py) and reads it.
- POST /api/figures/link-import {snapshot}: the browser read the page itself, through the
  bookmarklet (static/js/import.js). Many figure sites (MyFigureCollection, AmiAmi, Kotobukiya,
  HobbySearch) answer server requests with a bot check; the bookmarklet runs in the page the user
  has open in their own browser, so nothing is circumvented.

Nothing is saved here: the result fills the form, which the user checks and saves.
"""

import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from flask import jsonify, request

from .fetch import FetchError, fetch
from .figures import find_duplicate, normalize_date, split_list
from .line_presets import fill_from_preset
from .web import app, db, login_required

MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_SNAPSHOT_FIELDS = 200
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

# Product lines whose name settles the line (and often the category). Longest first wins.
LINES = (
    ("Nendoroid Doll", "Nendoroid", "Nendoroid"), ("Nendoroid", "Nendoroid", "Nendoroid"), ("figma", "figma", "figma"),
    ("POP UP PARADE L", "POP UP PARADE L", "Non-Scale-Figur"), ("POP UP PARADE", "POP UP PARADE", "Non-Scale-Figur"),
    ("ARTFX J", "ARTFX J", "Scale-Figur"), ("ARTFX", "ARTFX", "Scale-Figur"), ("BISHOUJO", "Bishoujo", "Scale-Figur"),
    ("S.H.Figuarts", "S.H.Figuarts", "Actionfigur"), ("Figuarts ZERO", "Figuarts ZERO", "Non-Scale-Figur"),
    ("Luminasta", "Luminasta", "Prize-Figur"), ("Noodle Stopper", "Noodle Stopper", "Prize-Figur"), ("Trio-Try-iT", "Trio-Try-iT", "Prize-Figur"),
    ("Q posket", "Q posket", "Prize-Figur"), ("Coreful", "Coreful", "Prize-Figur"), ("Desktop Cute", "Desktop Cute", "Prize-Figur"),
    ("BiCute Bunnies", "BiCute Bunnies", "Prize-Figur"), ("Aqua Float Girls", "Aqua Float Girls", "Prize-Figur"),
    ("GLITTER & GLAMOURS", "Glitter & Glamours", "Prize-Figur"), ("Relax time", "Relax time", "Prize-Figur"),
    ("Look Up", "Look Up", "Non-Scale-Figur"), ("G.E.M.", "G.E.M.", "Non-Scale-Figur"), ("Tenitol", "Tenitol", "Non-Scale-Figur"),
    ("Figure-rise Standard", "Figure-rise Standard", "Model Kit"), ("PLAMATEA", "PLAMATEA", "Model Kit"), ("PLAMAX", "PLAMAX", "Model Kit"),
    ("Shibuya Scramble Figure", "Shibuya Scramble Figure", "Scale-Figur"), ("F:NEX", "F:NEX", "Scale-Figur"),
    ("KDcolle", "KDcolle", "Scale-Figur"), ("eStream", "eStream", "Scale-Figur"), ("Hdge", "Hdge", "Non-Scale-Figur"),
)

# Label words (lower case, any language a figure page uses) -> field. A label matches when it
# equals one of these or starts with it.
LABELS = {
    "series": ("origin", "series", "serie", "franchise", "title", "work", "作品名", "作品", "シリーズ", "werk", "anime"),
    "characters": ("character", "characters", "charakter", "charaktere", "キャラクター"),
    "manufacturer": ("manufacturer", "hersteller", "company", "companies", "maker", "メーカー", "発売元", "製造元"),
    "brand": ("brand", "marke", "label", "ブランド"),
    "release_date": ("release date", "release", "releasedate", "erscheinungsdatum", "erscheinungstermin", "release-datum",
                     "veröffentlichung", "発売日", "発売時期", "発売予定", "launch date"),
    "price": ("price", "preis", "msrp", "retail price", "価格", "希望小売価格", "定価", "uvp"),
    "scale": ("scale", "maßstab", "massstab", "スケール", "scale & dimensions"),
    "dimensions": ("dimensions", "size", "height", "höhe", "größe", "abmessungen", "サイズ", "全高", "specifications", "仕様"),
    "sculptor": ("sculptor", "sculpting", "sculpted by", "bildhauer", "原型", "原型制作"),
    "material": ("material", "materials", "materialien", "素材", "材質"),
    "jan": ("jan", "jan code", "ean", "barcode", "gtin", "upc", "jancode", "janコード"),
    "category": ("category", "kategorie", "classification", "type", "product type", "カテゴリ", "種類"),
    "original_name": ("original name", "japanese name", "japanese title", "original title", "商品名"),
    "edition": ("edition", "version", "ausgabe"),
    "artist": ("artist", "artists", "painter", "paintwork", "illustrator", "彩色"),
}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent = tag, attrs, [], parent

    def elements(self):
        return [child for child in self.children if isinstance(child, Node)]

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def text(self):
        parts = []
        for child in self.children:
            if isinstance(child, Node):
                if child.tag in ("script", "style", "noscript", "template"):
                    continue
                if child.tag == "br":
                    parts.append(" ")
                parts.append(child.text())
            else:
                parts.append(child)
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def classes(self):
        return set((self.attrs.get("class") or "").split())


class TreeBuilder(HTMLParser):
    """A forgiving tree of the page: unclosed tags are closed by their parent's end tag."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {key: value or "" for key, value in attrs}, self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, {key: value or "" for key, value in attrs}, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def add_field(fields, label, value):
    label = re.sub(r"\s+", " ", str(label or "")).strip().rstrip(":：").strip()
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if label and value and len(label) <= 60 and label not in fields and len(fields) < MAX_SNAPSHOT_FIELDS:
        fields[label] = value[:500]


def snapshot_from_html(html, url):
    """The snapshot of a page from its HTML (what the bookmarklet gathers in the browser)."""
    builder = TreeBuilder()
    builder.feed(html)
    builder.close()
    root = builder.root
    meta, jsonld, fields = {}, [], {}
    title = heading = canonical = ""
    for node in root.walk():
        if node.tag == "meta":
            key = node.attrs.get("property") or node.attrs.get("name") or node.attrs.get("itemprop")
            if key and node.attrs.get("content") and key not in meta:
                meta[key] = unescape(node.attrs["content"]).strip()
        elif node.tag == "link" and "canonical" in (node.attrs.get("rel") or "").lower().split() and not canonical:
            canonical = urljoin(url, node.attrs.get("href") or "")
        elif node.tag == "title" and not title:
            title = node.text()
        elif node.tag == "h1" and not heading:
            heading = node.text()
        elif node.tag == "script" and "ld+json" in (node.attrs.get("type") or "").lower():
            raw = "".join(child for child in node.children if isinstance(child, str)).strip()
            try:
                jsonld.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    for node in root.walk():
        if "data-field" in node.classes():
            label = next((child for child in node.walk() if "data-label" in child.classes()), None)
            value = next((child for child in node.walk() if "data-value" in child.classes()), None)
            if label and value:
                add_field(fields, label.text(), value.text())
    for node in root.walk():
        if node.tag == "dt":
            siblings = node.parent.elements()
            index = siblings.index(node)
            if index + 1 < len(siblings) and siblings[index + 1].tag == "dd":
                add_field(fields, node.text(), siblings[index + 1].text())
        elif node.tag == "tr":
            cells = [child for child in node.elements() if child.tag in ("th", "td")]
            if len(cells) == 2:
                add_field(fields, cells[0].text(), cells[1].text())
    return {"url": url, "canonical": canonical, "title": title, "heading": heading, "meta": meta, "jsonld": jsonld, "fields": fields}


def walk_jsonld(value):
    if isinstance(value, list):
        for item in value:
            yield from walk_jsonld(item)
    elif isinstance(value, dict):
        yield value
        for key in ("@graph", "hasVariant", "mainEntity", "itemListElement", "item"):
            if key in value:
                yield from walk_jsonld(value[key])


def types_of(item):
    kind = item.get("@type")
    return {str(value).lower() for value in (kind if isinstance(kind, list) else [kind]) if value}


def first_product(jsonld):
    for item in walk_jsonld(jsonld):
        if types_of(item) & {"product", "productgroup", "individualproduct", "productmodel"}:
            return item
    return {}


def ld_text(value):
    if isinstance(value, dict):
        return ld_text(value.get("name") or value.get("@value") or value.get("url"))
    if isinstance(value, list):
        return ld_text(value[0]) if value else ""
    return unescape(str(value or "")).strip()


def ld_image(value):
    if isinstance(value, list):
        return next((image for image in (ld_image(item) for item in value) if image), "")
    if isinstance(value, dict):
        return ld_image(value.get("url") or value.get("contentUrl"))
    return str(value or "").strip()


def offer_of(product):
    offers = product.get("offers")
    for offer in walk_jsonld(offers) if offers else []:
        price = offer.get("price") or offer.get("lowPrice")
        if price is None and isinstance(offer.get("priceSpecification"), dict):
            price = offer["priceSpecification"].get("price")
        amount = parse_number(price)
        if amount is not None:
            currency = str(offer.get("priceCurrency") or (offer.get("priceSpecification") or {}).get("priceCurrency") or "").upper()
            return {"price": amount, "currency": currency}
    return None


def parse_number(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    match = re.search(r"\d[\d.,\s]*", text)
    if not match:
        return None
    number = match.group(0).strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", number):           # 14,800 / 14.800
        number = re.sub(r"[.,]", "", number)
    elif "," in number and "." in number:                       # 1.299,00 / 1,299.00
        number = number.replace(".", "").replace(",", ".") if number.rfind(",") > number.rfind(".") else number.replace(",", "")
    else:
        number = number.replace(",", ".")
    try:
        return round(float(number), 2)
    except ValueError:
        return None


CURRENCY_HINTS = (("¥", "JPY"), ("円", "JPY"), ("yen", "JPY"), ("jpy", "JPY"), ("€", "EUR"), ("eur", "EUR"), ("$", "USD"), ("usd", "USD"),
                  ("£", "GBP"), ("gbp", "GBP"), ("cny", "CNY"), ("rmb", "CNY"), ("hk$", "HKD"))


def price_from_text(text):
    amount = parse_number(text)
    if amount is None:
        return None
    lowered = text.lower()
    currency = next((code for hint, code in sorted(CURRENCY_HINTS, key=lambda pair: -len(pair[0])) if hint in lowered), "")
    return {"price": amount, "currency": currency}


def labelled(fields, key):
    """The value of the first field whose label is one of LABELS[key] (or starts with one)."""
    words = LABELS[key]
    for label, value in fields.items():
        lowered = label.lower()
        if lowered in words:
            return value
    for label, value in fields.items():
        lowered = label.lower()
        if any(lowered.startswith(word) for word in words if len(word) > 3):
            return value
    return ""


def strip_roles(value, prefer=None):
    """'Good Smile Company (As Manufacturer), Max Factory (As Distributor)' -> the company in the
    preferred role, or the first one; role notes in brackets removed."""
    parts = [part.strip() for part in re.split(r"\s*[,、/]\s*(?![^()]*\))", value) if part.strip()]
    if prefer:
        preferred = [part for part in parts if prefer.lower() in part.lower()]
        parts = preferred or parts
    return [re.sub(r"\s*[(（][^)）]*[)）]\s*", " ", part).strip() for part in parts]


def first_date(text):
    for pattern in (r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", r"\d{1,2}[./]\d{1,2}[./]\d{4}", r"\d{4}年\d{1,2}月(?:\d{1,2}日)?",
                    r"\d{4}[-/.]\d{1,2}", r"\d{1,2}[/.]\d{4}", r"[A-Za-zäÄ]+\.?\s+\d{4}", r"\b\d{4}\b"):
        for match in re.finditer(pattern, text or ""):
            value, error = normalize_date(match.group(0))
            if value and not error:
                return value
    return ""


def clean_title(title, site_name):
    title = re.sub(r"\s+", " ", title or "").strip()
    if site_name and site_name.lower() in title.lower():
        parts = [part.strip() for part in re.split(r"\s+[|–—-]\s+|\s*\|\s*", title) if part.strip()]
        parts = [part for part in parts if site_name.lower() not in part.lower()]
        title = " - ".join(parts) or title
    return re.sub(r"^(?:Buy|Pre-?order|Vorbestellung|Kaufen)\s*:?\s+", "", title, flags=re.I).strip()


def detect_line(text):
    lowered = (text or "").lower()
    for needle, line, category in sorted(LINES, key=lambda entry: -len(entry[0])):
        if needle.lower() in lowered:
            return line, category
    return "", ""


def extract(snapshot):
    """Figure fields (as the form takes them) from a snapshot, plus what the page offers it for and
    notes on what could not be read. Returns {"fields", "offer", "warnings", "unmapped", "guessed"};
    guessed names the fields that were only inferred (the manufacturer from the brand, the category
    from the line or the scale), which a line preset may overrule."""
    meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else {}
    page_fields = snapshot.get("fields") if isinstance(snapshot.get("fields"), dict) else {}
    page_fields = {str(key): str(value) for key, value in list(page_fields.items())[:MAX_SNAPSHOT_FIELDS]}
    product = first_product(snapshot.get("jsonld") or [])
    url = str(snapshot.get("url") or "")
    site_name = meta.get("og:site_name", "")
    fields, warnings, guessed = {}, [], []

    name = ld_text(product.get("name")) or meta.get("og:title") or snapshot.get("heading") or snapshot.get("title") or ""
    fields["name"] = clean_title(name, site_name)[:300]
    image = ld_image(product.get("image")) or meta.get("og:image") or meta.get("og:image:secure_url") or meta.get("twitter:image") or ""
    fields["image_url"] = urljoin(url, image) if image else ""
    description = ld_text(product.get("description")) or meta.get("og:description") or meta.get("description") or ""
    fields["description"] = re.sub(r"\s+", " ", description).strip()[:1500]
    canonical = str(snapshot.get("canonical") or meta.get("og:url") or url)
    fields["source_url"] = canonical if canonical.startswith("http") else url

    brand = labelled(page_fields, "brand")
    fields["brand"] = (strip_roles(brand) or [""])[0] if brand else (ld_text(product.get("brand")) or meta.get("product:brand", ""))
    manufacturer = labelled(page_fields, "manufacturer")
    fields["manufacturer"] = (strip_roles(manufacturer, "manufacturer") or [""])[0] if manufacturer else ld_text(product.get("manufacturer"))
    if not fields["manufacturer"] and fields["brand"]:
        # Shops name the maker as the product's brand more often than not.
        fields["manufacturer"] = fields["brand"]
        guessed.append("manufacturer")
    series = labelled(page_fields, "series")
    fields["series"] = ", ".join(strip_roles(series)) if series else ""
    characters = labelled(page_fields, "characters")
    fields["characters"] = ", ".join(split_list(", ".join(strip_roles(characters)))) if characters else ""
    sculptor = labelled(page_fields, "sculptor")
    if not sculptor:
        artists = labelled(page_fields, "artist")
        sculptor = ", ".join(part for part in strip_roles(artists, "sculptor") if artists and "sculptor" in artists.lower())
    else:
        sculptor = ", ".join(strip_roles(sculptor))
    fields["sculptor"] = sculptor
    fields["material"] = labelled(page_fields, "material")[:300]
    fields["original_name"] = labelled(page_fields, "original_name")[:300]
    fields["edition"] = labelled(page_fields, "edition")[:300]

    release = labelled(page_fields, "release_date")
    fields["release_date"] = first_date(release) if release else first_date(ld_text(product.get("releaseDate")))

    scale_text = " ".join(filter(None, (labelled(page_fields, "scale"), labelled(page_fields, "dimensions"), fields["name"])))
    # Digits around, not \b: in "1/7スケール" the katakana count as word characters.
    scale = re.search(r"(?<!\d)1\s*/\s*(\d{1,2})(?!\d)", scale_text)
    fields["scale"] = f"1/{scale.group(1)}" if scale else ("Non-Scale" if re.search(r"non[- ]?scale|ノンスケール", scale_text, re.I) else "")
    dimension_text = " ".join(filter(None, (labelled(page_fields, "dimensions"), labelled(page_fields, "scale"), fields["description"])))
    height = (re.search(r"H\s*[=:]?\s*(\d{2,4})\s*mm", dimension_text, re.I) or re.search(r"(?:height|höhe|全高|高さ)[^\d]{0,20}(\d{2,4})\s*mm", dimension_text, re.I)
              or re.search(r"(?:approx\.?|ca\.?|約)\s*(\d{2,4})\s*mm", dimension_text, re.I))
    if not height:
        cm = re.search(r"(?:H\s*[=:]?|height|höhe|approx\.?|ca\.?|約)\s*(\d{1,3}(?:[.,]\d)?)\s*cm", dimension_text, re.I)
        fields["height_mm"] = str(round(float(cm.group(1).replace(",", ".")) * 10)) if cm else ""
    else:
        fields["height_mm"] = height.group(1)

    jan = labelled(page_fields, "jan")
    gtin = next((ld_text(product.get(key)) for key in ("gtin13", "gtin", "gtin12", "gtin14", "gtin8", "ean") if product.get(key)), "")
    digits = re.sub(r"\D", "", jan or gtin or "")
    if not digits and re.fullmatch(r"\d{13}", str(product.get("sku") or "")):
        digits = str(product.get("sku"))
    fields["jan"] = digits if 8 <= len(digits) <= 14 else ""

    line, category = detect_line(f"{fields['name']} {labelled(page_fields, 'category')}")
    fields["line"] = line
    if category:
        guessed.append("category")   # the usual category of a known line (LINES)
    else:
        page_category = labelled(page_fields, "category").lower()
        if "prize" in page_category or "プライズ" in page_category:
            category = "Prize-Figur"
        elif "garage" in page_category:
            category = "Garage Kit"
        elif "model kit" in page_category or "plastic model" in page_category:
            category = "Model Kit"
        elif "plush" in page_category or "ぬいぐるみ" in page_category:
            category = "Plüsch"
        elif "action" in page_category:
            category = "Actionfigur"
        elif fields["scale"].startswith("1/"):
            category = "Scale-Figur"
            guessed.append("category")
        elif fields["scale"] == "Non-Scale":
            category = "Non-Scale-Figur"
            guessed.append("category")
    fields["category"] = category

    price_text = labelled(page_fields, "price")
    offer = offer_of(product)
    if not offer and (meta.get("og:price:amount") or meta.get("product:price:amount")):
        amount = parse_number(meta.get("product:price:amount") or meta.get("og:price:amount"))
        if amount is not None:
            offer = {"price": amount, "currency": (meta.get("product:price:currency") or meta.get("og:price:currency") or "").upper()}
    listed = price_from_text(price_text) if price_text else None
    retail = listed or offer
    if retail and retail["price"]:
        fields["msrp"] = retail["price"]
        fields["msrp_currency"] = retail["currency"] or "JPY"

    mapped_labels = {label for label in page_fields if any(
        label.lower() in words or any(label.lower().startswith(word) for word in words if len(word) > 3) for words in LABELS.values())}
    unmapped = {label: value for label, value in page_fields.items() if label not in mapped_labels}
    if not fields["name"]:
        warnings.append("Auf der Seite war kein Produktname zu finden.")
    if not fields["image_url"]:
        warnings.append("Kein Bild gefunden – du kannst eins hochladen.")
    if not any(fields.get(key) for key in ("manufacturer", "series", "release_date", "jan")):
        warnings.append("Hersteller, Franchise und Erscheinungsdatum standen nicht maschinenlesbar auf der Seite – bitte ergänzen.")
    return {"fields": {key: value for key, value in fields.items() if value not in ("", None)}, "offer": offer, "warnings": warnings,
            "unmapped": dict(list(unmapped.items())[:30]), "guessed": guessed}


def sanitize_snapshot(raw):
    """A snapshot from the browser, cut down to the shape and size extract() expects."""
    if not isinstance(raw, dict):
        return None
    jsonld = raw.get("jsonld") if isinstance(raw.get("jsonld"), list) else []
    return {
        "url": str(raw.get("url") or "")[:2000], "canonical": str(raw.get("canonical") or "")[:2000],
        "title": str(raw.get("title") or "")[:500], "heading": str(raw.get("heading") or "")[:500],
        "meta": {str(k)[:100]: str(v)[:2000] for k, v in list((raw.get("meta") or {}).items())[:300]} if isinstance(raw.get("meta"), dict) else {},
        "jsonld": jsonld[:30],
        "fields": {str(k)[:60]: str(v)[:500] for k, v in list((raw.get("fields") or {}).items())[:MAX_SNAPSHOT_FIELDS]} if isinstance(raw.get("fields"), dict) else {},
    }


@app.post("/api/figures/link-import")
@login_required
def link_import():
    payload = request.get_json(force=True) or {}
    if payload.get("snapshot") is not None:
        snapshot = sanitize_snapshot(payload["snapshot"])
        if not snapshot:
            return jsonify({"error": "Die übermittelten Seitendaten sind unvollständig."}), 400
    else:
        url = str(payload.get("url") or "").strip()
        if not url:
            return jsonify({"error": "Bitte einen Link einfügen."}), 400
        try:
            final_url, content_type, body = fetch(url, MAX_PAGE_BYTES, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.5")
        except FetchError as error:
            return jsonify({"error": str(error), "blocked": error.blocked}), 422
        if content_type and "html" not in content_type and "xml" not in content_type:
            return jsonify({"error": "Der Link führt nicht zu einer Webseite."}), 422
        charset = re.search(rb'charset=["\']?([\w-]+)', body[:4096])
        try:
            html = body.decode(charset.group(1).decode() if charset else "utf-8", errors="replace")
        except LookupError:
            html = body.decode("utf-8", errors="replace")
        snapshot = snapshot_from_html(html, final_url)
    result = extract(snapshot)
    # The line's preset fills what the page did not say, and what was only guessed.
    result["preset"] = fill_from_preset(db(), result["fields"], result.pop("guessed"))
    duplicate = find_duplicate(db(), result["fields"]) if result["fields"].get("name") else None
    result["duplicate"] = {"id": duplicate[0], "name": duplicate[1], "reason": duplicate[2]} if duplicate else None
    return jsonify(result)
