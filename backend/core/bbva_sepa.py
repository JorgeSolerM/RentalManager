"""BBVA pain.008.001.02 export, without database or network dependencies.

Structural compatibility with private bank-accepted references; not a substitute
for the bank's import validation. No XML/identity values are included in errors.
"""
from decimal import Decimal
import re
import unicodedata
import xml.etree.ElementTree as ET

from backend.core.iban import is_valid_iban
from backend.core.sepa import is_valid_bic, is_valid_sepa_identifier

NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
N = {"s": NS}
ET.register_namespace("", NS)


def sepa_text(value, limit, *, truncate=False):
    result = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    result = " ".join(re.sub(r"[^a-zA-Z0-9 /?:().,'+\-]", " ", result).split())
    if truncate:
        result = result[:limit].rstrip()
    if not result or len(result) > limit:
        raise ValueError("Texto SEPA vacío o demasiado largo; revise la configuración.")
    return result


def validate_bank_data(snapshot):
    for key in ("creditor_name", "debtor_name", "initiator_name"):
        if key in snapshot:
            sepa_text(snapshot[key], 70)
    for key in ("creditor_iban", "debtor_iban"):
        if key in snapshot and not is_valid_iban(snapshot[key]):
            raise ValueError("IBAN no válido; revise la configuración bancaria.")
    for key in ("creditor_bic", "debtor_bic"):
        # All supplied BBVA references carry BIC. Do not guess a bank from IBAN.
        if key in snapshot and (not snapshot[key] or not is_valid_bic(snapshot[key])):
            raise ValueError("Falta BIC válido para el perfil BBVA verificado.")
    if "creditor_identifier" in snapshot and not is_valid_sepa_identifier(snapshot["creditor_identifier"]):
        raise ValueError("Identificador de acreedor no válido.")


def render_bbva(group, message_id, created_at):
    snapshot = group.snapshot
    validate_bank_data(snapshot)
    for debit in group.debits:
        validate_bank_data(debit.snapshot)
        if debit.amount <= 0 or debit.amount != debit.amount.quantize(Decimal("0.01")) or debit.currency != "EUR":
            raise ValueError("Importe SEPA no válido.")
    root = ET.Element(f"{{{NS}}}Document")

    def add(parent, tag, value=None, **attrs):
        element = ET.SubElement(parent, f"{{{NS}}}{tag}", attrs)
        if value is not None:
            element.text = str(value)
        return element

    def private_id(parent, value, scheme=False):
        other = add(add(add(parent, "Id"), "PrvtId"), "Othr")
        add(other, "Id", sepa_text(value, 35))
        if scheme:
            add(add(other, "SchmeNm"), "Prtry", "SEPA")

    def agent(parent, tag, bic):
        add(add(add(parent, tag), "FinInstnId"), "BIC", bic)

    def account(parent, tag, iban):
        add(add(add(parent, tag), "Id"), "IBAN", iban)

    body = add(root, "CstmrDrctDbtInitn")
    header = add(body, "GrpHdr")
    add(header, "MsgId", sepa_text(message_id, 35))
    add(header, "CreDtTm", created_at.isoformat(timespec="seconds"))
    add(header, "NbOfTxs", len(group.debits))
    add(header, "CtrlSum", f"{sum(d.amount for d in group.debits):.2f}")
    initiator = add(header, "InitgPty")
    add(initiator, "Nm", sepa_text(snapshot["initiator_name"], 70))
    private_id(initiator, snapshot["initiator_identifier"])
    for sequence in ("RCUR", "OOFF"):
        debits = [d for d in group.debits if d.snapshot["sequence"] == sequence]
        if not debits:
            continue
        payment = add(body, "PmtInf")
        add(payment, "PmtInfId", sepa_text(f"G{group.id}-{sequence}-{message_id[-20:]}", 35))
        add(payment, "PmtMtd", "DD")
        add(payment, "BtchBookg", "true")
        add(payment, "NbOfTxs", len(debits))
        add(payment, "CtrlSum", f"{sum(d.amount for d in debits):.2f}")
        kind = add(payment, "PmtTpInf")
        add(add(kind, "SvcLvl"), "Cd", "SEPA")
        add(add(kind, "LclInstrm"), "Cd", "CORE")
        add(kind, "SeqTp", sequence)
        add(payment, "ReqdColltnDt", group.batch.requested_collection_date.isoformat())
        add(add(payment, "Cdtr"), "Nm", sepa_text(snapshot["creditor_name"], 70))
        account(payment, "CdtrAcct", snapshot["creditor_iban"])
        agent(payment, "CdtrAgt", snapshot["creditor_bic"])
        private_id(add(payment, "CdtrSchmeId"), snapshot["creditor_identifier"], True)
        for debit in debits:
            data = debit.snapshot
            tx = add(payment, "DrctDbtTxInf")
            add(add(tx, "PmtId"), "EndToEndId", sepa_text(debit.end_to_end_id, 35))
            add(tx, "InstdAmt", f"{debit.amount:.2f}", Ccy="EUR")
            mandate = add(add(tx, "DrctDbtTx"), "MndtRltdInf")
            add(mandate, "MndtId", data["mandate_reference"])
            add(mandate, "DtOfSgntr", data["signature_date"])
            add(mandate, "AmdmntInd", "false")
            agent(tx, "DbtrAgt", data["debtor_bic"])
            add(add(tx, "Dbtr"), "Nm", sepa_text(data["debtor_name"], 70))
            account(tx, "DbtrAcct", data["debtor_iban"])
            add(add(tx, "RmtInf"), "Ustrd", sepa_text(debit.remittance_information, 140))
    ET.indent(root, space="  ")
    content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    validate_structure(content)
    return content


def validate_structure(content):
    """Strict required-path/count/sum checks; explicitly NOT an XSD validator."""
    root = ET.fromstring(content)
    if root.tag != f"{{{NS}}}Document":
        raise ValueError("Namespace SEPA incorrecto.")
    header = root.find("s:CstmrDrctDbtInitn/s:GrpHdr", N)
    groups = root.findall("s:CstmrDrctDbtInitn/s:PmtInf", N)
    if header is None or not groups:
        raise ValueError("Estructura SEPA incompleta.")
    seen = set()
    for container, tx in [(header, root.findall(".//s:DrctDbtTxInf", N))] + [(g, g.findall("s:DrctDbtTxInf", N)) for g in groups]:
        if not tx or int(container.findtext("s:NbOfTxs", namespaces=N)) != len(tx) or Decimal(container.findtext("s:CtrlSum", namespaces=N)) != sum(Decimal(t.findtext("s:InstdAmt", namespaces=N)) for t in tx):
            raise ValueError("Totales SEPA incoherentes.")
    for group in groups:
        for path, expected in {"s:PmtMtd": "DD", "s:BtchBookg": "true", "s:PmtTpInf/s:SvcLvl/s:Cd": "SEPA", "s:PmtTpInf/s:LclInstrm/s:Cd": "CORE"}.items():
            if group.findtext(path, namespaces=N) != expected:
                raise ValueError("Perfil SEPA incorrecto.")
        if group.findtext("s:PmtTpInf/s:SeqTp", namespaces=N) not in {"RCUR", "OOFF"}:
            raise ValueError("Secuencia SEPA incorrecta.")
        for tx in group.findall("s:DrctDbtTxInf", N):
            for path in ("s:PmtId/s:EndToEndId", "s:DrctDbtTx/s:MndtRltdInf/s:MndtId", "s:DrctDbtTx/s:MndtRltdInf/s:DtOfSgntr", "s:Dbtr/s:Nm", "s:DbtrAcct/s:Id/s:IBAN", "s:RmtInf/s:Ustrd"):
                if not tx.findtext(path, namespaces=N):
                    raise ValueError("Adeudo SEPA incompleto.")
            reference = tx.findtext("s:PmtId/s:EndToEndId", namespaces=N)
            if reference in seen or len(reference) > 35:
                raise ValueError("Referencia de adeudo duplicada o no válida.")
            seen.add(reference)
