from __future__ import annotations

import pytest

from director.recipes import merge_intervals, parse_duration, run_recipe, slugify


def test_slugify_unicode_and_truncation():
    assert slugify("Hello World") == "hello-world"
    assert slugify("  A  B  ") == "a-b"
    assert slugify("Café déjà vu") == "cafe-deja-vu"
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("Straße") == "strasse"
    assert slugify("Über") == "uber"
    assert slugify("Æther") == "aether"
    assert slugify("Øresund") == "oresund"
    assert slugify("Łódź") == "lodz"
    assert slugify("Þingvellir") == "thingvellir"
    assert slugify("Hello_World") == "hello-world"
    assert slugify("") == ""
    assert slugify("---") == ""
    assert slugify("A" * 100, max_length=10) == "a" * 10
    assert slugify("Hello World", max_length=8) == "hello"
    assert slugify("Hello", max_length=0) == ""


def test_parse_duration_units_and_rejections():
    assert parse_duration("1h30m") == 5400
    assert parse_duration("45s") == 45
    assert parse_duration("90m") == 5400
    assert parse_duration("1h 5m 10s") == 3910
    assert parse_duration("1d2h") == 93600
    assert parse_duration("10") == 10
    assert parse_duration(" 1H 30M ") == 5400
    for bad in ("", "1x", "1h1h", "1m1h", "-1h"):
        with pytest.raises(ValueError):
            parse_duration(bad)


def test_merge_intervals():
    assert merge_intervals([(1, 3), (2, 6), (8, 10), (15, 18)]) == [(1, 6), (8, 10), (15, 18)]
    assert merge_intervals([(1, 4), (4, 5)]) == [(1, 5)]
    assert merge_intervals([(5, 6), (1, 2)]) == [(1, 2), (5, 6)]
    assert merge_intervals([]) == []
    assert merge_intervals([(1, 1)]) == [(1, 1)]
    assert merge_intervals([(1, 5), (2, 3)]) == [(1, 5)]
    with pytest.raises(ValueError):
        merge_intervals([(5, 1)])


def test_run_recipe_dispatch():
    assert run_recipe("slugify", ["Café"]) == "cafe"
    assert run_recipe("parse_duration", ["2h"]) == 7200
    assert run_recipe("merge_intervals", [[(1, 2), (2, 3)]]) == [(1, 3)]
