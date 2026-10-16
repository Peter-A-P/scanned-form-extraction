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
