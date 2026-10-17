"""The corpus schemas. Field names and matchers are the benchmark's own, from each corpus's
meta.json as read on 2026-10-16 (docs/data.md), misspellings included: VRDU's
`foreign_principle_name` stays misspelled so that a prediction file here can be scored by
VRDU's own evaluator without a rename table. The descriptions are what the prompt shows.
"""

from __future__ import annotations

from legible.schema import CorpusSchema, FieldKind, FieldSpec, GroupSpec

FARA = CorpusSchema(
    corpus="fara",
    version=1,
    description=(
        "A US Department of Justice Foreign Agents Registration Act filing: a registration "
        "statement amendment, a short-form registration or a dissemination report."
    ),
    fields=(
        FieldSpec(
            name="file_date",
            kind=FieldKind.DATE,
            description="The date the form was filed or signed.",
        ),
        FieldSpec(
            name="foreign_principle_name",
            kind=FieldKind.NAME,
            description="The name of the foreign principal the registrant acts for.",
        ),
        FieldSpec(
            name="registrant_name", kind=FieldKind.NAME, description="The name of the registrant."
        ),
        FieldSpec(
            name="registration_num",
            kind=FieldKind.CODE,
            description="The registrant's FARA registration number.",
        ),
        FieldSpec(
            name="signer_name",
            kind=FieldKind.NAME,
            description="The name of the person who signed the form.",
        ),
        FieldSpec(
            name="signer_title",
            kind=FieldKind.STRING,
            description="The signer's title or position.",
        ),
    ),
)

DEEPFORM = CorpusSchema(
    corpus="deepform",
    version=1,
    description=(
        "A political advertising order, invoice or contract from a US television station's "
        "FCC public file."
    ),
    fields=(
        FieldSpec(
            name="advertiser",
            kind=FieldKind.STRING,
            description="The advertiser buying the airtime.",
        ),
        FieldSpec(
            name="agency",
            kind=FieldKind.STRING,
            description="The agency that placed the order, if any.",
        ),
        FieldSpec(
            name="contract_num", kind=FieldKind.CODE, description="The contract or order number."
        ),
        FieldSpec(
            name="flight_from",
            kind=FieldKind.DATE,
            description="The first date of the flight (the run of the ads).",
        ),
        FieldSpec(
            name="flight_to", kind=FieldKind.DATE, description="The last date of the flight."
        ),
        FieldSpec(
            name="gross_amount", kind=FieldKind.PRICE, description="The gross total of the order."
        ),
        FieldSpec(
            name="product",
            kind=FieldKind.STRING,
            description="The product, candidate or issue advertised.",
        ),
        FieldSpec(
            name="property", kind=FieldKind.STRING, description="The station's call letters."
        ),
        FieldSpec(
            name="tv_address", kind=FieldKind.ADDRESS, description="The station's postal address."
        ),
        GroupSpec(
            name="line_item",
            description="One scheduled row of the order.",
            fields=(
                FieldSpec(
                    name="channel",
                    kind=FieldKind.STRING,
                    description="The channel the row airs on.",
                ),
                FieldSpec(
                    name="program_desc",
                    kind=FieldKind.STRING,
                    description="The programme or daypart.",
                ),
                FieldSpec(
                    name="program_start_date",
                    kind=FieldKind.DATE,
                    description="The row's first air date.",
                ),
                FieldSpec(
                    name="program_end_date",
                    kind=FieldKind.DATE,
                    description="The row's last air date.",
                ),
                FieldSpec(name="sub_amount", kind=FieldKind.PRICE, description="The row's amount."),
            ),
        ),
    ),
)

SCHEMAS: dict[str, CorpusSchema] = {s.corpus: s for s in (FARA, DEEPFORM)}


def _price(name: str, description: str) -> FieldSpec:
    return FieldSpec(name=name, kind=FieldKind.PRICE, description=description, decimal_mark="auto")


def _count(name: str, description: str) -> FieldSpec:
    return FieldSpec(name=name, kind=FieldKind.NUMBER, description=description, decimal_mark="auto")


def _text(name: str, description: str) -> FieldSpec:
    return FieldSpec(name=name, kind=FieldKind.STRING, description=description)


#: CORD v2's thirty classes, as `gt_parse` names them (docs/data.md). Prices are read with
#: the "auto" decimal mark because receipts print 60.000, 60,000 and 60000.00 for the same
#: amount on different receipts.
CORD = CorpusSchema(
    corpus="cord",
    version=1,
    description="A photographed restaurant or shop receipt from Indonesia.",
    fields=(
        GroupSpec(
            name="menu",
            description="One item bought.",
            fields=(
                _text("nm", "The item's name."),
                _text("num", "The item's code or number, if printed."),
                _price("unitprice", "The price of one unit."),
                _count("cnt", "How many were bought."),
                _price("discountprice", "A discount on this item."),
                _price("price", "The line's price."),
                _price("itemsubtotal", "The item's subtotal, if printed separately."),
                _text("vatyn", "Whether VAT applies to the item, as printed."),
                _text("etc", "Anything else printed on the item's line."),
            ),
        ),
        GroupSpec(
            name="sub_item",
            description="A component or option printed under an item, such as a set meal's parts.",
            fields=(
                _text("nm", "The component's name."),
                _price("unitprice", "The price of one unit."),
                _count("cnt", "How many."),
                _price("price", "The component's price."),
                _text("etc", "Anything else printed on its line."),
            ),
        ),
        GroupSpec(
            name="void_menu",
            description="An item voided on the receipt.",
            fields=(_text("nm", "The voided item's name."), _price("price", "Its price.")),
        ),
        _price("subtotal_price", "The subtotal."),
        _price("discount_price", "A discount on the whole bill."),
        _price("service_price", "The service charge."),
        _price("othersvc_price", "Any other service charge."),
        _price("tax_price", "The tax."),
        _text("subtotal_etc", "Anything else printed in the subtotal section."),
        _price("total_price", "The total to pay."),
        _text("total_etc", "Anything else printed in the total section."),
        _price("cashprice", "The cash tendered."),
        _price("changeprice", "The change given."),
        _price("creditcardprice", "The amount paid by card."),
        _price("emoneyprice", "The amount paid by e-money."),
        _count("menutype_cnt", "The number of distinct items, if printed."),
        _count("menuqty_cnt", "The total quantity of items, if printed."),
    ),
)

SCHEMAS["cord"] = CORD


# --- NIST Special Database 2 -------------------------------------------------------------

#: The 20 form faces of the 1988 IRS 1040 package that SD2 holds, by the id its answer files
#: open with (users' guide, February 2017).
NIST_FACES: dict[str, str] = {
    "1040_1": "Form 1040, page 1",
    "1040_2": "Form 1040, page 2",
    "2106_1": "Form 2106 (employee business expenses), page 1",
    "2106_2": "Form 2106, page 2",
    "2441": "Form 2441 (child and dependent care expenses)",
    "4562_1": "Form 4562 (depreciation and amortization), page 1",
    "4562_2": "Form 4562, page 2",
    "6251": "Form 6251 (alternative minimum tax)",
    "sch_a": "Schedule A (itemized deductions)",
    "sch_b": "Schedule B (interest and dividend income)",
    "sch_c_1": "Schedule C (profit or loss from business), page 1",
    "sch_c_2": "Schedule C, page 2",
    "sch_d_1": "Schedule D (capital gains and losses), page 1",
    "sch_d_2": "Schedule D, page 2",
    "sch_e_1": "Schedule E (supplemental income), page 1",
    "sch_e_2": "Schedule E, page 2",
    "sch_f_1": "Schedule F (profit or loss from farming), page 1",
    "sch_f_2": "Schedule F, page 2",
    "sch_se_1": "Schedule SE (self-employment tax), page 1",
    "sch_se_2": "Schedule SE, page 2",
}


def nist_name(field_id: str) -> str:
    """A schema name for an SD2 field id: `1040_1_6c_H1_V1` is `f_1040_1_6c_h1_v1`."""
    import re

    return "f_" + re.sub(r"[^a-z0-9]+", "_", field_id.lower()).strip("_")


def _nist_where(face: str, field_id: str) -> str:
    """Where a field is on its face, in the users' guide's own terms: the line number, then
    H for the column across and V for the row down where a line has several boxes."""
    rest = (
        field_id[len(face) + 1 :] if field_id.lower().startswith(face.lower() + "_") else field_id
    )
    parts = [p for p in rest.split("_") if p]
    line: list[str] = []
    place: list[str] = []
    for p in parts:
        if len(p) > 1 and p[0] in "HV" and p[1:].isdigit():
            place.append(("column " if p[0] == "H" else "row ") + p[1:])
        elif p == "L":
            line.append("the name and address block")
        else:
            line.append(p)
    where = (
        "line " + " ".join(line)
        if line and line[0] != "the name and address block"
        else " ".join(line)
    )
    return where + (", " + ", ".join(place) if place else "")


_NIST_KIND = {
    ("A", "NAME"): (FieldKind.NAME, "a name"),
    ("A", "SSN"): (FieldKind.STRING, "a social security number as printed"),
    ("A", "DATA"): (FieldKind.STRING, "text"),
    ("CA", "DATA"): (FieldKind.STRING, "text"),
}


def _nist_schema(face: str, rows: list[list[str]]) -> CorpusSchema:
    """One face's schema. Check marks and signatures (type ICON) are left out: their answer is
    a token for "a mark is here", not text to read. Every numeric type (whole dollars and
    cents in separate boxes, plain floats, integers, percentages) is compared digits only,
    VRDU's numerical-string match, because the forms print amounts as `5140  00` with the
    cents in a box of their own."""
    fields = []
    for field_id, kind, context in rows:
        if kind == "ICON":
            continue
        matcher, what = _NIST_KIND.get((kind, context), (FieldKind.CODE, "a number"))
        fields.append(
            FieldSpec(
                name=nist_name(field_id),
                kind=matcher,
                description=f"{_nist_where(face, field_id)}: {what} (SD2 field {field_id}).",
            )
        )
    return CorpusSchema(
        corpus=f"nist_{face.lower()}",
        version=1,
        description=(
            f"A machine-printed {NIST_FACES[face]} of the 1988 IRS 1040 package, filled with "
            "synthesised values, scanned in black and white."
        ),
        fields=tuple(fields),
    )


def _nist_schemas() -> dict[str, CorpusSchema]:
    import json
    from importlib import resources

    raw = json.loads(
        resources.files("legible.schema").joinpath("nist_fields.json").read_text("utf-8")
    )
    return {f"nist_{face.lower()}": _nist_schema(face, rows) for face, rows in raw["faces"].items()}


#: One schema per SD2 form face, keyed `nist_<face>`: a NIST document is one face, and each
#: face is its own form with its own fields.
NIST_SCHEMAS = _nist_schemas()
SCHEMAS.update(NIST_SCHEMAS)
