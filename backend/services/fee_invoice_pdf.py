"""Deterministic private invoice PDF, only from the immutable issued snapshot."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget


def render_invoice(snapshot):
    if not snapshot.get('synthetic') or not snapshot.get('number'):
        raise ValueError('Solo se generan documentos de prueba emitidos.')
    output=BytesIO()
    doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,
        topMargin=16*mm,bottomMargin=18*mm,title='Factura sintética de honorarios',author='RentalManager - pruebas')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallInvoice',fontName='Helvetica',fontSize=9,leading=12,spaceAfter=4))
    styles.add(ParagraphStyle(name='InvoiceHeading',fontName='Helvetica-Bold',fontSize=19,leading=23,textColor=colors.HexColor('#195e45')))
    def p(value,style='SmallInvoice'): return Paragraph(escape(str(value)),styles[style])
    qr=QrCodeWidget(snapshot['qr_url'],barLevel='M')
    bounds=qr.getBounds();size=34*mm
    drawing=Drawing(size,size,transform=[size/(bounds[2]-bounds[0]),0,0,size/(bounds[3]-bounds[1]),0,0]);drawing.add(qr)
    story=[Table([[p('FACTURA DE PRUEBA','InvoiceHeading'),drawing]],colWidths=[135*mm,39*mm]),
        p('SIMULACIÓN SIN VALIDEZ FISCAL - NO REMITIDA A AEAT'),
        p('VERI*FACTU · QR del entorno de pruebas. No acredita recepción por AEAT.'),Spacer(1,4*mm),
        p(snapshot['number'],'Heading2'),p(f"Expedición: {snapshot['issue_date']} · Operación: {snapshot['operation_date']}"),
        p(f"Liquidación del periodo: {snapshot['period_start']} / {snapshot['period_end']} (fin exclusivo)"),Spacer(1,4*mm)]
    def identity(data):
        return [p(data['name']),p(data['tax_id']),p(data['address']),
                p(f"{data['postal_code']} {data['city']} · {data.get('province','')} · {data['country']}")]
    story += [Table([[p('EMISOR','Heading3'),p('DESTINATARIO','Heading3')],
                     [identity(snapshot['issuer']),identity(snapshot['recipient'])]],colWidths=[87*mm,87*mm]),Spacer(1,6*mm)]
    rows=[[p('Finca / concepto'),p('Base'),p('IVA'),p('Retención'),p('Neto')]]
    for line in snapshot['lines']:
        tax=line['snapshot']
        rows.append([p(f"{line['property_name']} - {line['concept']}\nOperación {tax['operation_date']}"),
            p(tax['fee_base']+' €'),p(tax['fee_vat']+' €'),p(tax['fee_withholding']+' €'),p(tax['net_payable']+' €')])
    table=Table(rows,colWidths=[74*mm,25*mm,25*mm,25*mm,25*mm],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf2ed')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#195e45')),
        ('BOTTOMPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6)]))
    story += [table,Spacer(1,6*mm)]
    totals=[]
    for key,label in [('fee_base','Base imponible'),('fee_vat','IVA'),('fee_withholding','Retención'),
                      ('gross_invoice_total','TOTAL FACTURA FISCAL'),('net_payable','NETO A PAGAR / COMPENSAR')]:
        totals.append([p(label),p(snapshot[key]+' €')])
    story.append(KeepTogether(Table(totals,colWidths=[135*mm,39*mm])))
    for mention in dict.fromkeys(l['snapshot'].get('legal_mention') for l in snapshot['lines']):
        if mention: story.append(p(mention))
    story += [Spacer(1,5*mm),p('La emisión de este documento no registra ni repite un cobro o compensación.')]
    def footer(canvas,document):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.grey)
        canvas.drawString(18*mm,11*mm,'RentalManager · Documento sintético · Sin validez fiscal')
        canvas.drawRightString(192*mm,11*mm,str(document.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
