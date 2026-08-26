const RMGantt = {
    DAY_MS: 86400000,
    MIN_MONTH_WIDTH: 84,
    LABEL_WIDTH_DESKTOP: 240,
    LABEL_WIDTH_MOBILE: 150,
    HEADER_MONTHS: ["ene","feb","mar","abr","may","jun","jul","ago","sept","oct","nov","dic"],
    SHORT_MONTHS: ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"],

    init() {
        this.root=document.getElementById("ganttRoot"); if(!this.root)return;
        this.status=document.getElementById("ganttStatus");this.propertyFilter=document.getElementById("ganttPropertyFilter");this.inactive=document.getElementById("ganttInactive");
        this.data=JSON.parse(document.getElementById("ganttInitialData").textContent);this.viewMonths=Number(this.root.dataset.viewMonths)||8;this.bindControls();this.updateViewButtons();this.render();this.scrollToToday();this.observeSize();
    },
    parseDate(value){const [y,m,d]=value.split("-").map(Number);return Date.UTC(y,m-1,d);},
    isoDate(ms){return new Date(ms).toISOString().slice(0,10);},
    labelWidth(){return window.matchMedia("(max-width: 768px)").matches?this.LABEL_WIDTH_MOBILE:this.LABEL_WIDTH_DESKTOP;},
    buildMonths(){
        const months=[],windowStart=this.parseDate(this.data.window.start),windowEnd=this.parseDate(this.data.window.end);let cursor=windowStart;
        while(cursor<windowEnd){const current=new Date(cursor),naturalEnd=Date.UTC(current.getUTCFullYear(),current.getUTCMonth()+1,1),end=Math.min(naturalEnd,windowEnd);months.push({start:cursor,end,days:(end-cursor)/this.DAY_MS,date:current});cursor=end;}
        return months;
    },
    calculateMonthWidth(){const usable=Math.max(1,this.root.clientWidth-this.labelWidth());return Math.max(this.MIN_MONTH_WIDTH,usable/this.months.length);},
    datePosition(value){
        const instant=typeof value==="number"?value:this.parseDate(value),windowStart=this.parseDate(this.data.window.start),windowEnd=this.parseDate(this.data.window.end);
        if(instant<=windowStart)return 0;if(instant>=windowEnd)return this.months.length*this.monthWidth;
        const index=this.months.findIndex(month=>instant>=month.start&&instant<month.end),month=this.months[index],dayIndex=(instant-month.start)/this.DAY_MS;
        return (index+dayIndex/month.days)*this.monthWidth;
    },
    dateAtPosition(x){
        const safeX=Math.max(0,Math.min(x,this.months.length*this.monthWidth)),index=Math.min(this.months.length-1,Math.floor(safeX/this.monthWidth)),month=this.months[index],fraction=(safeX-index*this.monthWidth)/this.monthWidth,dayIndex=Math.min(month.days-1,Math.floor(fraction*month.days+1e-9));
        return month.start+dayIndex*this.DAY_MS;
    },
    bindControls(){
        document.getElementById("ganttToday").addEventListener("click",()=>this.loadDefault());
        document.getElementById("ganttPrevious").addEventListener("click",()=>this.shiftWindow(-1));
        document.getElementById("ganttNext").addEventListener("click",()=>this.shiftWindow(1));
        document.querySelectorAll(".gantt-view-button").forEach(button=>button.addEventListener("click",()=>this.setView(Number(button.dataset.months))));
        this.propertyFilter.addEventListener("change",()=>this.load());this.inactive.addEventListener("change",()=>this.load());
    },
    observeSize(){
        if(!window.ResizeObserver)return;
        this.resizeObserver=new ResizeObserver(()=>{cancelAnimationFrame(this.resizeFrame);this.resizeFrame=requestAnimationFrame(()=>this.renderPreservingCenter());});
        this.resizeObserver.observe(this.root);
    },
    renderPreservingCenter(){
        if(!this.monthWidth)return;const centerDate=this.dateAtPosition(Math.max(0,this.root.scrollLeft+this.root.clientWidth/2-this.labelWidth()));
        this.render();this.root.scrollLeft=Math.max(0,this.labelWidth()+this.datePosition(centerDate)-this.root.clientWidth/2);
    },
    shiftWindow(months){const s=new Date(this.parseDate(this.data.window.start)),e=new Date(this.parseDate(this.data.window.end));s.setUTCMonth(s.getUTCMonth()+months);e.setUTCMonth(e.getUTCMonth()+months);this.load(this.isoDate(s),this.isoDate(e));},
    loadDefault(){this.loadContextWindow(true);},
    setView(months){if(![4,8,12].includes(months)||months===this.viewMonths)return;this.viewMonths=months;this.updateViewButtons();this.updateUrlView();this.loadContextWindow(true);},
    updateViewButtons(){document.querySelectorAll(".gantt-view-button").forEach(button=>{const active=Number(button.dataset.months)===this.viewMonths;button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});},
    updateUrlView(){const url=new URL(window.location.href);url.searchParams.set("view",String(this.viewMonths));if(this.propertyFilter.value)url.searchParams.set("property_id",this.propertyFilter.value);else url.searchParams.delete("property_id");if(this.inactive.checked)url.searchParams.set("include_inactive","true");else url.searchParams.delete("include_inactive");history.replaceState({},"",url);},
    loadContextWindow(scrollToday){const t=new Date(this.parseDate(this.data.window.today)),s=new Date(Date.UTC(t.getUTCFullYear(),t.getUTCMonth()-1,1)),e=new Date(Date.UTC(s.getUTCFullYear(),s.getUTCMonth()+this.viewMonths,1));this.load(this.isoDate(s),this.isoDate(e),scrollToday);},
    async load(start=this.data.window.start,end=this.data.window.end,scrollToday=false){
        this.updateUrlView();
        const params=new URLSearchParams({start,end,include_inactive:String(this.inactive.checked)});if(this.propertyFilter.value)params.set("property_id",this.propertyFilter.value);
        this.root.classList.add("gantt-loading");this.status.textContent="Actualizando calendario…";
        try{const response=await fetch(`/gantt/data?${params}`);if(!response.ok)throw new Error();this.data=await response.json();this.render();if(scrollToday)this.scrollToToday();this.status.textContent="Calendario actualizado.";}
        catch(error){RMNotification.error("No se ha podido cargar el calendario.");this.status.textContent="Error al actualizar el calendario.";}
        finally{this.root.classList.remove("gantt-loading");}
    },
    render(){
        this.months=this.buildMonths();this.monthWidth=this.calculateMonthWidth();this.root.replaceChildren();const canvas=document.createElement("div");canvas.className="gantt-canvas";const width=this.months.length*this.monthWidth;canvas.append(this.header(width));
        for(const property of this.data.properties)for(const room of property.rooms)canvas.append(this.roomRow(room,width));
        if(!this.data.properties.length){const empty=document.createElement("div");empty.className="gantt-empty";empty.textContent="No hay habitaciones para los filtros seleccionados.";canvas.append(empty);}this.root.append(canvas);
    },
    header(width){
        const row=document.createElement("div");row.className="gantt-header";const label=document.createElement("div");label.className="gantt-label";label.textContent="Habitación";
        const timeline=document.createElement("div");timeline.className="gantt-timeline gantt-header-timeline";timeline.style.width=`${width}px`;
        this.months.forEach((segment,index)=>{const month=document.createElement("div");month.className="gantt-month";month.style.left=`${index*this.monthWidth}px`;month.style.width=`${this.monthWidth}px`;month.textContent=`${this.HEADER_MONTHS[segment.date.getUTCMonth()]} ${segment.date.getUTCFullYear()}`;timeline.append(month);});
        this.addMonthBoundaries(timeline);this.addTodayLine(timeline);row.append(label,timeline);return row;
    },
    roomRow(room,width){
        const maxLane=Math.max(0,...room.bookings.map(item=>item.lane)),height=Math.max(38,(maxLane+1)*34+4),row=document.createElement("div");row.className="gantt-room-row";
        const label=document.createElement("div");label.className="gantt-label";label.style.height=`${height}px`;const identity=document.createElement("div");identity.className="gantt-room-identity";const details=document.createElement("div");details.className="gantt-room-details";const link=document.createElement("a");link.className="gantt-room-link";link.href=`/rooms/${room.id}`;link.textContent=room.code;if(!room.active)link.insertAdjacentHTML("beforeend",' <span class="badge text-bg-secondary">Archivada</span>');details.append(link);identity.append(details);
        label.append(identity);if(["error","overdue","paused"].includes(room.sync.severity)){const sync=document.createElement("a");sync.href=`/rooms/${room.id}#configuracion`;sync.className=`gantt-sync-warning gantt-sync-${room.sync.severity}`;sync.textContent="⚠";sync.setAttribute("aria-label",this.syncLabel(room.sync));sync.title=this.syncLabel(room.sync);label.append(sync);}
        const timeline=document.createElement("div");timeline.className="gantt-timeline gantt-room-timeline";timeline.style.cssText=`width:${width}px;height:${height}px`;this.addMonthBoundaries(timeline);for(const booking of room.bookings)timeline.append(this.bookingBar(booking));this.addTodayLine(timeline);row.append(label,timeline);return row;
    },
    bookingBar(booking){
        const bar=document.createElement("button");bar.type="button";bar.className="gantt-booking";if(booking.overlap_kind)bar.classList.add(`gantt-overlap-${booking.overlap_kind}`);
        const hue=[...booking.origin.color_key].reduce((v,c)=>(v*31+c.charCodeAt(0))%360,17),visibleStart=booking.check_in<this.data.window.start?this.data.window.start:booking.check_in,visibleEnd=booking.check_out>this.data.window.end?this.data.window.end:booking.check_out,left=this.datePosition(visibleStart),width=this.datePosition(visibleEnd)-left,paintedWidth=Math.max(2,width),inset=Math.min(1,paintedWidth/4),leftInset=booking.check_in<this.data.window.start?0:inset,rightInset=booking.check_out>this.data.window.end?0:inset;
        bar.style.cssText=`left:${left}px;width:${paintedWidth}px;top:${booking.lane*34+2}px`;
        const visual=document.createElement("span");visual.className="gantt-booking-visual";visual.classList.add(booking.origin.slug==="manual"?"gantt-origin-manual":"gantt-origin-platform");visual.style.cssText=`--origin-hue:${hue};--booking-inset-left:${leftInset}px;--booking-inset-right:${rightInset}px`;
        this.fillBookingContent(visual,booking,Math.max(0,paintedWidth-leftInset-rightInset));bar.append(visual);
        const overlap=booking.overlap_kind==="historical"?" Coincidencia histórica.":booking.overlap_kind==="operational"?" Anomalía de solapamiento.":"",detail=`${booking.guest_name}. Entrada: ${this.formatDate(booking.check_in)}. Salida: ${this.formatDate(booking.check_out)}. Origen: ${booking.origin.name}. ${booking.editable?"Manual":"Importada, solo lectura"}.${overlap}`;bar.title=detail;bar.setAttribute("aria-label",detail);bar.addEventListener("click",event=>{event.stopPropagation();BookingUI.openEditModal(booking.id,!booking.editable);});return bar;
    },
    fillBookingContent(bar,booking,width){
        const fullRange=`${this.formatHumanDate(booking.check_in,true)} – ${this.formatHumanDate(booking.check_out,true)}`,shortRange=`${this.formatHumanDate(booking.check_in,false)}–${this.formatHumanDate(booking.check_out,false)}`;
        if(width>=220){bar.classList.add("gantt-booking-full");bar.append(this.bookingLine(`${booking.guest_name} · ${booking.origin.name}`,"gantt-booking-primary"),this.bookingLine(fullRange,"gantt-booking-dates"));}
        else if(width>=130){bar.classList.add("gantt-booking-medium");bar.append(this.bookingLine(booking.guest_name,"gantt-booking-primary"),this.bookingLine(shortRange,"gantt-booking-dates"));}
        else if(width>=65){bar.classList.add("gantt-booking-short");bar.append(this.bookingLine(shortRange,"gantt-booking-dates"));}
        else{bar.classList.add("gantt-booking-minimal");bar.textContent="•";}
    },
    bookingLine(text,className){const line=document.createElement("span");line.className=className;line.textContent=text;return line;},
    addMonthBoundaries(timeline){
        for(let index=1;index<this.months.length;index++){const boundary=document.createElement("div");boundary.className="gantt-month-boundary";boundary.style.left=`${index*this.monthWidth}px`;timeline.append(boundary);}
    },
    addTodayLine(timeline){const today=this.parseDate(this.data.window.today),start=this.parseDate(this.data.window.start),end=this.parseDate(this.data.window.end);if(today<start||today>=end)return;const line=document.createElement("div");line.className="gantt-today-column";line.style.left=`${this.datePosition(today)}px`;timeline.append(line);},
    scrollToToday(){const today=this.parseDate(this.data.window.today),start=this.parseDate(this.data.window.start),end=this.parseDate(this.data.window.end);if(today>=start&&today<end)this.root.scrollLeft=Math.max(0,this.labelWidth()+this.datePosition(today)-this.root.clientWidth/2);},
    syncLabel(sync){if(!sync.platforms.length)return "Sin importaciones configuradas";return sync.platforms.map(item=>`${item.name}: ${item.state}`).join("; ");},
    formatDate(value){return value.split("-").reverse().join("/");},
    formatHumanDate(value,year){const date=new Date(this.parseDate(value));return `${date.getUTCDate()} ${this.SHORT_MONTHS[date.getUTCMonth()]}${year?` ${date.getUTCFullYear()}`:""}`;}
};
document.addEventListener("DOMContentLoaded",()=>RMGantt.init());
