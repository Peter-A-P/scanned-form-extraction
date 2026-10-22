"""The verifier's rules per corpus: what each form defines, kept only where the truth obeys it.

A rule the corpus's own answers break would flag right fields, so every rule here was checked
against the training split's truth (`legible verify hold`, docs/verify-rules.md) and is kept only if
the truth satisfies it on at least 99% of the documents where it applies. The rules come from
the forms, not from the arms' reads: the 1988 Form 1040 and its schedules say which lines are
sums, a receipt says its items add up, a date field holds a date.

NIST's line numbers are the 1988 forms' own (`legible/schema/nist_fields.json`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from legible.verify import DateRule, PatternRule, Rule, SumRule


def _sum(face: str, name: str, total: str, parts: Sequence[str]) -> SumRule:
    p = f"f_{face}_"
    # The forms are filled in whole dollars, each line rounded on its own, so a total can sit
    # up to half a dollar a line from the sum of its parts (SD2's answers do: 51,319 against
    # 7,664 plus 43,654). A misread digit above the units still breaks the sum.
    slack = 0.5 * (len(parts) + 1) + 0.01
    return SumRule(name=name, parts=tuple(p + x for x in parts), total=p + total, tolerance=slack)


RULES: Mapping[str, tuple[Rule, ...]] = {
    "fara": (
        PatternRule(
            name="a registration number is digits", field="registration_num", pattern=r"\d{1,5}"
        ),
    ),
    "nist_1040_1": (
        _sum(
            "1040_1",
            "line 23, total income, adds lines 7 to 22",
            "23",
            [
                "7",
                "8a",
                "9",
                "10",
                "11",
                "12",
                "13",
                "14",
                "15",
                "16b",
                "17b",
                "18",
                "19",
                "20",
                "21b",
                "22_h2",
            ],
        ),
        _sum(
            "1040_1",
            "line 30, total adjustments, adds lines 24 to 29",
            "30",
            ["24", "25a", "25b", "26", "27", "28", "29_h2_v2"],
        ),
        _sum(
            "1040_1", "line 31, adjusted gross income, is line 23 less line 30", "23", ["30", "31"]
        ),
    ),
    "nist_1040_2": (
        _sum("1040_2", "line 35 is line 32 less line 34", "32", ["34_h2", "35"]),
        _sum("1040_2", "line 40 adds lines 38 and 39", "40", ["38_h4", "39_h3"]),
        _sum(
            "1040_2",
            "line 46, total credits, adds lines 41 to 45",
            "46",
            ["41", "42", "43", "44_h4", "45"],
        ),
        _sum(
            "1040_2",
            "line 53, other taxes, adds lines 48 to 52",
            "53",
            ["48", "49", "50_h3", "51", "52"],
        ),
        _sum(
            "1040_2",
            "line 61, total payments, adds lines 54 to 60",
            "61",
            ["54_h2", "55", "56", "57", "58", "59", "60"],
        ),
        _sum("1040_2", "line 64 is line 62 less line 63", "62", ["63", "64"]),
    ),
    "nist_sch_a": (_sum("scha", "line 17 adds lines 14 to 16", "17", ["14_h2", "15", "16"]),),
    "nist_sch_b": (
        _sum(
            "schb",
            "line 3, total interest, adds lines 1 and 2",
            "i_3",
            ["i_1_h2", *(f"i_2_h2_v{i}" for i in range(1, 14))],
        ),
        _sum(
            "schb",
            "line 5, total dividends, adds line 4",
            "ii_5",
            ["ii_4_v1", *(f"ii_4_h2_v{i}" for i in range(2, 15))],
        ),
        _sum("schb", "line 8 adds lines 6 and 7", "ii_8", ["ii_6", "ii_7"]),
    ),
}


#: Rules the forms define but the corpus's own training answers break more than 1% of the
#: time, measured and reported (`legible verify hold`) and not run. CORD's receipts follow no
#: one arithmetic: some print prices with tax in and a pre-tax subtotal, some print discounts
#: without a sign, some round the total to 100 rupiah. Line 47 of the 1040 is zero, not
#: negative, when the credits exceed the tax. FARA's and DeepForm's dates are as printed.
REJECTED: Mapping[str, tuple[Rule, ...]] = {
    # The corpora's own date answers keep what the page prints: VRDU's FARA dates are
    # transcriptions such as "23rd day of March 1962", and DeepForm's often lose the year.
    "fara": (DateRule(name="the filing date is a date", field="file_date"),),
    "deepform": (
        DateRule(name="the flight starts on a date", field="flight_from"),
        DateRule(name="the flight ends on a date", field="flight_to"),
    ),
    "cord": (
        SumRule(
            name="the items, less their discounts, add up to the subtotal",
            parts=("menu.price", "menu.discountprice"),
            total="subtotal_price",
        ),
        SumRule(
            name="the items, less their discounts, add up to the subtotal (to 100)",
            parts=("menu.price", "menu.discountprice"),
            total="subtotal_price",
            tolerance=100.5,
        ),
        SumRule(
            name="subtotal, tax, service and discount add up to the total",
            parts=(
                "subtotal_price",
                "tax_price",
                "service_price",
                "othersvc_price",
                "discount_price",
            ),
            total="total_price",
            requires=("subtotal_price",),
        ),
        SumRule(
            name="subtotal, tax, service and discount add up to the total (to 100)",
            parts=(
                "subtotal_price",
                "tax_price",
                "service_price",
                "othersvc_price",
                "discount_price",
            ),
            total="total_price",
            requires=("subtotal_price",),
            tolerance=100.5,
        ),
    ),
    "nist_1040_2": (_sum("1040_2", "line 47 is line 40 less line 46", "40", ["46", "47"]),),
    "nist_sch_b": (_sum("schb", "line 9 adds lines 5 and 8", "ii_9", ["ii_5", "ii_8"]),),
}
