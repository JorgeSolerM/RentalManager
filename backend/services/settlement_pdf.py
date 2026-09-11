"""Compact A4 presentation of a frozen, individual settlement payload."""
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
import re
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, CondPageBreak

RENDERER_VERSION = 3
ZERO = Decimal('0.00')


def euros(value):
    return f'{Decimal(str(value)):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' €'


def human_date(value):
    return date.fromisoformat(str(value)[:10]).strftime('%d/%m/%Y')


def render_settlement_pdf(payload, generated):
    output = BytesIO()
    ink,rule,tint = (colors.HexColor(v) for v in ('#25362d','#ced6d0','#edf2ee'))
    document = SimpleDocTemplate(output,pagesize=A4,leftMargin=15*mm,rightMargin=15*mm,
        topMargin=14*mm,bottomMargin=16*mm,title=f"Liquidación {payload['id']}",author=payload['identity']['issuer'])
    body=ParagraphStyle('Body',fontName='Helvetica',fontSize=9,leading=11.5,textColor=ink)
    styles={'body':body,'right':ParagraphStyle('Right',parent=body,alignment=TA_RIGHT),
        'bold':ParagraphStyle('Bold',parent=body,fontName='Helvetica-Bold'),
        'boldright':ParagraphStyle('BoldRight',parent=body,fontName='Helvetica-Bold',alignment=TA_RIGHT),
        'brand':ParagraphStyle('Brand',parent=body,fontName='Helvetica-Bold',fontSize=19,leading=23),
        'title':ParagraphStyle('Title',parent=body,fontName='Helvetica-Bold',fontSize=13,leading=17,alignment=TA_RIGHT),
        'section':ParagraphStyle('Section',parent=body,fontName='Helvetica-Bold',fontSize=9.5,leading=13,spaceBefore=10,spaceAfter=4),
        'small':ParagraphStyle('Small',parent=body,fontSize=8,leading=10,textColor=colors.HexColor('#5b655e'))}
    def p(value,style='body'):
        text=str(value or '').replace('\u2011','-').replace('\u2013','-').replace('\u2014','-')
        text=re.sub(r'\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b','[cuenta omitida]',text)
        return Paragraph(escape(text).replace('\n','<br/>'),styles[style])
    def sum_rows(rows,field='amount'):
        return sum((Decimal(r.get(field,'0')) for r in rows),ZERO)
    story=[]
    header=payload['identity']; properties=header['properties']; multiple=len(properties)>1
    period=f"{human_date(payload['start'])} - {human_date(date.fromisoformat(payload['end'])-timedelta(days=1))}"
    top=Table([[[p(header['issuer'],'brand'),p(header['manager'],'small'),p(header['email'],'small')],
        [p('LIQUIDACIÓN','title'),p(f"N.º {payload['id']} · Fecha {human_date(payload['closed_at'])}",'right'),p(period,'right')]]],colWidths=[86*mm,94*mm])
    top.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    story.append(top)
    identity=[['Propietario',header['owner']],['Fincas incluidas' if multiple else 'Finca',str(len(properties)) if multiple else next(iter(properties.values()),'No indicada')]]
    identity_table=Table([[p(a,'bold'),p(b)] for a,b in identity],colWidths=[30*mm,150*mm])
    identity_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),tint),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(identity_table)
    def table(headings,rows,widths):
        data=[[p(h,'boldright' if i==len(headings)-1 else 'bold') for i,h in enumerate(headings)]]
        data += [[p(cell,'right' if i==len(row)-1 else 'body') for i,cell in enumerate(row)] for row in rows]
        result=Table(data,colWidths=[v*mm for v in widths],repeatRows=1,hAlign='LEFT')
        result.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),tint),
            ('LINEBELOW',(0,0),(-1,0),.7,ink),('LINEBELOW',(0,1),(-1,-1),.25,rule),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        story.append(result)
    def section(title):
        # Reserve a heading and first row, not the entire potentially long table.
        story.append(CondPageBreak(90))
        story.append(p(title,'section'))
    def total(label,value):
        t=Table([[p(label,'bold'),p(euros(value),'boldright')]],colWidths=[143*mm,37*mm])
        t.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.6,ink),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
        story.append(t)
    def grouped(rows):
        groups=OrderedDict()
        for row in rows:
            groups.setdefault(str(row.get('property_id')),[]).append(row)
        return groups.items()
    income=[r for r in payload['rows'] if r['kind']=='income' and not r.get('reversal_of')]
    expenses=[r for r in payload['rows'] if r['kind']=='expense' and not r.get('reversal_of')]
    adjustments=[r for r in payload['rows'] if r.get('reversal_of')]
    section('RELACIÓN DE COBROS')
    for property_id,rows in grouped(income):
        if multiple:
            story.append(p(properties.get(property_id,'Finca no indicada'),'section'))
        table(['Inmueble / Habitación','Inquilino','Concepto','Cobrado'],
            [[r.get('room') or '-',header['references'].get(r['key'],{}).get('tenant') or '-',r['concept'],euros(r['amount'])] for r in rows],[36,43,71,30])
    if not income:
        story.append(p('Sin cobros.','small'))
    total('TOTAL COBROS',sum_rows(income))
    if expenses:
        section('RELACIÓN DE GASTOS')
        for property_id,rows in grouped(expenses):
            if multiple:
                story.append(p(properties.get(property_id,'Finca no indicada'),'section'))
            table(['Fecha','Concepto','Importe'],[[human_date(r['date']),r['concept'],euros(r['amount'])] for r in rows],[29,121,30])
        total('TOTAL GASTOS',sum_rows(expenses))
    else:
        story += [Spacer(1,5),p('Sin gastos.','small')]
    fee_groups=OrderedDict()
    for r in income:
        key=(str(r.get('property_id')),r.get('fee_terms_id'),str(r.get('fee_percentage','0')))
        fee_groups.setdefault(key,[]).append(r)
    if fee_groups:
        section('HONORARIOS DE GESTIÓN')
        fees=[]
        for (property_id,_,percentage),rows in fee_groups.items():
            pct=format(Decimal(percentage).normalize(),'f').replace('.',',')+' %'
            fees.append([properties.get(property_id,'Finca'),euros(sum_rows(rows)),pct,euros(sum_rows(rows,'fee'))])
        if len(fees)==1:
            _,base,pct,amount=fees[0]
            compact=Table([[p('Base: '+base),p('Porcentaje: '+pct),p('Honorarios: '+amount,'boldright')]],colWidths=[66*mm,49*mm,65*mm])
            compact.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
            story.append(compact)
        else:
            table(['Finca','Base cobrada','Porcentaje','Honorarios'],fees,[83,35,27,35])
    if adjustments:
        section('AJUSTES')
        lines=[]
        for r in adjustments:
            sign=Decimal('1') if r['kind']=='income' else Decimal('-1')
            lines.append([('Devolución de cobro: ' if r['kind']=='income' else 'Devolución de gasto: ')+r['concept'],euros(sign*Decimal(r['amount']))])
            if Decimal(r.get('fee','0')):
                lines.append(['Regularización honorarios',euros(-Decimal(r['fee']))])
        table(['Concepto','Importe'],lines,[145,35])
    t=payload['totals']
    # Presentation bridge only: the frozen economic result remains authoritative.
    gross_income,gross_expense,gross_fee=sum_rows(income),sum_rows(expenses),sum_rows(income,'fee')
    # Older closed snapshots keep their original economic semantics. Do not
    # retrofit a carry into their immutable result when regenerating a PDF.
    prior=Decimal(t['prior_balance'])
    final_balance=Decimal(t['economic_balance'])
    period_balance=Decimal(t.get('period_balance',t['economic_balance']))
    adjustment=period_balance-(gross_income-gross_expense-gross_fee)
    summary_rows=[('Total cobros',gross_income),('Total gastos',-gross_expense),('Honorarios',-gross_fee)]
    if adjustment:
        summary_rows.append(('Ajustes',adjustment))
    if prior and 'period_balance' in t:
        summary_rows += [('Resultado del periodo',period_balance),('Saldo anterior / compensación',prior)]
    summary_rows.append(('RESULTADO LIQUIDACIÓN',final_balance))
    direct,manager,difference=(Decimal(t[field]) for field in ('directly_received','manager_held_funds','inter_owner_difference'))
    if direct:
        summary_rows.append(('Recibido directamente por propietario',direct))
    if manager and (direct or difference):
        summary_rows.append(('Fondos bajo custodia del gestor',manager))
    if prior and 'period_balance' not in t:
        summary_rows.append(('Saldo anterior de fondos',prior))
    credit=Decimal(t.get('manager_credit',str(max(ZERO,-Decimal(t.get('carry_forward','0'))))))
    if credit:
        summary_rows.append(('SALDO A FAVOR DEL GESTOR',credit))
    paid=Decimal(payload['paid'])
    if paid:
        summary_rows += [('A transferir al cierre',Decimal(t['payout_due'])),('Pagado al propietario',paid),('PENDIENTE',Decimal(payload['pending']))]
    else:
        summary_rows.append(('A TRANSFERIR AL PROPIETARIO' if credit else 'PENDIENTE DE TRANSFERIR',Decimal(payload['pending'])))
    summary=Table([[p(label,'bold' if label.isupper() else 'body'),p(euros(value),'boldright' if label.isupper() else 'right')] for label,value in summary_rows],colWidths=[106*mm,36*mm],hAlign='RIGHT')
    commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]
    for i,(label,_) in enumerate(summary_rows):
        if label.isupper():
            commands += [('LINEABOVE',(0,i),(-1,i),.7,ink),('BACKGROUND',(0,i),(-1,i),tint)]
    summary.setStyle(TableStyle(commands))
    story.append(KeepTogether([p('RESUMEN','section'),summary]))
    if difference:
        message='Exceso recibido por copropietario: ' if difference>0 else 'Pendiente de regularización entre copropietarios: '
        story.append(KeepTogether([p('OBSERVACIÓN DE CUSTODIA','section'),p(message+euros(abs(difference)))]))
    if payload['payouts']:
        section('PAGOS AL PROPIETARIO')
        table(['Fecha','Cuenta destino','Importe'],[[human_date(r['date']),'**** '+r['account_suffix'],euros(r['amount'])] for r in payload['payouts']],[35,110,35])
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont('Helvetica',7.5); canvas.setFillColor(colors.HexColor('#69726b'))
        canvas.drawString(15*mm,9*mm,f"Liquidación #{payload['id']} · Documento privado · No es factura")
        canvas.drawRightString(195*mm,9*mm,f'Página {doc.page}'); canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
