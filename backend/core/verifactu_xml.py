"""Offline F1 test serializer. No SOAP transport, certificates or submission."""
from decimal import Decimal
from xml.etree import ElementTree as ET
from backend.core.verifactu_primitives import alta_hash

SF='https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd'
LR='https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd'
ET.register_namespace('sf',SF);ET.register_namespace('sfLR',LR)


def render_test_alta(payload,digest):
    if payload['TipoFactura']!='F1' or alta_hash(payload)!=digest:
        raise ValueError('Registro de alta F1 inconsistente.')
    def node(parent,name,value=None,ns=SF):
        e=ET.SubElement(parent,'{'+ns+'}'+name)
        if value is not None:e.text=str(value)
        return e
    root=ET.Element('{'+LR+'}RegFactuSistemaFacturacion')
    # Deliberately unmistakable for private offline validation artifacts.
    root.append(ET.Comment('SYNTHETIC TEST ONLY - NOT SUBMITTED TO AEAT'))
    obligor=node(node(root,'Cabecera',ns=LR),'ObligadoEmision')
    node(obligor,'NombreRazon',payload['NombreRazonEmisor']);node(obligor,'NIF',payload['IDEmisorFactura'])
    alta=node(node(root,'RegistroFactura',ns=LR),'RegistroAlta')
    node(alta,'IDVersion','1.0');identity=node(alta,'IDFactura')
    for k in ('IDEmisorFactura','NumSerieFactura','FechaExpedicionFactura'):node(identity,k,payload[k])
    for k in ('NombreRazonEmisor','TipoFactura','FechaOperacion','DescripcionOperacion'):node(alta,k,payload[k])
    recipient=payload['Destinatario'];dest=node(node(alta,'Destinatarios'),'IDDestinatario')
    node(dest,'NombreRazon',recipient['name'])
    if recipient['identification_type']=='NIF':node(dest,'NIF',recipient['tax_id'])
    else:
        other=node(dest,'IDOtro');node(other,'CodigoPais',recipient['identification_country'])
        node(other,'IDType',recipient['identification_type']);node(other,'ID',recipient['tax_id'])
    # Fiscal detail aggregates identical profiles, while invoice source lines
    # remain separate. No quota recomputation/rounding from summed bases.
    groups={}
    for row in payload['Desglose']:
        key=tuple(sorted((k,v) for k,v in row.items() if k not in ('BaseImponibleOimporteNoSujeto','CuotaRepercutida')))
        item=groups.setdefault(key,{**dict(key),'BaseImponibleOimporteNoSujeto':Decimal('0.00')})
        item['BaseImponibleOimporteNoSujeto']+=Decimal(row['BaseImponibleOimporteNoSujeto'])
        if 'CuotaRepercutida' in row:item['CuotaRepercutida']=item.get('CuotaRepercutida',Decimal('0.00'))+Decimal(row['CuotaRepercutida'])
    if not 1<=len(groups)<=12:raise ValueError('Número de desgloses no soportado.')
    detail=node(alta,'Desglose')
    for row in groups.values():
        part=node(detail,'DetalleDesglose')
        for k in ('Impuesto','ClaveRegimen','CalificacionOperacion','OperacionExenta','TipoImpositivo','BaseImponibleOimporteNoSujeto','CuotaRepercutida'):
            if k in row:node(part,k,row[k])
    for k in ('CuotaTotal','ImporteTotal'):node(alta,k,payload[k])
    chain=node(alta,'Encadenamiento')
    if payload['RegistroAnterior']:
        previous=node(chain,'RegistroAnterior')
        for k in ('IDEmisorFactura','NumSerieFactura','FechaExpedicionFactura'):node(previous,k,payload['RegistroAnterior'][k])
        node(previous,'Huella',payload['Huella'])
    else:node(chain,'PrimerRegistro','S')
    sif=node(alta,'SistemaInformatico');system=payload['SistemaInformatico']
    for k,source in (('NombreRazon','producer_name'),('NIF','producer_nif'),('NombreSistemaInformatico','name'),
        ('IdSistemaInformatico','id'),('Version','version'),('NumeroInstalacion','installation')):node(sif,k,system[source])
    node(sif,'TipoUsoPosibleSoloVerifactu','S');node(sif,'TipoUsoPosibleMultiOT','S')
    node(sif,'IndicadorMultiplesOT',payload.get('multiple_taxpayers','N'))
    node(alta,'FechaHoraHusoGenRegistro',payload['FechaHoraHusoGenRegistro']);node(alta,'TipoHuella','01');node(alta,'Huella',digest)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
