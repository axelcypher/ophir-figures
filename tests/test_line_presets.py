"""Line presets: what a product line fixes, kept once per line and filled into a figure's fields --
managed through the API, applied to the catalogue's figures of the line, and used by the link
import. (Migration 0005 adds the table.)"""
import pytest

from conftest import ADMIN, FRIEREN, REM, login, query

FIGMA = {"line": "figma", "manufacturer": "Max Factory", "brand": "Good Smile Company", "category": "figma", "scale": "Non-Scale", "material": "PVC, ABS"}


def presets(client):
    return client.get("/api/line-presets").get_json()


def test_a_preset_is_kept_once_per_line_and_listed_with_its_figures(client):
    response = client.post("/api/line-presets", json={**FIGMA, "line": "  figma ", "material": " PVC,   ABS "})
    assert response.status_code == 201, response.get_json()
    preset = response.get_json()
    assert {key: preset[key] for key in FIGMA} == FIGMA, "spacing is tidied"
    assert (preset["figures"], preset["incomplete"]) == (1, 1), "Rem is the catalogue's figma figure, without brand and material"
    assert preset["created_by_name"] == "Alex Morgan" and preset["can_delete"] is True

    data = presets(client)
    assert [item["line"] for item in data["presets"]] == ["figma"]
    assert data["fields"] == ["manufacturer", "brand", "category", "scale", "material"]
    lines = {item["line"]: item for item in data["lines"]}
    assert set(lines) == {"Nendoroid", "POP UP PARADE"}, "lines without a preset, figma has one"
    assert lines["Nendoroid"]["figures"] == 1
    assert lines["Nendoroid"]["common"] == {"manufacturer": "Good Smile Company", "brand": "", "category": "Nendoroid", "scale": "Non-Scale", "material": ""}


@pytest.mark.parametrize("payload, status, message", [
    ({"manufacturer": "Max Factory"}, 400, "Die Linie fehlt."),
    ({"line": "   ", "manufacturer": "Max Factory"}, 400, "Die Linie fehlt."),
    ({"line": "figma"}, 400, "legt noch nichts fest"),
    ({"line": "figma", "brand": "x" * 301}, 400, "zu lang"),
    ({"line": "FIGMA", "scale": "1/12"}, 409, "gibt es schon eine Vorlage"),   # case aside, one preset per line
])
def test_a_preset_needs_a_new_line_and_something_it_fixes(client, payload, status, message):
    first = client.post("/api/line-presets", json=FIGMA).get_json()
    response = client.post("/api/line-presets", json=payload)
    assert response.status_code == status
    assert message in response.get_json()["error"]
    if status == 409:
        assert response.get_json()["preset_id"] == first["id"]


def test_a_preset_is_corrected_by_anyone_but_deleted_by_its_maker_or_an_admin(client, admin):
    preset_id = client.post("/api/line-presets", json=FIGMA).get_json()["id"]
    nendoroid = admin.post("/api/line-presets", json={"line": "Nendoroid", "manufacturer": "Good Smile Company"}).get_json()

    changed = admin.patch(f"/api/line-presets/{preset_id}", json={"brand": "", "scale": "Non-Scale "}).get_json()
    assert (changed["brand"], changed["scale"], changed["manufacturer"]) == ("", "Non-Scale", "Max Factory")
    assert admin.patch(f"/api/line-presets/{preset_id}", json={"line": "nendoroid"}).status_code == 409
    assert client.patch(f"/api/line-presets/{preset_id}", json={key: "" for key in ("manufacturer", "category", "scale", "material")}).status_code == 400
    assert client.patch(f"/api/line-presets/{preset_id}", json={}).status_code == 400
    assert client.patch("/api/line-presets/999", json={"brand": "x"}).status_code == 404

    assert client.delete(f"/api/line-presets/{nendoroid['id']}").status_code == 403
    assert [item["can_delete"] for item in presets(client)["presets"]] == [True, False]
    assert admin.delete(f"/api/line-presets/{preset_id}").status_code == 200, "an admin deletes anyone's preset"
    assert admin.delete(f"/api/line-presets/{nendoroid['id']}").status_code == 200
    assert client.delete(f"/api/line-presets/{preset_id}").status_code == 404
    assert presets(client)["presets"] == []


def test_a_preset_outlives_the_account_that_made_it(client):
    other = login(ADMIN)
    other.post("/api/admin/users", json={"username": "gone", "display_name": "Gone", "password": "lang-genug-1"})
    gone = login(("gone", "lang-genug-1"))
    gone.post("/api/line-presets", json=FIGMA)
    other.delete(f"/api/admin/users/{query('SELECT id FROM users WHERE username=?', ('gone',))[0]['id']}")
    [preset] = presets(client)["presets"]
    assert (preset["line"], preset["created_by_name"], preset["can_delete"]) == ("figma", "", False)


def test_applying_a_preset_fills_only_empty_fields_of_its_line(client):
    query("INSERT INTO figures(id,name,line,manufacturer,category,scale,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
          (10, "figma Saber", "FIGMA", "Good Smile Company", "", "", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
    preset_id = client.post("/api/line-presets", json=FIGMA).get_json()["id"]
    assert client.get("/api/line-presets").get_json()["presets"][0]["incomplete"] == 2
    answer = client.post(f"/api/line-presets/{preset_id}/apply").get_json()
    assert answer == {"updated": 2, "filled": {"brand": 2, "material": 2, "category": 1, "scale": 1}}
    rows = {row["id"]: row for row in query("SELECT id,manufacturer,brand,category,scale,material FROM figures WHERE id IN (?,?,?)", (REM, 10, FRIEREN))}
    assert rows[10] == {"id": 10, "manufacturer": "Good Smile Company", "brand": "Good Smile Company", "category": "figma", "scale": "Non-Scale", "material": "PVC, ABS"}, \
        "a value it has stays: the manufacturer is not overwritten"
    assert rows[REM]["brand"] == "Good Smile Company" and rows[REM]["manufacturer"] == "Max Factory"
    assert rows[FRIEREN]["brand"] == "", "another line stays as it is"
    assert client.post(f"/api/line-presets/{preset_id}/apply").get_json() == {"updated": 0, "filled": {}}
    assert client.post("/api/line-presets/999/apply").status_code == 404


NENDOROID_PAGE = """<html><head><title>Nendoroid Frieren (Summer)</title>
<script type="application/ld+json">{"@type":"Product","name":"Nendoroid Frieren: Summer Ver.","brand":{"name":"Good Smile Company"}}</script>
</head><body><table><tr><th>Scale</th><td>Non-scale, approx. 100mm</td></tr></table></body></html>"""
POP_UP_PAGE = """<html><head><title>POP UP PARADE Mikasa</title></head><body><table>
<tr><th>Manufacturer</th><td>Max Factory</td></tr><tr><th>Material</th><td>PVC</td></tr></table></body></html>"""


def test_the_link_import_fills_in_from_the_lines_preset(client, fake_fetch):
    client.post("/api/line-presets", json={"line": "nendoroid", "manufacturer": "Good Smile Arts Shanghai", "brand": "Good Smile Company",
                                            "category": "Nendoroid (Deformed)", "material": "ABS, PVC"})
    client.post("/api/line-presets", json={"line": "POP UP PARADE", "manufacturer": "Good Smile Company", "material": "PVC, ABS", "scale": "Non-Scale"})
    fake_fetch.pages["https://shop.example/nendoroid"] = ("text/html", NENDOROID_PAGE.encode())
    fake_fetch.pages["https://shop.example/popup"] = ("text/html", POP_UP_PAGE.encode())

    result = client.post("/api/figures/link-import", json={"url": "https://shop.example/nendoroid"}).get_json()
    fields = result["fields"]
    assert fields["line"] == "Nendoroid"
    assert (fields["manufacturer"], fields["brand"]) == ("Good Smile Arts Shanghai", "Good Smile Company"), \
        "the manufacturer was only guessed from the brand: the preset knows better; the brand was on the page"
    assert fields["category"] == "Nendoroid (Deformed)", "a line's usual category is a guess too"
    assert (fields["scale"], fields["material"]) == ("Non-Scale", "ABS, PVC")
    assert result["preset"]["line"] == "nendoroid" and result["preset"]["applied"] == ["manufacturer", "category", "material"]

    result = client.post("/api/figures/link-import", json={"url": "https://shop.example/popup"}).get_json()
    assert (result["fields"]["manufacturer"], result["fields"]["material"], result["fields"]["scale"]) == ("Max Factory", "PVC", "Non-Scale"), \
        "what the page says wins; the preset fills the rest"
    assert result["preset"]["applied"] == ["scale"]


def test_the_link_import_without_a_preset_says_so(client, fake_fetch):
    fake_fetch.pages["https://shop.example/popup"] = ("text/html", POP_UP_PAGE.encode())
    result = client.post("/api/figures/link-import", json={"url": "https://shop.example/popup"}).get_json()
    assert result["preset"] is None and "guessed" not in result
    assert result["fields"]["line"] == "POP UP PARADE" and "scale" not in result["fields"]
