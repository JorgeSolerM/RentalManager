(() => {
'use strict';
const remote=document.querySelector('meta[name="rm-admin-remote"]')?.content==='1';
window.RMAdminUI=Object.freeze({remote});
const nav=document.getElementById('rmNavigation'),mq=matchMedia('(max-width:768px), (max-width:1280px) and (max-height:500px) and (any-pointer:coarse)');
function layout(){if(!nav)return;if(mq.matches){nav.classList.add('offcanvas');}else{bootstrap.Offcanvas.getInstance(nav)?.hide();nav.classList.remove('offcanvas');nav.removeAttribute('role');nav.removeAttribute('aria-modal');}}
layout();mq.addEventListener('change',layout);
nav?.addEventListener('click',e=>{if(mq.matches&&e.target.closest('a'))bootstrap.Offcanvas.getInstance(nav)?.hide();});
document.querySelectorAll('main table').forEach(table=>{if(table.closest('.table-responsive,.rm-table-scroll'))return;const wrap=document.createElement('div');wrap.className='rm-table-scroll';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Tabla desplazable');table.before(wrap);wrap.append(table);});
if(remote)document.addEventListener('click',e=>{const link=e.target.closest('.booking-link[data-booking-id]');if(link){e.preventDefault();e.stopImmediatePropagation();window.RMBookingReader.open(link.dataset.bookingId);}},true);
})();
