"""Arm E's rules, written by reading training pages only (2026-10-16).

FARA has a rule set per template, and a split gets only the sets for the templates in its
training part: on `FARA-lv3-unk_Amendment-...` the Amendment rules do not exist, which is the
whole point of the unseen-template measurement. DeepForm publishes no template label, so its
rules are one set written against the layouts seen in training (most are WideOrbit invoices and
orders); CORD's receipts have no templates and get one set of keyword rules. Every pattern is a
guess a person made from training pages, and none was tuned on dev or test.
"""

from __future__ import annotations

from typing import Final

from legible.arms.rules import Extract, RowRule, TemplateRules

DATE: Final = (
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{2,4})"
)
NUMBER: Final = r"\b(\d{3,6})\b"
#: A name before a trailing registration number or street address on the same line.
#: A line holding only a number: the registration number printed in the next column.
ONLY_NUMBER: Final = r"^\d{3,6}$"
NAME_BEFORE_NUMBER: Final = r"^([A-Za-z].*?)(?:\s+\d{1,6}\b.*)?$"

FARA_AMENDMENT = TemplateRules(
    name="fara-amendment",
    detect=(r"Amendment to Registration Statement",),
    fields={
        "registration_num": (
            Extract(anchor=r"Registration No", where="below", lines=2, value=NUMBER),
        ),
        "registrant_name": (
            Extract(
                anchor=r"Name of Registrant",
                where="below",
                column_end=r"^2\.?$",
                skip=ONLY_NUMBER,
                value=NAME_BEFORE_NUMBER,
            ),
        ),
        "signer_name": (
            Extract(
                anchor=r"print name under",
                where="below",
                max_gap=0.12,
                value=r"^([A-Z][A-Za-z.\- ]+?)\s*(?:,|$)",
            ),
        ),
        "signer_title": (
            Extract(anchor=r"print name under", where="below", max_gap=0.12, value=r",\s*(.+)$"),
        ),
        "file_date": (
            Extract(anchor=DATE, where="match", page=1),
            Extract(anchor=DATE, where="match"),
        ),
    },
)

FARA_SHORT_FORM = TemplateRules(
    name="fara-short-form",
    detect=(r"Short[- ]?Form Registration Statement",),
    fields={
        "registration_num": (
            Extract(anchor=r"Registration No", where="below", lines=2, value=NUMBER),
        ),
        "registrant_name": (
            Extract(
                anchor=r"name and address of the primary registrant",
                where="below",
                lines=1,
                skip=r"^Name\s+Address",
                value=NAME_BEFORE_NUMBER,
            ),
        ),
        "foreign_principle_name": (Extract(anchor=r"List every foreign principal", where="below"),),
        "signer_name": (Extract(anchor=r"^1\.\s*Name", where="below", value=NAME_BEFORE_NUMBER),),
        "file_date": (
            Extract(anchor=DATE, where="match", page=1),
            Extract(anchor=DATE, where="match"),
        ),
    },
)

FARA_DISSEMINATION = TemplateRules(
    name="fara-dissemination-report",
    detect=(r"DISSEMINATION REPORT",),
    fields={
        "registration_num": (
            Extract(anchor=r"REGISTRATION NO", where="below", lines=2, value=NUMBER),
        ),
        "registrant_name": (
            Extract(
                anchor=r"NAME OF REGIS", where="below", skip=ONLY_NUMBER, value=NAME_BEFORE_NUMBER
            ),
        ),
        "foreign_principle_name": (
            Extract(
                anchor=r"NAME OF FOREIGN PRINCIPAL",
                where="below",
                skip=r"MATERIAL WAS TRANSMITTED|^[\s,;.]*transmitted\.?$",
            ),
        ),
        "signer_name": (
            Extract(anchor=r"NAME AND TITLE", where="below", value=r"^([^,]+?)(?:,|$)"),
        ),
        "signer_title": (Extract(anchor=r"NAME AND TITLE", where="below", value=r",\s*(.+)$"),),
        "file_date": (
            Extract(anchor=r"DATE OF REPORT", where="below", value=DATE),
            Extract(anchor=DATE, where="match"),
        ),
    },
)

FARA_BY_TEMPLATE: Final[dict[str, TemplateRules]] = {
    "Amendment": FARA_AMENDMENT,
    "Short-Form": FARA_SHORT_FORM,
    "Dissemination Report": FARA_DISSEMINATION,
}


def fara_rules(train_templates: set[str]) -> tuple[TemplateRules, ...]:
    """The rule sets a FARA split may use: only those for templates its training part holds."""
    return tuple(FARA_BY_TEMPLATE[t] for t in sorted(train_templates) if t in FARA_BY_TEMPLATE)


_LABELS: Final = (
    r"\s(?:Invoice|Order|Estimate|Agency|Advertiser|Product|Property|Account|Flight|Station"
    r"|Contract|Market|Prod\d?|Demo|Billing|Original|Revision|Political|Priority)\b|\s\[|\s\|"
)
#: A header printed where a value was expected: the value is under it, not beside it.
_NOT_A_HEADER: Final = r"^(?!Original Date|Revision|Name\b|Code\b)(\S.*\S|\S)"
#: A daypart printed after the programme name ("6a-7a", "1058a-12p"), not part of it.
_DAYPART: Final = r"\d{1,4}(?::\d\d)?[ap]?-\d{1,4}(?::\d\d)?[ap]?"
_US_DATE: Final = r"\d{1,2}/\d{1,2}/\d{2,4}"

DEEPFORM = TemplateRules(
    name="deepform",
    detect=(r".",),
    fields={
        "advertiser": (
            Extract(
                anchor=r"\bAdvertiser\b(?!\s*(?:Code|Ref|ID))\s*(?:Name)?\s*:?",
                stop=_LABELS,
                value=_NOT_A_HEADER,
            ),
            Extract(anchor=r"\bAdvertiser\b(?!\s*(?:Code|Ref|ID))", where="below", cut=_LABELS),
        ),
        "agency": (
            Extract(
                anchor=r"\bAgency\b(?!\s*(?:Code|Ref|Commission|ID))\s*(?:Name)?\s*:?", stop=_LABELS
            ),
        ),
        "product": (Extract(anchor=r"\bProduct\b(?!\s*1/2)\s*(?:Desc)?\s*:?", stop=_LABELS),),
        "property": (
            Extract(
                anchor=r"\b(?:Property|Station)\b\s*:?",
                value=r"\b([KW][A-Z]{2,3}(?:-?(?:TV|DT|CD))?)\b",
            ),
            Extract(anchor=r"\b([KW][A-Z]{3})\b", where="match"),
        ),
        "contract_num": (
            Extract(
                anchor=r"\b(?:Order|Contract)\s*(?:/\s*Rev)?\s*(?:#|No\.?|Number)?\s*:?",
                value=r"(\d{4,})",
            ),
            Extract(anchor=r"\bInvoice\s*#", value=r"(\d{4,})"),
        ),
        "flight_from": (Extract(anchor=r"\bFlight\b|\bFlight Dates?\b", value=f"({_US_DATE})"),),
        "flight_to": (
            Extract(
                anchor=r"\bFlight\b|\bFlight Dates?\b",
                value=rf"{_US_DATE}\s*(?:-|to|thru)\s*({_US_DATE})",
            ),
        ),
        "gross_amount": (
            Extract(anchor=r"\bGross\s*(?:Total|Amount)?\b", value=r"(\$?[\d,]+\.\d{2})"),
            Extract(anchor=r"\bTotal\b", value=r"(\$?[\d,]+\.\d{2})"),
        ),
        "tv_address": (
            Extract(
                anchor=r"Remit (?:To|Address)",
                where="below",
                lines=2,
                cut=r"\s(?:Advertiser|Product|Invoice|Agency|Estimate)\b",
                skip=r"^(?:FOX\s+)?[KW][A-Z]{2,3}\b",
            ),
        ),
    },
    rows=(
        RowRule(
            group="line_item",
            start=r"\bLine\b.*\bCh(?:annel|an)\b|\bChannel\b.*\bDescription\b",
            end=r"Aired Spots|Gross Total|Order Totals?",
            pattern=r"^\d+\s+(?P<channel>[A-Z0-9][A-Z0-9-]*)\s+(?P<program_desc>.+?)"
            rf"(?:\s+{_DAYPART})*(?:\s+(?P<sub_amount>\$[\d,]+\.\d{{2}}))?$",
            exclude=_US_DATE,
            continuation=rf"(?P<program_start_date>{_US_DATE})\s*(?:-|to|thru)\s*(?P<program_end_date>{_US_DATE})",
        ),
    ),
)

#: Receipt amounts: grouped thousands (60.000, 1,946,000, a stray space after the mark) or
#: four or more bare digits. OCR lines on receipts carry junk either side, so nothing here is
#: anchored to the start or the end of a line.
_AMOUNT: Final = r"(-?\d{1,3}(?:[.,]\s?\d{3})+|-?\d{4,})"

CORD = TemplateRules(
    name="cord",
    detect=(r".",),
    fields={
        "subtotal_price": (Extract(anchor=r"SUB\s*-?\s*TOTAL|SUBTTL|SUB\s*TTL", value=_AMOUNT),),
        "tax_price": (Extract(anchor=r"\b(?:TAX|PB1|PPN|VAT|PAJAK)\b", value=_AMOUNT),),
        "service_price": (Extract(anchor=r"\bSERVICE|\bSVC\b|\bSERV\b", value=_AMOUNT),),
        "discount_price": (Extract(anchor=r"\bDISC(?:OUNT)?\b", value=_AMOUNT),),
        "total_price": (
            Extract(
                anchor=r"(?<![Bb]-)(?<![Bb] )(?<![Bb])\b(?:GRAND\s+)?TOTAL\b(?!\s*(?:ITEM|QTY|DISC))",
                value=_AMOUNT,
            ),
            Extract(anchor=r"\b(?:DUE|AMOUNT|TAGIHAN)\b", value=_AMOUNT),
        ),
        "cashprice": (Extract(anchor=r"\b(?:CASH|TUNAI)\b", value=_AMOUNT),),
        "changeprice": (Extract(anchor=r"\b(?:CHANGE|KEMBALI(?:AN)?)\b", value=_AMOUNT),),
        "creditcardprice": (
            Extract(anchor=r"\b(?:CARD|DEBIT|CREDIT|VISA|MASTER)\b", value=_AMOUNT),
        ),
    },
    rows=(
        RowRule(
            group="menu",
            end=r"SUB\s*-?\s*TOTAL|SUBTTL|\bTOTAL\b",
            exclude=r"\b(?:TAX|PB1|SERVICE|CASH|CHANGE|TOTAL)\b",
            pattern=(
                r"(?:\b(?P<cnt>\d{1,2})\s*[xX%]?\s+)?(?P<nm>[A-Za-z][A-Za-z0-9&'./ -]*?[A-Za-z])"
                r"\s+[=:~-]*\s*(?:@?\d[\d.,]*\s+)?(?P<price>\d{1,3}(?:[.,]\s?\d{3})+)"
            ),
        ),
    ),
)
