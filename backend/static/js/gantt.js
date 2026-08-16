const RMGantt = {
    DAY_MS: 86400000, DAY_WIDTH: 28,
    MONTHS: ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"],
    WEEKDAYS: ["D","L","M","X","J","V","S"],
    init() {
        this.root=document.getElementById("ganttRoot"); if(!this.root)return;
        this.status=document.getElementById("ganttStatus"); this.propertyFilter=document.getElementById("ganttPropertyFilter"); this.inactive=document.getElementById("ganttInactive");
        this.data=JSON.parse(document.getElementById("ganttInitialData").textContent); this.bindControls(); this.render(); this.scrollToToday();
    },
    parseDate(value) { const [y,m,d]=value.split("-").map(Number); return Date.UTC(y,m-1,d); },
    isoDate(ms) { return new Date(ms).toISOString().slice(0,10); },
    dayOffset(value,start=this.data.window.start) { return Math.round((this.parseDate(value)-this.parseDate(start))/this.DAY_MS); },
    bindControls() {
        document.getElementById("ganttToday").addEventListener("click",()=>this.loadDefault());
        document.getElementById("ganttPrevious").addEventListener("click",()=>this.shiftWindow(-3));
        document.getElementById("ganttNext").addEventListener("click",()=>this.shiftWindow(3));
        this.propertyFilter.addEventListener("change",()=>this.load()); this.inactive.addEventListener("change",()=>this.load());
    },
    shiftWindow(months) { const s=new Date(this.parseDate(this.data.window.start)),e=new Date(this.parseDate(this.data.window.end)); s.setUTCMonth(s.getUTCMonth()+months);e.setUTCMonth(e.getUTCMonth()+months);this.load(this.isoDate(s),this.isoDate(e)); },
    loadDefault() { const t=new Date(this.parseDate(this.data.window.today));const s=new Date(Date.UTC(t.getUTCFullYear(),t.getUTCMonth()-1,1));const e=new Date(Date.UTC(s.getUTCFullYear(),s.getUTCMonth()+6,1));this.load(this.isoDate(s),this.isoDate(e),true); },
    async load(start=this.data.window.start,end=this.data.window.end,scrollToday=false) {
        const params=new URLSearchParams({start,end,include_inactive:String(this.inactive.checked)});if(this.propertyFilter.value)params.set("property_id",this.propertyFilter.value);
        this.root.classList.add("gantt-loading");this.status.textContent="Actualizando calendario…";
        try { const response=await fetch(`/gantt/data?${params}`);if(!response.ok)throw new Error();this.data=await response.json();this.render();if(scrollToday)this.scrollToToday();this.status.textContent="Calendario actualizado."; }
        catch(error){ RMNotification.error("No se ha podido cargar el calendario.");this.status.textContent="Error al actualizar el calendario."; }
        finally { this.root.classList.remove("gantt-loading"); }
    },
    render() {
        this.root.replaceChildren();const canvas=document.createElement("div");canvas.className="gantt-canvas";const width=this.data.window.day_count*this.DAY_WIDTH;canvas.append(this.header(width));
        for(const property of this.data.properties){for(const room of property.rooms)canvas.append(this.roomRow(room,width));}
        if(!this.data.properties.length){const empty=document.createElement("div");empty.className="gantt-empty";empty.textContent="No hay habitaciones para los filtros seleccionados.";canvas.append(empty);}this.root.append(canvas);
    },
    header(width) {
        const row=document.createElement("div");row.className="gantt-header";const label=document.createElement("div");label.className="gantt-label";label.textContent="Habitación";
        const timeline=document.createElement("div");timeline.className="gantt-timeline gantt-header-timeline";timeline.style.width=`${width}px`;let cursor=this.parseDate(this.data.window.start),end=this.parseDate(this.data.window.end);
        while(cursor<end){const current=new Date(cursor),next=Date.UTC(current.getUTCFullYear(),current.getUTCMonth()+1,1),segmentEnd=Math.min(next,end),month=document.createElement("div");month.className="gantt-month";month.style.left=`${((cursor-this.parseDate(this.data.window.start))/this.DAY_MS)*this.DAY_WIDTH}px`;month.style.width=`${((segmentEnd-cursor)/this.DAY_MS)*this.DAY_WIDTH}px`;month.textContent=`${this.MONTHS[current.getUTCMonth()]} ${current.getUTCFullYear()}`;timeline.append(month);cursor=next;}
        for(let offset=0;offset<this.data.window.day_count;offset++){const value=new Date(this.parseDate(this.data.window.start)+offset*this.DAY_MS),day=document.createElement("div");day.className="gantt-day";if([0,6].includes(value.getUTCDay()))day.classList.add("gantt-weekend");day.style.left=`${offset*this.DAY_WIDTH}px`;day.innerHTML=`<span>${value.getUTCDate()}</span><br><span>${this.WEEKDAYS[value.getUTCDay()]}</span>`;timeline.append(day);}this.addTodayLine(timeline);row.append(label,timeline);return row;
    },
    roomRow(room,width) {
        const maxLane=Math.max(0,...room.bookings.map(item=>item.lane)),height=Math.max(48,(maxLane+1)*36+8),row=document.createElement("div");row.className="gantt-room-row";
        const label=document.createElement("div");label.className="gantt-label";label.style.height=`${height}px`;const identity=document.createElement("div");identity.className="gantt-room-identity";const details=document.createElement("div");details.className="gantt-room-details";const link=document.createElement("a");link.className="gantt-room-link";link.href=`/rooms/${room.id}`;link.textContent=room.code;if(!room.active)link.insertAdjacentHTML("beforeend",' <span class="badge text-bg-secondary">Inactiva</span>');details.append(link);identity.append(details);
        const sync=document.createElement("a");sync.href=`/rooms/${room.id}#configuracion`;sync.className=`gantt-sync gantt-sync-${room.sync.severity}`;sync.setAttribute("aria-label",this.syncLabel(room.sync));sync.title=this.syncLabel(room.sync);label.append(identity,sync);
        const timeline=document.createElement("div");timeline.className="gantt-timeline gantt-room-timeline";timeline.style.cssText=`width:${width}px;height:${height}px`;timeline.addEventListener("click",event=>this.openGap(event,room,timeline));for(const booking of room.bookings)timeline.append(this.bookingBar(booking));this.addTodayLine(timeline);row.append(label,timeline);return row;
    },
    bookingBar(booking) {
        const bar=document.createElement("button");bar.type="button";bar.className="gantt-booking";bar.classList.add(booking.origin.slug==="manual"?"gantt-origin-manual":"gantt-origin-platform");if(booking.overlap_kind)bar.classList.add(`gantt-overlap-${booking.overlap_kind}`);
        const hue=[...booking.origin.color_key].reduce((v,c)=>(v*31+c.charCodeAt(0))%360,17),visibleStart=Math.max(0,this.dayOffset(booking.check_in)),visibleEnd=Math.min(this.data.window.day_count,this.dayOffset(booking.check_out)),left=visibleStart*this.DAY_WIDTH,width=(visibleEnd-visibleStart)*this.DAY_WIDTH;bar.style.cssText=`left:${left}px;width:${Math.max(2,width)}px;top:${booking.lane*36+5}px;--origin-hue:${hue}`;bar.textContent=`${booking.guest_name} · ${booking.origin.name}`;
        const overlap=booking.overlap_kind==="historical"?" Coincidencia histórica.":booking.overlap_kind==="operational"?" Anomalía de solapamiento.":"",detail=`${booking.guest_name}. Entrada: ${this.formatDate(booking.check_in)}. Salida: ${this.formatDate(booking.check_out)}. Origen: ${booking.origin.name}. ${booking.editable?"Manual":"Importada, solo lectura"}.${overlap}`;bar.title=detail;bar.setAttribute("aria-label",detail);bar.addEventListener("click",event=>{event.stopPropagation();BookingUI.openEditModal(booking.id,!booking.editable);});return bar;
    },
    openGap(event,room,timeline){if(event.target!==timeline||!room.active)return;const offset=Math.floor((event.clientX-timeline.getBoundingClientRect().left)/this.DAY_WIDTH),value=this.isoDate(this.parseDate(this.data.window.start)+offset*this.DAY_MS);if(value<this.data.window.today)return;BookingUI.openCreateModal(room.id,value);BookingUI.modal.show();},
    addTodayLine(timeline){const offset=this.dayOffset(this.data.window.today);if(offset<0||offset>=this.data.window.day_count)return;const line=document.createElement("div");line.className="gantt-today-column";line.style.left=`${offset*this.DAY_WIDTH}px`;timeline.append(line);},
    scrollToToday(){const offset=this.dayOffset(this.data.window.today);if(offset>=0)this.root.scrollLeft=Math.max(0,offset*this.DAY_WIDTH-this.root.clientWidth/2);},
    syncLabel(sync){if(!sync.platforms.length)return "Sin importaciones configuradas";return sync.platforms.map(item=>`${item.name}: ${item.state}`).join("; ");},formatDate(value){return value.split("-").reverse().join("/");}
};
document.addEventListener("DOMContentLoaded",()=>RMGantt.init());
