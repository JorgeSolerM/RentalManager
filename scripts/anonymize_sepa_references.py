"""Emit synthetic fixtures as JSON; never copy reference XML or print real values.

Run locally only. The private input directory is deliberately fixed. Every leaf
is replaced except the public protocol constants. Output is suitable for an
apply_patch operation, not for importing into the application database.
"""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/sepa_reference"
NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
N = {"s": NS}
ET.register_namespace("", NS)
CONSTANTS = {"PmtMtd": "DD", "BtchBookg": "true", "SeqTp": "RCUR",
             "Prtry": "SEPA", "AmdmntInd": "false"}


def synthetic_iban(country, number):
    lengths = {"ES": 20, "DE": 18, "NL": 14, "LT": 16, "FR": 23, "PT": 21}
    bban = str(number).zfill(lengths[country])
    if country == "NL":
        bban = "TEST" + str(number).zfill(10)
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in bban + country + "00")
    return f"{country}{98 - int(digits) % 97:02d}{bban}"


def build():
    files = sorted(SOURCE.glob("*.xml"))
    if len(files) != 7:
        raise RuntimeError("Expected seven private reference files")
    for p in files:
        if subprocess.run(["git", "check-ignore", "--quiet", str(p)], cwd=ROOT).returncode:
            raise RuntimeError("Private references must be ignored before reading")
    originals = [ET.parse(p).getroot() for p in files]
    private_values = set()
    for root in originals:
        for el in root.iter():
            if len(el) == 0 and el.text and el.tag.split("}")[-1] in {
                "Nm", "IBAN", "BIC", "Id", "MndtId", "EndToEndId", "MsgId",
                "PmtInfId", "Ustrd", "AdrLine", "StrtNm", "TwnNm", "CtrySubDvsn",
            }:
                private_values.add(el.text.strip().casefold())
    output = {}
    identities = {}

    def pseudonym(kind, original):
        key = (kind, original)
        if key not in identities:
            identities[key] = len(identities) + 1
        return identities[key]

    for sample, original in enumerate(originals, 1):
        root = deepcopy(original)
        if root.tag != f"{{{NS}}}Document":
            raise RuntimeError("Unexpected namespace")
        counter = 0

        def replace(el, parent="", ancestors=()):
            nonlocal counter
            tag = el.tag.split("}")[-1]
            if len(el):
                el.text = None
                for child in el:
                    replace(child, tag, ancestors + (tag,))
            else:
                counter += 1
                token = f"TEST{sample:02d}{counter:04d}"
                if tag in CONSTANTS:
                    value = CONSTANTS[tag]
                elif tag == "Cd":
                    value = {"SvcLvl": "SEPA", "LclInstrm": "CORE"}[parent]
                elif tag == "IBAN":
                    value = synthetic_iban(el.text[:2], 900000 + pseudonym("iban", el.text))
                elif tag == "BIC":
                    value = "TEST" + el.text[4:6] + "MMXXX"
                elif tag == "Id" and "CdtrSchmeId" in ancestors:
                    account = synthetic_iban("ES", 999900000 + pseudonym("creditor", el.text))
                    value = account[:4] + "ZZZ" + account[4:]
                elif tag == "Id" and "InitgPty" in ancestors:
                    value = f"TESTINITIATOR{pseudonym('initiator', el.text):04d}"
                elif tag == "Ctry":
                    value = el.text  # public country code, not an address
                elif tag == "CreDtTm":
                    value = "2099-09-01T09:00:00"
                elif tag == "ReqdColltnDt":
                    value = "2099-09-10"
                elif tag == "DtOfSgntr":
                    value = "2099-08-01"
                elif tag == "InstdAmt":
                    value = f"{100 + counter}.00"
                elif tag in {"NbOfTxs", "CtrlSum"}:
                    value = "0"  # recalculated below
                elif tag == "Ustrd":
                    value = ("ALQUILER SEPTIEMBRE 2099", "ALQUILER + SUMINISTROS",
                             "ALQUILER + FIANZA")[counter % 3] + " - FINCA DE PRUEBA"
                elif tag == "Nm":
                    value = f"SUJETO SINTETICO TEST{pseudonym('name', el.text):04d}"
                elif tag in {"BldgNb", "PstCd"}:
                    value = "99999"
                else:
                    value = token
                el.text = value
            el.attrib.clear()
            if tag == "InstdAmt":
                el.set("Ccy", "EUR")
            el.tail = None

        replace(root)
        for group in root.findall(".//s:PmtInf", N):
            tx = group.findall("s:DrctDbtTxInf", N)
            group.find("s:NbOfTxs", N).text = str(len(tx))
            group.find("s:CtrlSum", N).text = str(sum(Decimal(t.find("s:InstdAmt", N).text) for t in tx))
        header = root.find(".//s:GrpHdr", N)
        header.find("s:NbOfTxs", N).text = str(len(root.findall(".//s:DrctDbtTxInf", N)))
        header.find("s:CtrlSum", N).text = str(sum(Decimal(e.text) for e in root.findall(".//s:InstdAmt", N)))
        for el in root.iter():
            if len(el) == 0 and el.text and el.text.casefold() in private_values:
                raise RuntimeError("Anonymization rejected: private value collision")
        ET.indent(root, space="  ")
        output[f"tests/fixtures/sepa_bbva/reference_{sample:02d}.xml"] = ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"
    return output


if __name__ == "__main__":
    try:
        result = build()
    except Exception:
        # Parsing errors must not echo source lines containing private values.
        raise SystemExit("Reference validation/anonymization failed; no output emitted") from None
    print(json.dumps(result))
