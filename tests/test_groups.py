"""Figures in groups side by side -- by franchise, brand, manufacturer or line -- in the catalogue,
the collection and a wishlist (?group=<kind>), with the grid's filters applied first."""
import pytest

from conftest import FRIEREN, MIKASA, MIKU, REM, TWINS, default_list, query


def groups(client, url="/api/figures", **args):
    answer = client.get(url, query_string=args).get_json()
    assert "figures" not in answer, "a grouped answer has groups instead of figures"
    return answer


def by_name(answer):
    return {group["name"]: group for group in answer["groups"]}


def test_the_catalogue_groups_by_franchise(client):
    client.post("/api/collection", json={"figure_id": REM, "quantity": 2})
    client.post("/api/preorders", json={"figure_id": TWINS})
    query("INSERT INTO price_observations(figure_id,amount,observed_at) VALUES(?,?,?),(?,?,?)",
          (REM, 40, "2026-01-01T00:00:00+00:00", TWINS, 250.5, "2026-01-01T00:00:00+00:00"))
    answer = groups(client, group="series")
    assert answer["group"] == "series" and answer["total"] == answer["shown"] == 5
    assert [group["name"] for group in answer["groups"]] == ["Attack on Titan", "Frieren: Beyond Journey's End", "Re:Zero", "Vocaloid"]
    rezero = by_name(answer)["Re:Zero"]
    assert {key: rezero[key] for key in ("count", "owned", "copies", "preordered", "wished", "value", "latest_release")} == {
        "count": 2, "owned": 1, "copies": 2, "preordered": 1, "wished": 0, "value": 290.5, "latest_release": "2026-12"}
    assert [sample["id"] for sample in rezero["samples"]] == [TWINS, REM], "in the grid's order: newest release first"
    assert set(rezero["samples"][0]) == {"id", "name", "has_image", "image_version"}
    assert "Re:Zero" in [value for value, _ in answer["facets"]["series"]], "the filter bar keeps its facets"


def test_figures_without_a_value_form_the_last_group(client):
    answer = groups(client, group="line")
    assert [(group["name"], group["count"]) for group in answer["groups"]] == [("figma", 1), ("Nendoroid", 1), ("POP UP PARADE", 1), ("", 2)]
    assert [(group["name"], group["count"]) for group in groups(client, group="brand")["groups"]] == [("", 5)], "no sample figure has a brand"


@pytest.mark.parametrize("sort, expected", [
    ("name", ["Good Smile Company", "Kadokawa", "Max Factory"]),
    ("count", ["Good Smile Company", "Kadokawa", "Max Factory"]),
    ("owned", ["Max Factory", "Good Smile Company", "Kadokawa"]),        # share of the group in the collection
    ("value", ["Kadokawa", "Good Smile Company", "Max Factory"]),
    ("release", ["Kadokawa", "Good Smile Company", "Max Factory"]),      # latest release first
    ("nonsense", ["Good Smile Company", "Kadokawa", "Max Factory"]),
])
def test_groups_sort_by_name_size_share_value_or_release(client, sort, expected):
    client.post("/api/collection", json={"figure_id": REM})
    client.post("/api/collection", json={"figure_id": MIKU})
    query("INSERT INTO price_observations(figure_id,amount,observed_at) VALUES(?,?,?),(?,?,?)",
          (TWINS, 300, "2026-01-01T00:00:00+00:00", MIKU, 200, "2026-01-01T00:00:00+00:00"))
    assert [group["name"] for group in groups(client, group="manufacturer", group_sort=sort)["groups"]] == expected


def test_the_grid_filters_apply_before_grouping(client):
    answer = groups(client, group="manufacturer", q="Rem")
    assert [(group["name"], group["count"]) for group in answer["groups"]] == [("Kadokawa", 1), ("Max Factory", 1)]
    assert answer["shown"] == 2 and answer["total"] == 5
    answer = groups(client, group="series", mode="owned")
    assert answer["groups"] == []


def test_samples_prefer_figures_with_a_picture(client):
    query("UPDATE figures SET image_key='abc.png' WHERE id=?", (MIKASA,))
    samples = by_name(groups(client, group="manufacturer"))["Good Smile Company"]["samples"]
    assert [sample["id"] for sample in samples] == [MIKASA, MIKU, FRIEREN]
    assert samples[0]["has_image"] is True and samples[0]["image_version"] == "abc.png"


def test_the_collection_groups_with_what_the_copies_cost_and_are_worth(client):
    client.post("/api/collection", json={"figure_id": MIKU, "quantity": 2, "purchase_price": "150"})
    client.post("/api/collection", json={"figure_id": FRIEREN, "purchase_price": "45"})
    client.post("/api/collection", json={"figure_id": REM})
    answer = groups(client, "/api/collection", group="manufacturer", group_sort="value")
    assert [(group["name"], group["count"], group["copies"], group["value"], group["spent"]) for group in answer["groups"]] == [
        ("Good Smile Company", 2, 3, 345.0, 345.0), ("Max Factory", 1, 1, 0.0, 0.0)]
    assert answer["stats"]["figures"] == 3, "the totals stay"


def test_a_wishlist_groups_and_counts_reached_targets(client):
    list_id = default_list(client)
    for figure_id in (REM, TWINS, MIKU):
        client.post(f"/api/watchlists/{list_id}/figures", json={"figure_id": figure_id, "target_price": "100"})
    query("INSERT INTO price_observations(figure_id,amount,observed_at) VALUES(?,?,?)", (REM, 80, "2026-01-01T00:00:00+00:00"))
    answer = groups(client, f"/api/watchlists/{list_id}/figures", group="series")
    assert [(group["name"], group["count"], group["target_reached"]) for group in answer["groups"]] == [("Re:Zero", 2, 1), ("Vocaloid", 1, 0)]
    assert answer["stats"]["count"] == 3 and answer["list"]["id"] == list_id


def test_an_unknown_kind_answers_with_figures(client):
    assert len(client.get("/api/figures", query_string={"group": "price"}).get_json()["figures"]) == 5
