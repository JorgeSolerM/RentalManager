"""Private local adapter. Never connects to the original or an active server."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile


# Explicit projection: no historical receipts, blobs, SMTP credentials or passwords.
COLUMNS = {
    'ALQ_INQUILINOS': 'CODIGO APEYNOM NIF MAIL TEL FAX DIRSIGLA DIR DIRNUM DIRPISO DIRLETRA POB CP PROVINCIA PAIS IBAN BANCO SUCURSAL DC CUENTA CUENTA1 CUENTA2 CUENTA3 TITULAR',
    'ALQ_INQUILINOS_H': 'CODIGO APEYNOM NIF MAIL TEL FAX DIRSIGLA DIR DIRNUM DIRPISO DIRLETRA POB CP PROVINCIA PAIS IBAN BANCO SUCURSAL DC CUENTA CUENTA1 CUENTA2 CUENTA3 TITULAR',
    'ALQ_INMUEBLES': 'CODIGO CODFINCA CODINQUILINO1 CODINQUILINO2 CODINQUILINO3 CODPAGADOR FECHAINICIO FECHAVENCIMIENTO FECHA_ULT_RECIBO VACIO RENTA FIANZA_IMPORTE DIR DIRNUM DIRPISO DIRLETRA REFDOMICI DCREFDOMI FECHA_MANDATO',
    'ALQ_FINCAS': 'CODIGO DIR DIRNUM POB CODPROPIETARIO ACTIVA',
    'ALQ_PROPIETARIOS': 'CODIGO APEYNOM NIF MAIL TEL FAX DIR DIRNUM POB CP PROVINCIA IBAN BANCO SUCURSAL DC CUENTA CUENTA1 CUENTA2 CUENTA3 TITULAR SUFIJO',
    'ALQ_INMUEBLES_INDIVISOS': 'CODIGO CODFINCA CODPROPIETARIO PARTICIPACION',
    'COMUN_BANCOS': 'CODBANCO SWIFT',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=True).encode()).hexdigest()


@dataclass
class Snapshot:
    tables: dict
    fingerprint: str


class SourceUnavailable(ValueError):
    pass


class FirebirdSource:
    def __init__(self, database: Path, executable: Path):
        self.database, self.executable = Path(database).resolve(), Path(executable).resolve()

    def read(self):
        if not self.database.is_file() or not self.executable.is_file():
            raise SourceUnavailable('Fuente privada o motor compatible no disponible.')
        # Embedded may write transaction metadata even for READ ONLY: disposable copy.
        with tempfile.TemporaryDirectory(prefix='rentalmanager_nf_') as temp:
            copy = Path(temp) / 'audit.ib'
            shutil.copyfile(self.database, copy)
            env = os.environ.copy()
            for key in ('ISC_USER', 'ISC_PASSWORD', 'ISC_DATABASE', 'FIREBIRD'):
                env.pop(key, None)
            return self._marked(copy, env)

    def _marked(self, copy, env):
        tables = {}
        for table, cols in COLUMNS.items():
            sql = f'ROLLBACK;\nSET TRANSACTION READ ONLY;\nSET LIST ON;\nSELECT {",".join(cols.split())} FROM {table};\nROLLBACK;\nQUIT;\n'
            try:
                p = subprocess.run([str(self.executable), '-q', '-b', '-user', 'SYSDBA', str(copy)],
                    input=sql, capture_output=True, text=True, encoding='cp1252', errors='strict',
                    timeout=30, env=env, cwd=self.executable.parent,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except (OSError, subprocess.SubprocessError, UnicodeError):
                raise SourceUnavailable('No se pudo leer la copia aislada.') from None
            if p.returncode or p.stderr.strip():
                raise SourceUnavailable('Consulta de origen no disponible.')
            rows, row = [], {}
            first = cols.split()[0]
            for line in p.stdout.replace('SQL>', '').splitlines():
                parts = line.strip().split(None, 1)
                if not parts or parts[0] not in cols.split():
                    continue
                key = parts[0]
                if key == first and row:
                    rows.append(row); row = {}
                value = parts[1].strip() if len(parts) > 1 else ''
                row[key] = None if value == '<null>' else value
            if row: rows.append(row)
            if table in ('ALQ_INQUILINOS','ALQ_INQUILINOS_H','ALQ_PROPIETARIOS'):
                # Per-form verified semantics, not inferred from column names.
                for row in rows: row['_phone_entity'] = table
            tables[table] = rows
        return Snapshot(tables, digest(tables))
