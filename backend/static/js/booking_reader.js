(() => {
'use strict';
const dialog=document.getElementById('rmBookingReader'),body=document.getElementById('rmBookingReaderBody'),title=document.getElementById('rmBookingReaderTitle');
let sequence=0,controller;
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const link=(text,href)=>{const a=el('a',text,'btn btn-outline-primary');a.href=href;return a;};
const date=value=>value?value.split('-').reverse().join('/'):'—';
const modal=()=>bootstrap.Modal.getOrCreateInstance(dialog);
dialog.addEventListener('hidden.bs.modal',()=>{sequence++;controller?.abort();body.replaceChildren();});
async function open(id,roomCode){
 if(!/^\d+$/.test(String(id)))return;
 const mine=++sequence;controller?.abort();controller=new AbortController();const signal=controller.signal;
 title.textContent='Detalle de reserva';body.replaceChildren(el('p','Cargando…'));modal().show();
 try{
  const response=await fetch(`/bookings/${id}`,{signal});if(!response.ok)throw Error('No se puede consultar esta reserva.');
  const booking=await response.json();if(mine!==sequence)return;
  body.replaceChildren();const dl=el('dl');
  for(const [name,value] of [['Habitación',roomCode||`Habitación ${booking.room_id}`],['Entrada',date(booking.check_in)],['Salida',date(booking.check_out)],['Origen',booking.origin||'—'],['Notas',booking.notes||'Sin notas']]){dl.append(el('dt',name),el('dd',value));}body.append(dl);
  const actions=el('div',undefined,'rm-contact-actions');actions.append(link('Ver habitación',`/rooms/${booking.room_id}`),link('Cuenta económica',`/bookings/${id}/finance`));
  if(!RMAdminUI.remote){const edit=el('button','Editar reserva','btn btn-outline-secondary');edit.type='button';edit.addEventListener('click',()=>{dialog.addEventListener('hidden.bs.modal',()=>BookingUI.openEditModal(id),{once:true});modal().hide();});actions.append(edit);}body.append(actions);
  body.append(el('h3','Personas vinculadas','h5 mt-4'));
  const people=[...new Map((booking.parties||[]).map(p=>[p.person_id,p])).values()];
  if(!people.length)body.append(el('p',booking.guest_name||booking.source_guest_name||'Sin persona vinculada'));
  for(const person of people){
   if(mine!==sequence)return;const section=el('section',undefined,'rm-reader-person');section.append(el('h4',person.person_name,'h6'));section.append(link('Ficha de persona',`/persons/${person.person_id}`));body.append(section);
   try{
    const contact=await fetch(`/persons/${person.person_id}`,{signal});if(!contact.ok)throw Error();
    const doc=new DOMParser().parseFromString(await contact.text(),'text/html');if(mine!==sequence)return;
    const phone=doc.querySelector('[data-rm-person-phone]')?.textContent.trim()||'',email=doc.querySelector('[data-rm-person-email]')?.textContent.trim()||'';
    section.append(el('p',phone||'Sin teléfono'),el('p',email||'Sin correo'));const buttons=el('div',undefined,'rm-contact-actions');
    const normalized=phone.replace(/[ () .-]/g,'');
    if(/^\+?\d{6,15}$/.test(normalized))buttons.append(link('Llamar',`tel:${normalized}`));
    const international=normalized.startsWith('00')?'+'+normalized.slice(2):normalized;
    if(/^\+[1-9]\d{7,14}$/.test(international)){const wa=link('WhatsApp',`https://wa.me/${international.slice(1)}`);wa.target='_blank';wa.rel='noopener noreferrer';buttons.append(wa);}
    else if(phone)section.append(el('small','WhatsApp requiere teléfono con prefijo internacional.','text-muted'));
    if(/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)&&!/[\r\n]/.test(email))buttons.append(link('Correo',`mailto:${encodeURIComponent(email)}`));
    section.append(buttons);
   }catch(error){if(error.name==='AbortError')return;section.append(el('p','Contacto no disponible. Puedes abrir la ficha autorizada.','text-muted'));}
  }
 }catch(error){if(error.name!=='AbortError'&&mine===sequence)body.replaceChildren(el('p',error.message,'alert alert-warning'));}
}
function room(room){
 sequence++;controller?.abort();title.textContent=`Reservas · ${room.code}`;body.replaceChildren();
 for(const b of [...room.bookings].sort((a,b)=>a.check_in.localeCompare(b.check_in))){const button=el('button',`${b.guest_name||'Reserva'} · ${date(b.check_in)} – ${date(b.check_out)}${b.overlap_kind?' · Solapamiento':''}`,'btn btn-outline-secondary text-start w-100 mb-2');button.type='button';button.addEventListener('click',()=>open(b.id,room.code));body.append(button);}
 if(!room.bookings.length)body.append(el('p','Sin reservas en este intervalo.'));modal().show();
}
window.RMBookingReader=Object.freeze({open,room});
})();
