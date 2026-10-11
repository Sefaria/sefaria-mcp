"""_optimize_topics_response keeps refs/links in the shape the topics API returns."""
from sefaria_mcp.logic import _optimize_topics_response


def _ref(i):
    return {"ref": f"Genesis 1:{i}", "is_sheet": False}


def test_grouped_refs_are_kept_and_limited():
    data = {
        "slug": "justice",
        "refs": {
            "about": {"refs": [_ref(i) for i in range(1, 26)], "title": {"en": "About"}, "shouldDisplay": True},
            "mention": {"refs": [_ref(i) for i in range(1, 4)], "title": {"en": "Mention"}, "shouldDisplay": True},
        },
    }
    out = _optimize_topics_response(data)
    about = out["refs"]["about"]
    assert len(about["refs"]) == 10
    assert about["refs"][0]["ref"] == "Genesis 1:1"
    assert about["total"] == 25
    assert about["title"] == {"en": "About"}
    assert "note" in about
    mention = out["refs"]["mention"]
    assert len(mention["refs"]) == 3
    assert mention["total"] == 3
    assert "note" not in mention


def test_grouped_links_are_kept_and_limited():
    links = [{"topic": f"t{i}", "isInverse": False} for i in range(15)]
    data = {"slug": "justice", "links": {"related-to": {"links": links, "title": {"en": "Related"}, "shouldDisplay": True}}}
    out = _optimize_topics_response(data)
    assert len(out["links"]["related-to"]["links"]) == 10
    assert out["links"]["related-to"]["total"] == 15


def test_flat_list_refs_still_supported():
    data = {"slug": "x", "refs": [_ref(i) for i in range(1, 13)]}
    out = _optimize_topics_response(data)
    assert len(out["refs"]) == 10
    assert out["refs_note"] == "Showing first 10 of 12 total refs"


def test_no_refs_when_not_requested():
    out = _optimize_topics_response({"slug": "x", "description": {"en": "d"}})
    assert "refs" not in out and "links" not in out


def test_refs_are_slimmed_to_essential_fields():
    ref = {"ref": "Leviticus 19:36", "is_sheet": False, "descriptions": {"en": {"title": "T", "prompt": "P"}},
           "similarRefs": [{"ref": "x"}] * 50, "order": {"pr": 1.0}, "expandedRefs": ["Leviticus 19:36"]}
    out = _optimize_topics_response({"refs": {"about": {"refs": [ref], "title": {"en": "About"}}}})
    assert out["refs"]["about"]["refs"] == [{"ref": "Leviticus 19:36", "is_sheet": False,
                                              "descriptions": {"en": {"title": "T", "prompt": "P"}}}]
