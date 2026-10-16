"""Test schemas: shaped like the corpora, owned by the tests so a corpus schema change
cannot quietly change what a grader test means."""

from __future__ import annotations

from legible.schema import CorpusSchema, FieldKind, FieldSpec, GroupSpec

ORDER = CorpusSchema(
    corpus="order",
    version=1,
    description="An ad-buy-shaped order: scalars and repeated line items.",
    fields=(
        FieldSpec(name="advertiser", kind=FieldKind.STRING, description="Who buys the airtime."),
        FieldSpec(
            name="agency", kind=FieldKind.STRING, description="The agency placing the order."
        ),
        FieldSpec(name="contract_num", kind=FieldKind.CODE, description="Contract number."),
        FieldSpec(name="flight_from", kind=FieldKind.DATE, description="First air date."),
        FieldSpec(name="gross_amount", kind=FieldKind.PRICE, description="Order total."),
        FieldSpec(name="product", kind=FieldKind.STRING, description="What is advertised."),
        GroupSpec(
            name="line_item",
            description="One row of the order.",
            fields=(
                FieldSpec(name="program", kind=FieldKind.STRING, description="Programme."),
                FieldSpec(name="start", kind=FieldKind.DATE, description="Row start date."),
                FieldSpec(name="amount", kind=FieldKind.PRICE, description="Row amount."),
            ),
        ),
    ),
)

RECEIPT = CorpusSchema(
    corpus="receipt",
    version=1,
    description="A CORD-shaped receipt: whole-unit prices with thousands separators.",
    fields=(
        GroupSpec(
            name="menu",
            description="Items bought.",
            fields=(
                FieldSpec(name="nm", kind=FieldKind.STRING, description="Item name."),
                FieldSpec(
                    name="cnt", kind=FieldKind.NUMBER, description="Count.", decimal_mark=None
                ),
                FieldSpec(
                    name="price", kind=FieldKind.PRICE, description="Line price.", decimal_mark=None
                ),
            ),
        ),
        FieldSpec(
            name="subtotal_price", kind=FieldKind.PRICE, description="Subtotal.", decimal_mark=None
        ),
        FieldSpec(name="tax_price", kind=FieldKind.PRICE, description="Tax.", decimal_mark=None),
        FieldSpec(
            name="total_price", kind=FieldKind.PRICE, description="Total.", decimal_mark=None
        ),
    ),
)
