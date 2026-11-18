/* Read-only: no booking endpoints, storage, analytics or mutation handlers. */
(() => {
  'use strict';
  const status = document.getElementById('calendar-status');
  const region = document.getElementById('calendar-scroll');
  const period = document.getElementById('calendar-period');
  const previous=document.getElementById('calendar-previous'), next=document.getElementById('calendar-next');
  const navigation=document.getElementById('calendar-navigation'), monthLabel=document.getElementById('calendar-month');
  const header=document.getElementById('calendar-header'), mobileWeeks=document.getElementById('calendar-mobile-weeks');
  const byProperty=document.getElementById('calendar-sort-property'), byAvailability=document.getElementById('calendar-sort-availability');
  let sortMode='property', reorder=()=>{};
  byProperty.addEventListener('click',()=>reorder('property'));
  byAvailability.addEventListener('click',()=>reorder('availability'));
  let selectedMonth=null, navigate=()=>{};
  previous.addEventListener('click',()=>navigate(-1));
  next.addEventListener('click',()=>navigate(1));
  const dayLabel = value => new Intl.DateTimeFormat('es-ES', {timeZone:'UTC'}).format(new Date(value+'T12:00:00Z'));
  const priceLabel = value => {
    if (value === null || value === undefined || String(value).trim() === '') return 'Consultar precio';
    const amount=Number(value);
    return Number.isFinite(amount) && amount>=0
      ? new Intl.NumberFormat('es-ES',{maximumFractionDigits:2}).format(amount)+' €/mes'
      : 'Consultar precio';
  };
  const element = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  function clear(message) {
    region.replaceChildren(); region.hidden = true; period.textContent = ''; status.textContent = message;
    navigation.hidden=true; header.hidden=true; mobileWeeks.replaceChildren(); navigate=()=>{}; reorder=()=>{};
  }
  function render(data) {
    const weeks = [];
    for (let d = new Date(data.start+'T12:00:00Z'); d.toISOString().slice(0,10)<data.end; d.setUTCDate(d.getUTCDate()+1)) {
      const date=d.toISOString().slice(0,10), monday=new Date(d);
      monday.setUTCDate(monday.getUTCDate()-(monday.getUTCDay()+6)%7);
      const key=monday.toISOString().slice(0,10);
      if (!weeks.length || weeks[weeks.length-1].start!==key) weeks.push({start:key,dates:[]});
      weeks[weeks.length-1].dates.push(date);
    }
    const table = element('table', undefined, 'availability-table');
    const caption = element('caption', 'Disponibilidad semanal por finca y habitación'); table.append(caption);
    const head = element('thead'), months = element('tr'), days = element('tr');
    const label = element('th', 'Finca / habitación', 'calendar-label'); label.rowSpan=2; label.scope='col'; months.append(label);
    const monthGroups = [], monthCells=[];
    for (const week of weeks) {
      const value=week.start;
      const key=value.slice(0,7), last=monthGroups[monthGroups.length-1];
      week.month=key;
      week.monthStart=!last || last.key!==key;
      if (last && last.key===key) last.count++; else monthGroups.push({key,count:1,date:value});
      week.clipped=week.dates.length<7;
      week.label=dayLabel(week.dates[0])+' – '+dayLabel(week.dates[week.dates.length-1])+(week.clipped?' (semana limitada al período consultado)':'');
      const short=value=>String(Number(value.slice(8)))+'/'+String(Number(value.slice(5,7)));
      const cell=element('th',short(week.dates[0])+'–'+short(week.dates[week.dates.length-1])+(week.clipped?'*':''),'week'+(week.monthStart?' month-start':''));
      cell.scope='col'; cell.title=week.label; cell.setAttribute('aria-label',week.label); days.append(cell);
      monthCells.push({cell,key});
    }
    for (const group of monthGroups) {
      const cell=element('th', new Intl.DateTimeFormat('es-ES',{month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(group.date+'T12:00:00Z')));
      cell.colSpan=group.count; cell.scope='colgroup'; months.append(cell);
      group.header=cell;
    }
    head.append(months,days); table.append(head);
    let count=0;
    const propertyBodies=[], roomRows=[];
    for (const property of data.properties) {
      const body=element('tbody'), divider=element('tr',undefined,'property-divider');
      const groupName=element('th',property.name,'calendar-label'); groupName.scope='rowgroup';
      const filler=element('th',''); filler.colSpan=weeks.length; divider.append(groupName,filler); body.append(divider);
      const propertyRows=[]; propertyBodies.push({body,divider,rows:propertyRows});
      for (const room of property.rooms) {
        count++; const row=element('tr'), identity=element('th',undefined,'calendar-label'); identity.scope='row';
        const link=element('a',undefined,'room-link'); link.href=room.listing_url; link.target='_blank'; link.rel='noopener noreferrer'; link.referrerPolicy='no-referrer';
        const identifier=room.slug || room.name;
        link.title='Ver anuncio de esta habitación'; link.setAttribute('aria-label',property.name+' · '+identifier+' · Ver anuncio de esta habitación');
        const thumbnail=element('span',undefined,'room-thumbnail'); thumbnail.setAttribute('aria-hidden','true');
        if (room.thumbnail_url) {
          const image=element('img'); image.src=room.thumbnail_url; image.alt=''; image.width=64; image.height=48; image.loading='lazy'; image.decoding='async';
          image.addEventListener('error',()=>image.remove()); thumbnail.append(image);
        }
        link.append(thumbnail,element('span',identifier));
        identity.append(link,element('small',priceLabel(room.price_monthly),'room-price'),element('small',room.available_from ? 'Disponible desde '+dayLabel(room.available_from) : 'Sin disponibilidad ofrecida')); row.append(identity);
        for (const week of weeks) {
          const states=week.dates.map(date=>Boolean(room.available_from) && date>=room.available_from && !room.occupied.some(interval=>interval.start<=date && date<interval.end));
          const available=states.filter(Boolean).length;
          const kind=available===week.dates.length?'available':available?'partial':'occupied';
          const text={occupied:'Ocupado / sin disponibilidad ofrecida',available:'Disponible',partial:'Parcialmente disponible'}[kind];
          const description=week.label+': '+text+' · '+available+' de '+week.dates.length+' días disponibles';
          const cell=element('td',undefined,'week'+(week.monthStart?' month-start':''));
          const block=document.createElementNS('http://www.w3.org/2000/svg','svg');
          block.setAttribute('viewBox','0 0 '+states.length+' 1'); block.setAttribute('preserveAspectRatio','none');
          block.setAttribute('class','week-block'); block.setAttribute('aria-hidden','true'); block.setAttribute('focusable','false');
          for (let start=0;start<states.length;) {
            let end=start+1; while (end<states.length && states[end]===states[start]) end++;
            const segment=document.createElementNS('http://www.w3.org/2000/svg','rect');
            segment.setAttribute('x',String(start)); segment.setAttribute('y','0'); segment.setAttribute('width',String(end-start)); segment.setAttribute('height','1');
            segment.setAttribute('class',states[start]?'day-available':'day-unavailable'); block.append(segment); start=end;
          }
          cell.append(block); monthCells.push({cell,key:week.month});
          cell.setAttribute('aria-label',description); cell.title=description; row.append(cell);
        }
        body.append(row);
        propertyRows.push(row); roomRows.push({row,room});
      }
      table.append(body);
    }
    const left=region.scrollLeft, top=region.scrollTop;
    region.replaceChildren(table); region.hidden=count===0; region.scrollLeft=left; region.scrollTop=top;
    const flatBody=element('tbody');
    // The API's start is today's Europe/Madrid date, not the displayed month.
    const rank=room=>!room.available_from || room.available_from>=data.end ? 2 : room.available_from<=data.start ? 0 : 1;
    const ordered=roomRows.slice().sort((a,b)=>rank(a.room)-rank(b.room)
      || (rank(a.room)===1 ? a.room.available_from.localeCompare(b.room.available_from) : 0)
      || (a.room.slug || a.room.name).localeCompare(b.room.slug || b.room.name,'es')
      || a.room.listing_url.localeCompare(b.room.listing_url));
    reorder=(mode,preserve=true)=>{
      const pageTop=window.scrollY, innerTop=region.scrollTop;
      const mobile=window.matchMedia('(max-width:768px)').matches;
      const scrolled=mobile ? header.getBoundingClientRect().top<=0 : innerTop>0;
      const boundary=mobile ? Math.max(0,header.getBoundingClientRect().bottom) : region.getBoundingClientRect().top+80;
      const visible=roomRows.map(item=>({row:item.row,rect:item.row.getBoundingClientRect()}))
        .filter(item=>item.rect.bottom>boundary).sort((a,b)=>a.rect.top-b.rect.top)[0];
      sortMode=mode;
      if (mode==='availability') {
        flatBody.replaceChildren(...ordered.map(item=>item.row)); table.replaceChildren(head,flatBody);
      } else {
        for (const group of propertyBodies) group.body.replaceChildren(group.divider,...group.rows);
        table.replaceChildren(head,...propertyBodies.map(group=>group.body));
      }
      byProperty.setAttribute('aria-pressed',String(mode==='property'));
      byAvailability.setAttribute('aria-pressed',String(mode==='availability'));
      if (preserve) {
        const delta=scrolled && visible ? visible.row.getBoundingClientRect().top-visible.rect.top : 0;
        if (mobile) window.scrollTo({top:pageTop+delta,behavior:'instant'});
        else {region.scrollTop=innerTop+delta; window.scrollTo({top:pageTop,behavior:'instant'});}
      }
    };
    reorder(sortMode,false);
    function selectMonth(key,scroll=false) {
      const pageTop=window.scrollY;
      const index=Math.max(0,monthGroups.findIndex(group=>group.key===key)), group=monthGroups[index];
      if (!group) return;
      selectedMonth=group.key;
      for (const item of monthCells) item.cell.className=item.cell.className.replace(' selected-week','')+(item.key===selectedMonth?' selected-week':'');
      table.setAttribute('data-week-count',String(group.count));
      mobileWeeks.setAttribute('data-week-count',String(group.count));
      mobileWeeks.replaceChildren(...weeks.filter(week=>week.month===selectedMonth).map(week=>{
        const source=monthCells.find(item=>item.cell.scope==='col' && item.cell.title===week.label).cell;
        const heading=element('span',source.textContent); heading.title=week.label; heading.setAttribute('aria-label',week.label); return heading;
      }));
      monthLabel.textContent=new Intl.DateTimeFormat('es-ES',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(group.date+'T12:00:00Z'));
      previous.disabled=index===0; next.disabled=index===monthGroups.length-1;
      if (scroll) region.scrollLeft=Math.max(0,group.header.offsetLeft-label.offsetWidth);
      // Column replacement must not let browser scroll anchoring move the reader.
      if (scroll) window.scrollTo({top:pageTop,behavior:'instant'});
    }
    selectMonth(selectedMonth);
    navigation.hidden=count===0;
    header.hidden=count===0;
    navigate=direction=>{
      const index=monthGroups.findIndex(group=>group.key===selectedMonth), group=monthGroups[index+direction];
      if (group) selectMonth(group.key,true);
    };
    period.textContent=dayLabel(data.start)+' — '+dayLabel(data.last_day)+' · Europe/Madrid';
    status.textContent=count?count+' habitaciones · Consulta actualizada':'No hay habitaciones con disponibilidad definitiva en estos seis meses.';
  }
  async function refresh() {
    try {
      const response=await fetch('/colaboradores/disponibilidad/data',{method:'GET',cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer'});
      if (!response.ok) { clear('No se pudo actualizar la disponibilidad. Vuelve a intentarlo más tarde.'); return; }
      render(await response.json());
    } catch (_) { clear('No se pudo actualizar la disponibilidad. Vuelve a abrir el enlace.'); }
  }
  refresh();
  setInterval(refresh,60000);
})();
