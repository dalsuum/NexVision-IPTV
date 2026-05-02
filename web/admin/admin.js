
const API=window.location.origin+'/api'; // auto-detect server address
const THEME_KEY='nv_theme_mode';
let jwt=localStorage.getItem('nv_jwt'),me=null,curPage='dashboard',rtimer=null;

// ── City picker ───────────────────────────────────────────────────────────────
let _citiesCache=null;
async function loadCities(){
  if(_citiesCache)return _citiesCache;
  try{const r=await fetch('/admin/cities.json');_citiesCache=await r.json();}
  catch(e){_citiesCache=[];}
  return _citiesCache;
}
function cityPickerHtml(id,val=''){
  return `<div class="cs-wrap"><input id="${id}" value="${esc(val)}" placeholder="Type to search city..." autocomplete="off" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:9px 12px;color:var(--text);font-size:13px;outline:none;transition:.2s;box-sizing:border-box" oninput="onCityInput(this)" onfocus="onCityInput(this)" onblur="hideCityDrop(this)"><div class="cs-drop" id="${id}-drop"></div></div>`;
}
async function onCityInput(el){
  const cities=await loadCities();
  const q=el.value.toLowerCase().trim();
  const drop=document.getElementById(el.id+'-drop');
  if(!drop)return;
  if(!q){drop.style.display='none';return;}
  const matches=cities.filter(c=>c.toLowerCase().includes(q)).slice(0,80);
  if(!matches.length){drop.innerHTML='<div class="cs-none">No cities found</div>';drop.style.display='block';return;}
  drop.innerHTML=matches.map(c=>`<div class="cs-opt" onmousedown="pickCity('${el.id}','${c.replace(/'/g,"\\'")}')">${c}</div>`).join('');
  drop.style.display='block';
}
function pickCity(id,city){
  const el=document.getElementById(id);if(el)el.value=city;
  const drop=document.getElementById(id+'-drop');if(drop)drop.style.display='none';
}
function hideCityDrop(el){
  setTimeout(()=>{const d=document.getElementById(el.id+'-drop');if(d)d.style.display='none';},200);
}

function applyTheme(mode){
  const m=(mode==='light')?'light':'dark';
  document.documentElement.setAttribute('data-theme',m);
  updateThemeButton(m);
}
function updateThemeButton(mode){
  const btn=document.getElementById('theme-toggle');
  if(btn){
    if(mode==='light'){btn.innerHTML='<span id="theme-icon">☀️</span> Normal';}
    else{btn.innerHTML='<span id="theme-icon">🌙</span> Dark';}
  }
}
function toggleTheme(){
  const cur=localStorage.getItem(THEME_KEY)||'dark';
  const next=(cur==='dark')?'light':'dark';
  localStorage.setItem(THEME_KEY,next);
  applyTheme(next);
}
applyTheme(localStorage.getItem(THEME_KEY)||'dark');
updateThemeButton(localStorage.getItem(THEME_KEY)||'dark');

// ── Helpers ──────────────────────────────────────────────────────────────────
async function req(path,opts={}){
  const h={'Content-Type':'application/json'};
  if(jwt)h['Authorization']='Bearer '+jwt;
  try{
    const r=await fetch(API+path,{...opts,headers:{...h,...(opts.headers||{})}});
    if(r.status===401){logout();return null;}
    const ct=(r.headers.get('content-type')||'').toLowerCase();
    if(ct.includes('application/json')) return await r.json();
    const txt=await r.text();
    return {error: txt || ('HTTP '+r.status), status: r.status};
  }catch(e){
    return {error:'Network request failed'};
  }
}
function toast(msg,dur=2800){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('on');setTimeout(()=>t.classList.remove('on'),dur);}
function fmtMin(m){if(!m)return'0m';const h=Math.floor(m/60),mn=m%60;return h>0?h+'h '+mn+'m':mn+'m';}
function fmtNum(n){return(n||0).toLocaleString();}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

// ── Auth ──────────────────────────────────────────────────────────────────────
async function doLogin(){
  const u=document.getElementById('lu').value,p=document.getElementById('lp').value;
  const r=await fetch(API+'/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})}).then(r=>r.json()).catch(()=>null);
  if(!r||r.error){document.getElementById('lerr').textContent=r?.error||'Cannot connect';return;}
  jwt=r.token;me=r.user;localStorage.setItem('nv_jwt',jwt);startApp();
}
async function checkAuth(){if(!jwt)return false;const r=await req('/auth/me');if(!r||r.error)return false;me=r;return true;}
function logout(){jwt=null;me=null;localStorage.removeItem('nv_jwt');document.getElementById('app').classList.remove('on');document.getElementById('login').style.display='flex';clearInterval(rtimer);}
async function startApp(){
  document.getElementById('login').style.display='none';
  document.getElementById('app').classList.add('on');
  document.getElementById('sb-uname').textContent=me.username;
  document.getElementById('sb-urole').textContent=me.role;
  // Load deployment mode before rendering anything
  const s0 = await req('/settings');
  if (s0) {
    window._settings = s0;
    applyDeploymentMode(s0.deployment_mode||'hotel');
    applyAdminBranding(s0);
  }
  await updateCounts();go('dashboard');
  clearInterval(rtimer);
  rtimer=setInterval(()=>{updateCounts();if(curPage==='dashboard')pages.dashboard();},30000);
}

function applyDeploymentMode(mode) {
  window._deployMode = mode;
  const isHotel = mode !== 'commercial';

  // ── Sidebar brand label / title (supports custom settings) ───────────────
  applyAdminBranding(window._settings || {});

  // ── Rooms/Screens nav item ─────────────────────────────────────────────────
  const niRooms = document.getElementById('ni-rooms');
  if (niRooms) {
    niRooms.innerHTML = `<span class="ic">${isHotel?'🏨':'🖥'}</span>${isHotel?'Rooms &amp; Devices':'Screens &amp; Devices'}<span class="bc" id="cnt-rooms">—</span>`;
  }
  TITLES['rooms'] = isHotel ? 'Rooms & Devices' : 'Screens & Devices';
  if (curPage === 'rooms') document.getElementById('tb-title').textContent = TITLES['rooms'];

  // ── Hotel section label ────────────────────────────────────────────────────
  const hotelSec = document.getElementById('sb-hotel-sec');
  if (hotelSec) hotelSec.textContent = isHotel ? 'Hotel' : 'Display';

  // ── Hotel-only sidebar items: show in hotel, hide in commercial ────────────
  const hotelOnlyNav = ['ni-services', 'ni-prayer', 'ni-birthdays'];
  hotelOnlyNav.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = isHotel ? '' : 'none';
  });

  // ── Notifications: Birthdays moved into Hotel section in commercial mode ───
  // In hotel mode show Birthdays in Notifications section; hide the duplicate
  const bdayNotif = document.getElementById('ni-birthdays');    // Notifications section
  const bdaySb    = document.getElementById('ni-birthdays-sb'); // Hotel section (commercial)
  if (bdayNotif) bdayNotif.style.display = isHotel ? '' : 'none';
  if (bdaySb)    bdaySb.style.display    = 'none'; // always hidden (moved above)

  // ── Page title update if already on a renamed page ────────────────────────
  if (curPage === 'settings') document.getElementById('tb-title').textContent = isHotel ? 'System Settings' : 'Admin Settings';
  TITLES['settings'] = isHotel ? 'System Settings' : 'Admin Settings';

  // ── Topbar "X / Y online" label ───────────────────────────────────────────
  const tbRooms = document.getElementById('tb-rooms');
  if (tbRooms && tbRooms.textContent.includes(' / ')) {
    tbRooms.textContent = tbRooms.textContent.replace(/rooms|screens/i, isHotel ? 'rooms' : 'screens');
  }
}

function applyAdminBranding(s) {
  const cfg = s || window._settings || {};
  const deployMode = window._deployMode || cfg.deployment_mode || 'hotel';
  const isHotel = deployMode !== 'commercial';

  const brandText = String(cfg.admin_brand_name || 'NEXVISION').trim() || 'NEXVISION';
  const modeText = String(cfg.admin_mode_label || '').trim() || (isHotel ? 'Hotel CMS' : 'Admin');
  const titleText = String(cfg.admin_title || '').trim() || 'NexVision CMS v5';
  const logoUrl = String(cfg.admin_logo_url || '').trim();

  const sbBrand = document.getElementById('sb-brand');
  if (sbBrand) {
    if (logoUrl) {
      sbBrand.innerHTML = '<img src="' + esc(logoUrl) + '" alt="' + esc(brandText) + '">';
      const logoImg = sbBrand.querySelector('img');
      if (logoImg) logoImg.onerror = () => { sbBrand.textContent = brandText; };
    } else {
      sbBrand.textContent = brandText;
    }
  }

  const modeLabel = document.getElementById('sb-mode-label');
  if (modeLabel) modeLabel.textContent = modeText;

  const lcBrand = document.querySelector('.lc-brand');
  if (lcBrand) lcBrand.textContent = brandText;

  document.title = titleText;
}
async function updateCounts(){
  const[ch,vod,radio,rooms]=await Promise.all([req('/channels?active=0&limit=99999'),req('/vod'),req('/radio'),req('/rooms')]);
  if(Array.isArray(ch))document.getElementById('cnt-channels').textContent=ch.length;
  if(Array.isArray(vod))document.getElementById('cnt-vod').textContent=vod.length;
  if(Array.isArray(radio))document.getElementById('cnt-radio').textContent=radio.length;
  if(Array.isArray(rooms)){const on=rooms.filter(r=>r.online).length;document.getElementById('cnt-rooms').textContent=rooms.length;const _u=(window._deployMode||'hotel')!=='commercial'?'rooms':'screens';document.getElementById('tb-rooms').textContent=on+' / '+rooms.length+' '+_u+' online';}
}

// ── Navigation ────────────────────────────────────────────────────────────────
const TITLES={dashboard:'Dashboard',channels:'TV Channels',groups:'Media Groups',vodManager:'VOD Manager',vod:'Video on Demand',packages:'Content Packages',radio:'Web Radio',pages:'Content Pages',rooms:'Rooms & Devices',devices:'Android TV Devices',skins:'Skins',users:'Users',reports:'Reports & Analytics',messages:'Messages & Alerts',birthdays:'Birthday Manager',rss:'RSS Feeds',vip:'VIP Access',services:'Guest Services',epg:'EPG / Programme Schedule',prayer:'Prayer Times',clock:'Clock & Alarm',settings:'System Settings',navigation:'Navigation Menu',homeLayout:'Home Layout',slides:'Promo Slides',ads:'Ads Manager'};
async function go(page){
  document.body.classList.remove('vod-embed-mode');
  document.querySelectorAll('.ni').forEach(n=>n.classList.remove('on'));
  const ni=document.getElementById('ni-'+page);if(ni)ni.classList.add('on');
  curPage=page;document.getElementById('tb-title').textContent=TITLES[page]||page;
  document.getElementById('content').innerHTML='<div style="padding:44px;text-align:center;color:var(--text3)">Loading...</div>';
  await pages[page]?.();
}
async function refreshCurrent(){
  const b=document.querySelector('.tb-ref');b.classList.add('spin');
  await pages[curPage]?.();await updateCounts();
  setTimeout(()=>b.classList.remove('spin'),600);
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(title,body,footer='',size=''){
  document.getElementById('mtitle').textContent=title;
  document.getElementById('mbody').innerHTML=body;
  document.getElementById('mfooter').innerHTML=footer;
  document.getElementById('modal').className='modal'+(size?' '+size:'');
  document.getElementById('overlay').classList.add('on');
  const firstField = document.querySelector('#mbody input:not([type="checkbox"]):not([type="radio"]):not([disabled]), #mbody select:not([disabled]), #mbody textarea:not([disabled])')
    || document.querySelector('#mbody button:not([disabled]), #mbody input:not([disabled])');
  if(firstField) requestAnimationFrame(()=>firstField.focus({preventScroll:true}));
}
function closeModal(){window._pkgEditor=null;document.getElementById('overlay').classList.remove('on');}

// ── Charts ────────────────────────────────────────────────────────────────────
function barChart(items,lk,vk,color){
  if(!items||!items.length)return'<div style="color:var(--text3);font-size:12px;padding:10px">No data</div>';
  const max=Math.max(...items.map(i=>i[vk]||0),1);
  return'<div class="bar-list">'+items.map(i=>'<div class="bar-item"><div class="bar-lbl" title="'+esc(i[lk])+'">'+esc(i[lk])+'</div><div class="bar-track"><div class="bar-fill" style="width:'+Math.round((i[vk]||0)/max*100)+'%;background:'+color+'"></div></div><div class="bar-val">'+fmtNum(i[vk])+'</div></div>').join('')+'</div>';
}
function miniBar(items,vk,tipFn,color){
  if(!items||!items.length)return'';
  const max=Math.max(...items.map(i=>i[vk]||0),1);
  return'<div class="mini-bars">'+items.map(i=>'<div class="mb" style="height:'+Math.max(Math.round((i[vk]||0)/max*52),2)+'px;background:'+color+'" data-tip="'+esc(tipFn(i))+'"></div>').join('')+'</div>';
}

// ── Bulk selection helpers ────────────────────────────────────────────────────
function initBulk(prefix,onDelete,onBulkDelete,extraBtns){
  window['_extraBtns_'+prefix] = extraBtns || '';
  const chkAll=document.getElementById('chk-all-'+prefix);
  if(chkAll){
    chkAll.onchange=()=>{
      document.querySelectorAll('.row-chk-'+prefix).forEach(c=>{c.checked=chkAll.checked;c.closest('tr').classList.toggle('sel',chkAll.checked);});
      updateBulkBar(prefix,onDelete,onBulkDelete);
    };
  }
  document.querySelectorAll('.row-chk-'+prefix).forEach(c=>{
    c.onchange=()=>{c.closest('tr').classList.toggle('sel',c.checked);updateBulkBar(prefix,onDelete,onBulkDelete);};
  });
}
function updateBulkBar(prefix,onDelete,onBulkDelete){
  const sel=getSelected(prefix);
  const bar=document.getElementById('bulk-bar-'+prefix);
  if(!bar)return;
  window['_bulkDel_'+prefix] = onBulkDelete;
  if(sel.length>0){
    bar.classList.add('on');
    bar.innerHTML='<b style="color:var(--gold)">'+sel.length+' selected</b>'
      +'<button class="btn btn-d btn-sm" onclick="window[\'_bulkDel_'+prefix+'\']()">🗑 Delete Selected</button>'
      +(window['_extraBtns_'+prefix]||'')
      +'<button class="btn btn-g btn-sm" onclick="clearSel(\''+prefix+'\')">✕ Clear</button>';
  } else {
    bar.classList.remove('on');
  }
}

// ── Bulk Export (channels) ────────────────────────────────────────────────────
function _dlFile(name,content,mime){
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([content],{type:mime}));
  a.download=name;a.click();URL.revokeObjectURL(a.href);
}
function _escX(v){return String(v==null?'':v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function exportChannels(fmt){
  const ids=getSelected('ch');
  const all=window._chs||[];
  const data=ids.length?all.filter(c=>ids.includes(c.id)):all;
  if(!data.length){toast('No channels to export');return;}
  const heads=['#','Name','Type','Stream URL','Group','Status'];
  const rows=data.map(c=>[
    c.direct_play_num||'',
    c.name||'',
    c.channel_type||'stream_udp',
    c.stream_url||'',
    c.group_name||'',
    c.active?'Active':'Inactive'
  ]);
  const ts=new Date().toISOString().slice(0,10);

  if(fmt==='csv'){
    const csv=[heads,...rows].map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\r\n');
    _dlFile('channels_'+ts+'.csv','\uFEFF'+csv,'text/csv;charset=utf-8');

  } else if(fmt==='excel'){
    let t='<table><thead><tr>'+heads.map(h=>'<th><b>'+_escX(h)+'</b></th>').join('')+'</tr></thead><tbody>';
    rows.forEach(r=>{t+='<tr>'+r.map(v=>'<td>'+_escX(v)+'</td>').join('')+'</tr>';});
    t+='</tbody></table>';
    const xls='<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">'
      +'<head><meta charset="UTF-8"><!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets>'
      +'<x:ExcelWorksheet><x:Name>Channels</x:Name><x:WorksheetOptions><x:DisplayGridlines/>'
      +'</x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->'
      +'<style>td,th{font-family:Calibri,Arial;font-size:11pt}th{background:#f2f2f2}</style></head>'
      +'<body>'+t+'</body></html>';
    _dlFile('channels_'+ts+'.xls',xls,'application/vnd.ms-excel;charset=utf-8');

  } else if(fmt==='pdf'){
    const win=window.open('','_blank','width=900,height=700');
    if(!win){toast('Allow pop-ups to export PDF');return;}
    let t='<tr>'+heads.map(h=>'<th>'+_escX(h)+'</th>').join('')+'</tr>';
    rows.forEach(r=>{t+='<tr>'+r.map(v=>'<td>'+_escX(v)+'</td>').join('')+'</tr>';});
    win.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Channels Export</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font:11px Arial,sans-serif;padding:20px;color:#222}
  h2{font-size:15px;margin-bottom:4px}
  .sub{font-size:10px;color:#888;margin-bottom:14px}
  table{border-collapse:collapse;width:100%;table-layout:fixed}
  th{background:#2b2b3a;color:#fff;padding:6px 8px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.5px}
  td{padding:5px 8px;border-bottom:1px solid #eee;font-size:10px;word-break:break-all}
  tr:nth-child(even) td{background:#f9f9f9}
  @media print{body{padding:0}button{display:none}}
</style></head><body>
<h2>TV Channels Export</h2>
<div class="sub">${data.length} channels &nbsp;·&nbsp; Exported ${new Date().toLocaleString()}</div>
<table><thead>${t.slice(0,t.indexOf('</tr>')+5)}</thead><tbody>${t.slice(t.indexOf('</tr>')+5)}</tbody></table>
<br><button onclick="window.print()" style="padding:7px 18px;background:#c9a84c;color:#000;border:none;border-radius:6px;cursor:pointer;font-weight:600">🖨 Print / Save as PDF</button>
</body></html>`);
    win.document.close();
  }
}
function getSelected(prefix){return[...document.querySelectorAll('.row-chk-'+prefix+':checked')].map(c=>parseInt(c.value));}
function clearSel(prefix){document.querySelectorAll('.row-chk-'+prefix).forEach(c=>{c.checked=false;c.closest('tr')?.classList.remove('sel');});const b=document.getElementById('bulk-bar-'+prefix);if(b)b.classList.remove('on');const ca=document.getElementById('chk-all-'+prefix);if(ca)ca.checked=false;}

// ── CSV Parser ────────────────────────────────────────────────────────────────
function parseCSV(text){
  const lines=text.trim().split(/\r?\n/);
  if(lines.length<2)return[];
  const hdr=lines[0].split(',').map(h=>h.trim().replace(/^"|"$/g,''));
  return lines.slice(1).filter(l=>l.trim()).map(line=>{
    const vals=[];let cur='',inQ=false;
    for(const ch of line){if(ch==='"'){inQ=!inQ;}else if(ch===','&&!inQ){vals.push(cur.trim());cur='';}else{cur+=ch;}}
    vals.push(cur.trim());
    const obj={};hdr.forEach((h,i)=>obj[h]=vals[i]?.replace(/^"|"$/g,'')||'');
    return obj;
  });
}

// ── Export helpers ────────────────────────────────────────────────────────────
function exportCSV(data,cols,filename){
  const hdr=cols.map(c=>c.label);
  const rows=data.map(r=>cols.map(c=>{const v=r[c.key]||'';return'"'+String(v).replace(/"/g,'""')+'"';}));
  const csv=[hdr.join(','),...rows.map(r=>r.join(','))].join('\n');
  dlBlob(csv,'text/csv',filename+'.csv');
}
function exportXLSX(data,cols,filename){
  const ws=XLSX.utils.json_to_sheet(data.map(r=>{const o={};cols.forEach(c=>o[c.label]=r[c.key]||'');return o;}));
  const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'Data');
  XLSX.writeFile(wb,filename+'.xlsx');
}
function exportPDF(data,cols,title,filename){
  const w=window.open('','_blank');
  const rows=data.map(r=>'<tr>'+cols.map(c=>'<td>'+esc(String(r[c.key]||''))+'</td>').join('')+'</tr>').join('');
  w.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${title}</title><style>
    body{font-family:Arial,sans-serif;font-size:11px;color:#222;padding:16px}
    h2{font-size:15px;margin-bottom:12px;color:#000}
    table{width:100%;border-collapse:collapse}
    th{background:#1a1a2e;color:#fff;padding:7px 10px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.5px}
    td{padding:6px 10px;border-bottom:1px solid #e0e0e0;font-size:11px}
    tr:nth-child(even)td{background:#f8f8fc}
    .footer{margin-top:14px;font-size:10px;color:#888;text-align:right}
    @media print{button{display:none}}
  
/* ── V8: Navigation Editor ──────────────────────────────────────────────────── */
.nav-pos-row{display:flex;gap:10px;margin-bottom:18px;flex-wrap:wrap}
.pos-opt{flex:1;min-width:160px;border:2px solid var(--border2);border-radius:12px;padding:18px 14px;cursor:pointer;transition:.2s;text-align:center;background:var(--bg3)}
.pos-opt:hover{border-color:var(--border2);background:var(--bg4)}
.pos-opt.on{border-color:var(--gold);background:var(--gd)}
.pos-opt .po-icon{font-size:28px;margin-bottom:6px}
.pos-opt .po-label{font-family:'Syne',sans-serif;font-weight:700;font-size:14px;margin-bottom:3px}
.pos-opt .po-desc{font-size:11px;color:var(--text2)}
.pos-opt.on .po-label{color:var(--gold)}

.ni-list{display:flex;flex-direction:column;gap:6px}
.ni-row{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg3);border:1px solid var(--border);border-radius:10px;transition:.15s;user-select:none}
.ni-row:hover{border-color:var(--border2)}
.ni-row.disabled{opacity:.45}
.ni-drag{color:var(--text3);cursor:grab;font-size:16px;flex-shrink:0;padding:0 4px}
.ni-drag:active{cursor:grabbing}
.ni-icon{font-size:20px;flex-shrink:0;width:28px;text-align:center}
.ni-label{flex:1;font-size:13px;font-weight:500}
.ni-key{font-family:'DM Mono',monospace;font-size:10px;color:var(--text3);background:var(--bg4);padding:1px 6px;border-radius:4px}
.ni-sys{font-size:9px;color:var(--text3);font-family:'DM Mono',monospace;letter-spacing:1px;text-transform:uppercase}
.ni-toggle{position:relative;width:36px;height:20px;flex-shrink:0}
.ni-toggle input{opacity:0;width:0;height:0;position:absolute}
.ni-toggle-track{position:absolute;inset:0;background:var(--bg4);border-radius:20px;border:1px solid var(--border2);cursor:pointer;transition:.2s}
.ni-toggle-track::after{content:'';position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;background:var(--text3);transition:.2s}
.ni-toggle input:checked + .ni-toggle-track{background:rgba(212,168,67,.25);border-color:var(--gold)}
.ni-toggle input:checked + .ni-toggle-track::after{transform:translateX(16px);background:var(--gold)}
.ni-row.dragging{opacity:.5;border-style:dashed;border-color:var(--gold)}
.ni-row.drag-over{border-color:var(--gold);background:var(--gd)}

/* Style selector */
.style-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.style-opt{flex:1;min-width:120px;border:1px solid var(--border2);border-radius:8px;padding:12px 10px;cursor:pointer;transition:.15s;text-align:center;background:var(--bg3)}
.style-opt:hover{background:var(--bg4)}.style-opt.on{border-color:var(--gold);background:var(--gd)}
.style-opt .so-preview{font-size:11px;font-family:'DM Mono',monospace;margin-bottom:5px;color:var(--text2)}
.style-opt.on .so-preview{color:var(--gold)}
.style-opt .so-label{font-size:13px;font-weight:500}


/* ── V8: Promo Slides Admin ──────────────────────────────────────────────────── */
.slide-preview{width:100%;height:120px;background-size:cover;background-position:center;border-radius:8px;position:relative;overflow:hidden;border:1px solid var(--border)}
.slide-preview-overlay{position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,0.7),transparent)}
.slide-preview-text{position:absolute;bottom:10px;left:12px;color:#fff;font-size:12px;z-index:1}
.home-setting-row{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--bg3);border-radius:8px;margin-bottom:8px}
.home-setting-label{font-size:13px;font-weight:500}
.home-setting-sub{font-size:11px;color:var(--text2);margin-top:2px}
/* Big toggle */
.big-toggle{position:relative;width:52px;height:28px;flex-shrink:0}
.big-toggle input{opacity:0;width:0;height:0;position:absolute}
.big-toggle-track{position:absolute;inset:0;background:var(--bg4);border-radius:28px;border:1px solid var(--border2);cursor:pointer;transition:.25s}
.big-toggle-track::after{content:'';position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:var(--text3);transition:.25s}
.big-toggle input:checked + .big-toggle-track{background:rgba(212,168,67,.25);border-color:var(--gold)}
.big-toggle input:checked + .big-toggle-track::after{transform:translateX(24px);background:var(--gold)}

</style></head><body>
  <h2>NexVision — ${title}</h2>
  <p style="font-size:10px;color:#888;margin-bottom:10px">Generated: ${new Date().toLocaleString()}</p>
  <button onclick="window.print()" style="margin-bottom:10px;padding:6px 14px;background:#d4a843;color:#000;border:none;border-radius:6px;cursor:pointer;font-weight:600">🖨 Print / Save PDF</button>
  <table><thead><tr>${cols.map(c=>'<th>'+c.label+'</th>').join('')}</tr></thead><tbody>${rows}</tbody></table>
  <div class="footer">NexVision IPTV Platform • Total ${data.length} records</div>
  </body></html>`);w.document.close();
}
function dlBlob(content,mime,filename){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([content],{type:mime}));a.download=filename;a.click();}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGES
// ═══════════════════════════════════════════════════════════════════════════════
const pages={

// ── DASHBOARD ────────────────────────────────────────────────────────────────
async dashboard(){
  const[ov,sum]=await Promise.all([req('/stats/overview'),req('/reports/summary?days=7')]);
  if(!ov)return;
  const on=ov.online_rooms,tot=ov.total_rooms;
  const _isHotel=(window._deployMode||'hotel')!=='commercial';
  const _unitPlural=_isHotel?'Rooms':'Screens';
  document.getElementById('tb-rooms').textContent=on+' / '+tot+' online';
  document.getElementById('content').innerHTML=`
  <div class="stat-row">
    <div class="sc gold"><div class="sc-lbl">${_unitPlural} Online</div><div class="sc-val">${on}<span style="font-size:14px;color:var(--text3)"> / ${tot}</span></div><div class="sc-sub">Live right now</div></div>
    <div class="sc blue"><div class="sc-lbl">TV Channels</div><div class="sc-val">${ov.total_channels}</div><div class="sc-sub">Active streams</div></div>
    <div class="sc green"><div class="sc-lbl">VoD Library</div><div class="sc-val">${ov.total_movies}</div><div class="sc-sub">Movies available</div></div>
    <div class="sc purple"><div class="sc-lbl">Watch Hours</div><div class="sc-val">${Math.round(ov.total_watch_hours)}</div><div class="sc-sub">All time</div></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:16px">
    <div class="tbl-wrap" style="padding:16px"><div class="sec-hdr" style="margin-bottom:10px"><div class="sec-title">Top Channels</div><span style="font-size:11px;color:var(--text3)">Last 7 days</span></div>${barChart((sum?.top_channels||[]).slice(0,6),'name','total_minutes','var(--gold)')}</div>
    <div class="tbl-wrap" style="padding:16px"><div class="sec-hdr" style="margin-bottom:10px"><div class="sec-title">Top ${_unitPlural}</div><span style="font-size:11px;color:var(--text3)">By watch time</span></div>${barChart((sum?.top_rooms||[]).slice(0,6),'room_number','total_minutes','var(--blue)')}</div>
    <div class="tbl-wrap" style="padding:16px"><div class="sec-hdr" style="margin-bottom:10px"><div class="sec-title">Top Movies</div><span style="font-size:11px;color:var(--text3)">By sessions</span></div>${barChart((sum?.top_vod||[]).slice(0,6),'title','sessions','var(--purple)')}</div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
    <div class="tbl-wrap" style="padding:16px"><div class="sec-title" style="margin-bottom:10px">Daily Activity — Last 7 Days</div>${miniBar(sum?.daily||[],'total_minutes',d=>d.day+': '+fmtMin(d.total_minutes),'var(--green)')}<div style="font-size:10px;color:var(--text3);margin-top:5px;font-family:'DM Mono',monospace">Minutes watched per day</div></div>
    <div class="tbl-wrap" style="padding:16px"><div class="sec-title" style="margin-bottom:10px">Hourly Pattern (24h)</div>${miniBar(sum?.hourly||[],'total_minutes',h=>h.hour+':00 — '+fmtMin(h.total_minutes),'var(--orange)')}<div style="font-size:10px;color:var(--text3);margin-top:5px;font-family:'DM Mono',monospace">Peak viewing hours</div></div>
  </div>`;
},

// ── CHANNELS ─────────────────────────────────────────────────────────────────
async channels(){
  const[chResp,groups]=await Promise.all([req('/channels?active=0&limit=99999'),req('/media-groups')]);
  const chs = Array.isArray(chResp) ? chResp : (chResp && chResp.channels) ? chResp.channels : [];
  if(!chs)return;window._chs=chs;window._groups=groups||[];
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr">
    <div class="sec-title">TV Channels <span style="color:var(--text3);font-weight:400">(${chs.length})</span></div>
    <div class="sec-acts">
      <div class="sw"><input placeholder="Search..." oninput="fChs(this.value)" id="ch-q"></div>
      <select id="ch-gf" onchange="fChs(document.getElementById('ch-q').value)" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:7px 10px;font-size:12px;outline:none">
        <option value="">All Groups</option>${(groups||[]).map(g=>'<option value="'+g.id+'">'+esc(g.name)+'</option>').join('')}
      </select>
      <select id="ch-tf" onchange="fChs(document.getElementById('ch-q').value)" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:7px 10px;font-size:12px;outline:none">
        <option value="">All Types</option>
        <option value="stream_udp">🔵 UDP/Multicast</option>
        <option value="m3u">🟢 M3U/HLS</option>
        <option value="analog_tuner">🟠 Analog Tuner</option>
      </select>
      <button class="btn btn-p" onclick="eCh(null)">+ Add</button>
      <button class="btn btn-g" onclick="openM3UImport()">📥 M3U Import</button>
      <button class="btn btn-g" onclick="openCSVImport('channels')">📋 CSV Import</button>
    </div>
  </div>
  <div id="bulk-bar-ch" class="bulk-bar"></div>
  <div class="tbl-wrap"><table>
    <thead><tr><th class="chk"><input type="checkbox" id="chk-all-ch" style="width:14px;height:14px;accent-color:var(--gold)"></th><th>#</th><th>Name</th><th>Type</th><th>Stream URL</th><th>Group</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody id="ch-tbody">${chs.map(c=>chRow(c)).join('')}</tbody>
  </table></div>`;
  const _chExportBtns='<button class="btn btn-sm" style="background:rgba(74,158,255,.15);color:#4a9eff;border:1px solid rgba(74,158,255,.3)" onclick="exportChannels(\'csv\')">⬇ CSV</button>'
    +'<button class="btn btn-sm" style="background:rgba(82,217,142,.15);color:#52d98e;border:1px solid rgba(82,217,142,.3)" onclick="exportChannels(\'excel\')">⬇ Excel</button>'
    +'<button class="btn btn-sm" style="background:rgba(232,72,85,.15);color:#e84855;border:1px solid rgba(232,72,85,.3)" onclick="exportChannels(\'pdf\')">⬇ PDF</button>';
  initBulk('ch',null,async()=>{const ids=getSelected('ch');if(!ids.length)return;if(!confirm('Delete '+ids.length+' channels?'))return;const r=await req('/channels/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' channels deleted');await pages.channels();}},_chExportBtns);
},

// ── GROUPS ───────────────────────────────────────────────────────────────────
async groups(){
  const gs=await req('/media-groups');if(!gs)return;window._groups=gs;
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">Media Groups <span style="color:var(--text3);font-weight:400">(${gs.length})</span></div>
  <div class="sec-acts">
    <button class="btn btn-p" onclick="eGroup(null)">+ Add</button>
    <button class="btn btn-g" onclick="openBulkAdd('groups')">+ Bulk Add</button>
  </div></div>
  <div id="bulk-bar-grp" class="bulk-bar"></div>
  <div class="tbl-wrap"><table>
    <thead><tr><th class="chk"><input type="checkbox" id="chk-all-grp" style="width:14px;height:14px;accent-color:var(--gold)"></th><th>Name</th><th>Channels</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>${gs.map(g=>`<tr><td><input type="checkbox" class="row-chk-grp" value="${g.id}"></td><td><b>${esc(g.name)}</b></td><td><span class="bdg bb">${g.channel_count||0} ch</span></td><td><span class="bdg ${g.active?'bg':'br'}">${g.active?'Active':'Inactive'}</span></td>
    <td><div class="tda"><button class="btn btn-g btn-sm" onclick="eGroup(${g.id})">Edit</button>${g.name!=='All Channels'?'<button class="btn btn-d btn-sm" onclick="dGroup('+g.id+',\''+esc(g.name)+'\')">Del</button>':''}</div></td></tr>`).join('')}
    </tbody></table></div>`;
  initBulk('grp',null,async()=>{const ids=getSelected('grp');if(!ids.length)return;if(!confirm('Delete '+ids.length+' groups?'))return;const r=await req('/media-groups/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' groups deleted');await pages.groups();}});
},

// ── VOD ───────────────────────────────────────────────────────────────────────
async vodManager(){
  document.getElementById('content').innerHTML=`
  <div class="embed-shell">
    <div class="vod-topbar">
      <span class="sec-title">VOD Manager</span>
      <nav class="topnav">
        <a class="active" onclick="vodNav(this,'/vod/?embedded=1&inframe=1')">VOD</a>
        <a onclick="vodNav(this,'/vod/admin?embedded=1&inframe=1')">Admin</a>
        <a onclick="vodNav(this,'/vod/admin/storage?embedded=1&inframe=1')">Storage</a>
      </nav>
      <span class="vod-topbar-status" id="hdr-status">FFmpeg OK | Disk: 9.7 GB free | Up: 8h 34m 15s</span>
    </div>
    <iframe id="vod-frame" class="embed-frame" src="/vod/?embedded=1&inframe=1&_ts=${Date.now()}" title="VOD Manager" loading="lazy" referrerpolicy="same-origin"></iframe>
  </div>`;
},

// ── VOD ───────────────────────────────────────────────────────────────────────
async vod(){
  const movies=await req('/vod');if(!movies)return;window._vod=movies;
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">Video on Demand <span style="color:var(--text3);font-weight:400">(${movies.length})</span></div>
  <div class="sec-acts">
    <div class="sw"><input placeholder="Search..." oninput="fVod(this.value)"></div>
    <button class="btn btn-p" onclick="eVod(null)">+ Add</button>
    <button class="btn btn-g" onclick="openCSVImport('vod')">📋 CSV Import</button>
  </div></div>
  <div id="bulk-bar-vod" class="bulk-bar"></div>
  <div class="tbl-wrap"><table>
    <thead><tr><th class="chk"><input type="checkbox" id="chk-all-vod" style="width:14px;height:14px;accent-color:var(--gold)"></th><th>Title</th><th>Genre</th><th>Year</th><th>Rating</th><th>Price</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody id="vod-tbody">${movies.map(m=>vodRow(m)).join('')}</tbody>
  </table></div>`;
  initBulk('vod',null,async()=>{const ids=getSelected('vod');if(!ids.length)return;if(!confirm('Delete '+ids.length+' movies?'))return;const r=await req('/vod/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' movies deleted');await pages.vod();}});
},

// ── PACKAGES ─────────────────────────────────────────────────────────────────
async packages(){
  const pkgs=await req('/vod/packages/all');if(!pkgs)return;window._pkgs=pkgs;
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">VoD Packages</div>
  <div class="sec-acts">
    <button class="btn btn-p" onclick="ePkg(null)">+ Add</button>
    <button class="btn btn-g" onclick="openCSVImport('packages')">📋 CSV Import</button>
  </div></div>
  <div id="bulk-bar-pkg" class="bulk-bar"></div>
  <div class="tbl-wrap"><table>
    <thead><tr><th class="chk"><input type="checkbox" id="chk-all-pkg" style="width:14px;height:14px;accent-color:var(--gold)"></th><th>Name</th><th>Description</th><th>Price</th><th>Duration</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>${pkgs.map(p=>`<tr><td><input type="checkbox" class="row-chk-pkg" value="${p.id}"></td><td><b>${esc(p.name)}</b></td><td style="color:var(--text2)">${esc(p.description)}</td><td><span class="bdg bo">$${p.price}</span></td><td><span class="bdg bb">${p.duration_hours}h</span></td>
    <td><span class="bdg ${p.active?'bg':'br'}">${p.active?'Active':'Inactive'}</span></td>
    <td><div class="tda"><button class="btn btn-g btn-sm" onclick="ePkg(${p.id})">Edit</button><button class="btn btn-d btn-sm" onclick="dPkg(${p.id},'${esc(p.name)}')">Del</button></div></td></tr>`).join('')}
  </tbody></table></div>`;
  initBulk('pkg',null,async()=>{const ids=getSelected('pkg');if(!ids.length)return;if(!confirm('Delete '+ids.length+' packages?'))return;const r=await req('/vod/packages/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' packages deleted');await pages.packages();}});
},

// ── RADIO ─────────────────────────────────────────────────────────────────────
async radio(){
  const[stations,countries]=await Promise.all([req('/radio'),req('/radio/countries')]);
  if(!stations)return;window._stations=stations;
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">Web Radio <span style="color:var(--text3);font-weight:400">(${stations.length})</span></div>
  <div class="sec-acts">
    <div class="sw"><input placeholder="Search..." oninput="fRadio(this.value)"></div>
    <select id="radio-ctry" onchange="fRadio('')" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:7px 10px;font-size:12px;outline:none">
      <option value="">All Countries</option>${(countries||[]).map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join('')}
    </select>
    <button class="btn btn-p" onclick="eStation(null)">+ Add</button>
    <button class="btn btn-g" onclick="openCSVImport('radio')">📋 CSV Import</button>
  </div></div>
  <div id="bulk-bar-rad" class="bulk-bar"></div>
  <div class="tbl-wrap"><table>
    <thead><tr><th class="chk"><input type="checkbox" id="chk-all-rad" style="width:14px;height:14px;accent-color:var(--gold)"></th><th>Station</th><th>Country</th><th>Genre</th><th>Stream URL</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody id="radio-tbody">${stations.map(s=>radioRow(s)).join('')}</tbody>
  </table></div>`;
  initBulk('rad',null,async()=>{const ids=getSelected('rad');if(!ids.length)return;if(!confirm('Delete '+ids.length+' stations?'))return;const r=await req('/radio/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' stations deleted');await pages.radio();}});
},

// ── CONTENT PAGES ─────────────────────────────────────────────────────────────
async pages(){
  const ps=await req('/content');if(!ps)return;window._pages=ps;
  // Fetch items for all pages in parallel
  const allItems=await Promise.all(ps.map(p=>req('/content/'+p.id+'/items').then(it=>[p.id,it||[]])));
  window._pageItems=Object.fromEntries(allItems);
  const groups=[...new Set(ps.map(p=>p.group_name))];
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">Content Pages <span style="color:var(--text3);font-weight:400">(${ps.length})</span></div>
  <button class="btn btn-p" onclick="ePage(null)">+ Add Page</button></div>
  ${groups.map(g=>`
  <div style="margin-bottom:28px">
    <div style="font-size:10px;color:var(--text2);font-family:'DM Mono',monospace;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;padding:4px 11px;background:var(--bg3);border-radius:6px;display:inline-block">${esc(g)}</div>
    ${ps.filter(p=>p.group_name===g).map(p=>`
    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;margin-bottom:14px;overflow:hidden">

      <div style="display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--bg3);border-bottom:1px solid var(--border)">
        <div style="flex:1;min-width:0">
          <span style="font-weight:700;font-size:14px">${esc(p.name)}</span>
          <span class="bdg ${p.active?'bg':'br'}" style="font-size:9px;margin-left:7px">${p.active?'Active':'Hidden'}</span>
          <span style="font-size:11px;color:var(--text3);margin-left:8px">${esc(p.template)} template</span>
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn btn-p btn-sm" onclick="inlineAddItem(${p.id})">+ Add Item</button>
          <button class="btn btn-b btn-sm" onclick="ePage(${p.id})">Edit Page</button>
          <button class="btn btn-d btn-sm" onclick="dPage(${p.id},'${esc(p.name)}')">Del</button>
        </div>
      </div>

      <div id="page-items-${p.id}" style="padding:14px 16px;display:flex;flex-direction:column;gap:10px">
        ${renderInlineItems(p.id)}
      </div>
    </div>`).join('')}
  </div>`).join('')}`;
},

// ── ROOMS ─────────────────────────────────────────────────────────────────────
async rooms(){
  const [rooms, pkgMap]=await Promise.all([req('/rooms'),req('/rooms/packages-map')]);
  if(!rooms)return;window._rooms=rooms;
  const _pkgMap=pkgMap||{};
  const on=rooms.filter(r=>r.online).length;
  const isHotel=(window._deployMode||'hotel')!=='commercial';
  const termUnit=isHotel?'Room':'Screen';
  const termUnits=isHotel?'Rooms':'Screens';
  const pageTitle=isHotel?'Rooms &amp; Devices':'Screens &amp; Devices';
  const regInstr=isHotel
    ?`📱 <b>Device Registration:</b> On TV/box browser → go to <code style="background:var(--bg4);padding:1px 6px;border-radius:4px;font-family:'DM Mono',monospace">http://SERVER:5000</code> → type room number.`
    :`🖥 <b>Screen Registration:</b> On display browser → go to <code style="background:var(--bg4);padding:1px 6px;border-radius:4px;font-family:'DM Mono',monospace">http://SERVER:5000</code> → enter screen/location ID.`;
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">${pageTitle}</div>
  <div class="sec-acts"><span class="bdg bg">● ${on} Online</span><span class="bdg br">○ ${rooms.length-on} Offline</span>
    <button class="btn btn-p" onclick="eRoom(null)">+ Add ${termUnit}</button>
    <button class="btn btn-g" onclick="openBulkAddRooms()">+ Bulk Add</button>
  </div></div>
  <div class="room-grid">${rooms.map(r=>`<div class="rtile ${r.online?'online':'offline'}" onclick="eRoom(${r.id})"><div class="rn">${esc(r.room_number)}</div><div class="rs">${r.online?'ONLINE':'OFFLINE'}</div></div>`).join('')}</div>
  <div class="ibox warn" style="margin-bottom:14px">${regInstr}</div>
  <div id="bulk-bar-rm" class="bulk-bar"></div>
  <div class="tbl-wrap"><table>
    <thead><tr><th class="chk"><input type="checkbox" id="chk-all-rm" style="width:14px;height:14px;accent-color:var(--gold)"></th><th>${termUnit}</th><th>Display Name</th><th>Packages</th><th>Status</th><th>Last Seen</th><th>Device</th><th>Actions</th></tr></thead>
    <tbody>${rooms.map(r=>{const rPkgs=_pkgMap[String(r.id)]||[];return`<tr><td><input type="checkbox" class="row-chk-rm" value="${r.id}"></td><td><b>${esc(r.room_number)}</b></td><td style="color:var(--text2)">${esc(r.tv_name)||'—'}</td>
    <td>${rPkgs.length?rPkgs.map(n=>`<span class="bdg bb" style="font-size:10px">${esc(n)}</span>`).join(' '):'<span style="color:var(--text3);font-size:11px">All free</span>'}</td>
    <td><span class="bdg ${r.online?'bg':'br'}">${r.online?'Online':'Offline'}</span></td>
    <td style="font-size:11px;color:var(--text2)">${r.last_seen?new Date(r.last_seen+'Z').toLocaleString():'Never'}</td>
    <td style="font-size:10px;color:var(--text3);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc((r.user_agent||'—').split(' ')[0]||'—')}</td>
    <td><div class="tda"><button class="btn btn-g btn-xs" onclick="eRoom(${r.id})">Edit</button><button class="btn btn-b btn-xs" onclick="rgenToken(${r.id},'${esc(r.room_number)}')">New Token</button><button class="btn btn-d btn-xs" onclick="dRoom(${r.id},'${esc(r.room_number)}')">Del</button></div></td></tr>`;}).join('')}
  </tbody></table></div>`;
  initBulk('rm',null,async()=>{const ids=getSelected('rm');if(!ids.length)return;if(!confirm('Delete '+ids.length+' '+termUnits.toLowerCase()+'?'))return;const r=await req('/rooms/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' '+termUnits.toLowerCase()+' deleted');await pages.rooms();}});
},

// ── ANDROID TV DEVICES ────────────────────────────────────────────────────────
async devices(){
  const devs=await req('/devices');if(!devs)return;
  document.getElementById('cnt-devices').textContent=devs.length;
  const on=devs.filter(d=>d.online).length;
  const ago=ts=>{if(!ts)return'Never';const s=Math.floor((Date.now()-new Date(ts+'Z'))/1000);if(s<60)return s+'s ago';if(s<3600)return Math.floor(s/60)+'m ago';if(s<86400)return Math.floor(s/3600)+'h ago';return Math.floor(s/86400)+'d ago';};
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">Android TV Devices</div>
  <div class="sec-acts"><span class="bdg bg">● ${on} Active</span><span class="bdg br">○ ${devs.length-on} Inactive</span></div></div>
  <div class="ibox info">📱 Devices register automatically when the Android TV app calls the heartbeat endpoint every 5&nbsp;minutes. A device is shown as <b>Active</b> if it checked in within the last 10&nbsp;minutes.</div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>MAC Address</th><th>Room</th><th>Device Name</th><th>App Version</th><th>Status</th><th>Last Seen</th><th>Registered</th></tr></thead>
    <tbody>${devs.length?devs.map(d=>`<tr>
      <td><b style="font-family:monospace;letter-spacing:.5px">${esc(d.mac_address)}</b></td>
      <td>${esc(d.room_number||'—')}</td>
      <td style="color:var(--text2)">${esc(d.device_name||'—')}</td>
      <td><span class="bdg bb" style="font-size:10px">${esc(d.app_version||'unknown')}</span></td>
      <td><span class="bdg ${d.online?'bg':'br'}">${d.online?'Active':'Inactive'}</span></td>
      <td style="font-size:11px;color:var(--text2)">${ago(d.last_seen)}</td>
      <td style="font-size:11px;color:var(--text3)">${d.created_at?new Date(d.created_at+'Z').toLocaleDateString():'—'}</td>
    </tr>`).join(''):'<tr><td colspan="7" style="text-align:center;color:var(--text3);padding:32px">No devices registered yet. Devices appear here after their first heartbeat.</td></tr>'}
    </tbody></table></div>`;
},

// ── SKINS ─────────────────────────────────────────────────────────────────────
async skins(){
  const skins=await req('/skins');if(!skins)return;window._skins=skins;
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">Skins &amp; Themes</div><button class="btn btn-p" onclick="eSkin(null)">+ Add Skin</button></div>
  <div class="ibox warn">⚠️ <b>Default Skin</b> must remain default and must not be deleted.</div>
  <div class="card-grid">${skins.map(s=>`<div class="card" style="${s.is_default?'border-color:var(--gold)':''}"><div class="card-title">${esc(s.name)}${s.is_default?'<span class="bdg bo">Default</span>':''}</div>
  <div class="card-sub">${esc(s.template)}</div>
  <div class="card-acts"><button class="btn btn-g btn-sm" onclick="eSkin(${s.id})">Edit</button>${!s.is_default?'<button class="btn btn-d btn-sm" onclick="dSkin('+s.id+',\''+esc(s.name)+'\')">Del</button>':''}</div>
  </div>`).join('')}</div>`;
},

// ── USERS ─────────────────────────────────────────────────────────────────────
async users(){
  const users=await req('/users');if(!users)return;
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">System Users</div><button class="btn btn-p" onclick="eUser()">+ Add User</button></div>
  <div class="tbl-wrap"><table><thead><tr><th>Username</th><th>Role</th><th>City / Region</th><th>Created</th><th>Actions</th></tr></thead>
  <tbody>${users.map(u=>`<tr><td><b>${esc(u.username)}</b>${u.id===me?.id?' <span class="bdg bg" style="font-size:9px">You</span>':''}</td>
  <td><span class="bdg ${u.role==='admin'?'bo':u.role==='operator'?'bb':'bg'}">${u.role}</span></td>
  <td style="font-size:12px;color:var(--text2)">${u.city?'🌍 '+esc(u.city):'<span style="color:var(--text3)">—</span>'}</td>
  <td style="font-size:11px;color:var(--text2)">${u.created_at||'—'}</td>
  <td style="display:flex;gap:6px"><button class="btn btn-g btn-sm" onclick="eEditUser(${u.id},'${esc(u.username)}','${esc(u.city||'')}','${u.role}')">Edit</button>${u.id!==me?.id?'<button class="btn btn-d btn-sm" onclick="dUser('+u.id+',\''+esc(u.username)+'\')">Delete</button>':''}</td></tr>`).join('')}
  </tbody></table></div>`;
},

// ── REPORTS ───────────────────────────────────────────────────────────────────
async reports(){
  document.getElementById('content').innerHTML=`
  <div class="sec-hdr"><div class="sec-title">Reports &amp; Analytics</div>
  <div class="sec-acts">
    <select id="rpt-days" onchange="loadRpt(this.value)" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:7px 12px;font-size:13px;outline:none">
      <option value="7">Last 7 Days</option><option value="30" selected>Last 30 Days</option><option value="90">Last 90 Days</option><option value="365">Last Year</option>
    </select>
  </div></div>
  <div class="tabs">
    <button class="tab on" onclick="swRpt('channels',this)">📺 Channels</button>
    <button class="tab" onclick="swRpt('rooms',this)">${(window._deployMode||'hotel')!=='commercial'?'🏨 Rooms':'🖥 Screens'}</button>
    <button class="tab" onclick="swRpt('vod',this)">🎬 Movies</button>
    <button class="tab" onclick="swRpt('radio',this)">📻 Radio</button>
    <button class="tab" onclick="swRpt('pages',this)">📄 Pages</button>
  </div>
  <div id="rpt-body"><div style="padding:32px;text-align:center;color:var(--text3)">Loading...</div></div>`;
  window._rptTab='channels';loadRpt(30);
}
};// end pages

function vodNav(el,src){
  document.querySelectorAll('.topnav a').forEach(a=>a.classList.remove('active'));
  el.classList.add('active');
  const f=document.getElementById('vod-frame');
  if(f) f.src=src+'&_ts='+Date.now();
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROW RENDERERS
// ═══════════════════════════════════════════════════════════════════════════════
const CTYPE_LABELS={'stream_udp':'🔵 UDP','m3u':'🟢 M3U','analog_tuner':'🟠 Tuner'};
function chRow(c){return'<tr id="chr-'+c.id+'"><td><input type="checkbox" class="row-chk-ch" value="'+c.id+'"></td><td><span style="font-family:\'DM Mono\',monospace;color:var(--text3)">'+(c.direct_play_num||'—')+'</span></td><td><b>'+esc(c.name)+'</b></td><td><span class="bdg '+(c.channel_type==='m3u'?'bg':c.channel_type==='analog_tuner'?'bor':'bb')+'" style="font-size:10px">'+(CTYPE_LABELS[c.channel_type]||'🔵 UDP')+'</span></td><td><span style="font-family:\'DM Mono\',monospace;font-size:10px;color:var(--text3);max-width:180px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+esc(c.stream_url)+'">'+esc(c.stream_url)+'</span></td><td><span class="bdg bb">'+esc(c.group_name||'—')+'</span></td><td><span class="bdg '+(c.active&&!c.temporarily_unavailable?'bg':c.temporarily_unavailable?'bo':'br')+'">'+(c.active?(c.temporarily_unavailable?'Temp.Off':'Active'):'Inactive')+'</span></td><td><div class="tda"><button class="btn btn-g btn-xs" onclick="eCh('+c.id+')">Edit</button><button class="btn btn-d btn-xs" onclick="dCh('+c.id+',\''+esc(c.name)+'\')">Del</button></div></td></tr>';}
function fChs(q){
  const gf = document.getElementById('ch-gf')?.value;
  const tf = document.getElementById('ch-tf')?.value;
  const tb = document.getElementById('ch-tbody');
  if (!tb) return;
  let l = window._chs || [];
  if (q) l = l.filter(c => c.name.toLowerCase().includes(q.toLowerCase()) || c.stream_url.includes(q));
  if (gf) l = l.filter(c => String(c.media_group_id) === gf);
  if (tf) l = l.filter(c => (c.channel_type || 'stream_udp') === tf);
  tb.innerHTML = l.map(c => chRow(c)).join('');
  // Re-attach bulk delete after re-render
  initBulk('ch', null, async () => {
    const ids = getSelected('ch');
    if (!ids.length) { toast('Select channels first'); return; }
    if (!confirm('Delete ' + ids.length + ' channel(s)?')) return;
    const r = await req('/channels/bulk-delete', {method:'POST', body:JSON.stringify({ids})});
    if (r?.ok) { toast('🗑 Deleted ' + r.deleted + ' channels'); await pages.channels(); }
  });
}
function vodRow(m){return'<tr id="vodr-'+m.id+'"><td><input type="checkbox" class="row-chk-vod" value="'+m.id+'"></td><td><b>'+esc(m.title)+'</b><div style="font-size:11px;color:var(--text3)">'+esc((m.description||'').substring(0,45))+(m.description?.length>45?'…':'')+'</div></td><td><span class="bdg bb">'+esc(m.genre)+'</span></td><td style="color:var(--text2)">'+(m.year||'—')+'</td><td><span style="color:var(--gold)">★'+m.rating+'</span></td><td><span class="bdg bo">$'+m.price+'</span></td><td><span class="bdg '+(m.active?'bg':'br')+'">'+(m.active?'Active':'Hidden')+'</span></td><td><div class="tda"><button class="btn btn-g btn-xs" onclick="eVod('+m.id+')">Edit</button><button class="btn btn-d btn-xs" onclick="dVod('+m.id+',\''+esc(m.title)+'\')">Del</button></div></td></tr>';}
function fVod(q){const tb=document.getElementById('vod-tbody');if(!tb)return;tb.innerHTML=(window._vod||[]).filter(m=>m.title.toLowerCase().includes(q.toLowerCase())).map(m=>vodRow(m)).join('');initBulk('vod',null,async()=>{const ids=getSelected('vod');if(!ids.length)return;if(!confirm('Delete '+ids.length+' movies?'))return;const r=await req('/vod/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' deleted');await pages.vod();}});}
function radioRow(s){return'<tr id="rsr-'+s.id+'"><td><input type="checkbox" class="row-chk-rad" value="'+s.id+'"></td><td><b>'+esc(s.name)+'</b></td><td>'+(esc(s.country)||'—')+'</td><td><span class="bdg bp">'+(esc(s.genre)||'—')+'</span></td><td><span style="font-family:\'DM Mono\',monospace;font-size:10px;color:var(--text3);max-width:170px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+esc(s.stream_url)+'">'+esc(s.stream_url)+'</span></td><td><span class="bdg '+(s.active?'bg':'br')+'">'+(s.active?'Active':'Inactive')+'</span></td><td><div class="tda"><button class="btn btn-g btn-xs" onclick="eStation('+s.id+')">Edit</button><button class="btn btn-d btn-xs" onclick="dStation('+s.id+',\''+esc(s.name)+'\')">Del</button></div></td></tr>';}
function fRadio(q){const ctry=document.getElementById('radio-ctry')?.value;const tb=document.getElementById('radio-tbody');if(!tb)return;let l=window._stations||[];if(q)l=l.filter(s=>s.name.toLowerCase().includes(q.toLowerCase()));if(ctry)l=l.filter(s=>s.country===ctry);tb.innerHTML=l.map(s=>radioRow(s)).join('');initBulk('rad',null,async()=>{const ids=getSelected('rad');if(!ids.length)return;if(!confirm('Delete '+ids.length+' stations?'))return;const r=await req('/radio/bulk-delete',{method:'POST',body:JSON.stringify({ids})});if(r?.ok){toast('🗑 '+r.deleted+' deleted');await pages.radio();}});}

// ═══════════════════════════════════════════════════════════════════════════════
// CHANNEL CRUD (with channel type)
// ═══════════════════════════════════════════════════════════════════════════════
function eCh(id){const c=id?(window._chs||[]).find(x=>x.id===id):null;const gs=window._groups||[];const ct=c?.channel_type||'stream_udp';
openModal(c?'Edit Channel':'Add Channel',`<div class="fgrid">
<div class="fg fcol"><label>Channel Name *</label><input id="c-name" value="${esc(c?.name||'')}"></div>
<div class="fg fcol"><label>Channel Type</label>
  <div class="ctype-row">
    <label class="ctype-opt${ct==='stream_udp'?' on':''}" onclick="setCType(this,'stream_udp')"><input type="radio" name="c-type" value="stream_udp" ${ct==='stream_udp'?'checked':''}>🔵 UDP / Multicast</label>
    <label class="ctype-opt${ct==='m3u'?' on':''}" onclick="setCType(this,'m3u')"><input type="radio" name="c-type" value="m3u" ${ct==='m3u'?'checked':''}>🟢 M3U / HLS</label>
    <label class="ctype-opt${ct==='analog_tuner'?' on':''}" onclick="setCType(this,'analog_tuner')"><input type="radio" name="c-type" value="analog_tuner" ${ct==='analog_tuner'?'checked':''}>🟠 Analog Tuner</label>
  </div>
</div>
<div class="fg fcol"><label>Stream URL / Frequency *</label><input id="c-url" value="${esc(c?.stream_url||'')}" placeholder="udp://@224.x.x.x:port  or  http://...  or  freq:channel_num"></div>
<div class="fg"><label>Media Group</label><select id="c-grp">${gs.map(g=>'<option value="'+g.id+'"'+(c?.media_group_id===g.id?' selected':'')+'>'+esc(g.name)+'</option>').join('')}</select></div>
<div class="fg"><label>Direct Play #</label><input id="c-num" type="number" value="${c?.direct_play_num||''}"></div>
<div class="fg"><label>Logo</label><input id="c-logo" value="${esc(c?.logo||'')}"></div>
<div class="fg"><label>Status</label><select id="c-active"><option value="1" ${!c||c.active?'selected':''}>Active</option><option value="0" ${c&&!c.active?'selected':''}>Inactive</option></select></div>
<div class="fg fcol"><label style="display:flex;align-items:center;gap:8px;cursor:pointer"><input type="checkbox" id="c-tmp" ${c?.temporarily_unavailable?'checked':''} style="width:14px;height:14px;accent-color:var(--gold)"><span>Temporarily Unavailable</span></label></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svCh(${id||'null'})">Save Channel</button>`);}
function setCType(el,val){document.querySelectorAll('.ctype-opt').forEach(o=>o.classList.remove('on'));el.classList.add('on');el.querySelector('input').checked=true;}
async function svCh(id){const d={name:document.getElementById('c-name').value.trim(),stream_url:document.getElementById('c-url').value.trim(),media_group_id:parseInt(document.getElementById('c-grp').value),direct_play_num:parseInt(document.getElementById('c-num').value)||null,logo:document.getElementById('c-logo').value.trim(),active:parseInt(document.getElementById('c-active').value),temporarily_unavailable:document.getElementById('c-tmp').checked?1:0,channel_type:[...document.querySelectorAll('input[name=c-type]')].find(r=>r.checked)?.value||'stream_udp'};
if(!d.name||!d.stream_url){alert('Name and URL required');return;}
const r=id?await req('/channels/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/channels',{method:'POST',body:JSON.stringify(d)});
if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Channel updated':'✅ Channel added');await pages.channels();}
async function dCh(id,name){if(!confirm('Delete "'+name+'"?'))return;await req('/channels/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.channels();}

// ── M3U Import ────────────────────────────────────────────────────────────────
function openM3UImport(){
  openModal('M3U Import',`
  <div class="ibox info">📥 Import channels directly from an M3U playlist. Groups will be auto-created.<br>A server-side M3U file can be used when the URL is left blank.</div>
  <div class="fgrid">
    <div class="fg fcol"><label>M3U URL or leave blank to use server file</label><input id="m3u-url" placeholder="http://... or leave blank"></div>
    <div class="fg"><label>Filter by Group (optional)</label><input id="m3u-grp" placeholder="e.g. News, Sports"></div>
    <div class="fg"><label>Max Channels (0 = all)</label><input id="m3u-max" type="number" value="0"></div>
    <div class="fg fcol"><label>Channel Type for imported channels</label>
      <select id="m3u-ctype" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none">
        <option value="m3u">🟢 M3U / HLS</option>
        <option value="stream_udp">🔵 UDP / Multicast</option>
      </select>
    </div>
  </div>
  <div id="m3u-prog" style="display:none"><div class="prog-wrap"><div class="prog-fill" id="m3u-pfill" style="width:0%"></div></div><div id="m3u-ptext" style="font-size:12px;color:var(--text2);margin-top:5px">Importing...</div></div>
  <div id="m3u-result" style="margin-top:10px"></div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="runM3UImport()">📥 Start Import</button>`,'modal-lg');}
async function runM3UImport(){
  const url=document.getElementById('m3u-url').value.trim();
  const grp=document.getElementById('m3u-grp').value.trim();
  const max=parseInt(document.getElementById('m3u-max').value)||0;
  const ctype=document.getElementById('m3u-ctype').value;
  document.getElementById('m3u-prog').style.display='block';
  document.getElementById('m3u-pfill').style.width='30%';
  document.getElementById('m3u-ptext').textContent='Uploading to server...';
  const body={channel_type:ctype};
  if(url)body.url=url;
  if(grp)body.group_filter=grp;
  if(max)body.max_channels=max;
  const r=await req('/channels/import-m3u',{method:'POST',body:JSON.stringify(body)});
  document.getElementById('m3u-pfill').style.width='100%';
  if(!r){document.getElementById('m3u-result').innerHTML='<div style="color:var(--red)">Import failed — server error</div>';return;}
  document.getElementById('m3u-ptext').textContent='Done!';
  document.getElementById('m3u-result').innerHTML='<div style="color:var(--green);font-size:13px">✅ Imported: <b>'+fmtNum(r.imported||0)+'</b> channels &nbsp; Skipped: <b>'+(r.skipped||0)+'</b></div>';
  await updateCounts();
}

// ── CSV Import modal ──────────────────────────────────────────────────────────
const CSV_TEMPLATES={
  channels:{cols:'name,stream_url,channel_type,group_name,logo',hint:'channel_type: stream_udp | m3u | analog_tuner'},
  vod:{cols:'title,genre,year,language,runtime,rating,price,stream_url,description',hint:''},
  packages:{cols:'name,description,price,duration_hours',hint:'price in USD, duration_hours is integer'},
  radio:{cols:'name,stream_url,country,genre,logo',hint:''},
  rooms:{cols:'room_number,tv_name',hint:'tv_name is optional'},
  groups:{cols:'name',hint:'One group name per row'}
};
function openCSVImport(type){
  const t=CSV_TEMPLATES[type]||{cols:'',hint:''};
  openModal('CSV Bulk Import — '+type.toUpperCase(),`
  <div class="ibox info">📋 <b>CSV Format:</b> First row must be headers. Required columns: <code style="background:var(--bg4);padding:1px 6px;border-radius:4px;font-family:'DM Mono',monospace">${t.cols}</code>${t.hint?'<br>'+t.hint:''}</div>
  <div class="csv-drop" id="csv-drop" onclick="document.getElementById('csv-file').click()" ondragover="event.preventDefault();this.classList.add('drag')" ondragleave="this.classList.remove('drag')" ondrop="handleCSVDrop(event,'${type}')">
    <input type="file" id="csv-file" accept=".csv,.txt" style="display:none" onchange="handleCSVFile(event,'${type}')">
    <div style="font-size:28px;margin-bottom:8px">📄</div>
    <div><b>Click to choose CSV file</b> or drag &amp; drop</div>
    <div style="font-size:12px;margin-top:4px;color:var(--text3)">Supports .csv and .txt files</div>
  </div>
  <div style="margin:12px 0;text-align:center;color:var(--text3);font-size:12px">— or paste CSV text below —</div>
  <textarea id="csv-text" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:10px;color:var(--text);font-family:'DM Mono',monospace;font-size:12px;height:110px;outline:none;resize:vertical" placeholder="${t.cols}&#10;Row 1 data...&#10;Row 2 data..."></textarea>
  <div id="csv-preview" style="margin-top:10px"></div>
  <div id="csv-result" style="margin-top:8px"></div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="runCSVImport('${type}')">📥 Import</button>`,'modal-lg');}
function handleCSVDrop(e,type){e.preventDefault();document.getElementById('csv-drop').classList.remove('drag');const file=e.dataTransfer.files[0];if(file)loadCSVFile(file,type);}
function handleCSVFile(e,type){const file=e.target.files[0];if(file)loadCSVFile(file,type);}
function loadCSVFile(file,type){const reader=new FileReader();reader.onload=e=>{document.getElementById('csv-text').value=e.target.result;previewCSV(type);};reader.readAsText(file);}
function previewCSV(type){const text=document.getElementById('csv-text').value;const rows=parseCSV(text);const el=document.getElementById('csv-preview');if(!rows.length){el.innerHTML='';return;}el.innerHTML='<div style="font-size:12px;color:var(--text2);padding:6px 0">Preview: <b style="color:var(--text)">'+rows.length+'</b> rows detected. First row: '+Object.entries(rows[0]).map(([k,v])=>'<b>'+esc(k)+'</b>='+esc(v.substring(0,20))).join(', ')+'</div>';}
async function runCSVImport(type){
  const text=document.getElementById('csv-text').value.trim();
  if(!text){alert('No CSV data');return;}
  const rows=parseCSV(text);
  if(!rows.length){alert('No valid rows found');return;}
  const epMap={channels:'/channels/bulk-import-csv',vod:'/vod/bulk-add',packages:'/vod/packages/bulk-add',radio:'/radio/bulk-add',rooms:'/rooms/bulk-add',groups:'/media-groups/bulk-add'};
  const ep=epMap[type];if(!ep)return;
  let body;
  if(type==='groups')body={names:rows.map(r=>r.name||r[Object.keys(r)[0]]).filter(Boolean)};
  else if(type==='rooms')body={rooms:rows};
  else body={rows};
  document.getElementById('csv-result').innerHTML='<div style="color:var(--text2)">Importing...</div>';
  const r=await req(ep,{method:'POST',body:JSON.stringify(body)});
  if(!r){document.getElementById('csv-result').innerHTML='<div style="color:var(--red)">Failed</div>';return;}
  let msg='✅ Added/Imported: <b>'+(r.added||r.imported||0)+'</b>';
  if(r.errors?.length)msg+=' &nbsp; ⚠️ '+r.errors.length+' errors: '+r.errors.slice(0,3).join(', ');
  document.getElementById('csv-result').innerHTML='<div style="color:var(--green);font-size:13px">'+msg+'</div>';
  await updateCounts();
}

// ── Bulk Add Groups ───────────────────────────────────────────────────────────
function openBulkAdd(type){
  openModal('Bulk Add Media Groups',`
  <div class="ibox info">Enter one group name per line.</div>
  <textarea id="bulk-names" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:10px;color:var(--text);font-family:'DM Mono',monospace;font-size:13px;height:160px;outline:none;resize:vertical" placeholder="Sports\nNews\nEntertainment\nKids\n..."></textarea>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="runBulkAddGroups()">Add Groups</button>`);}
async function runBulkAddGroups(){const names=document.getElementById('bulk-names').value.split('\n').map(s=>s.trim()).filter(Boolean);const r=await req('/media-groups/bulk-add',{method:'POST',body:JSON.stringify({names})});if(r?.ok){closeModal();toast('✅ '+r.added+' groups added');await pages.groups();}}

// ── Bulk Add Rooms ────────────────────────────────────────────────────────────
function openBulkAddRooms(){
  openModal('Bulk Add Rooms',`
  <div class="ibox info">Add a range of room numbers or enter individual numbers.<br><b>Range:</b> e.g. <code style="background:var(--bg4);padding:1px 6px;border-radius:4px;font-family:'DM Mono',monospace">101-120</code> adds rooms 101, 102 … 120</div>
  <div class="fgrid">
    <div class="fg"><label>From Room #</label><input id="rm-from" type="number" placeholder="101"></div>
    <div class="fg"><label>To Room #</label><input id="rm-to" type="number" placeholder="120"></div>
    <div class="fg"><label>TV Name Prefix</label><input id="rm-prefix" placeholder="TV-" value="TV-"></div>
    <div class="fg"><label>Floor Prefix (optional)</label><input id="rm-floor" placeholder="Leave blank to use number as-is"></div>
  </div>
  <div style="margin:10px 0;text-align:center;color:var(--text3);font-size:12px">— or enter room numbers one per line —</div>
  <textarea id="rm-list" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:10px;color:var(--text);font-family:'DM Mono',monospace;font-size:13px;height:80px;outline:none;resize:vertical" placeholder="201\n202\n203..."></textarea>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="runBulkAddRooms()">Add Rooms</button>`);}
async function runBulkAddRooms(){
  const from=parseInt(document.getElementById('rm-from').value)||0;
  const to=parseInt(document.getElementById('rm-to').value)||0;
  const prefix=document.getElementById('rm-prefix').value||'TV-';
  const list=document.getElementById('rm-list').value.split('\n').map(s=>s.trim()).filter(Boolean);
  const rooms=[];
  if(from&&to&&to>=from){for(let n=from;n<=to;n++)rooms.push({room_number:String(n),tv_name:prefix+n});}
  list.forEach(n=>rooms.push({room_number:n,tv_name:prefix+n}));
  if(!rooms.length){alert('No rooms to add');return;}
  const r=await req('/rooms/bulk-add',{method:'POST',body:JSON.stringify({rooms,prefix})});
  if(r?.ok){closeModal();toast('✅ '+r.added+' rooms added'+(r.errors?.length?' ('+r.errors.length+' skipped)':''));await pages.rooms();}
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUPS CRUD
// ═══════════════════════════════════════════════════════════════════════════════
function eGroup(id){const g=id?(window._groups||[]).find(x=>x.id===id):null;
openModal(g?'Edit Group':'Add Group',`<div class="fgrid">
<div class="fg fcol"><label>Group Name *</label><input id="g-name" value="${esc(g?.name||'')}"></div>
<div class="fg"><label>Status</label><select id="g-active"><option value="1" ${!g||g.active?'selected':''}>Active</option><option value="0" ${g&&!g.active?'selected':''}>Inactive</option></select></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svGroup(${id||'null'})">Save</button>`);}
async function svGroup(id){const d={name:document.getElementById('g-name').value.trim(),active:parseInt(document.getElementById('g-active').value)};if(!d.name)return;const r=id?await req('/media-groups/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/media-groups',{method:'POST',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Created');await pages.groups();}
async function dGroup(id,name){if(!confirm('Delete "'+name+'"?'))return;await req('/media-groups/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.groups();}

// ═══════════════════════════════════════════════════════════════════════════════
// VOD CRUD
// ═══════════════════════════════════════════════════════════════════════════════
function eVod(id){const m=id?(window._vod||[]).find(x=>x.id===id):null;
openModal(m?'Edit Movie':'Add Movie',`<div class="fgrid">
<div class="fg fcol"><label>Title *</label><input id="m-title" value="${esc(m?.title||'')}"></div>
<div class="fg fcol"><label>Description</label><textarea id="m-desc">${esc(m?.description||'')}</textarea></div>
<div class="fg"><label>Genre</label><input id="m-genre" value="${esc(m?.genre||'')}"></div>
<div class="fg"><label>Year</label><input id="m-year" type="number" value="${m?.year||''}"></div>
<div class="fg"><label>Language</label><input id="m-lang" value="${esc(m?.language||'English')}"></div>
<div class="fg"><label>Runtime (min)</label><input id="m-runtime" type="number" value="${m?.runtime||0}"></div>
<div class="fg"><label>Rating (0-10)</label><input id="m-rating" type="number" step="0.1" max="10" value="${m?.rating||0}"></div>
<div class="fg"><label>Price ($)</label><input id="m-price" type="number" step="0.01" value="${m?.price||0}"></div>
<div class="fg fcol"><label>Stream URL</label><input id="m-stream" value="${esc(m?.stream_url||'')}"></div>
<div class="fg"><label>Status</label><select id="m-active"><option value="1" ${!m||m.active?'selected':''}>Active</option><option value="0" ${m&&!m.active?'selected':''}>Hidden</option></select></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svVod(${id||'null'})">Save</button>`);}
async function svVod(id){const d={title:document.getElementById('m-title').value.trim(),description:document.getElementById('m-desc').value,genre:document.getElementById('m-genre').value,year:parseInt(document.getElementById('m-year').value)||null,language:document.getElementById('m-lang').value||'English',runtime:parseInt(document.getElementById('m-runtime').value)||0,rating:parseFloat(document.getElementById('m-rating').value)||0,price:parseFloat(document.getElementById('m-price').value)||0,stream_url:document.getElementById('m-stream').value,active:parseInt(document.getElementById('m-active').value)};if(!d.title)return;const r=id?await req('/vod/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/vod',{method:'POST',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Added');await pages.vod();}
async function dVod(id,title){if(!confirm('Delete "'+title+'"?'))return;await req('/vod/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.vod();}

// ═══════════════════════════════════════════════════════════════════════════════
// PACKAGES CRUD
// ═══════════════════════════════════════════════════════════════════════════════
function ePkg(id){const p=id?(window._pkgs||[]).find(x=>x.id===id):null;
openModal(p?'Edit Package':'Add Package',`<div class="fgrid">
<div class="fg fcol"><label>Package Name *</label><input id="p-name" value="${esc(p?.name||'')}"></div>
<div class="fg fcol"><label>Description</label><input id="p-desc" value="${esc(p?.description||'')}"></div>
<div class="fg"><label>Price ($)</label><input id="p-price" type="number" step="0.01" value="${p?.price||0}"></div>
<div class="fg"><label>Duration (hours)</label><input id="p-dur" type="number" value="${p?.duration_hours||24}"></div>
<div class="fg"><label>Status</label><select id="p-active"><option value="1" ${!p||p.active?'selected':''}>Active</option><option value="0" ${p&&!p.active?'selected':''}>Inactive</option></select></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svPkg(${id||'null'})">Save</button>`);}
async function svPkg(id){const d={name:document.getElementById('p-name').value.trim(),description:document.getElementById('p-desc').value,price:parseFloat(document.getElementById('p-price').value)||0,duration_hours:parseInt(document.getElementById('p-dur').value)||24,active:parseInt(document.getElementById('p-active').value)};if(!d.name)return;const r=id?await req('/vod/packages/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/vod/packages',{method:'POST',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Created');await pages.packages();}
async function dPkg(id,name){if(!confirm('Delete "'+name+'"?'))return;await req('/vod/packages/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.packages();}

// ═══════════════════════════════════════════════════════════════════════════════
// RADIO CRUD
// ═══════════════════════════════════════════════════════════════════════════════
function eStation(id){const s=id?(window._stations||[]).find(x=>x.id===id):null;
openModal(s?'Edit Station':'Add Station',`<div class="fgrid">
<div class="fg fcol"><label>Station Name *</label><input id="s-name" value="${esc(s?.name||'')}"></div>
<div class="fg"><label>Country</label><input id="s-ctry" value="${esc(s?.country||'')}"></div>
<div class="fg"><label>Genre</label><input id="s-genre" value="${esc(s?.genre||'')}"></div>
<div class="fg fcol"><label>Stream URL *</label><input id="s-url" value="${esc(s?.stream_url||'')}"></div>
<div class="fg"><label>Logo URL</label><input id="s-logo" value="${esc(s?.logo||'')}"></div>
<div class="fg"><label>Status</label><select id="s-active"><option value="1" ${!s||s.active?'selected':''}>Active</option><option value="0" ${s&&!s.active?'selected':''}>Inactive</option></select></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svStation(${id||'null'})">Save</button>`);}
async function svStation(id){const d={name:document.getElementById('s-name').value.trim(),country:document.getElementById('s-ctry').value,genre:document.getElementById('s-genre').value,stream_url:document.getElementById('s-url').value.trim(),logo:document.getElementById('s-logo').value,active:parseInt(document.getElementById('s-active').value)};if(!d.name||!d.stream_url){alert('Name and URL required');return;}const r=id?await req('/radio/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/radio',{method:'POST',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Added');await pages.radio();}
async function dStation(id,name){if(!confirm('Delete "'+name+'"?'))return;await req('/radio/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.radio();}

// ═══════════════════════════════════════════════════════════════════════════════
// CONTENT PAGES CRUD + RICH TEXT ITEMS
// ═══════════════════════════════════════════════════════════════════════════════
function ePage(id){const p=id?(window._pages||[]).find(x=>x.id===id):null;
openModal(p?'Edit Page':'Add Page',`<div class="fgrid">
<div class="fg fcol"><label>Page Name *</label><input id="pg-name" value="${esc(p?.name||'')}"></div>
<div class="fg"><label>Group</label><input id="pg-grp" value="${esc(p?.group_name||'Hotel')}" placeholder="Hotel, F&B..."></div>
<div class="fg"><label>Template</label><select id="pg-tmpl">${['Default','Map','Gallery','List','Menu'].map(t=>'<option'+(p?.template===t?' selected':'')+'>'+t+'</option>').join('')}</select></div>
<div class="fg"><label>Status</label><select id="pg-active"><option value="1" ${!p||p.active?'selected':''}>Active</option><option value="0" ${p&&!p.active?'selected':''}>Hidden</option></select></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svPage(${id||'null'})">Save</button>`);}
async function svPage(id){const d={name:document.getElementById('pg-name').value.trim(),group_name:document.getElementById('pg-grp').value||'Hotel',template:document.getElementById('pg-tmpl').value,active:parseInt(document.getElementById('pg-active').value)};if(!d.name)return;const r=id?await req('/content/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/content',{method:'POST',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Created');await pages.pages();}
async function dPage(id,name){if(!confirm('Delete page "'+name+'" and all its items?'))return;await req('/content/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.pages();}

function renderInlineItems(pid){
  const items=(window._pageItems||{})[pid]||[];
  if(!items.length)return'<div style="color:var(--text3);font-size:12px;text-align:center;padding:10px 0">No items yet — click + Add Item to get started.</div>';
  return items.map(i=>`
  <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:12px;display:flex;align-items:stretch">
    <div style="flex:0 0 130px;height:90px;border-radius:7px;overflow:hidden;border:1px solid var(--border);background:var(--bg4);display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:24px;flex-shrink:0;margin-right:14px">
      ${i.photo_url||i.image?'<img src="'+(i.photo_url||i.image)+'" style="width:100%;height:100%;object-fit:cover" alt="">':'&#128247;'}
    </div>
    <div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:4px">
      <div style="font-weight:700;font-size:13px;color:var(--text)">${esc(i.title)}</div>
      ${i.content_html?'<span style="display:inline-block;font-size:9px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:4px;padding:1px 5px;margin-bottom:2px;width:fit-content">Rich Text</span>':''}
      <div style="font-size:12px;color:var(--text2);line-height:1.4">${esc((i.description||'').substring(0,120))}${(i.description||'').length>120?'…':''}</div>
    </div>
    <div style="display:flex;flex-direction:column;gap:5px;justify-content:center;flex-shrink:0;margin-left:10px">
      <button class="btn btn-g btn-xs" onclick="inlineEditItem(${i.id},${pid})">Edit</button>
      <button class="btn btn-d btn-xs" onclick="inlineDelItem(${i.id},${pid})">Del</button>
    </div>
  </div>`).join('');
}

function inlineAddItem(pid){
  window._editPid=pid;window._editItems=(window._pageItems||{})[pid]||[];
  openItemForm(null);
}
function inlineEditItem(iid,pid){
  window._editPid=pid;window._editItems=(window._pageItems||{})[pid]||[];
  openItemForm(iid);
}
async function inlineDelItem(iid,pid){
  if(!confirm('Delete this item?'))return;
  await req('/content/items/'+iid,{method:'DELETE'});
  toast('🗑 Deleted');
  const fresh=await req('/content/'+pid+'/items');
  if(!window._pageItems)window._pageItems={};
  window._pageItems[pid]=fresh||[];
  const el=document.getElementById('page-items-'+pid);
  if(el)el.innerHTML=renderInlineItems(pid);
}

async function ePageItems(pid,pname){
  const items=await req('/content/'+pid+'/items');
  window._editPid=pid;window._editItems=items||[];
  renderItemsMdl(pname);
}
function renderItemsMdl(pname){
  const items=window._editItems||[];
  openModal('Items — '+pname,`
  <div style="display:flex;justify-content:flex-end;margin-bottom:12px">
    <button class="btn btn-p btn-sm" onclick="openItemForm(null)">+ Add Item</button>
  </div>
  <div id="items-list">
    ${items.length===0?'<div style="color:var(--text3);text-align:center;padding:24px">No items. Click Add Item.</div>':items.map(i=>`
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:10px;display:flex;align-items:stretch;gap:0">

      <div style="flex:0 0 130px;height:90px;border-radius:7px;overflow:hidden;border:1px solid var(--border);background:var(--bg4);display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:24px;flex-shrink:0;margin-right:14px">
        ${i.photo_url||i.image?'<img src="'+(i.photo_url||i.image)+'" style="width:100%;height:100%;object-fit:cover" alt="">':'&#128247;'}
      </div>

      <div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:4px">
        <div style="font-weight:700;font-size:13px;color:var(--text)">${esc(i.title)}</div>
        ${i.content_html?'<span style="display:inline-block;font-size:9px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:4px;padding:1px 5px;margin-bottom:2px;width:fit-content">Rich Text</span>':''}
        <div style="font-size:12px;color:var(--text2);line-height:1.4">${esc((i.description||'').substring(0,100))}${(i.description||'').length>100?'…':''}</div>
      </div>

      <div style="display:flex;flex-direction:column;gap:5px;justify-content:center;flex-shrink:0;margin-left:10px">
        <button class="btn btn-g btn-xs" onclick="openItemForm(${i.id})">Edit</button>
        <button class="btn btn-d btn-xs" onclick="delItem(${i.id})">Del</button>
      </div>
    </div>`).join('')}
  </div>`,'<button class="btn btn-g" onclick="closeModal()">Close</button>',true);}

function openItemForm(id){
  const item=(window._editItems||[]).find(x=>x.id===id)||null;
  const photoUrl=item?.photo_url||item?.image||'';
  openModal(item?'Edit Item':'Add Item',`
  <div class="fgrid">
    <div class="fg fcol" style="grid-column:1/-1"><label>Title *</label><input id="it-title" value="${esc(item?.title||'')}"></div>

    <div style="grid-column:1/-1;display:flex;gap:16px;align-items:flex-start">

      <div style="flex:0 0 220px;display:flex;flex-direction:column;gap:8px">
        <label style="font-size:12px;color:var(--text2);font-weight:600">Photo / Image</label>
        <div style="display:flex;gap:6px;align-items:stretch">
          <input id="it-img" value="${esc(photoUrl)}" placeholder="Paste URL…" oninput="prevItemPhoto(this.value)" style="flex:1;min-width:0;font-size:12px">
          <label style="display:flex;align-items:center;gap:4px;padding:6px 10px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.25);border-radius:8px;cursor:pointer;font-size:11px;white-space:nowrap;flex-shrink:0" title="Upload image file">
            &#128193; Upload
            <input type="file" accept="image/*" style="display:none" onchange="uploadItemPhoto(event)">
          </label>
        </div>
        <div id="it-img-wrap" style="width:100%;height:150px;border-radius:8px;border:1px solid var(--border);background:var(--bg4);display:flex;align-items:center;justify-content:center;overflow:hidden;color:var(--text3);font-size:28px">
          ${photoUrl?`<img id="it-img-prev" src="${esc(photoUrl)}" style="width:100%;height:100%;object-fit:cover" alt="preview">`:'<span id="it-img-prev-ico">&#128247;</span>'}
        </div>
      </div>

      <div style="flex:1;display:flex;flex-direction:column;gap:8px">
        <label style="font-size:12px;color:var(--text2);font-weight:600">Short Description</label>
        <textarea id="it-desc" style="height:168px;resize:vertical">${esc(item?.description||'')}</textarea>
      </div>
    </div>
    <div class="fg fcol" style="grid-column:1/-1">
      <label>Rich Text Content</label>
      <div class="rte-toolbar" id="rte-tb">
        <button class="rte-btn" onclick="rte('bold')" title="Bold"><b>B</b></button>
        <button class="rte-btn" onclick="rte('italic')" title="Italic"><i>I</i></button>
        <button class="rte-btn" onclick="rte('underline')" title="Underline"><u>U</u></button>
        <button class="rte-btn" onclick="rte('strikeThrough')" title="Strike">S&#773;</button>
        <button class="rte-btn" onclick="rteBlock('h1')" title="H1">H1</button>
        <button class="rte-btn" onclick="rteBlock('h2')" title="H2">H2</button>
        <button class="rte-btn" onclick="rteBlock('h3')" title="H3">H3</button>
        <button class="rte-btn" onclick="rte('insertUnorderedList')" title="Bullet List">• List</button>
        <button class="rte-btn" onclick="rte('insertOrderedList')" title="Numbered List">1. List</button>
        <button class="rte-btn" onclick="rteBlock('blockquote')" title="Quote">❝ Quote</button>
        <button class="rte-btn" onclick="rteLink()" title="Link">🔗</button>
        <button class="rte-btn" onclick="rte('removeFormat')" title="Clear">✕ Clear</button>
      </div>
      <div class="rte-body" id="rte-body" contenteditable="true">${item?.content_html||''}</div>
    </div>

    <div class="fg fcol" style="grid-column:1/-1">
      <label style="display:flex;align-items:center;gap:8px">
        Gallery Images <span style="font-size:10px;color:var(--text3);font-weight:400">(auto-slideshow on TV)</span>
      </label>
      ${id ? `
      <div style="display:flex;gap:6px;align-items:stretch;margin-bottom:8px">
        <input id="gal-url-inp" placeholder="Paste image URL and click Add…" style="flex:1;font-size:12px">
        <button class="btn btn-g btn-sm" onclick="galAddUrl(${id})">+ Add URL</button>
        <label style="display:flex;align-items:center;gap:4px;padding:6px 12px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.25);border-radius:8px;cursor:pointer;font-size:11px;white-space:nowrap;flex-shrink:0">
          &#128193; Upload
          <input type="file" accept="image/*" multiple style="display:none" onchange="galUploadFiles(event,${id})">
        </label>
      </div>
      <div id="gal-grid" style="display:flex;flex-wrap:wrap;gap:8px">
        ${(item?.images||[]).length===0
          ? '<div style="color:var(--text3);font-size:12px;padding:8px 0">No gallery images yet.</div>'
          : (item.images||[]).map(img=>`
            <div id="gal-img-${img.id}" style="position:relative;width:90px;height:68px;border-radius:7px;overflow:hidden;border:1px solid var(--border);flex-shrink:0">
              <img src="${esc(img.url)}" style="width:100%;height:100%;object-fit:cover" alt="">
              <button onclick="galDel(${img.id},${id})" style="position:absolute;top:2px;right:2px;background:rgba(0,0,0,.7);border:none;color:#fff;width:18px;height:18px;border-radius:4px;cursor:pointer;font-size:11px;line-height:1;display:flex;align-items:center;justify-content:center">✕</button>
            </div>`).join('')}
      </div>` : `<div style="color:var(--text3);font-size:12px;padding:8px 0;border:1px dashed var(--border);border-radius:8px;text-align:center">Save item first, then you can add gallery images.</div>`}
    </div>
    <div class="fg"><label>Sort Order</label><input id="it-ord" type="number" value="${item?.sort_order||0}"></div>
    <div class="fg"><label>Status</label><select id="it-active"><option value="1" ${!item||item.active?'selected':''}>Active</option><option value="0" ${item&&!item.active?'selected':''}>Hidden</option></select></div>
  </div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svItem(${id||'null'})">Save Item</button>`,'modal-lg');}

// RTE helpers
function rte(cmd){document.getElementById('rte-body').focus();document.execCommand(cmd,false,null);}
function rteBlock(tag){document.getElementById('rte-body').focus();document.execCommand('formatBlock',false,tag);}
function rteLink(){const url=prompt('Enter URL:');if(url){document.getElementById('rte-body').focus();document.execCommand('createLink',false,url);}}
function prevPhoto(url){const img=document.getElementById('it-img-prev');if(!img)return;img.src=url;img.className='ph-prev'+(url?' on':'');}
function prevItemPhoto(url){
  const wrap=document.getElementById('it-img-wrap');if(!wrap)return;
  if(url){
    wrap.innerHTML='<img id="it-img-prev" src="'+url+'" style="width:100%;height:100%;object-fit:cover" alt="preview">';
  } else {
    wrap.innerHTML='<span id="it-img-prev-ico">&#128247;</span>';
  }
}
async function uploadItemPhoto(event){
  const file=event.target.files[0];if(!file)return;
  if(file.size>10*1024*1024){toast('Image too large. Max 10MB.');return;}
  const fd=new FormData();fd.append('file',file);
  const lbl=event.target.closest('label');const orig=lbl?lbl.innerHTML:'';
  if(lbl)lbl.innerHTML='<span>Uploading…</span>';
  try{
    const h={};if(jwt)h['Authorization']='Bearer '+jwt;
    const res=await fetch(API+'/upload',{method:'POST',headers:h,body:fd});
    const data=await res.json();
    if(!data.url){toast('Upload failed: '+(data.error||'unknown'));return;}
    const inp=document.getElementById('it-img');if(inp){inp.value=data.url;}
    prevItemPhoto(data.url);
    toast('Photo uploaded');
  }catch(e){toast('Upload error: '+e.message);}
  finally{if(lbl)lbl.innerHTML=orig;}
}

// ── Gallery helpers ──────────────────────────────────────────────────────────
let _galCurrentIid=null;

function _galRenderGrid(imgs){
  const grid=document.getElementById('gal-grid');if(!grid)return;
  if(!imgs.length){grid.innerHTML='<div style="color:var(--text3);font-size:12px;padding:8px 0">No gallery images yet.</div>';return;}
  grid.innerHTML=imgs.map(img=>{
    const pos=img.position||'center center';
    const fit=img.fit||'cover';
    return `<div id="gal-img-${img.id}" style="position:relative;width:100px;height:76px;border-radius:7px;overflow:hidden;border:2px solid var(--border);flex-shrink:0;cursor:pointer" title="Click to adjust">
      <img src="${esc(img.url)}" style="width:100%;height:100%;object-fit:${fit};object-position:${pos}" alt="">
      <div style="position:absolute;inset:0;background:rgba(0,0,0,0);transition:.15s" onmouseover="this.style.background='rgba(0,0,0,.35)'" onmouseout="this.style.background='rgba(0,0,0,0)'"></div>
      <button onclick="galOpenEditor(${img.id},'${esc(img.url)}','${pos}','${fit}')" style="position:absolute;bottom:3px;left:3px;background:rgba(0,0,0,.75);border:none;color:#fff;padding:2px 6px;border-radius:4px;cursor:pointer;font-size:10px;font-weight:600">✎ Adjust</button>
      <button onclick="galDel(${img.id})" style="position:absolute;top:3px;right:3px;background:rgba(0,0,0,.75);border:none;color:#fff;width:18px;height:18px;border-radius:4px;cursor:pointer;font-size:11px">✕</button>
    </div>`;
  }).join('');
}

// ── Photo adjustment editor ──────────────────────────────────────────────────
let _galEditId=null;
const _GAL_POSITIONS=[
  ['top left','top center','top right'],
  ['center left','center center','center right'],
  ['bottom left','bottom center','bottom right']
];

function galOpenEditor(imgId, url, pos, fit){
  _galEditId=imgId;
  const posLabel={'top left':'↖','top center':'↑','top right':'↗','center left':'←','center center':'⊕','center right':'→','bottom left':'↙','bottom center':'↓','bottom right':'↘'};
  const fitIcon={'cover':'⬛ Cover (crop to fill)','contain':'🔲 Contain (show full)'};

  const el=document.createElement('div');
  el.id='gal-editor-overlay';
  el.style.cssText='position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.75);display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)';
  el.innerHTML=`
    <div style="background:var(--bg2);border:1px solid var(--border2);border-radius:16px;width:520px;max-width:95vw;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.6)">
      <div style="padding:18px 22px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
        <div style="font-weight:700;font-size:15px">Photo Adjustment</div>
        <button onclick="galCloseEditor()" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);width:30px;height:30px;border-radius:8px;cursor:pointer;font-size:15px">✕</button>
      </div>
      <div style="display:flex;gap:0">
        <div style="flex:1;padding:18px 20px;border-right:1px solid var(--border)">
          <div style="font-size:11px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">Position / Focus Point</div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-bottom:16px">
            ${_GAL_POSITIONS.flat().map(p=>`<button id="gpos-${p.replace(/ /g,'-')}" onclick="galSetPos('${p}')" style="padding:12px 6px;border-radius:7px;border:2px solid ${p===pos?'var(--gold)':'var(--border)'};background:${p===pos?'var(--gd)':'var(--bg3)'};color:${p===pos?'var(--gold)':'var(--text2)'};cursor:pointer;font-size:18px;transition:.15s" title="${p}">${posLabel[p]||p}</button>`).join('')}
          </div>
          <div style="font-size:11px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Fit Mode</div>
          <div style="display:flex;flex-direction:column;gap:6px">
            ${['cover','contain'].map(f=>`<button id="gfit-${f}" onclick="galSetFit('${f}')" style="padding:9px 14px;border-radius:7px;border:2px solid ${f===fit?'var(--gold)':'var(--border)'};background:${f===fit?'var(--gd)':'var(--bg3)'};color:${f===fit?'var(--gold)':'var(--text2)'};cursor:pointer;font-size:12px;text-align:left;transition:.15s">${fitIcon[f]}</button>`).join('')}
          </div>
        </div>
        <div style="flex:1.1;padding:18px 20px;display:flex;flex-direction:column;gap:12px">
          <div style="font-size:11px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:1px">Live Preview</div>
          <div id="gal-preview-wrap" style="width:100%;aspect-ratio:16/9;border-radius:10px;overflow:hidden;border:1px solid var(--border);background:var(--bg4)">
            <img id="gal-preview-img" src="${esc(url)}" style="width:100%;height:100%;object-fit:${fit};object-position:${pos};display:block">
          </div>
          <div id="gal-pos-label" style="font-size:11px;color:var(--text3);text-align:center">${pos} &nbsp;|&nbsp; ${fit}</div>
          <button onclick="galSaveAdjust()" style="margin-top:auto;padding:11px;background:var(--gold);color:#000;border:none;border-radius:9px;font-weight:700;cursor:pointer;font-size:13px">Save Adjustment</button>
        </div>
      </div>
    </div>`;
  el.addEventListener('click',e=>{if(e.target===el)galCloseEditor();});
  document.body.appendChild(el);
  window._galEditorPos=pos;
  window._galEditorFit=fit;
}

function galSetPos(p){
  window._galEditorPos=p;
  _GAL_POSITIONS.flat().forEach(pp=>{
    const b=document.getElementById('gpos-'+pp.replace(/ /g,'-'));
    if(!b)return;
    const active=pp===p;
    b.style.borderColor=active?'var(--gold)':'var(--border)';
    b.style.background=active?'var(--gd)':'var(--bg3)';
    b.style.color=active?'var(--gold)':'var(--text2)';
  });
  const img=document.getElementById('gal-preview-img');
  if(img)img.style.objectPosition=p;
  const lbl=document.getElementById('gal-pos-label');
  if(lbl)lbl.textContent=p+' | '+(window._galEditorFit||'cover');
}

function galSetFit(f){
  window._galEditorFit=f;
  ['cover','contain'].forEach(ff=>{
    const b=document.getElementById('gfit-'+ff);
    if(!b)return;
    const active=ff===f;
    b.style.borderColor=active?'var(--gold)':'var(--border)';
    b.style.background=active?'var(--gd)':'var(--bg3)';
    b.style.color=active?'var(--gold)':'var(--text2)';
  });
  const img=document.getElementById('gal-preview-img');
  if(img)img.style.objectFit=f;
  const lbl=document.getElementById('gal-pos-label');
  if(lbl)lbl.textContent=(window._galEditorPos||'center center')+' | '+f;
}

async function galSaveAdjust(){
  const pos=window._galEditorPos||'center center';
  const fit=window._galEditorFit||'cover';
  const r=await req('/content/item-images/'+_galEditId,{method:'PATCH',body:JSON.stringify({position:pos,fit})});
  if(r?.error){alert(r.error);return;}
  galCloseEditor();
  const el=document.getElementById('gal-img-'+_galEditId);
  if(el){
    const img=el.querySelector('img');
    if(img){img.style.objectPosition=pos;img.style.objectFit=fit;}
    el.querySelector('button[onclick^="galOpenEditor"]').setAttribute('onclick',`galOpenEditor(${_galEditId},'${r.url||''}','${pos}','${fit}')`);
  }
  toast('Adjustment saved');
}

function galCloseEditor(){
  const el=document.getElementById('gal-editor-overlay');
  if(el)el.remove();
}

async function galAddUrl(iid){
  const inp=document.getElementById('gal-url-inp');
  const url=(inp?.value||'').trim();if(!url){toast('Paste a URL first');return;}
  _galCurrentIid=iid;
  const imgs=await req('/content/items/'+iid+'/gallery',{method:'POST',body:JSON.stringify({url})});
  if(imgs?.error){alert(imgs.error);return;}
  inp.value='';
  _galRenderGrid(imgs);
  toast('Image added');
}
async function galUploadFiles(event,iid){
  const files=[...event.target.files];if(!files.length)return;
  _galCurrentIid=iid;
  const lbl=event.target.closest('label');const orig=lbl?lbl.innerHTML:'';
  let last=null;
  for(const file of files){
    if(file.size>10*1024*1024){toast('Skipped (>10MB): '+file.name);continue;}
    if(lbl)lbl.innerHTML='<span>Uploading…</span>';
    const fd=new FormData();fd.append('file',file);
    try{
      const h={};if(jwt)h['Authorization']='Bearer '+jwt;
      const res=await fetch(API+'/content/items/'+iid+'/gallery/upload',{method:'POST',headers:h,body:fd});
      const data=await res.json();
      if(data.images)last=data.images;
      toast('Uploaded: '+file.name);
    }catch(e){toast('Error: '+e.message);}
  }
  if(lbl)lbl.innerHTML=orig;
  event.target.value='';
  if(last)_galRenderGrid(last);
}
async function galDel(imgId){
  if(!confirm('Remove this image?'))return;
  await req('/content/item-images/'+imgId,{method:'DELETE'});
  const el=document.getElementById('gal-img-'+imgId);if(el)el.remove();
  const grid=document.getElementById('gal-grid');
  if(grid&&!grid.querySelector('[id^="gal-img-"]'))grid.innerHTML='<div style="color:var(--text3);font-size:12px;padding:8px 0">No gallery images yet.</div>';
  toast('Removed');
}

async function svItem(id){
  const d={title:document.getElementById('it-title').value.trim(),description:document.getElementById('it-desc').value,photo_url:document.getElementById('it-img').value,image:document.getElementById('it-img').value,content_html:document.getElementById('rte-body').innerHTML,sort_order:parseInt(document.getElementById('it-ord').value)||0,active:parseInt(document.getElementById('it-active').value)};
  if(!d.title)return;
  const r=id?await req('/content/items/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/content/'+window._editPid+'/items',{method:'POST',body:JSON.stringify(d)});
  if(r?.error){alert(r.error);return;}
  toast(id?'✅ Item updated':'✅ Item added');
  closeModal();
  const pid=window._editPid;
  const fresh=await req('/content/'+pid+'/items');
  if(!window._pageItems)window._pageItems={};
  window._pageItems[pid]=fresh||[];
  const el=document.getElementById('page-items-'+pid);
  if(el)el.innerHTML=renderInlineItems(pid);
}
async function delItem(id){
  if(!confirm('Delete this item?'))return;
  await req('/content/items/'+id,{method:'DELETE'});
  toast('🗑 Deleted');
  const pid=window._editPid;
  const fresh=await req('/content/'+pid+'/items');
  if(!window._pageItems)window._pageItems={};
  window._pageItems[pid]=fresh||[];
  const el=document.getElementById('page-items-'+pid);
  if(el)el.innerHTML=renderInlineItems(pid);
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROOMS CRUD
// ═══════════════════════════════════════════════════════════════════════════════
async function eRoom(id){
  const unit = (window._deployMode==='commercial')?'Screen':'Room';
  const r = id ? (window._rooms||[]).find(x=>x.id===id) : null;
  const [allPkgs, roomPkgs] = await Promise.all([
    req('/packages'),
    id ? req('/rooms/'+id+'/packages') : Promise.resolve([])
  ]);
  const assignedIds = new Set((roomPkgs||[]).map(p=>p.id));
  const pkgItems = (allPkgs||[]).map(p=>`
    <label class="vip-item">
      <input type="checkbox" class="room-pkg-cb" value="${p.id}" ${assignedIds.has(p.id)?'checked':''}>
      <span>${esc(p.name)}</span>
    </label>`).join('');

  const _isHotelMode = (window._deployMode||window._settings?.deployment_mode||'hotel') !== 'commercial';
  openModal(r?`Edit ${unit} ${r.room_number}:`:`Add ${unit}`,`
  <div class="fgrid">
    <div class="fg"><label>${unit} Number *</label><input id="r-num" class="finp" value="${esc(r?.room_number||'')}" placeholder="101" ${r?'readonly':''}></div>
    <div class="fg"><label>TV Name</label><input id="r-tvname" class="finp" value="${esc(r?.tv_name||'')}" placeholder="TV-101"></div>
  </div>
  ${r?`<div style="margin-top:12px;background:var(--bg3);border-radius:8px;padding:10px;font-size:12px;color:var(--text2)">
    <b style="color:var(--text)">Status:</b> <span class="bdg ${r.online?'bg':'br'}">${r.online?'Online':'Offline'}</span>
    &nbsp; <b style="color:var(--text)">Last Seen:</b> ${r.last_seen?new Date(r.last_seen+'Z').toLocaleString():'Never'}
  </div>`:''}
  ${_isHotelMode?`<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border2)">
    <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:10px">👤 Guest Info (PMS)</div>
    <div class="fgrid" style="gap:10px">
      <div class="fg fcol"><label>Guest Name</label><input id="r-guest-name" class="finp" value="${esc(r?.guest_name||'')}" placeholder="Mr. John Doe"></div>
      <div class="fg"><label>Check-in Time</label><input id="r-checkin" class="finp" type="datetime-local" value="${esc((r?.checkin_time||'').replace(' ','T').slice(0,16))}"></div>
      <div class="fg"><label>Check-out Time</label><input id="r-checkout-time" class="finp" type="datetime-local" value="${esc((r?.checkout_time||'').replace(' ','T').slice(0,16))}"></div>
    </div>
  </div>`:''}
  <div class="fg fcol" style="margin-top:14px">
    <label>Packages <span style="font-weight:400;color:var(--text2);font-size:11px">(no packages = no access to any content)</span></label>
    <div class="vip-list" style="max-height:160px">
      ${pkgItems||'<div style="padding:10px;color:var(--text3);font-size:13px">No packages defined yet — create them in Packages first.</div>'}
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svRoom(${id||'null'})">Save</button>`);
}

async function svRoom(id){
  const checkinRaw  = document.getElementById('r-checkin')?.value||'';
  const checkoutRaw = document.getElementById('r-checkout-time')?.value||'';
  const d={
    room_number:   document.getElementById('r-num').value.trim(),
    tv_name:       document.getElementById('r-tvname').value.trim(),
    guest_name:    document.getElementById('r-guest-name')?.value.trim()||'',
    checkin_time:  checkinRaw  ? checkinRaw.replace('T',' ')  : '',
    checkout_time: checkoutRaw ? checkoutRaw.replace('T',' ') : '',
  };
  if(!d.room_number)return;
  const r=id?await req('/rooms/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/rooms',{method:'POST',body:JSON.stringify(d)});
  if(r?.error){alert(r.error);return;}
  // Save package assignments
  const rid = r.id || id;
  const pkg_ids = [...document.querySelectorAll('.room-pkg-cb:checked')].map(cb=>parseInt(cb.value));
  await req('/rooms/'+rid+'/packages',{method:'POST',body:JSON.stringify({package_ids:pkg_ids})});
  closeModal();toast(id?'✅ Updated':'✅ Created');await pages.rooms();
}
async function rgenToken(id,num){if(!confirm('Reset token for Room '+num+'?\nDevice must re-register by typing room number.'))return;await req('/rooms/'+id+'/token',{method:'POST'});toast('🔄 Room '+num+' token reset');await pages.rooms();}
async function dRoom(id,num){if(!confirm('Delete Room '+num+'?'))return;await req('/rooms/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.rooms();}

// ═══════════════════════════════════════════════════════════════════════════════
// SKINS + USERS CRUD
// ═══════════════════════════════════════════════════════════════════════════════
function eSkin(id){const s=id?(window._skins||[]).find(x=>x.id===id):null;
openModal(s?'Edit Skin':'Add Skin',`<div class="fgrid">
<div class="fg fcol"><label>Skin Name *</label><input id="sk-name" value="${esc(s?.name||'')}"></div>
<div class="fg"><label>Template</label><select id="sk-tmpl"><option ${!s||s.template==='Default Skin'?'selected':''}>Default Skin</option></select></div>
<div class="fg fcol"><label>Background Image URL</label><input id="sk-bg" value="${esc(s?.background_image||'')}"></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svSkin(${id||'null'})">Save</button>`);}
async function svSkin(id){const d={name:document.getElementById('sk-name').value.trim(),template:document.getElementById('sk-tmpl').value,background_image:document.getElementById('sk-bg').value};if(!d.name)return;const r=id?await req('/skins/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/skins',{method:'POST',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Created');await pages.skins();}
async function dSkin(id,name){if(!confirm('Delete skin "'+name+'"?'))return;const r=await req('/skins/'+id,{method:'DELETE'});if(r?.error){alert(r.error);return;}toast('🗑 Deleted');await pages.skins();}
function eUser(){openModal('Add User',`<div class="fgrid">
<div class="fg"><label>Username *</label><input id="u-name"></div>
<div class="fg"><label>Password *</label><input id="u-pass" type="password"></div>
<div class="fg"><label>Role</label><select id="u-role"><option value="viewer">Viewer</option><option value="operator">Operator</option><option value="admin">Admin</option></select></div>
<div class="fg"><label>City / Region</label>${cityPickerHtml('u-city')}</div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svUser()">Create</button>`);}
async function svUser(){const d={username:document.getElementById('u-name').value.trim(),password:document.getElementById('u-pass').value,role:document.getElementById('u-role').value,city:document.getElementById('u-city').value.trim()};if(!d.username||!d.password)return;const r=await req('/users',{method:'POST',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast('✅ User created');await pages.users();}
async function dUser(id,name){if(!confirm('Delete "'+name+'"?'))return;await req('/users/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.users();}
function eEditUser(id,username,city,role){openModal('Edit User — '+username,`<div class="fgrid">
<div class="fg"><label>City / Region</label>${cityPickerHtml('eu-city',city)}</div>
<div class="fg"><label>Role</label><select id="eu-role"><option value="viewer"${role==='viewer'?' selected':''}>Viewer</option><option value="operator"${role==='operator'?' selected':''}>Operator</option><option value="admin"${role==='admin'?' selected':''}>Admin</option></select></div>
<div class="fg" style="grid-column:span 2"><label>New Password <span style="font-weight:400;color:var(--text3)">(leave blank to keep)</span></label><input id="eu-pass" type="password"></div>
</div>`,`<button class="btn btn-g" onclick="closeModal()">Cancel</button><button class="btn btn-p" onclick="svEditUser(${id})">Save</button>`);}
async function svEditUser(id){const d={city:document.getElementById('eu-city').value.trim(),role:document.getElementById('eu-role').value,password:document.getElementById('eu-pass').value};if(!d.password)delete d.password;const r=await req('/users/'+id,{method:'PUT',body:JSON.stringify(d)});if(r?.error){alert(r.error);return;}closeModal();toast('✅ User updated');await pages.users();}

// ═══════════════════════════════════════════════════════════════════════════════
// REPORTS + EXPORT
// ═══════════════════════════════════════════════════════════════════════════════
window._rptTab='channels';window._rptData=[];
async function loadRpt(days){
  const tab=window._rptTab||'channels';const el=document.getElementById('rpt-body');if(!el)return;
  el.innerHTML='<div style="padding:28px;text-align:center;color:var(--text3)">Loading...</div>';
  const data=await req('/reports/'+tab+'?days='+days);
  if(!data){el.innerHTML='<div style="padding:28px;color:var(--red)">Failed</div>';return;}
  window._rptData=data;window._rptDays=days;
  renderRpt(tab,data,days);
}
function swRpt(tab,btn){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));btn.classList.add('on');window._rptTab=tab;const days=document.getElementById('rpt-days')?.value||30;loadRpt(days);}

const RPT_DEFS={
  channels:{title:'Channel Viewership',cols:[{label:'Channel',key:'name'},{label:'Group',key:'group_name'},{label:'Sessions',key:'sessions'},{label:'Watch Time (min)',key:'total_minutes'},{label:'Unique Rooms',key:'unique_rooms'}],bk:'total_minutes',bl:'name',bc:'var(--gold)'},
  rooms:{title:'Room Activity',cols:[{label:'Room',key:'room_number'},{label:'TV Name',key:'tv_name'},{label:'Sessions',key:'sessions'},{label:'Watch Time (min)',key:'total_minutes'},{label:'Last Activity',key:'last_activity'},{label:'Status',key:'online'}],bk:'total_minutes',bl:'room_number',bc:'var(--blue)'},
  vod:{title:'Movie Views',cols:[{label:'Title',key:'title'},{label:'Genre',key:'genre'},{label:'Year',key:'year'},{label:'Sessions',key:'sessions'},{label:'Watch Time (min)',key:'total_minutes'},{label:'Unique Rooms',key:'unique_rooms'}],bk:'sessions',bl:'title',bc:'var(--purple)'},
  radio:{title:'Radio Stations',cols:[{label:'Station',key:'name'},{label:'Country',key:'country'},{label:'Genre',key:'genre'},{label:'Sessions',key:'sessions'},{label:'Watch Time (min)',key:'total_minutes'}],bk:'sessions',bl:'name',bc:'var(--orange)'},
  pages:{title:'Content Pages',cols:[{label:'Page',key:'name'},{label:'Group',key:'group_name'},{label:'Template',key:'template'},{label:'Items',key:'item_count'}],bk:'item_count',bl:'name',bc:'var(--green)'}
};
function renderRpt(tab,data,days){
  const el=document.getElementById('rpt-body');if(!el)return;
  const def=RPT_DEFS[tab];const topN=data.slice(0,10);
  const rowFn=r=>'<tr>'+def.cols.map(c=>{let v=r[c.key]||'—';if(c.key==='total_minutes')v=fmtMin(r[c.key]);if(c.key==='online')v='<span class="bdg '+(r.online?'bg':'br')+'">'+(r.online?'Online':'Offline')+'</span>';return'<td>'+v+'</td>';}).join('')+'</tr>';
  el.innerHTML=`
  <div class="exp-bar"><div class="exp-lbl">Export ${data.length} records — ${def.title} (Last ${days} days)</div>
    <button class="btn btn-g btn-sm" onclick="exportCSV(window._rptData,RPT_DEFS[window._rptTab].cols,'nexvision-${tab}-report')">⬇ CSV</button>
    <button class="btn btn-gr btn-sm" onclick="exportXLSX(window._rptData,RPT_DEFS[window._rptTab].cols,'nexvision-${tab}-report')">⬇ Excel</button>
    <button class="btn btn-b btn-sm" onclick="exportPDF(window._rptData,RPT_DEFS[window._rptTab].cols,'${def.title} Report','nexvision-${tab}-report')">🖨 PDF</button>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px">
    <div class="tbl-wrap" style="padding:15px"><div class="sec-title" style="margin-bottom:10px">📊 Top ${topN.length} — ${def.title}</div>${barChart(topN,def.bl,def.bk,def.bc)}</div>
    <div class="tbl-wrap" style="padding:15px"><div class="sec-title" style="margin-bottom:8px">Summary</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:8px">
      <div class="sc gold" style="padding:13px"><div class="sc-lbl">Total Records</div><div class="sc-val">${fmtNum(data.length)}</div></div>
      <div class="sc blue" style="padding:13px"><div class="sc-lbl">Total Sessions</div><div class="sc-val">${fmtNum(data.reduce((a,r)=>a+(r.sessions||0),0))}</div></div>
      <div class="sc green" style="padding:13px"><div class="sc-lbl">Total Time</div><div class="sc-val" style="font-size:17px">${fmtMin(data.reduce((a,r)=>a+(r.total_minutes||0),0))}</div></div>
      <div class="sc purple" style="padding:13px"><div class="sc-lbl">Avg / Record</div><div class="sc-val" style="font-size:17px">${fmtMin(Math.round(data.reduce((a,r)=>a+(r.total_minutes||0),0)/(data.length||1)))}</div></div>
    </div></div>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr>${def.cols.map(c=>'<th>'+c.label+'</th>').join('')}</tr></thead>
    <tbody>${data.length?data.map(r=>rowFn(r)).join(''):'<tr><td colspan="'+def.cols.length+'" style="text-align:center;color:var(--text3);padding:24px">No data for this period</td></tr>'}</tbody>
  </table></div>`;}


// ═══════════════════════════════════════════════════════════════════════════════
// V6 PAGE FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

// ── MESSAGES ─────────────────────────────────────────────────────────────────
pages.messages = async function() {
  const [msgs, rooms] = await Promise.all([req('/messages'), req('/rooms')]);
  if (!msgs) return;
  window._msgs = msgs; window._rooms_ref = rooms||[];

  const typeColor = {emergency:'br', normal:'bb', birthday:'bo'};
  const typeIcon  = {emergency:'🚨', normal:'📢', birthday:'🎂'};

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">Messages &amp; Alerts</div>
    <div class="sec-acts">
      <button class="btn btn-d" onclick="eMsg(null,'emergency')">🚨 Emergency</button>
      <button class="btn btn-b" onclick="eMsg(null,'normal')">📢 Broadcast</button>
      <button class="btn btn-p" onclick="eMsg(null,'room')">📩 Room Message</button>
    </div>
  </div>
  <div class="ibox info">Messages are delivered to TV screens, browsers and phones in real time.
    <b>Emergency</b> messages appear as full-screen red overlays. <b>Normal</b> messages appear as banners. Room-targeted messages go only to specified rooms.</div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Type</th><th>Title</th><th>Body</th><th>Target</th><th>Expires</th><th>Status</th><th>Sent</th><th>Actions</th></tr></thead>
    <tbody>${msgs.map(m=>`
      <tr>
        <td><span class="bdg ${typeColor[m.type]||'bb'}">${typeIcon[m.type]||'📢'} ${m.type}</span></td>
        <td><b>${esc(m.title)}</b></td>
        <td style="color:var(--text2);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.body)}</td>
        <td>${m.target==='all'?'<span class="bdg bg">All Rooms</span>':'<span class="bdg bp">'+esc(m.room_ids)+'</span>'}</td>
        <td style="font-size:11px;color:var(--text2)">${m.expires_at?new Date(m.expires_at).toLocaleString():'Never'}</td>
        <td><span class="bdg ${m.active?'bg':'br'}">${m.active?'Active':'Dismissed'}</span></td>
        <td style="font-size:11px;color:var(--text2)">${m.sent_at?new Date(m.sent_at).toLocaleString():'—'}</td>
        <td><div class="tda">
          <button class="btn btn-g btn-xs" onclick="eMsg(${m.id})">Edit</button>
          ${m.active?'<button class="btn btn-xs" style="background:var(--od);color:var(--orange);border:1px solid rgba(255,153,68,.2)" onclick="dismissMsg('+m.id+')">Dismiss</button>':''}
          <button class="btn btn-d btn-xs" onclick="dMsg(${m.id})">Del</button>
        </div></td>
      </tr>`).join('')}
    </tbody>
  </table></div>`;
};

function eMsg(id, forceType) {
  const m = id ? (window._msgs||[]).find(x=>x.id===id) : null;
  const rooms = window._rooms_ref||[];
  const mtype = m?.type || forceType || 'normal';
  const isRoom = mtype==='room' || m?.target==='room';

  openModal(m?'Edit Message':'New Message', `
  <div class="fgrid">
    <div class="fg"><label>Type</label>
      <select id="m-type" onchange="toggleMsgTarget(this.value)" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="emergency" ${mtype==='emergency'?'selected':''}>🚨 Emergency (Full-screen alert)</option>
        <option value="normal" ${mtype==='normal'&&!isRoom?'selected':''}>📢 Normal Broadcast (Banner)</option>
        <option value="room" ${isRoom?'selected':''}>📩 Room Targeted</option>
        <option value="birthday" ${mtype==='birthday'?'selected':''}>🎂 Birthday Message</option>
      </select>
    </div>
    <div class="fg"><label>Status</label>
      <select id="m-active" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1" ${!m||m.active?'selected':''}>Active</option>
        <option value="0" ${m&&!m.active?'selected':''}>Dismissed</option>
      </select>
    </div>
    <div class="fg fcol"><label>Title *</label><input id="m-title" value="${esc(m?.title||'')}"></div>
    <div class="fg fcol"><label>Message Body *</label><textarea id="m-body" style="height:90px">${esc(m?.body||'')}</textarea></div>
    <div class="fg" id="m-target-row" style="${isRoom?'':'display:none'}">
      <label>Target Rooms (comma-separated room numbers or IDs)</label>
      <input id="m-rooms" value="${esc(m?.room_ids||'')}" placeholder="101, 205, 310...">
      <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:5px">
        ${rooms.slice(0,30).map(r=>`<button type="button" class="btn btn-g btn-xs" onclick="toggleRoomTag('${esc(r.room_number)}','m-rooms')">${esc(r.room_number)}</button>`).join('')}
      </div>
    </div>
    <div class="fg"><label>Expires At (leave blank = permanent)</label><input id="m-exp" type="datetime-local" value="${m?.expires_at?m.expires_at.slice(0,16):''}"></div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svMsg(${id||'null'})">Send Message</button>`);
}
function toggleMsgTarget(v){const row=document.getElementById('m-target-row');if(row)row.style.display=v==='room'?'':'none';}
function toggleRoomTag(room,inputId){const inp=document.getElementById(inputId);if(!inp)return;let vals=inp.value.split(',').map(s=>s.trim()).filter(Boolean);if(vals.includes(room))vals=vals.filter(v=>v!==room);else vals.push(room);inp.value=vals.join(', ');}
async function svMsg(id){
  const type=document.getElementById('m-type').value;
  const target=type==='room'?'room':'all';
  const d={title:document.getElementById('m-title').value.trim(),body:document.getElementById('m-body').value.trim(),type,target,room_ids:document.getElementById('m-rooms')?.value||'',expires_at:document.getElementById('m-exp').value||null,active:parseInt(document.getElementById('m-active').value)};
  if(!d.title||!d.body){alert('Title and body required');return;}
  const r=id?await req('/messages/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/messages',{method:'POST',body:JSON.stringify(d)});
  if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Message updated':'✅ Message sent');await pages.messages();
}
async function dismissMsg(id){await req('/messages/'+id+'/dismiss',{method:'POST'});toast('Message dismissed');await pages.messages();}
async function dMsg(id){if(!confirm('Delete message?'))return;await req('/messages/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.messages();}


// ── BIRTHDAYS ────────────────────────────────────────────────────────────────
pages.birthdays = async function() {
  const [bdays, rooms] = await Promise.all([req('/birthdays'), req('/rooms')]);
  if (!bdays) return;
  window._bdays = bdays; window._rooms_ref = rooms||[];

  // Find today's birthdays
  const today = new Date();
  const todayMD = String(today.getMonth()+1).padStart(2,'0')+'-'+String(today.getDate()).padStart(2,'0');
  const todayBdays = bdays.filter(b=>b.birth_date && b.birth_date.slice(5)===todayMD && b.active);

  document.getElementById('content').innerHTML = `
  ${todayBdays.length>0?`<div class="ibox" style="border-color:rgba(212,168,67,.4);background:var(--gd);margin-bottom:14px">
    🎂 <b>${todayBdays.length} Birthday${todayBdays.length>1?'s':''} Today!</b>
    ${todayBdays.map(b=>`<b>${esc(b.guest_name)}</b>${b.room_number?' (Room '+esc(b.room_number)+')':''}`).join(', ')}
  </div>`:''}
  <div class="sec-hdr">
    <div class="sec-title">Birthday Manager</div>
    <button class="btn btn-p" onclick="eBday(null)">+ Add Birthday</button>
  </div>
  <div class="ibox info">Birthdays matching today's date are automatically displayed as celebration messages on guest TV screens with a happy birthday banner and greeting.</div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Guest Name</th><th>Room</th><th>Date</th><th>Today?</th><th>Custom Message</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>${bdays.map(b=>{
      const isTd = b.birth_date && b.birth_date.slice(5)===todayMD;
      return `<tr style="${isTd?'background:rgba(212,168,67,.04)':''}">
        <td><b>${esc(b.guest_name)}</b></td>
        <td>${b.room_number?'<span class="bdg bb">Room '+esc(b.room_number)+'</span>':'<span style="color:var(--text3)">—</span>'}</td>
        <td style="font-family:'DM Mono',monospace;font-size:12px">${esc(b.birth_date)}</td>
        <td>${isTd?'<span class="bdg bo">🎂 TODAY</span>':'—'}</td>
        <td style="color:var(--text2);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(b.message||'—')}</td>
        <td><span class="bdg ${b.active?'bg':'br'}">${b.active?'Active':'Inactive'}</span></td>
        <td><div class="tda">
          <button class="btn btn-g btn-xs" onclick="eBday(${b.id})">Edit</button>
          <button class="btn btn-d btn-xs" onclick="dBday(${b.id})">Del</button>
        </div></td>
      </tr>`;}).join('')}
    </tbody>
  </table></div>`;
};
function eBday(id){
  const b=id?(window._bdays||[]).find(x=>x.id===id):null;
  const rooms=window._rooms_ref||[];
  openModal(b?'Edit Birthday':'Add Birthday',`
  <div class="fgrid">
    <div class="fg fcol"><label>Guest Name *</label><input id="bd-name" value="${esc(b?.guest_name||'')}"></div>
    <div class="fg"><label>Room Number</label>
      <select id="bd-room" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="">— No specific room —</option>
        ${rooms.map(r=>`<option value="${esc(r.room_number)}" ${b?.room_number===r.room_number?'selected':''}>${esc(r.room_number)} — ${esc(r.tv_name||r.room_number)}</option>`).join('')}
      </select>
    </div>
    <div class="fg"><label>Birth Date *</label><input id="bd-date" type="date" value="${b?.birth_date||''}"></div>
    <div class="fg fcol"><label>Custom Message (leave blank for default)</label>
      <input id="bd-msg" value="${esc(b?.message||'')}" placeholder="Happy Birthday! Wishing you a wonderful day!"></div>
    <div class="fg"><label>Status</label>
      <select id="bd-active" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1" ${!b||b.active?'selected':''}>Active</option>
        <option value="0" ${b&&!b.active?'selected':''}>Inactive</option>
      </select>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svBday(${id||'null'})">Save</button>`);
}
async function svBday(id){
  const d={guest_name:document.getElementById('bd-name').value.trim(),room_number:document.getElementById('bd-room').value,birth_date:document.getElementById('bd-date').value,message:document.getElementById('bd-msg').value,active:parseInt(document.getElementById('bd-active').value)};
  if(!d.guest_name||!d.birth_date){alert('Name and date required');return;}
  const r=id?await req('/birthdays/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/birthdays',{method:'POST',body:JSON.stringify(d)});
  if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Birthday added');await pages.birthdays();
}
async function dBday(id){if(!confirm('Delete birthday?'))return;await req('/birthdays/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.birthdays();}


// ── RSS FEEDS ────────────────────────────────────────────────────────────────
pages.rss = async function() {
  const [feeds, settings] = await Promise.all([req('/rss'), req('/settings')]);
  if (!feeds) return;
  window._feeds = feeds;
  const txtCol   = settings?.ticker_text_color || '#ffffff';
  const bgCol    = settings?.ticker_bg_color   || '#09090f';
  const bgOp     = settings?.ticker_bg_opacity ?? 92;
  const tkLabel  = settings?.ticker_label || 'NEWS';
  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">RSS Feeds</div>
    <button class="btn btn-p" onclick="eRss(null)">+ Add Feed</button>
  </div>

  <!-- Ticker Appearance (global) -->
  <div class="tbl-wrap" style="padding:18px;margin-bottom:18px">
    <div class="sec-title" style="font-size:13px;color:var(--text2);margin-bottom:14px">🎨 Ticker Appearance</div>
    <div style="margin-bottom:14px">
      <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:6px">Ticker Label</label>
      <input id="tk-label" value="${esc(tkLabel)}" placeholder="NEWS" maxlength="20"
        oninput="_rssPreview()"
        style="max-width:220px;font-size:13px">
      <small style="color:var(--text3);font-size:11px;margin-left:10px">Shown in the badge on the left of the ticker</small>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;align-items:end">
      <div>
        <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:6px">Text Color</label>
        <div style="display:flex;gap:8px;align-items:center">
          <input type="color" id="tk-text-color" value="${esc(txtCol)}"
            oninput="document.getElementById('tk-text-hex').value=this.value;_rssPreview()"
            style="width:40px;height:34px;border:1px solid var(--border2);border-radius:6px;cursor:pointer;padding:2px">
          <input type="text" id="tk-text-hex" value="${esc(txtCol)}"
            oninput="document.getElementById('tk-text-color').value=this.value;_rssPreview()"
            style="flex:1;font-family:'DM Mono',monospace;font-size:12px">
        </div>
      </div>
      <div>
        <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:6px">Background Color</label>
        <div style="display:flex;gap:8px;align-items:center">
          <input type="color" id="tk-bg-color" value="${esc(bgCol)}"
            oninput="document.getElementById('tk-bg-hex').value=this.value;_rssPreview()"
            style="width:40px;height:34px;border:1px solid var(--border2);border-radius:6px;cursor:pointer;padding:2px">
          <input type="text" id="tk-bg-hex" value="${esc(bgCol)}"
            oninput="document.getElementById('tk-bg-color').value=this.value;_rssPreview()"
            style="flex:1;font-family:'DM Mono',monospace;font-size:12px">
        </div>
      </div>
      <div>
        <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:6px">Opacity <span id="tk-op-val">${bgOp}</span>%</label>
        <input type="range" id="tk-bg-opacity" min="10" max="100" value="${bgOp}"
          oninput="document.getElementById('tk-op-val').textContent=this.value;_rssPreview()"
          style="width:100%">
      </div>
    </div>
    <div style="margin-top:14px">
      <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:6px">Live Preview</label>
      <div id="rss-preview-bar" style="border-radius:7px;padding:8px 16px;overflow:hidden;white-space:nowrap;display:flex;align-items:center;transition:.2s">
        <span id="rss-preview-label" style="background:var(--gold);color:#000;font-size:9px;font-weight:700;padding:2px 10px;border-radius:3px;margin-right:14px;flex-shrink:0;letter-spacing:1px">📰 ${esc(tkLabel)}</span>
        <span id="rss-preview-text" style="font-size:12px">Hotel News Headline • Latest updates from your city • Breaking news here</span>
      </div>
    </div>
    <div style="margin-top:14px;text-align:right">
      <button class="btn btn-p" onclick="saveTickerStyle()">💾 Save Ticker Style</button>
    </div>
  </div>

  <div class="ibox info">
    <b>Emergency feeds</b> appear as a red scrolling ticker at the top of every screen.
    <b>Normal feeds</b> appear as a news ticker at the bottom using the style above.
    Feeds refresh automatically based on the configured interval.
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Title</th><th>Source</th><th>Type</th><th>Refresh</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>${feeds.map(f=>{
      const isText = !!(f.text_content && f.text_content.trim());
      const srcLabel = isText
        ? `<span style="font-size:10px;color:var(--text2)">✏️ ${esc(f.text_content.split('\n')[0].slice(0,60))}${f.text_content.length>60?'…':''}</span>`
        : `<span style="font-family:'DM Mono',monospace;font-size:10px;color:var(--text3)" title="${esc(f.url)}">${esc((f.url||'').slice(0,60))}${(f.url||'').length>60?'…':''}</span>`;
      return `<tr>
        <td><b>${esc(f.title)}</b></td>
        <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${srcLabel}</td>
        <td><span class="bdg ${f.type==='emergency'?'br':'bb'}">${f.type==='emergency'?'🚨 Emergency':'📰 Normal'}</span></td>
        <td style="color:var(--text2)">${f.refresh_minutes}min</td>
        <td><span class="bdg ${f.active?'bg':'br'}">${f.active?'Active':'Inactive'}</span></td>
        <td><div class="tda">
          <button class="btn btn-g btn-sm" onclick="eRss(${f.id})">Edit</button>
          <button class="btn btn-d btn-sm" onclick="dRss(${f.id})">Del</button>
        </div></td>
      </tr>`;}).join('')}
    </tbody>
  </table></div>`;
  _rssPreview();
};

function _rssPreview(){
  const txtCol = document.getElementById('tk-text-color')?.value || '#ffffff';
  const bgCol  = document.getElementById('tk-bg-color')?.value  || '#09090f';
  const op     = parseInt(document.getElementById('tk-bg-opacity')?.value || 92) / 100;
  const label  = (document.getElementById('tk-label')?.value || 'NEWS').trim() || 'NEWS';
  const r=parseInt(bgCol.slice(1,3),16), g=parseInt(bgCol.slice(3,5),16), b=parseInt(bgCol.slice(5,7),16);
  const bar   = document.getElementById('rss-preview-bar');
  const text  = document.getElementById('rss-preview-text');
  const badge = document.getElementById('rss-preview-label');
  if (bar)   bar.style.background = `rgba(${r},${g},${b},${op})`;
  if (text)  text.style.color = txtCol;
  if (badge) badge.textContent = '📰 ' + label;
}

async function saveTickerStyle(){
  const d = {
    ticker_text_color: document.getElementById('tk-text-color').value || '#ffffff',
    ticker_bg_color:   document.getElementById('tk-bg-color').value   || '#09090f',
    ticker_bg_opacity: document.getElementById('tk-bg-opacity').value || '92',
    ticker_label:      (document.getElementById('tk-label').value || 'NEWS').trim() || 'NEWS'
  };
  const r = await req('/settings', {method:'POST', body:JSON.stringify(d)});
  if (r?.ok === false) { toast('❌ Failed to save'); return; }
  toast('✅ Ticker style saved');
}

function eRss(id){
  const f=id?(window._feeds||[]).find(x=>x.id===id):null;
  const isText = !!(f?.text_content && f.text_content.trim());
  openModal(f?'Edit RSS Feed':'Add RSS Feed',`
  <div class="fgrid">
    <div class="fg fcol"><label>Feed Title *</label><input id="f-title" value="${esc(f?.title||'')}"></div>
    <div class="fg fcol"><label>Source</label>
      <select id="f-src-type" onchange="_rssToggleSrc()" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="url" ${!isText?'selected':''}>🔗 RSS URL</option>
        <option value="text" ${isText?'selected':''}>✏️ Custom Text</option>
      </select>
    </div>
    <div class="fg fcol" id="f-url-wrap" style="${isText?'display:none':''}"><label>RSS URL</label><input id="f-url" value="${esc(f?.url||'')}" placeholder="https://feeds.example.com/rss.xml"></div>
    <div class="fg fcol" id="f-text-wrap" style="${isText?'':'display:none'}"><label>Ticker Text</label><textarea id="f-text" rows="4" style="width:100%;background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;resize:vertical" placeholder="One line per ticker item&#10;Line 1&#10;Line 2&#10;Line 3">${esc(f?.text_content||'')}</textarea><small style="color:var(--text3);font-size:11px">Each line becomes a separate ticker item.</small></div>
    <div class="fg"><label>Type</label>
      <select id="f-type" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="normal" ${!f||f.type==='normal'?'selected':''}>📰 Normal — bottom ticker</option>
        <option value="emergency" ${f?.type==='emergency'?'selected':''}>🚨 Emergency — top red ticker</option>
      </select>
    </div>
    <div class="fg"><label>Refresh (minutes)</label><input id="f-refresh" type="number" value="${f?.refresh_minutes||15}" min="1"></div>
    <div class="fg"><label>Status</label>
      <select id="f-active" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1" ${!f||f.active?'selected':''}>Active</option>
        <option value="0" ${f&&!f.active?'selected':''}>Inactive</option>
      </select>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svRss(${id||'null'})">Save Feed</button>`);
}
function _rssToggleSrc(){
  const isText = document.getElementById('f-src-type')?.value === 'text';
  const urlWrap  = document.getElementById('f-url-wrap');
  const textWrap = document.getElementById('f-text-wrap');
  if (urlWrap)  urlWrap.style.display  = isText ? 'none' : '';
  if (textWrap) textWrap.style.display = isText ? ''     : 'none';
}
async function svRss(id){
  const srcType = document.getElementById('f-src-type')?.value || 'url';
  const d={
    title:document.getElementById('f-title').value.trim(),
    url: srcType==='url' ? (document.getElementById('f-url')?.value.trim()||'') : '',
    text_content: srcType==='text' ? (document.getElementById('f-text')?.value.trim()||'') : '',
    type:document.getElementById('f-type').value,
    refresh_minutes:parseInt(document.getElementById('f-refresh').value)||15,
    active:parseInt(document.getElementById('f-active').value)
  };
  if(!d.title){alert('Title is required');return;}
  if(srcType==='url' && !d.url){alert('RSS URL is required');return;}
  if(srcType==='text' && !d.text_content){alert('Ticker text is required');return;}
  const r=id?await req('/rss/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/rss',{method:'POST',body:JSON.stringify(d)});
  if(!r){toast('❌ Save failed');return;}
  if(r?.error){alert(r.error);return;}
  closeModal();toast(id?'✅ Feed updated':'✅ Feed added');await pages.rss();
}
async function dRss(id){if(!confirm('Delete this feed?'))return;await req('/rss/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.rss();}


// ── PACKAGES ──────────────────────────────────────────────────────────────────
pages.packages = async function() {
  const unit  = (window._deployMode==='commercial') ? 'Screen' : 'Room';
  const units = unit + 's';
  const [pkgs, chResp, allVod, allRooms] = await Promise.all([
    req('/packages'), req('/channels?active=0&limit=99999'), req('/vod'), req('/rooms')
  ]);
  window._pkg_list       = pkgs  || [];
  window._pkg_chs        = (chResp && chResp.channels) ? chResp.channels : (Array.isArray(chResp) ? chResp : []);
  window._pkg_total_chs  = (chResp && chResp.total) ? chResp.total : window._pkg_chs.length;
  window._pkg_vod        = allVod|| [];
  window._pkg_rooms  = allRooms||[];

  const rows = (pkgs||[]).map(p => {
    const chCount    = p.select_all_channels ? p.channel_count : (p.channel_ids||[]).length;
    const vodCount   = p.vod_count   !== undefined ? p.vod_count   : (p.vod_ids||[]).length;
    const radioCount = p.radio_count !== undefined ? p.radio_count : (p.radio_ids||[]).length;
    return `<tr>
      <td><b>${esc(p.name)}</b>${p.description?`<br><span style="color:var(--text3);font-size:12px">${esc(p.description)}</span>`:''}
      </td>
      <td><span class="bdg bg">${chCount} ch</span> <span class="bdg bb">${vodCount} VOD</span> <span class="bdg bor">${radioCount} radio</span></td>
      <td><span class="bdg">${p.active?'Active':'Inactive'}</span></td>
      <td><div class="tda">
        <button class="btn btn-b btn-sm" onclick="ePkg(${p.id})">Edit</button>
        <button class="btn btn-d btn-sm" onclick="dPkg(${p.id},'${esc(p.name)}')">Delete</button>
      </div></td>
    </tr>`;
  }).join('');

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">Packages</div>
    <button class="btn btn-p" onclick="ePkg()">+ New Package</button>
  </div>
  <div class="ibox info">
    Packages bundle channels, VOD and radio stations. ${units} with <b>no packages assigned have no access</b> to any content.
    Assign packages to ${units.toLowerCase()} from the Rooms page or via VIP Access → Packages tab.
  </div>
  ${pkgs&&pkgs.length?`
  <div class="tbl-wrap"><table>
    <thead><tr><th>Package</th><th>Content</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`
  :`<div class="ibox">No packages yet. Create one to start bundling content.</div>`}`;
};

async function ePkg(id) {
  const p = id ? (window._pkg_list||[]).find(x=>x.id===id) : null;
  // Load ALL channels for selection in package editor
  const allChsResp = await req('/channels?active=0&limit=99999');
  const allChs = Array.isArray(allChsResp) ? allChsResp : (allChsResp && allChsResp.channels) ? allChsResp.channels : (window._pkg_chs||[]);
  const allVod   = window._pkg_vod||[];
  const allRadio = await req('/radio') || [];
  const totalChs = allChs.length;

  // Auto-detect "all channels" mode: backend flag or all IDs assigned
  const pkgChIds = new Set((p && p.channel_ids) ? p.channel_ids : []);
  window._pkgAllChs = !!(p && p.select_all_channels) || (pkgChIds.size >= totalChs && totalChs > 0);

  window._pkgEditor = {
    items: {
      channels: allChs,
      vod: allVod,
      radio: allRadio
    },
    selected: {
      channels: new Set(pkgChIds),
      vod: new Set((p && p.vod_ids) ? p.vod_ids : []),
      radio: new Set((p && p.radio_ids) ? p.radio_ids : [])
    },
    search: {
      channels: '',
      vod: '',
      radio: ''
    },
    totalChannels: totalChs
  };

  openModal(id?'Edit Package':'New Package',`
  <div class="fgrid">
    <div class="fg fcol" style="grid-column:1/-1">
      <label>Package Name *</label>
      <input id="pkg-name" class="finp" value="${esc(p?.name||'')}" placeholder="e.g. Basic, Premium…">
    </div>
    <div class="fg fcol" style="grid-column:1/-1">
      <label>Description</label>
      <input id="pkg-desc" class="finp" value="${esc(p?.description||'')}" placeholder="Optional description">
    </div>
    <div class="fg fcol">
      <label>Active</label>
      <select id="pkg-active" class="finp">
        <option value="1" ${!p||p.active?'selected':''}>Active</option>
        <option value="0" ${p&&!p.active?'selected':''}>Inactive</option>
      </select>
    </div>
  </div>
  <div class="fgrid" style="margin-top:16px">
    <div class="fg fcol">
      <label>📺 Channels <span id="pkg-ch-count" style="font-weight:400;color:var(--text2)"></span></label>
      <div style="margin-bottom:8px;padding:10px;border-radius:8px;border:1px solid var(--border1);background:var(--bg3)">
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-weight:500">
          <input type="checkbox" id="pkg-all-chs-toggle" style="width:16px;height:16px;accent-color:var(--gold)"
            ${window._pkgAllChs?'checked':''}
            onchange="_pkgSetAllChannels(this.checked)">
          Include ALL channels <span style="color:var(--text2);font-weight:400">(${totalChs.toLocaleString()} total — entire library)</span>
        </label>
        <div id="pkg-ch-all-banner" style="margin-top:6px;font-size:12px;color:var(--gold);display:${window._pkgAllChs?'block':'none'}">
          ✓ All ${totalChs.toLocaleString()} channels will be included. Uncheck to select specific channels.
        </div>
      </div>
      <div id="pkg-ch-selective" style="display:${window._pkgAllChs?'none':'block'}">
        <input class="vip-srch" placeholder="Search channels... (${allChs.length.toLocaleString()} loaded)" oninput="_pkgUpdateSearch('channels',this.value)">
        <div class="pkg-bulk">
          <button onclick="_pkgSelectAllChannels(true)">Select All ${allChs.length.toLocaleString()}</button>
          <button onclick="_pkgToggleFiltered('channels',false)">Clear</button>
        </div>
        <div class="vip-list" id="pkg-ch-list"></div>
      </div>
    </div>
    <div class="fg fcol">
      <label>🎬 VOD <span id="pkg-vod-count" style="font-weight:400;color:var(--text2)"></span></label>
      <input class="vip-srch" placeholder="Search VOD..." oninput="_pkgUpdateSearch('vod',this.value)">
      <div class="pkg-bulk">
        <button onclick="_pkgToggleFiltered('vod',true)">Select All</button>
        <button onclick="_pkgToggleFiltered('vod',false)">Clear</button>
      </div>
      <div class="vip-list" id="pkg-vod-list"></div>
    </div>
    <div class="fg fcol">
      <label>📻 Radio <span id="pkg-radio-count" style="font-weight:400;color:var(--text2)"></span></label>
      <input class="vip-srch" placeholder="Search radio..." oninput="_pkgUpdateSearch('radio',this.value)">
      <div class="pkg-bulk">
        <button onclick="_pkgToggleFiltered('radio',true)">Select All</button>
        <button onclick="_pkgToggleFiltered('radio',false)">Clear</button>
      </div>
      <div class="vip-list" id="pkg-radio-list"></div>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svPkg(${id||0})">Save Package</button>`,
  'modal-lg');
  _pkgRenderAll();
  _pkgCount();
}

const PKG_RENDER_LIMIT = 250;

function _pkgItems(kind) {
  return window._pkgEditor?.items?.[kind] || [];
}

function _pkgSelected(kind) {
  return window._pkgEditor?.selected?.[kind] || new Set();
}

function _pkgLabel(kind, item) {
  return kind === 'vod' ? item.title : item.name;
}

function _pkgListId(kind) {
  return kind === 'channels' ? 'pkg-ch-list' : kind === 'vod' ? 'pkg-vod-list' : 'pkg-radio-list';
}

function _pkgEmptyLabel(kind) {
  return kind === 'channels' ? 'No channels' : kind === 'vod' ? 'No VOD titles' : 'No radio stations';
}

function _pkgFilteredItems(kind) {
  const items = _pkgItems(kind);
  const query = (window._pkgEditor?.search?.[kind] || '').trim().toLowerCase();
  if(!query) return items;
  return items.filter(item=>_pkgLabel(kind, item).toLowerCase().includes(query));
}

function _pkgRenderList(kind) {
  const host = document.getElementById(_pkgListId(kind));
  if(!host) return;
  const filtered = _pkgFilteredItems(kind);
  const selected = _pkgSelected(kind);
  const visible = filtered.slice(0, PKG_RENDER_LIMIT);
  if(!visible.length) {
    host.innerHTML = `<div style="padding:10px;color:var(--text3);font-size:13px">${_pkgEmptyLabel(kind)}</div>`;
    return;
  }
  const itemsHtml = visible.map(item=>`
    <label class="vip-item">
      <input type="checkbox" onchange="_pkgToggleItem('${kind}',${item.id},this.checked)" ${selected.has(item.id)?'checked':''}>
      <span>${esc(_pkgLabel(kind, item))}</span>
    </label>`).join('');
  const moreHtml = filtered.length > PKG_RENDER_LIMIT
    ? `<div style="padding:10px;color:var(--text3);font-size:12px;border-top:1px solid var(--border)">Showing first ${PKG_RENDER_LIMIT.toLocaleString()} of ${filtered.length.toLocaleString()} matches. Refine the search to narrow the list.</div>`
    : '';
  host.innerHTML = itemsHtml + moreHtml;
}

function _pkgRenderAll() {
  _pkgRenderList('channels');
  _pkgRenderList('vod');
  _pkgRenderList('radio');
}

function _pkgUpdateSearch(kind, value) {
  if(!window._pkgEditor) return;
  window._pkgEditor.search[kind] = value || '';
  _pkgRenderList(kind);
}

function _pkgToggleItem(kind, id, checked) {
  const selected = _pkgSelected(kind);
  if(checked) selected.add(id);
  else selected.delete(id);
  _pkgCount();
}

function _pkgToggleFiltered(kind, checked) {
  const selected = _pkgSelected(kind);
  _pkgFilteredItems(kind).forEach(item=>{
    if(checked) selected.add(item.id);
    else selected.delete(item.id);
  });
  _pkgRenderList(kind);
  _pkgCount();
}

function _pkgSetAllChannels(checked) {
  window._pkgAllChs = !!checked;
  const toggle = document.getElementById('pkg-all-chs-toggle');
  const banner = document.getElementById('pkg-ch-all-banner');
  const selective = document.getElementById('pkg-ch-selective');
  if(toggle) toggle.checked = window._pkgAllChs;
  if(banner) banner.style.display = window._pkgAllChs ? 'block' : 'none';
  if(selective) selective.style.display = window._pkgAllChs ? 'none' : 'block';
  _pkgCount();
}

function _pkgSelectAllChannels(checked) {
  const loaded = _pkgItems('channels').length;
  const total = window._pkgEditor?.totalChannels || loaded;
  if (checked && total > loaded) {
    const ok = confirm(`You're selecting ${loaded.toLocaleString()} channels, but there are ${total.toLocaleString()} total channels available.\n\nDo you want to include ALL ${total.toLocaleString()} channels instead?\n\nClick OK to include all channels, or Cancel to only select the ${loaded.toLocaleString()} shown.`);
    if (ok) {
      _pkgSetAllChannels(true);
      return;
    }
  }
  _pkgToggleFiltered('channels', checked);
}
function _pkgCount() {
  const allToggle = document.getElementById('pkg-all-chs-toggle');
  if (allToggle) window._pkgAllChs = allToggle.checked;
  const totalChannels = window._pkgEditor?.totalChannels || window._pkg_total_chs || '';
  const cc = window._pkgAllChs ? (totalChannels || 'all') : _pkgSelected('channels').size;
  const vc = _pkgSelected('vod').size;
  const rc = _pkgSelected('radio').size;
  const el1 = document.getElementById('pkg-ch-count');
  const el2 = document.getElementById('pkg-vod-count');
  const el3 = document.getElementById('pkg-radio-count');
  if(el1) el1.textContent = window._pkgAllChs ? `(ALL ${totalChannels.toLocaleString()} channels)` : `(${cc} selected)`;
  if(el2) el2.textContent = `(${vc} selected)`;
  if(el3) el3.textContent = `(${rc} selected)`;
}

async function svPkg(id) {
  const name = document.getElementById('pkg-name')?.value.trim();
  if(!name){alert('Package name required');return;}
  const selectAllChs = !!(window._pkgAllChs);
  const channel_ids = selectAllChs ? [] : [..._pkgSelected('channels')].sort((a,b)=>a-b);
  const vod_ids     = [..._pkgSelected('vod')].sort((a,b)=>a-b);
  const radio_ids   = [..._pkgSelected('radio')].sort((a,b)=>a-b);
  const active      = parseInt(document.getElementById('pkg-active')?.value||'1');
  const desc        = document.getElementById('pkg-desc')?.value||'';
  const body = JSON.stringify({name, description:desc, active, channel_ids, vod_ids, radio_ids, select_all_channels: selectAllChs});
  const r = id
    ? await req('/packages/'+id,{method:'PUT',body})
    : await req('/packages',{method:'POST',body});
  if(r?.error){alert(r.error);return;}
  closeModal();
  toast(id?'✅ Package updated':'✅ Package created');
  await pages.packages();
}

async function dPkg(id,name) {
  if(!confirm(`Delete package "${name}"? Rooms will lose access to its content.`))return;
  await req('/packages/'+id,{method:'DELETE'});
  toast('🗑 Package deleted');
  await pages.packages();
}


// ── VIP ACCESS ────────────────────────────────────────────────────────────────
pages.vip = async function() {
  const unit = (window._deployMode==='commercial') ? 'Screen' : 'Room';
  const units = unit+'s';
  const vodListRes = await fetch(window.location.origin+'/vod/api/videos?limit=500',{headers:jwt?{Authorization:'Bearer '+jwt}:{}}).then(r=>r.json()).catch(()=>({videos:[]}));
  const [vipChs, allChs, rooms, vipVod, pkgs, pkgRoomMapRaw] = await Promise.all([
    req('/vip/channels'), req('/channels?active=0'), req('/rooms'),
    req('/vip/vod'), req('/packages'), req('/rooms/packages-map')
  ]);
  window._vip_chs   = vipChs||[];
  window._all_chs   = allChs||[];
  window._rooms_ref = rooms||[];
  window._vip_vod   = vipVod||[];
  window._all_vod   = vodListRes?.videos||[];
  window._pkg_list  = pkgs||[];
  // Build reverse map: package_id -> [room_ids]
  const pkgRoomMap = {};
  Object.entries(pkgRoomMapRaw||{}).forEach(([roomId, pkgNames])=>{
    (pkgs||[]).filter(p=>pkgNames.includes(p.name)).forEach(p=>{
      if(!pkgRoomMap[p.id]) pkgRoomMap[p.id]=[];
      pkgRoomMap[p.id].push(parseInt(roomId));
    });
  });
  window._pkgRoomMap = pkgRoomMap;
  window._vip_active_tab = window._vip_active_tab||'channels';

  const chTab  = window._vip_active_tab==='channels';
  const vodTab = window._vip_active_tab==='vod';
  const pkgTab = window._vip_active_tab==='packages';

  // ── Channels tab content ──
  const chRows = (vipChs||[]).map(c=>`
    <tr>
      <td><b>${esc(c.name)}</b></td>
      <td><span class="bdg ${c.channel_type==='m3u'?'bg':c.channel_type==='analog_tuner'?'bor':'bb'}">${c.channel_type||'udp'}</span></td>
      <td>
        <div style="display:flex;flex-wrap:wrap;gap:4px">
          ${(c.rooms||[]).map(r=>`
            <span class="bdg bb" style="cursor:pointer" title="Click to revoke"
              onclick="revokeVip(${c.id},${r.id},'${esc(r.room_number)}','${esc(c.name)}')">${unit} ${esc(r.room_number)} ✕</span>`).join('')}
          ${!c.rooms?.length?`<span style="color:var(--text3);font-size:12px">No ${units.toLowerCase()} assigned</span>`:''}
        </div>
      </td>
      <td><div class="tda">
        <button class="btn btn-d btn-sm" onclick="revokeAllVip(${c.id},'${esc(c.name)}')">Revoke All</button>
      </div></td>
    </tr>`).join('');

  // ── VOD tab content ──
  // Group vipVod by video
  const vodMap = {};
  (vipVod||[]).forEach(v=>{
    if(!vodMap[v.video_id]) vodMap[v.video_id]={video_id:v.video_id,title:v.title,rooms:[]};
    vodMap[v.video_id].rooms.push({id:v.room_id,room_number:v.room_number});
  });
  const vodRows = Object.values(vodMap).map(v=>`
    <tr>
      <td><b>${esc(v.title||v.video_id)}</b></td>
      <td>
        <div style="display:flex;flex-wrap:wrap;gap:4px">
          ${v.rooms.map(r=>`
            <span class="bdg bb" style="cursor:pointer" title="Click to revoke"
              onclick="revokeVipVod('${esc(v.video_id)}',${r.id},'${esc(r.room_number)}','${esc(v.title||v.video_id)}')">${unit} ${esc(r.room_number)} ✕</span>`).join('')}
        </div>
      </td>
      <td><div class="tda">
        <button class="btn btn-d btn-sm" onclick="revokeAllVipVod('${esc(v.video_id)}','${esc(v.title||v.video_id)}')">Revoke All</button>
      </div></td>
    </tr>`).join('');

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">VIP Access</div>
    <button class="btn btn-p" onclick="eVipGrant()">+ Grant VIP Access</button>
  </div>
  <div class="ibox info">
    By default, ${units.toLowerCase()} have <b>no access</b> to any content. Assign packages to grant access to channels, VOD and radio.
    VIP grants give individual access on top of packages.
  </div>
  <div style="display:flex;gap:8px;margin-bottom:16px">
    <button class="btn ${chTab?'btn-p':'btn-g'}" onclick="window._vip_active_tab='channels';pages.vip()">📺 Channels</button>
    <button class="btn ${vodTab?'btn-p':'btn-g'}" onclick="window._vip_active_tab='vod';pages.vip()">🎬 VOD</button>
    <button class="btn ${pkgTab?'btn-p':'btn-g'}" onclick="window._vip_active_tab='packages';pages.vip()">📦 Packages</button>
  </div>
  ${chTab?`
    ${vipChs&&vipChs.length?`
    <div class="tbl-wrap"><table>
      <thead><tr><th>Channel</th><th>Type</th><th>${units} with Access</th><th>Actions</th></tr></thead>
      <tbody>${chRows}</tbody>
    </table></div>`
    :`<div class="ibox">No VIP channels yet. Use <b>+ Grant VIP Access</b> to restrict a channel.</div>`}
  `:vodTab?`
    ${Object.keys(vodMap).length?`
    <div class="tbl-wrap"><table>
      <thead><tr><th>Title</th><th>${units} with Access</th><th>Actions</th></tr></thead>
      <tbody>${vodRows}</tbody>
    </table></div>`
    :`<div class="ibox">No VIP VOD titles yet. Use <b>+ Grant VIP Access</b> to restrict a VOD title.</div>`}
  `:`
    ${(pkgs&&pkgs.length)?`
    <div class="tbl-wrap"><table>
      <thead><tr><th>Package</th><th>${units} Assigned</th><th>Content</th><th>Actions</th></tr></thead>
      <tbody>${(pkgs||[]).map(p=>{
        const assignedRooms=(rooms||[]).filter(r=>(window._pkgRoomMap&&window._pkgRoomMap[String(p.id)]||[]).includes(r.id));
        return`<tr>
          <td><b>${esc(p.name)}</b>${p.description?`<br><span style="color:var(--text3);font-size:11px">${esc(p.description)}</span>`:''}
          </td>
          <td><div style="display:flex;flex-wrap:wrap;gap:4px">
            ${assignedRooms.map(r=>`<span class="bdg bb" style="cursor:pointer" title="Click to remove"
              onclick="revokeRoomPkg(${r.id},'${esc(r.room_number)}',${p.id},'${esc(p.name)}')">${unit} ${esc(r.room_number)} ✕</span>`).join('')}
            ${!assignedRooms.length?`<span style="color:var(--text3);font-size:12px">No ${units.toLowerCase()} assigned</span>`:''}
          </div></td>
          <td><span class="bdg bg">${(p.channel_ids||[]).length} ch</span> <span class="bdg bb">${(p.vod_ids||[]).length} VOD</span></td>
          <td></td>
        </tr>`;}).join('')}
      </tbody>
    </table></div>`
    :`<div class="ibox">No packages defined yet. Create packages first, then assign them here.</div>`}
  `}`;
};

// ── Grant VIP modal ───────────────────────────────────────────────────────────
function eVipGrant(){
  const t = window._vip_active_tab;
  window._vip_grant_type = t==='vod' ? 'vod' : t==='packages' ? 'package' : 'channel';
  window._vip_chip_rooms = new Set();
  window._vip_sel_content = new Set();
  _renderVipModal();
}

async function revokeRoomPkg(roomId, roomNum, pkgId, pkgName){
  const unit = (window._deployMode==='commercial')?'Screen':'Room';
  if(!confirm(`Remove ${unit} ${roomNum} from package "${pkgName}"?`)) return;
  const existing = await req('/rooms/'+roomId+'/packages');
  const remaining = (existing||[]).filter(p=>p.id!==pkgId).map(p=>p.id);
  await req('/rooms/'+roomId+'/packages',{method:'POST',body:JSON.stringify({package_ids:remaining})});
  toast('📦 Package removed');
  await pages.vip();
}

function _renderVipModal(){
  const unit  = (window._deployMode==='commercial') ? 'Screen' : 'Room';
  const units = unit+'s';
  const type  = window._vip_grant_type||'channel';
  const isVod = type==='vod';
  const isPkg = type==='package';
  const rooms = window._rooms_ref||[];

  const chips = [...(window._vip_chip_rooms||[])].map(n=>`
    <span class="vip-chip">${unit} ${esc(n)} <span onclick="vipRemoveChip('${esc(n)}')" style="cursor:pointer;margin-left:3px">✕</span></span>`).join('');

  // Content list (channel / vod / package)
  let contentList = '';
  if(isPkg){
    contentList = (window._pkg_list||[]).map(p=>`
      <label class="vip-item" id="vipci-${p.id}">
        <input type="checkbox" value="${p.id}" onchange="_vipToggleContent(this)">
        <span><b>${esc(p.name)}</b>${p.description?` <span style="color:var(--text3);font-size:11px">— ${esc(p.description)}</span>`:''}</span>
      </label>`).join('');
  } else if(isVod){
    contentList = (window._all_vod||[]).map(v=>`
      <label class="vip-item" id="vipci-${esc(v.id)}">
        <input type="checkbox" value="${esc(v.id)}" onchange="_vipToggleContent(this)">
        <span>${esc(v.title||v.id)}</span>
      </label>`).join('');
  } else {
    contentList = (window._all_chs||[]).map(c=>`
      <label class="vip-item" id="vipci-${c.id}">
        <input type="checkbox" value="${c.id}" onchange="_vipToggleContent(this)">
        <span>${esc(c.name)}</span>
      </label>`).join('');
  }

  const contentLabel = isPkg ? 'Packages' : isVod ? 'VOD Titles' : 'Channels';

  openModal(`Grant VIP Access`,`
  <div class="vip-tabs">
    <button class="btn ${type==='channel'?'btn-p':'btn-g'} btn-sm" onclick="window._vip_grant_type='channel';window._vip_sel_content=new Set();_renderVipModal()">📺 Channel</button>
    <button class="btn ${type==='vod'?'btn-p':'btn-g'} btn-sm" onclick="window._vip_grant_type='vod';window._vip_sel_content=new Set();_renderVipModal()">🎬 VOD</button>
    <button class="btn ${type==='package'?'btn-p':'btn-g'} btn-sm" onclick="window._vip_grant_type='package';window._vip_sel_content=new Set();_renderVipModal()">📦 Package</button>
  </div>
  ${isPkg?`<div class="ibox info" style="margin-bottom:12px;font-size:12px">Assigns the selected package(s) to ${units.toLowerCase()}, giving them access to all content inside those packages.</div>`:''}
  <div class="fgrid">
    <div class="fg fcol">
      <label>${contentLabel} * <span id="vip-sel-count" style="font-weight:400;color:var(--text2)">(0 selected)</span></label>
      <input class="vip-srch" placeholder="Search..." oninput="vipFilterContent(this.value)" id="vip-srch">
      <div class="vip-list" id="vip-content-list">${contentList||`<div style="padding:10px;color:var(--text3);font-size:13px">No ${contentLabel.toLowerCase()} found</div>`}</div>
    </div>
    <div class="fg fcol" style="position:relative">
      <label>${units} * <span style="font-weight:400;color:var(--text2);font-size:11px">(type number + Enter)</span></label>
      <div class="vip-chip-wrap" id="vip-chip-wrap" onclick="document.getElementById('vip-chip-inp').focus()">
        ${chips}
        <input class="vip-chip-inp" id="vip-chip-inp" placeholder="${unit} number..." autocomplete="off"
          oninput="_vipChipInput(this.value)"
          onkeydown="if(event.key==='Enter'){event.preventDefault();vipAddChip(this.value.trim())}"
          onblur="setTimeout(()=>document.getElementById('vip-sug')&&document.getElementById('vip-sug').remove(),200)">
      </div>
      <div id="vip-sug-wrap" style="position:relative"></div>
      <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn btn-g btn-xs" onclick="vipSelectAllRooms()">All ${units}</button>
        <button class="btn btn-g btn-xs" onclick="vipClearRooms()">Clear</button>
      </div>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svVipGrant()">Grant Access</button>`,'modal-lg');

  // restore selections
  window._vip_sel_content = window._vip_sel_content||new Set();
  window._vip_sel_content.forEach(id=>{
    const el=document.querySelector(`#vip-content-list input[value="${id}"]`);
    if(el){el.checked=true;el.closest('label').style.background='var(--bg2)';}
  });
  _vipUpdateCount();
}

function _vipToggleContent(cb){
  if(!window._vip_sel_content) window._vip_sel_content=new Set();
  const v = window._vip_grant_type==='vod' ? cb.value : parseInt(cb.value);
  if(cb.checked){window._vip_sel_content.add(v);cb.closest('label').style.background='var(--bg2)';}
  else{window._vip_sel_content.delete(v);cb.closest('label').style.background='';}
  _vipUpdateCount();
}
function _vipUpdateCount(){
  const el=document.getElementById('vip-sel-count');
  if(el) el.textContent=`(${(window._vip_sel_content||new Set()).size} selected)`;
}
function vipFilterContent(q){
  const items=document.querySelectorAll('#vip-content-list .vip-item');
  const lq=q.toLowerCase();
  items.forEach(el=>{el.style.display=el.textContent.toLowerCase().includes(lq)?'':'none';});
}
function _vipChipInput(val){
  const rooms=window._rooms_ref||[];
  const unit=(window._deployMode==='commercial')?'Screen':'Room';
  const wrap=document.getElementById('vip-sug-wrap');
  if(!wrap)return;
  const matches=rooms.filter(r=>r.room_number.toString().startsWith(val.trim())&&!window._vip_chip_rooms.has(r.room_number.toString()));
  if(!val.trim()||!matches.length){wrap.innerHTML='';return;}
  wrap.innerHTML=`<div id="vip-sug" class="vip-sug">${matches.slice(0,8).map(r=>`
    <div class="vip-sug-item" onmousedown="vipAddChip('${esc(r.room_number.toString())}')">${unit} ${esc(r.room_number.toString())}</div>`).join('')}</div>`;
}
function vipAddChip(num){
  if(!num)return;
  const rooms=window._rooms_ref||[];
  const exists=rooms.some(r=>r.room_number.toString()===num.toString());
  if(!exists){toast('⚠ '+((window._deployMode==='commercial')?'Screen':'Room')+' '+num+' not found');return;}
  if(!window._vip_chip_rooms) window._vip_chip_rooms=new Set();
  window._vip_chip_rooms.add(num.toString());
  const inp=document.getElementById('vip-chip-inp');
  if(inp){inp.value='';inp.focus();}
  const sw=document.getElementById('vip-sug-wrap');if(sw)sw.innerHTML='';
  _vipRenderChips();
}
function vipRemoveChip(num){
  window._vip_chip_rooms&&window._vip_chip_rooms.delete(num.toString());
  _vipRenderChips();
}
function vipSelectAllRooms(){
  const rooms=window._rooms_ref||[];
  window._vip_chip_rooms=new Set(rooms.map(r=>r.room_number.toString()));
  _vipRenderChips();
}
function vipClearRooms(){
  window._vip_chip_rooms=new Set();
  _vipRenderChips();
}
function _vipRenderChips(){
  const unit=(window._deployMode==='commercial')?'Screen':'Room';
  const wrap=document.getElementById('vip-chip-wrap');
  const inp=document.getElementById('vip-chip-inp');
  if(!wrap)return;
  // remove existing chips, keep input
  [...wrap.querySelectorAll('.vip-chip')].forEach(c=>c.remove());
  const chips=[...(window._vip_chip_rooms||[])].map(n=>{
    const s=document.createElement('span');
    s.className='vip-chip';
    s.innerHTML=`${unit} ${esc(n)} <span onclick="vipRemoveChip('${esc(n)}')" style="cursor:pointer;margin-left:3px">✕</span>`;
    return s;
  });
  chips.forEach(c=>wrap.insertBefore(c,inp));
}

async function svVipGrant(){
  const type       = window._vip_grant_type||'channel';
  const isVod      = type==='vod';
  const isPkg      = type==='package';
  const selContent = [...(window._vip_sel_content||new Set())];
  const chipNums   = [...(window._vip_chip_rooms||new Set())];
  const unit       = (window._deployMode==='commercial')?'screen':'room';
  const contentWord= isPkg?'package':isVod?'VOD title':'channel';

  if(!selContent.length){alert('Select at least one '+contentWord);return;}
  if(!chipNums.length){alert('Add at least one '+unit);return;}

  // Resolve room numbers to IDs
  const rooms=window._rooms_ref||[];
  const roomIds=chipNums.map(n=>{const r=rooms.find(x=>x.room_number.toString()===n);return r?r.id:null;}).filter(Boolean);
  if(!roomIds.length){alert('No valid '+unit+'s found');return;}

  let r, errors=[];
  if(isPkg){
    // For each room, add the selected packages (merge with existing)
    for(const rid of roomIds){
      const existing=await req('/rooms/'+rid+'/packages');
      const existingIds=(existing||[]).map(p=>p.id);
      const merged=[...new Set([...existingIds,...selContent.map(Number)])];
      r=await req('/rooms/'+rid+'/packages',{method:'POST',body:JSON.stringify({package_ids:merged})});
      if(r?.error) errors.push(r.error);
    }
  } else if(isVod){
    r=await req('/vip/vod-access',{method:'POST',body:JSON.stringify({video_ids:selContent,room_ids:roomIds})});
    if(r?.error) errors.push(r.error);
  } else {
    for(const chId of selContent){
      r=await req('/vip/access',{method:'POST',body:JSON.stringify({channel_id:chId,room_ids:roomIds})});
      if(r?.error) errors.push(r.error);
    }
  }
  if(errors.length){alert('Some errors:\n'+errors.join('\n'));return;}
  window._vip_sel_content=new Set();
  closeModal();
  toast('✅ Access granted');
  await pages.vip();
}

async function revokeVip(chId,rmId,rmNum,chName){
  const unit=(window._deployMode==='commercial')?'Screen':'Room';
  if(!confirm(`Revoke ${unit} ${rmNum} access to "${chName}"?`))return;
  await req('/vip/access',{method:'DELETE',body:JSON.stringify({channel_id:chId,room_id:rmId})});
  toast('🔒 Access revoked');await pages.vip();
}
async function revokeAllVip(chId,chName){
  if(!confirm(`Revoke ALL access to "${chName}"? Channel will become non-VIP.`))return;
  await req('/vip/access',{method:'DELETE',body:JSON.stringify({channel_id:chId})});
  toast('🔒 All access revoked');await pages.vip();
}
async function revokeVipVod(videoId,rmId,rmNum,title){
  const unit=(window._deployMode==='commercial')?'Screen':'Room';
  if(!confirm(`Revoke ${unit} ${rmNum} access to "${title}"?`))return;
  await req('/vip/vod-access',{method:'DELETE',body:JSON.stringify({video_id:videoId,room_id:rmId})});
  toast('🔒 VOD access revoked');await pages.vip();
}
async function revokeAllVipVod(videoId,title){
  if(!confirm(`Revoke ALL access to "${title}"?`))return;
  await req('/vip/vod-access',{method:'DELETE',body:JSON.stringify({video_id:videoId})});
  toast('🔒 All VOD access revoked');await pages.vip();
}

// ── updateCounts v6 addition ──────────────────────────────────────────────────
const _origUpdateCounts = updateCounts;
updateCounts = async function() {
  await _origUpdateCounts();
  const msgs = await req('/messages');
  if (Array.isArray(msgs)) {
    const active = msgs.filter(m=>m.active).length;
    const el = document.getElementById('cnt-msg');
    if (el) el.textContent = active || '—';
  }
};



// ═══════════════════════════════════════════════════════════════════════════════
// V7 PAGE FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

// ── GUEST SERVICES ────────────────────────────────────────────────────────────
pages.services = async function() {
  const svcs = await req('/services/all');
  if (!svcs) return;
  window._svcs = svcs;
  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">Guest Services</div>
    <button class="btn btn-p" onclick="eSvc(null)">+ Add Service</button>
  </div>
  <div class="ibox info">Guest services appear on the TV/phone as quick-dial tiles. Guests tap a tile to see the service phone number and description. Set sort_order to control the display sequence.</div>
  <div class="card-grid" id="svc-grid">
    ${svcs.map(s=>`
    <div class="card" style="${!s.active?'opacity:.5':''}">
      <div class="card-title">
        <span style="font-size:22px">${s.icon}</span>
        ${esc(s.name)}
        <span class="bdg ${s.active?'bg':'br'}" style="font-size:9px">${s.active?'Active':'Hidden'}</span>
      </div>
      <div class="card-sub" style="margin-bottom:4px"><span class="bdg bb">${esc(s.category)}</span></div>
      ${s.phone?`<div style="font-family:'DM Mono',monospace;font-size:12px;color:var(--gold);margin-top:4px">📞 ${esc(s.phone)}</div>`:''}
      <div style="font-size:12px;color:var(--text2);margin-top:4px">${esc(s.description)}</div>
      <div class="card-acts">
        <button class="btn btn-g btn-sm" onclick="eSvc(${s.id})">Edit</button>
        <button class="btn btn-d btn-sm" onclick="dSvc(${s.id})">Del</button>
      </div>
    </div>`).join('')}
  </div>`;
};

function eSvc(id) {
  const s = id ? (window._svcs||[]).find(x=>x.id===id) : null;
  const ICONS = ['📞','🏨','🍽','🛎','🔧','💆','💼','✈','🚗','🧹','🛁','🏊','🎾','💊','🔑','📦','🍹','🎭','🛒','📸'];
  openModal(s?'Edit Service':'Add Service', `
  <div class="fgrid">
    <div class="fg fcol"><label>Service Name *</label><input id="sv-name" value="${esc(s?.name||'')}"></div>
    <div class="fg"><label>Category</label><input id="sv-cat" value="${esc(s?.category||'General')}" placeholder="Reception, F&B, Leisure..."></div>
    <div class="fg"><label>Icon</label>
      <input id="sv-icon" value="${esc(s?.icon||'📞')}" style="font-size:20px;text-align:center">
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">${ICONS.map(ic=>`<button type="button" style="font-size:20px;background:var(--bg3);border:1px solid var(--border2);border-radius:6px;padding:4px 8px;cursor:pointer" onclick="document.getElementById('sv-icon').value='${ic}'">${ic}</button>`).join('')}</div>
    </div>
    <div class="fg"><label>Phone Number</label><input id="sv-phone" value="${esc(s?.phone||'')}" placeholder="Extension or full number"></div>
    <div class="fg fcol"><label>Description</label><textarea id="sv-desc">${esc(s?.description||'')}</textarea></div>
    <div class="fg"><label>Sort Order</label><input id="sv-ord" type="number" value="${s?.sort_order||0}"></div>
    <div class="fg"><label>Status</label>
      <select id="sv-active" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1" ${!s||s.active?'selected':''}>Active</option>
        <option value="0" ${s&&!s.active?'selected':''}>Hidden</option>
      </select>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svSvc(${id||'null'})">Save</button>`);
}
async function svSvc(id) {
  const d = {name:document.getElementById('sv-name').value.trim(),category:document.getElementById('sv-cat').value,icon:document.getElementById('sv-icon').value,phone:document.getElementById('sv-phone').value,description:document.getElementById('sv-desc').value,sort_order:parseInt(document.getElementById('sv-ord').value)||0,active:parseInt(document.getElementById('sv-active').value)};
  if(!d.name)return;
  const r=id?await req('/services/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/services',{method:'POST',body:JSON.stringify(d)});
  if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ Updated':'✅ Created');await pages.services();
}
async function dSvc(id){if(!confirm('Delete this service?'))return;await req('/services/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.services();}


// ── EPG / PROGRAMME SCHEDULE ──────────────────────────────────────────────────
pages.epg = async function() {
  const [epg, chs, mon] = await Promise.all([req('/epg?hours=48'), req('/channels?active=0'), req('/epg/monitor')]);
  if (!chs) return;
  window._epg    = epg||[];
  window._chs_epg = chs||[];
  window._epgMon = mon||{};

  // Group EPG by channel
  const byChannel = {};
  (epg||[]).forEach(e => {
    if (!byChannel[e.channel_id]) byChannel[e.channel_id] = [];
    byChannel[e.channel_id].push(e);
  });

  const now = new Date();
  function fmtTime(s) { const d=new Date(s); return d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0'); }
  function isPast(e) { return new Date(e.end_time) < now; }
  function isCurrent(e) { const s=new Date(e.start_time),en=new Date(e.end_time); return s<=now&&en>now; }
  const m = mon||{};
  const cov = (m.total_channels||0) ? Math.round(((m.covered_channels||0)/(m.total_channels||1))*100) : 0;
  const lastStatus = m.last_status === 'ok' ? '<span class="bdg bg">Healthy</span>' : (m.last_status === 'error' ? '<span class="bdg br">Error</span>' : '<span class="bdg bb">Idle</span>');

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">EPG / Programme Schedule</div>
    <div class="sec-acts">
      <button class="btn btn-p" onclick="eEpg(null)">+ Add Entry</button>
      <button class="btn btn-g" onclick="openEpgBulk()">📋 Bulk Add</button>
      <button class="btn btn-d btn-sm" onclick="clearOldEpg()">🗑 Clear Old</button>
    </div>
  </div>
  <div class="tbl-wrap" style="padding:14px;margin-bottom:12px">
    <div style="display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:10px;margin-bottom:12px">
      <div class="ibox"><div style="font-size:11px;color:var(--text2)">Status</div><div style="margin-top:6px">${lastStatus}</div></div>
      <div class="ibox"><div style="font-size:11px;color:var(--text2)">Coverage</div><div style="margin-top:6px;font-weight:700">${cov}%</div><div style="font-size:11px;color:var(--text3)">${m.covered_channels||0} / ${m.total_channels||0} channels</div></div>
      <div class="ibox"><div style="font-size:11px;color:var(--text2)">Upcoming Entries</div><div style="margin-top:6px;font-weight:700">${fmtNum(m.upcoming_entries||0)}</div></div>
      <div class="ibox"><div style="font-size:11px;color:var(--text2)">Last Imported</div><div style="margin-top:6px;font-weight:700">${fmtNum(m.last_imported||0)} / ${fmtNum(m.last_parsed||0)}</div><div style="font-size:11px;color:var(--text3)">Unmatched: ${fmtNum(m.last_unmatched||0)}</div></div>
      <div class="ibox"><div style="font-size:11px;color:var(--text2)">Last Sync</div><div style="margin-top:6px;font-weight:700">${m.last_sync_at?esc(m.last_sync_at):'Never'}</div><div style="font-size:11px;color:var(--text3)">${m.last_duration_ms?('Duration: '+m.last_duration_ms+' ms'):''}</div></div>
    </div>
    <div class="fgrid" style="grid-template-columns:2fr 130px 100px auto auto auto;align-items:end">
      <div class="fg fcol"><label>EPG Source URL (XMLTV — from your IPTV provider)</label><input id="epg-auto-url" value="${esc(m.auto_url||'')}" placeholder="http://your-iptv-provider.com/epg.xml"></div>
      <div class="fg"><label>Interval (min)</label><input id="epg-auto-interval" type="number" min="15" value="${parseInt(m.auto_interval_minutes||360)||360}"></div>
      <div class="fg"><label>Auto Sync</label><select id="epg-auto-enabled" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%"><option value="1" ${(m.auto_enabled?'selected':'')}>On</option><option value="0" ${(!m.auto_enabled?'selected':'')}>Off</option></select></div>
      <button class="btn btn-p" onclick="saveEpgMonitorSettings()">💾 Save</button>
      <button class="btn btn-g" onclick="generateEpgGuideXml()">📄 Generate guide.xml</button>
      <button class="btn btn-g" onclick="syncEpgNow()">⟳ Sync Now</button>
      <button class="btn btn-g" onclick="pages.epg()">↻ Refresh</button>
    </div>
    <div id="epg-monitor-msg" style="margin-top:8px;font-size:12px;color:var(--text2)">${m.last_message?esc(m.last_message):''}</div>
  </div>
  <div class="ibox info">EPG entries appear on the TV screen when a guest is watching a channel — showing current programme and what's coming next.</div>
  ${Object.keys(byChannel).length === 0 ? '<div class="ibox">No EPG data yet. Use <b>+ Add Entry</b> or <b>Bulk Add</b> to populate the programme guide.</div>' :
    Object.entries(byChannel).map(([chId, entries]) => {
      const ch = chs.find(c=>c.id==chId);
      return `<div style="margin-bottom:18px">
        <div style="font-size:11px;color:var(--text2);font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:2px;margin-bottom:8px;padding:4px 12px;background:var(--bg3);border-radius:6px;display:inline-flex;align-items:center;gap:10px">
          📺 ${esc(ch?.name||'Channel '+chId)}
          <button class="btn btn-p btn-xs" style="font-size:11px;padding:2px 8px;text-transform:none;letter-spacing:0" onclick="eEpg(null,${chId})">+ Add</button>
        </div>
        <div class="tbl-wrap"><table>
          <thead><tr><th>Time</th><th>Title</th><th>Category</th><th>Duration</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>${entries.map(e=>{
            const dur = Math.round((new Date(e.end_time)-new Date(e.start_time))/60000);
            const status = isPast(e)?'<span class="bdg br">Past</span>':isCurrent(e)?'<span class="bdg bg">● NOW</span>':'<span class="bdg bb">Upcoming</span>';
            return `<tr style="${isCurrent(e)?'background:rgba(61,220,132,.04)':''}">
              <td style="font-family:'DM Mono',monospace;font-size:12px;white-space:nowrap">${fmtTime(e.start_time)} – ${fmtTime(e.end_time)}</td>
              <td><b>${esc(e.title)}</b>${e.description?'<div style="font-size:11px;color:var(--text3)">'+esc(e.description.substring(0,60))+'</div>':''}</td>
              <td>${e.category?'<span class="bdg bp">'+esc(e.category)+'</span>':'—'}</td>
              <td style="color:var(--text2)">${dur}m</td>
              <td>${status}</td>
              <td><div class="tda">
                <button class="btn btn-g btn-xs" onclick="eEpg(${e.id})">Edit</button>
                <button class="btn btn-d btn-xs" onclick="dEpg(${e.id})">Del</button>
              </div></td>
            </tr>`;}).join('')}
          </tbody>
        </table></div>
      </div>`;
    }).join('')
  }`;
};

function eEpg(id, preChId) {
  const e = id ? (window._epg||[]).find(x=>x.id===id) : null;
  const chs = window._chs_epg||[];
  const selChId = e?.channel_id ?? preChId ?? null;
  const selChName = selChId ? (chs.find(c=>c.id==selChId)?.name||'') : '';
  const fmtLocal = s => s ? new Date(s).toISOString().slice(0,16) : '';
  openModal(e?'Edit EPG Entry':'Add EPG Entry', `
  <div class="fgrid">
    <div class="fg fcol"><label>Channel *</label>
      <input id="ep-ch-search" list="ep-ch-datalist" placeholder="Type to search channel…"
        autocomplete="off" value="${esc(selChName)}"
        oninput="(function(v){const m=(window._chs_epg||[]).find(c=>c.name.toLowerCase()===v.toLowerCase());if(m)document.getElementById('ep-ch').value=m.id;})(this.value)"
        style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
      <datalist id="ep-ch-datalist">${chs.map(c=>`<option value="${esc(c.name)}"></option>`).join('')}</datalist>
      <input type="hidden" id="ep-ch" value="${selChId||''}">
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap">
        <button type="button" class="btn btn-g btn-xs" onclick="autoMatchEpgChannel()">Auto Match Channel</button>
        <span id="ep-ch-hint" style="font-size:12px;color:var(--text2)">Auto-match runs for NOW/Upcoming when title/time are valid.</span>
      </div>
    </div>
    <div class="fg fcol"><label>Programme Title *</label><input id="ep-title" value="${esc(e?.title||'')}" oninput="autoMatchEpgChannelAuto()"></div>
    <div class="fg fcol"><label>Description</label><textarea id="ep-desc" style="height:60px">${esc(e?.description||'')}</textarea></div>
    <div class="fg"><label>Start Time *</label><input id="ep-start" type="datetime-local" value="${fmtLocal(e?.start_time)}" onchange="autoMatchEpgChannelAuto()"></div>
    <div class="fg"><label>End Time *</label><input id="ep-end" type="datetime-local" value="${fmtLocal(e?.end_time)}" onchange="autoMatchEpgChannelAuto()"></div>
    <div class="fg"><label>Category</label><input id="ep-cat" value="${esc(e?.category||'')}" placeholder="News, Sports, Drama..."></div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svEpg(${id||'null'})">Save</button>`);
}

function _epgNormText(v){
  return String(v||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
}

function _epgIsNowOrUpcoming(startVal, endVal){
  const now = Date.now();
  const s = Date.parse(startVal||'');
  const e = Date.parse(endVal||'');
  if(!Number.isFinite(e)) return false;
  if(Number.isFinite(s) && s > e) return false;
  return e > now;
}

function autoMatchEpgChannel(opts){
  opts = opts || {};
  const silent = !!opts.silent;
  const requireNowUpcoming = !!opts.requireNowUpcoming;
  const hint = document.getElementById('ep-ch-hint');
  const titleRaw = (document.getElementById('ep-title')?.value||'').trim();
  const titleNorm = _epgNormText(titleRaw);
  if(!titleNorm){
    if(!silent && hint) hint.innerHTML = '<span style="color:var(--red)">Enter programme title first.</span>';
    return {matched:false,reason:'missing-title'};
  }

  const startVal = document.getElementById('ep-start')?.value || '';
  const endVal = document.getElementById('ep-end')?.value || '';
  if(requireNowUpcoming && !_epgIsNowOrUpcoming(startVal, endVal)){
    if(!silent && hint) hint.innerHTML = '<span style="color:var(--text2)">Auto-match runs only for NOW/Upcoming entries.</span>';
    return {matched:false,reason:'not-now-upcoming'};
  }

  const startMs = startVal ? Date.parse(startVal) : NaN;
  const endMs = endVal ? Date.parse(endVal) : NaN;

  const rows = window._epg || [];
  const chs = window._chs_epg || [];
  const scoreByChannel = Object.create(null);

  for(const row of rows){
    const chId = parseInt(row.channel_id);
    if(!chId) continue;
    const rowTitle = _epgNormText(row.title||'');
    if(!rowTitle) continue;

    let score = 0;
    if(rowTitle === titleNorm) score += 10;
    else if(rowTitle.includes(titleNorm) || titleNorm.includes(rowTitle)) score += 6;
    else continue;

    const rs = Date.parse(row.start_time||'');
    const re = Date.parse(row.end_time||'');
    const hasTargetTime = Number.isFinite(startMs) || Number.isFinite(endMs);
    const hasRowTime = Number.isFinite(rs) && Number.isFinite(re);
    if(hasTargetTime && hasRowTime){
      const tStart = Number.isFinite(startMs) ? startMs : endMs;
      const tEnd = Number.isFinite(endMs) ? endMs : startMs;
      const overlap = Math.max(0, Math.min(tEnd, re) - Math.max(tStart, rs));
      if(overlap > 0) score += 8;
      const dist = Math.min(Math.abs(tStart-rs), Math.abs(tEnd-re));
      if(dist <= 2*60*60*1000) score += 2;
    }

    scoreByChannel[chId] = (scoreByChannel[chId]||0) + score;
  }

  const best = Object.entries(scoreByChannel).sort((a,b)=>b[1]-a[1])[0];
  if(!best){
    if(!silent && hint) hint.innerHTML = '<span style="color:var(--red)">No confident match found. Please select channel manually.</span>';
    return {matched:false,reason:'no-match'};
  }

  const bestId = parseInt(best[0]);
  const bestScore = best[1]||0;
  const ch = chs.find(c=>parseInt(c.id)===bestId);
  if(!ch){
    if(!silent && hint) hint.innerHTML = '<span style="color:var(--red)">Suggested channel not available in list.</span>';
    return {matched:false,reason:'channel-missing'};
  }

  const chHidden = document.getElementById('ep-ch');
  const chSearch = document.getElementById('ep-ch-search');
  if(chHidden) chHidden.value = ch.id;
  if(chSearch) chSearch.value = ch.name;
  if(hint) hint.innerHTML = '<span style="color:var(--green)">Matched: <b>'+esc(ch.name)+'</b> (score '+bestScore+')</span>';
  return {matched:true,channel_id:ch.id,channel_name:ch.name,score:bestScore};
}

function autoMatchEpgChannelAuto(){
  return autoMatchEpgChannel({silent:true,requireNowUpcoming:true});
}

async function svEpg(id) {
  const d={channel_id:null,title:document.getElementById('ep-title').value.trim(),description:document.getElementById('ep-desc').value,start_time:document.getElementById('ep-start').value,end_time:document.getElementById('ep-end').value,category:document.getElementById('ep-cat').value};

  // Auto-match at save time for NOW/Upcoming entries when channel isn't explicitly selected.
  if(_epgIsNowOrUpcoming(d.start_time, d.end_time)){
    autoMatchEpgChannel({silent:true,requireNowUpcoming:true});
  }

  // resolve channel id from search input if hidden input wasn't updated by datalist selection
  const chs = window._chs_epg||[];
  const searchVal = (document.getElementById('ep-ch-search')?.value||'').trim().toLowerCase();
  const matchedCh = chs.find(c=>c.name.toLowerCase()===searchVal);
  const chId = matchedCh ? matchedCh.id : parseInt(document.getElementById('ep-ch').value);
  d.channel_id = chId;
  if(!d.channel_id||!d.title||!d.start_time||!d.end_time){alert('Channel and title are required');return;}
  const r=id?await req('/epg/'+id,{method:'PUT',body:JSON.stringify(d)}):await req('/epg',{method:'POST',body:JSON.stringify(d)});
  if(r?.error){alert(r.error);return;}closeModal();toast(id?'✅ EPG updated':'✅ EPG entry added');await pages.epg();
}
async function dEpg(id){if(!confirm('Delete EPG entry?'))return;await req('/epg/'+id,{method:'DELETE'});toast('🗑 Deleted');await pages.epg();}
async function clearOldEpg(){if(!confirm('Delete all EPG entries older than 1 day?'))return;const r=await req('/epg/clear-old',{method:'POST'});if(r?.ok){toast('🗑 Old EPG cleared');await pages.epg();}}

function openEpgBulk(){
  const chs=window._chs_epg||[];
  openModal('Bulk Add EPG',`
  <div class="ibox info">Paste CSV with columns: <code style="background:var(--bg4);padding:1px 6px;border-radius:4px;font-family:'DM Mono',monospace">channel_name,title,start_time,end_time,category,description</code><br>Date format: <b>YYYY-MM-DD HH:MM</b></div>
  <textarea id="epg-csv" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:10px;color:var(--text);font-family:'DM Mono',monospace;font-size:12px;height:160px;outline:none;resize:vertical" placeholder="channel_name,title,start_time,end_time,category&#10;BBC News,Morning News,2025-01-20 06:00,2025-01-20 09:00,News&#10;CNN,World Report,2025-01-20 09:00,2025-01-20 12:00,News"></textarea>
  <div id="epg-bulk-result" style="margin-top:8px"></div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="runEpgBulk()">Import</button>`,'modal-lg');
}
async function runEpgBulk(){
  const text=document.getElementById('epg-csv').value.trim();
  if(!text){alert('No data');return;}
  const rows=parseCSV(text);
  if(!rows.length){alert('No valid rows');return;}
  const chs=window._chs_epg||[];
  const entries=[];
  for(const row of rows){
    const ch=chs.find(c=>c.name.toLowerCase().trim()===String(row.channel_name||'').toLowerCase().trim());
    if(!ch)continue;
    entries.push({channel_id:ch.id,title:row.title||'',start_time:row.start_time||'',end_time:row.end_time||'',category:row.category||'',description:row.description||''});
  }
  if(!entries.length){document.getElementById('epg-bulk-result').innerHTML='<div style="color:var(--red)">No matching channels found. Check channel names.</div>';return;}
  const r=await req('/epg/bulk',{method:'POST',body:JSON.stringify({entries})});
  document.getElementById('epg-bulk-result').innerHTML='<div style="color:var(--green)">✅ Added: <b>'+r.added+'</b> entries</div>';
  await pages.epg();
}

async function saveEpgMonitorSettings(){
  const url = document.getElementById('epg-auto-url').value.trim();
  const enabled = document.getElementById('epg-auto-enabled').value;
  const interval = Math.max(15, parseInt(document.getElementById('epg-auto-interval').value||'360')||360);
  const msg = document.getElementById('epg-monitor-msg');
  const r = await req('/settings',{method:'POST',body:JSON.stringify({
    epg_auto_url: url,
    epg_auto_enabled: enabled,
    epg_auto_interval_minutes: String(interval)
  })});
  if(!r || r.error){msg.innerHTML='<span style="color:var(--red)">Failed to save settings</span>';return;}
  msg.innerHTML='<span style="color:var(--green)">✅ EPG monitor settings saved</span>';
}

async function syncEpgNow(){
  const url = document.getElementById('epg-auto-url').value.trim();
  const msg = document.getElementById('epg-monitor-msg');
  if(!url){
    msg.innerHTML='<span style="color:var(--red)">Please enter an external XMLTV EPG URL from your IPTV provider.</span>';
    return;
  }
  if(url === 'http://localhost:3000/guide.xml' || url === 'http://127.0.0.1:3000/guide.xml'){
    msg.innerHTML='<span style="color:var(--red)">⚠️ That URL is the local output file — enter your IPTV provider\'s XMLTV EPG URL instead.</span>';
    return;
  }

  msg.innerHTML='⏳ Sync started — fetching and importing EPG data...';
  const r = await req('/epg/sync-now',{method:'POST',body:JSON.stringify({url})});
  if(!r || r.error){msg.innerHTML='<span style="color:var(--red)">Sync failed: '+esc(r?.error||'unknown error')+'</span>';return;}
  msg.innerHTML='⏳ Importing EPG in background — stats will update automatically...';
  // Poll for completion: refresh every 4s up to 5 times
  let polls = 0;
  const poll = setInterval(async()=>{
    polls++;
    const m2 = await req('/epg/monitor');
    const curMsg = document.getElementById('epg-monitor-msg');
    if(!curMsg){clearInterval(poll);return;}
    if(m2 && m2.last_status && m2.last_status !== 'running'){
      clearInterval(poll);
      await pages.epg();
    } else if(polls >= 5){
      clearInterval(poll);
      await pages.epg();
    }
  }, 4000);
}

async function generateEpgGuideXml(){
  const msg = document.getElementById('epg-monitor-msg');
  msg.innerHTML='Generating guide.xml...';
  const r = await req('/epg/generate-guide',{method:'POST',body:JSON.stringify({days:2,path:'/opt/nexvision/epg/public/guide.xml'})});
  if(!r || r.error){
    msg.innerHTML='<span style="color:var(--red)">Generate failed: '+esc(r?.error||'unknown error')+'</span>';
    return;
  }
  msg.innerHTML='<span style="color:var(--green)">✅ Generated '+esc(r.path)+' ('+fmtNum(r.size_bytes||0)+' bytes). Use URL: http://localhost:3000/guide.xml</span>';
}


// ── SYSTEM SETTINGS ───────────────────────────────────────────────────────────
pages.settings = async function() {
  const s = await req('/settings');
  if (!s) return;
  window._settings = s;
  const _mode = s.deployment_mode || 'hotel';
  const _isHotel = _mode !== 'commercial';
  document.getElementById('content').innerHTML = `
  <div class="sec-hdr"><div class="sec-title">System Settings</div>
    <button class="btn btn-p" onclick="saveSettings()">💾 Save All Settings</button>
  </div>

  <!-- ── Deployment Mode Switcher ─────────────────────────────────────────── -->
  <div class="tbl-wrap" style="padding:20px;margin-bottom:18px;border:2px solid rgba(201,168,76,.28);background:linear-gradient(135deg,rgba(201,168,76,.05),transparent)">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px">
      <div>
        <div style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:3px">Deployment Mode</div>
        <div style="font-size:12px;color:var(--text2)">Choose how this system is deployed — affects labels, features and device registration.</div>
      </div>
      <div style="display:flex;background:var(--bg4);border-radius:10px;padding:3px;gap:3px">
        <button id="mode-btn-hotel"      onclick="setDeployMode('hotel')"
          style="border:none;padding:9px 22px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;transition:.18s;${_isHotel?'background:var(--gold);color:#000':'background:transparent;color:var(--text2)'}">
          🏨 Hotel
        </button>
        <button id="mode-btn-commercial" onclick="setDeployMode('commercial')"
          style="border:none;padding:9px 22px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;transition:.18s;${!_isHotel?'background:var(--gold);color:#000':'background:transparent;color:var(--text2)'}">
          🏢 Commercial
        </button>
      </div>
    </div>
    <div id="mode-desc" style="margin-top:13px;font-size:12px;color:var(--text2);padding:10px 14px;background:var(--bg4);border-radius:8px;line-height:1.6">
      ${_isHotel
        ? '🏨 <b>Hotel Mode</b> — Room registration by room number, check-in/out tracking, guest services, prayer times, room-based billing, birthday manager.'
        : '🏢 <b>Commercial Mode</b> — Screen/display registration by location ID, digital signage focus, public venue management. Hotel-specific guest features are hidden.'}
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
    <div>
      <div class="sec-title" style="margin-bottom:12px;font-size:13px;color:var(--text2)">🧩 General Preferences</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg hotel-only" style="${_isHotel?'':'display:none'}"><label>Checkout Time</label><input id="s-checkout" value="${esc(s.checkout_time||'12:00')}" placeholder="12:00"></div>
          <div class="fg hotel-only" style="${_isHotel?'':'display:none'}"><label>Currency</label>
            <select id="s-currency" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              ${['USD','EUR','GBP','AED','SAR','KWD','BHD','OMR','QAR','EGP','TRY','INR'].map(c=>`<option ${s.currency===c?'selected':''}>${c}</option>`).join('')}
            </select>
          </div>
          <div class="fg"><label>Default Language</label>
            <select id="s-lang" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              <option value="en" ${s.language==='en'?'selected':''}>English</option>
              <option value="ar" ${s.language==='ar'?'selected':''}>Arabic</option>
              <option value="fr" ${s.language==='fr'?'selected':''}>French</option>
              <option value="de" ${s.language==='de'?'selected':''}>German</option>
              <option value="es" ${s.language==='es'?'selected':''}>Spanish</option>
            </select>
          </div>
        </div>
      </div>


      <div class="sec-title hotel-only" style="margin:14px 0 12px;font-size:13px;color:var(--text2);${_isHotel?'':'display:none'}">🏨 Guest Info & PMS</div>
      <div class="tbl-wrap hotel-only" style="${_isHotel?'':'display:none'}padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg fcol" style="grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;gap:10px">
            <div>
              <div style="font-size:13px;font-weight:600;color:var(--text)">PMS Integration</div>
              <div style="font-size:11px;color:var(--text2);margin-top:3px">Connect to hotel PMS to sync guest name, check-in and check-out times</div>
            </div>
            <label class="big-toggle">
              <input type="checkbox" id="s-pms-enabled" ${s.pms_enabled==='1'?'checked':''} onchange="togglePmsFields()">
              <span class="big-toggle-track"></span>
            </label>
          </div>
          <div class="fg" id="pms-type-row" style="${s.pms_enabled==='1'?'':'display:none'}"><label>PMS System</label>
            <select id="s-pms-type" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              <option value="fias"       ${(s.pms_type||'fias')==='fias'      ?'selected':''}>Oracle FIAS</option>
              <option value="grms"       ${s.pms_type==='grms'      ?'selected':''}>GRMS System</option>
              <option value="thirdparty" ${s.pms_type==='thirdparty'?'selected':''}>Third-party PMS</option>
            </select>
          </div>
          <div class="fg" id="pms-host-row" style="${s.pms_enabled==='1'?'':'display:none'}"><label>PMS Host / IP</label><input id="s-pms-host" value="${esc(s.pms_host||'')}" placeholder="192.168.1.100"></div>
          <div class="fg" id="pms-port-row" style="${s.pms_enabled==='1'?'':'display:none'}"><label>Port</label><input id="s-pms-port" value="${esc(s.pms_port||'5010')}" placeholder="5010"></div>
          <div class="fg" id="pms-user-row" style="${s.pms_enabled==='1'?'':'display:none'}"><label>Username</label><input id="s-pms-user" value="${esc(s.pms_username||'')}" placeholder="pms_user"></div>
          <div class="fg" id="pms-pass-row" style="${s.pms_enabled==='1'?'':'display:none'}"><label>Password</label><input type="password" id="s-pms-pass" value="${esc(s.pms_password||'')}" placeholder="••••••••"></div>
          <div class="fg fcol" id="pms-welcome-row" style="${s.pms_enabled==='1'?'':'display:none'};grid-column:1/-1">
            <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:8px;padding-top:4px;border-top:1px solid var(--border2)">Welcome Screen</div>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px">
              <div>
                <div style="font-size:13px;color:var(--text)">Welcome Music</div>
                <div style="font-size:11px;color:var(--text2)">Play audio when guest welcome screen appears</div>
              </div>
              <label class="big-toggle">
                <input type="checkbox" id="s-welcome-music-enabled" ${s.welcome_music_enabled==='1'?'checked':''} onchange="toggleWelcomeMusicUrl()">
                <span class="big-toggle-track"></span>
              </label>
            </div>
            <div id="welcome-music-url-row" style="${s.welcome_music_enabled==='1'?'':'display:none'}">
              <label>Music URL (.mp3 / .ogg)</label>
              <input id="s-welcome-music-url" value="${esc(s.welcome_music_url||'')}" placeholder="https://... or /static/welcome.mp3">
            </div>
          </div>
        </div>
      </div>

      <div class="sec-title" style="margin:14px 0 12px;font-size:13px;color:var(--text2)">📶 Wi-Fi Info</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg"><label>Wi-Fi Network Name</label><input id="s-wifi-name" value="${esc(s.wifi_name||'')}"></div>
          <div class="fg"><label>Wi-Fi Password</label><input id="s-wifi-pass" value="${esc(s.wifi_password||'')}"></div>
        </div>
      </div>

      <div class="sec-title" style="margin:14px 0 12px;font-size:13px;color:var(--text2)">🌤 Weather</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg fcol"><label>Weather City</label>
            <select id="s-weather-city" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              <option value="">— Select City —</option>
              <optgroup label="🇦🇪 UAE">
                ${[['Abu Dhabi','Abu Dhabi'],['Al Ain','Al Ain'],['Dubai','Dubai'],['Sharjah','Sharjah'],['Ajman','Ajman'],['Ras Al Khaimah','Ras Al Khaimah'],['Fujairah','Fujairah'],['Umm Al Quwain','Umm Al Quwain']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
              <optgroup label="🇸🇦 Saudi Arabia">
                ${[['Riyadh','Riyadh'],['Jeddah','Jeddah'],['Mecca','Mecca'],['Medina','Medina'],['Dammam','Dammam'],['Khobar','Khobar'],['Tabuk','Tabuk'],['Abha','Abha']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
              <optgroup label="🌍 Middle East">
                ${[['Kuwait City','Kuwait City'],['Doha','Doha'],['Manama','Manama'],['Muscat','Muscat'],['Amman','Amman'],['Beirut','Beirut'],['Baghdad','Baghdad'],['Tehran','Tehran'],['Sanaa','Sanaa'],['Aden','Aden'],['Asmara','Asmara']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
              <optgroup label="🌍 Africa">
                ${[['Cairo','Cairo'],['Alexandria','Alexandria'],['Casablanca','Casablanca'],['Rabat','Rabat'],['Tunis','Tunis'],['Algiers','Algiers'],['Tripoli','Tripoli'],['Khartoum','Khartoum'],['Addis Ababa','Addis Ababa'],['Nairobi','Nairobi'],['Lagos','Lagos'],['Accra','Accra'],['Dakar','Dakar'],['Johannesburg','Johannesburg'],['Cape Town','Cape Town']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
              <optgroup label="🌍 Europe">
                ${[['London','London'],['Paris','Paris'],['Berlin','Berlin'],['Madrid','Madrid'],['Rome','Rome'],['Amsterdam','Amsterdam'],['Brussels','Brussels'],['Vienna','Vienna'],['Zurich','Zurich'],['Stockholm','Stockholm'],['Oslo','Oslo'],['Copenhagen','Copenhagen'],['Helsinki','Helsinki'],['Warsaw','Warsaw'],['Prague','Prague'],['Budapest','Budapest'],['Lisbon','Lisbon'],['Athens','Athens'],['Istanbul','Istanbul'],['Ankara','Ankara'],['Moscow','Moscow'],['Kyiv','Kyiv']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
              <optgroup label="🌏 Asia">
                ${[['Mumbai','Mumbai'],['Delhi','Delhi'],['Bangalore','Bangalore'],['Chennai','Chennai'],['Kolkata','Kolkata'],['Hyderabad','Hyderabad'],['Karachi','Karachi'],['Lahore','Lahore'],['Islamabad','Islamabad'],['Dhaka','Dhaka'],['Colombo','Colombo'],['Kathmandu','Kathmandu'],['Beijing','Beijing'],['Shanghai','Shanghai'],['Hong Kong','Hong Kong'],['Tokyo','Tokyo'],['Seoul','Seoul'],['Singapore','Singapore'],['Bangkok','Bangkok'],['Kuala Lumpur','Kuala Lumpur'],['Jakarta','Jakarta'],['Manila','Manila'],['Taipei','Taipei'],['Osaka','Osaka'],['Ho Chi Minh City','Ho Chi Minh City'],['Hanoi','Hanoi']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
              <optgroup label="🌎 Americas">
                ${[['New York','New York'],['Los Angeles','Los Angeles'],['Chicago','Chicago'],['Houston','Houston'],['Miami','Miami'],['Toronto','Toronto'],['Montreal','Montreal'],['Vancouver','Vancouver'],['Mexico City','Mexico City'],['Sao Paulo','Sao Paulo'],['Rio de Janeiro','Rio de Janeiro'],['Buenos Aires','Buenos Aires'],['Bogota','Bogota'],['Lima','Lima'],['Santiago','Santiago']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
              <optgroup label="🌏 Oceania">
                ${[['Sydney','Sydney'],['Melbourne','Melbourne'],['Brisbane','Brisbane'],['Perth','Perth'],['Auckland','Auckland']].map(([l,v])=>`<option value="${v}" ${(s.weather_city||'')=== v?'selected':''}>${l}</option>`).join('')}
              </optgroup>
            </select>
          </div>
        </div>
      </div>

      <div class="sec-title" style="margin:14px 0 12px;font-size:13px;color:var(--text2)">📡 Cast QR</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg" style="display:flex;align-items:center;justify-content:space-between;gap:10px">
            <label style="margin:0">Show Cast QR on TV</label>
            <label class="big-toggle">
              <input type="checkbox" id="s-cast-qr-enabled" ${s.cast_qr_enabled==='1'?'checked':''}>
              <span class="big-toggle-track"></span>
            </label>
          </div>
          <div class="fg fcol"><label>Cast Server URL</label>
            <input id="s-cast-server-url" value="${esc(s.cast_server_url||'')}" placeholder="https://cast.yourdomain.com">
          </div>
          <div class="fg"><label>Show On</label>
            <select id="s-cast-qr-display" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              <option value="both"        ${(s.cast_qr_display||'both')==='both'       ?'selected':''}>Home + Screensaver</option>
              <option value="home"        ${s.cast_qr_display==='home'       ?'selected':''}>Home Screen Only</option>
              <option value="screensaver" ${s.cast_qr_display==='screensaver'?'selected':''}>Screensaver Only</option>
            </select>
          </div>
          <div class="fg"><label>Position (Home Screen)</label>
            <select id="s-cast-qr-position" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              <option value="bottom-right" ${(s.cast_qr_position||'bottom-right')==='bottom-right'?'selected':''}>↘ Bottom Right</option>
              <option value="bottom-left"  ${s.cast_qr_position==='bottom-left' ?'selected':''}>↙ Bottom Left</option>
              <option value="top-right"    ${s.cast_qr_position==='top-right'   ?'selected':''}>↗ Top Right</option>
              <option value="top-left"     ${s.cast_qr_position==='top-left'    ?'selected':''}>↖ Top Left</option>
            </select>
          </div>
        </div>
      </div>
    </div>
    <div>
      <div class="sec-title" style="margin:14px 0 12px;font-size:13px;color:var(--text2)">📺 Chromecast Web Sender</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg fcol"><label>Receiver App ID</label>
            <input id="s-cast-app-id" value="${esc(s.cast_app_id||'')}" placeholder="CC1AD845 (Default Media Receiver)" style="font-family:'DM Mono',monospace;letter-spacing:.05em">
          </div>
        </div>
      </div>
    </div>
    <div>
      <div class="sec-title" style="margin-bottom:12px;font-size:13px;color:var(--text2)">🖥 TV / Screensaver</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg"><label>Screensaver Delay (seconds)</label>
            <select id="s-ss-delay" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              ${[[600,'10 min'],[1800,'30 min'],[3600,'60 min'],[0,'Never']].map(([v,l])=>`<option value="${v}" ${s.screensaver_delay==v?'selected':''}>${l}</option>`).join('')}
            </select>
          </div>
          <div class="fg"><label>Screensaver Type</label>
            <select id="s-ss-type" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              <option value="clock" ${s.screensaver_type==='clock'?'selected':''}>🕐 Clock & Date</option>
              <option value="logo"  ${s.screensaver_type==='logo'?'selected':''}>🖼 Brand Logo</option>
              <option value="off"   ${s.screensaver_type==='off'?'selected':''}>Off</option>
            </select>
          </div>
        </div>
      </div>

      <div class="sec-title" style="margin:14px 0 12px;font-size:13px;color:var(--text2)">📞 Contact</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fg"><label>${_isHotel?'Support / Front Desk Phone':'Support / Contact Phone'}</label><input id="s-support-phone" value="${esc(s.support_phone||'')}"></div>
      </div>

      <div class="sec-title" style="margin:14px 0 12px;font-size:13px;color:var(--text2)">🪪 CMS Branding</div>
      <div class="tbl-wrap" style="padding:18px">
        <div class="fgrid" style="gap:12px">
          <div class="fg"><label>Sidebar Brand Text</label><input id="s-admin-brand" value="${esc(s.admin_brand_name||'NEXVISION')}" placeholder="NEXVISION"></div>
          <div class="fg"><label>Sidebar Label</label><input id="s-admin-mode-label" value="${esc(s.admin_mode_label||(_isHotel?'Hotel CMS':'Admin'))}" placeholder="Hotel CMS"></div>
          <div class="fg fcol"><label>Browser Title</label><input id="s-admin-title" value="${esc(s.admin_title||'NexVision CMS v5')}" placeholder="NexVision CMS v5"></div>
          <div class="fg fcol"><label>Sidebar Logo URL (optional)</label><div style="display:flex;gap:8px;align-items:stretch"><input id="s-admin-logo" value="${esc(s.admin_logo_url||'')}" placeholder="https://.../logo.png" style="flex:1"><label style="display:flex;align-items:center;gap:5px;padding:8px 14px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:8px;cursor:pointer;font-size:12px;white-space:nowrap;flex-shrink:0">&#128193; Upload<input type="file" accept="image/*" style="display:none" onchange="uploadAdminLogoFile(event)"></label></div></div>
        </div>
      </div>

      <div class="sec-title" style="margin:14px 0 12px;font-size:13px;color:var(--text2)">⚙ Quick Actions</div>
      <div class="tbl-wrap" style="padding:18px">
        <div style="display:flex;flex-direction:column;gap:8px">
          <button class="btn btn-d" onclick="clearOldEpg()">🗑 Clear Old EPG Entries</button>
          <button class="btn btn-g" onclick="go('reports')">📊 View Reports</button>
          <button class="btn btn-g" onclick="go('rooms')">${_isHotel?'🏨 View Room Status':'🖥 View Screen Status'}</button>
        </div>
      </div>
    </div>
  </div>`;
};

async function saveSettings() {
  const d = {
    hotel_name:       window._settings?.hotel_name || '',
    hotel_logo:       window._settings?.hotel_logo || '',
    checkout_time:    document.getElementById('s-checkout')?.value||'12:00',
    currency:         document.getElementById('s-currency')?.value||'USD',
    language:         document.getElementById('s-lang')?.value||'en',
    wifi_name:        document.getElementById('s-wifi-name')?.value||'',
    wifi_password:    document.getElementById('s-wifi-pass')?.value||'',
    screensaver_delay:document.getElementById('s-ss-delay')?.value||'600',
    screensaver_type: document.getElementById('s-ss-type')?.value||'clock',
    support_phone:    document.getElementById('s-support-phone')?.value||'',
    deployment_mode:  window._deployMode || 'hotel',
    admin_brand_name: document.getElementById('s-admin-brand')?.value||'NEXVISION',
    admin_mode_label: document.getElementById('s-admin-mode-label')?.value||'',
    admin_title:      document.getElementById('s-admin-title')?.value||'NexVision CMS v5',
    admin_logo_url:   document.getElementById('s-admin-logo')?.value||'',
    weather_city:     document.getElementById('s-weather-city')?.value||'',
    cast_qr_enabled:       document.getElementById('s-cast-qr-enabled')?.checked  ? '1' : '0',
    cast_server_url:       document.getElementById('s-cast-server-url')?.value||'',
    cast_app_id:           document.getElementById('s-cast-app-id')?.value||'',
    cast_qr_display:       document.getElementById('s-cast-qr-display')?.value||'both',
    cast_qr_position:      document.getElementById('s-cast-qr-position')?.value||'bottom-right',
    pms_enabled:           document.getElementById('s-pms-enabled')?.checked       ? '1' : '0',
    pms_type:              document.getElementById('s-pms-type')?.value            || 'fias',
    pms_host:              document.getElementById('s-pms-host')?.value            || '',
    pms_port:              document.getElementById('s-pms-port')?.value            || '5010',
    pms_username:          document.getElementById('s-pms-user')?.value            || '',
    pms_password:          document.getElementById('s-pms-pass')?.value            || '',
    welcome_music_enabled: document.getElementById('s-welcome-music-enabled')?.checked ? '1' : '0',
    welcome_music_url:     document.getElementById('s-welcome-music-url')?.value   || '',
  };
  const r = await req('/settings', {method:'POST', body:JSON.stringify(d)});
  if (r?.ok) {
    window._settings = {...(window._settings||{}), ...d};
    applyDeploymentMode(d.deployment_mode || 'hotel');
    applyAdminBranding(window._settings);
    toast('✅ Settings saved');
  }
}

function setDeployMode(mode) {
  window._deployMode = mode;
  const isHotel = mode !== 'commercial';
  // Mode buttons
  const bh = document.getElementById('mode-btn-hotel');
  const bc = document.getElementById('mode-btn-commercial');
  if (bh) { bh.style.background = isHotel ? 'var(--gold)' : 'transparent'; bh.style.color = isHotel ? '#000' : 'var(--text2)'; }
  if (bc) { bc.style.background = !isHotel ? 'var(--gold)' : 'transparent'; bc.style.color = !isHotel ? '#000' : 'var(--text2)'; }
  // Description
  const desc = document.getElementById('mode-desc');
  if (desc) desc.innerHTML = isHotel
    ? '🏨 <b>Hotel Mode</b> — Room registration by room number, check-in/out tracking, guest services, prayer times, room-based billing, birthday manager.'
    : '🏢 <b>Commercial Mode</b> — Screen/display registration by location ID, digital signage focus, public venue management. Hotel-specific guest features are hidden.';
  // Show/hide hotel-only fields
  document.querySelectorAll('.hotel-only').forEach(el => el.style.display = isHotel ? '' : 'none');
  // Apply globally (sidebar label etc.)
  applyDeploymentMode(mode);
}

function togglePmsFields() {
  const on = document.getElementById('s-pms-enabled')?.checked;
  ['pms-type-row','pms-host-row','pms-port-row','pms-user-row','pms-pass-row','pms-welcome-row']
    .forEach(id => { const el = document.getElementById(id); if (el) el.style.display = on ? '' : 'none'; });
  if (!on) { const mu = document.getElementById('welcome-music-url-row'); if (mu) mu.style.display = 'none'; }
}

function toggleWelcomeMusicUrl() {
  const on = document.getElementById('s-welcome-music-enabled')?.checked;
  const el = document.getElementById('welcome-music-url-row');
  if (el) el.style.display = on ? '' : 'none';
}


// ═══════════════════════════════════════════════════════════════════════════════
// V8 — PRAYER TIMES PAGE
// ═══════════════════════════════════════════════════════════════════════════════
pages.prayer = async function() {
  const s = await req('/settings');
  if (!s) return;
  window._settings = s;

  // Try to fetch current prayer times to show preview
  let prayerPreview = '';
  if (s.prayer_enabled === '1') {
    const p = await req('/prayer');
    if (p && p.enabled && p.timings) {
      const rows = ['Fajr','Sunrise','Dhuhr','Asr','Maghrib','Isha']
        .map(n => p.timings[n] ? `<tr><td><b>${n}</b></td><td style="font-family:'DM Mono',monospace;color:var(--gold)">${p.timings[n].split(' ')[0]}</td><td style="font-size:12px;color:var(--text2);text-align:right">${({Fajr:'الفجر',Sunrise:'الشروق',Dhuhr:'الظهر',Asr:'العصر',Maghrib:'المغرب',Isha:'العشاء'})[n]||''}</td></tr>` : '')
        .join('');
      prayerPreview = `
      <div class="tbl-wrap" style="padding:0">
        <div style="padding:14px 16px;border-bottom:1px solid var(--border);font-size:12px;color:var(--text2)">
          Today — <b style="color:var(--text)">${esc(p.city||'')} • ${esc(p.date||'')}</b>
          ${p.hijri ? '<span style="color:var(--gold);margin-left:8px">'+esc(p.hijri)+' '+esc(p.hijri_month||'')+'</span>' : ''}
          ${p.offline ? '<span style="color:var(--red);margin-left:8px;font-size:10px">⚠ Offline — approx.</span>' : ''}
        </div>
        <table style="margin:0"><thead><tr><th>Prayer</th><th>Time</th><th style="text-align:right">Arabic</th></tr></thead>
        <tbody>${rows}</tbody></table>
      </div>`;
    }
  }

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr"><div class="sec-title">Prayer Times</div>
    <button class="btn btn-p" onclick="savePrayerSettings()">💾 Save Settings</button>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
    <div>
      <div class="tbl-wrap" style="padding:20px">
        <div class="fgrid" style="gap:14px">
          <div class="fg fcol">
            <label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:12px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px">
              <input type="checkbox" id="prayer-enabled" ${s.prayer_enabled==='1'?'checked':''} style="width:16px;height:16px;accent-color:var(--gold)">
              <div>
                <div style="font-size:14px;color:var(--text);font-weight:500">Enable Prayer Times</div>
                <div style="font-size:11px;color:var(--text2);margin-top:2px">Shows prayer schedule on TV screens with countdown and Adhan notifications</div>
              </div>
            </label>
          </div>
          <div class="fg"><label>City</label>
            <select id="prayer-city" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              ${[['Dubai','Dubai'],['Abu Dhabi','AbuDhabi'],['Sharjah','Sharjah'],['Ajman','Ajman'],['RAK','RasAlKhaimah'],['Fujairah','Fujairah'],['UAQ','UmmAlQuwain'],['Riyadh','Riyadh'],['Jeddah','Jeddah'],['Mecca','Mecca'],['Medina','Medina'],['Kuwait City','KuwaitCity'],['Doha','Doha'],['Manama','Manama'],['Muscat','Muscat'],['Cairo','Cairo'],['Amman','Amman'],['Beirut','Beirut'],['Istanbul','Istanbul'],['London','London'],['Paris','Paris'],['New York','NewYork']]
              .map(([label,val])=>`<option value="${val}" ${(s.prayer_city||'Dubai')===val?'selected':''}>${label}</option>`).join('')}
            </select>
          </div>
          <div class="fg"><label>Country</label>
            <select id="prayer-country" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              ${[['UAE','AE'],['Saudi Arabia','SA'],['Kuwait','KW'],['Qatar','QA'],['Bahrain','BH'],['Oman','OM'],['Egypt','EG'],['Jordan','JO'],['Lebanon','LB'],['Turkey','TR'],['UK','GB'],['France','FR'],['USA','US']]
              .map(([label,val])=>`<option value="${val}" ${(s.prayer_country||'AE')===val?'selected':''}>${label}</option>`).join('')}
            </select>
          </div>
          <div class="fg"><label>Calculation Method</label>
            <select id="prayer-method" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
              <option value="4"  ${(s.prayer_method||'4')==='4'?'selected':''}>Umm Al-Qura University (UAE / Saudi Arabia)</option>
              <option value="2"  ${s.prayer_method==='2'?'selected':''}>Islamic Society of North America (ISNA)</option>
              <option value="1"  ${s.prayer_method==='1'?'selected':''}>University of Islamic Sciences, Karachi</option>
              <option value="3"  ${s.prayer_method==='3'?'selected':''}>Muslim World League (MWL)</option>
              <option value="5"  ${s.prayer_method==='5'?'selected':''}>Egyptian General Authority of Survey</option>
              <option value="8"  ${s.prayer_method==='8'?'selected':''}>Gulf Region</option>
              <option value="15" ${s.prayer_method==='15'?'selected':''}>Diyanet İşleri Başkanlığı (Turkey)</option>
            </select>
          </div>
          <div class="fg fcol">
            <label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:10px 12px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px">
              <input type="checkbox" id="prayer-notify" ${(s.prayer_notify||'1')==='1'?'checked':''} style="width:14px;height:14px;accent-color:var(--gold)">
              <div>
                <div style="font-size:13px;color:var(--text)">Show Adhan Notification</div>
                <div style="font-size:11px;color:var(--text2);margin-top:1px">Display notification banner at prayer time</div>
              </div>
            </label>
          </div>
        </div>
      </div>
      <div class="ibox info" style="margin-top:12px">
        Prayer times are fetched from <b>aladhan.com</b> API and cached daily.
        After saving, the TV screen will auto-refresh prayer data.
        <br><b>UAE default:</b> Umm Al-Qura University method (Method 4).
      </div>
    </div>
    <div>
      <div class="sec-title" style="margin-bottom:12px;font-size:13px;color:var(--text2)">Today's Prayer Times Preview</div>
      ${prayerPreview || '<div class="ibox">Enable prayer times and save to see today\'s schedule here.</div>'}
    </div>
  </div>`;
};

async function savePrayerSettings() {
  const d = {
    prayer_enabled: document.getElementById('prayer-enabled').checked ? '1' : '0',
    prayer_city:    document.getElementById('prayer-city').value,
    prayer_country: document.getElementById('prayer-country').value,
    prayer_method:  document.getElementById('prayer-method').value,
    prayer_notify:  document.getElementById('prayer-notify').checked ? '1' : '0',
  };
  const r = await req('/prayer/settings', {method:'POST', body:JSON.stringify(d)});
  if (r?.ok) {
    toast('✅ Prayer settings saved');
    await pages.prayer(); // refresh to show updated times
  }
}





// ═══════════════════════════════════════════════════════════════════════════════
// V8 — NAVIGATION MANAGER PAGE
// ═══════════════════════════════════════════════════════════════════════════════

pages.navigation = async function() {
  const data = await req('/nav/items');
  if (!data) return;
  window._navItems  = data.items  || [];
  window._navPos    = data.position || 'top';
  window._navStyle  = data.style   || 'pill';
  renderNavPage();
};

function renderNavPage() {
  const items = window._navItems || [];
  const pos   = window._navPos   || 'top';
  const style = window._navStyle || 'pill';

  // Live mini preview
  function previewTop(sts) {
    return sts.map(it => `<span style="padding:4px 10px;border-radius:5px;font-size:10px;background:${it.enabled?'rgba(212,168,67,0.15)':'rgba(255,255,255,0.04)'};color:${it.enabled?'var(--gold)':'var(--text3)'};border:1px solid ${it.enabled?'rgba(212,168,67,0.3)':'var(--border)'}">${it.icon} ${it.label}</span>`).join('');
  }
  function previewBottom(sts) {
    return sts.filter(it=>it.enabled).slice(0,6).map(it =>
      `<div style="display:flex;flex-direction:column;align-items:center;gap:2px;padding:0 10px"><span style="font-size:16px">${it.icon}</span><span style="font-size:8px;color:var(--text2)">${it.label}</span></div>`
    ).join('');
  }

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">Navigation Menu</div>
    <div class="sec-acts">
      <button class="btn btn-p" onclick="addNavItem()">+ Add Custom Item</button>
      <button class="btn btn-gr" onclick="saveNavOrder()">💾 Save Order</button>
    </div>
  </div>


  <div class="sec-title" style="font-size:12px;color:var(--text2);margin-bottom:10px">📍 Menu Position</div>
  <div class="nav-pos-row">
    <div class="pos-opt ${pos==='top'?'on':''}" onclick="setNavPos('top')">
      <div class="po-icon">⬆</div>
      <div class="po-label">Top Bar</div>
      <div class="po-desc">Horizontal menu inside the header</div>
      <div style="margin-top:10px;padding:8px;background:var(--bg4);border-radius:6px;display:flex;flex-direction:column;gap:4px">
        <div style="height:4px;background:var(--border);border-radius:2px;margin-bottom:4px"></div>
        <div style="display:flex;gap:4px;flex-wrap:wrap">${previewTop(items.slice(0,5))}</div>
        <div style="flex:1;min-height:40px;background:var(--bg);border-radius:4px;margin-top:4px"></div>
      </div>
    </div>
    <div class="pos-opt ${pos==='bottom'?'on':''}" onclick="setNavPos('bottom')">
      <div class="po-icon">⬇</div>
      <div class="po-label">Bottom Bar</div>
      <div class="po-desc">Icon + label tab bar at screen bottom</div>
      <div style="margin-top:10px;padding:8px;background:var(--bg4);border-radius:6px;display:flex;flex-direction:column;gap:4px">
        <div style="flex:1;min-height:40px;background:var(--bg);border-radius:4px;margin-bottom:4px"></div>
        <div style="display:flex;justify-content:space-around;padding:6px;background:var(--bg3);border-radius:6px;border-top:1px solid var(--border)">${previewBottom(items)}</div>
      </div>
    </div>
  </div>


  <div class="sec-title" style="font-size:12px;color:var(--text2);margin-bottom:10px;margin-top:4px">🎨 Button Style</div>
  <div class="style-row">
    ${[
      {k:'pill',  lbl:'Pill',       prev:'[ Home ]  [ TV ]'},
      {k:'flat',  lbl:'Flat',       prev:'Home   TV   Radio'},
      {k:'boxed', lbl:'Boxed',      prev:'┌Home┐ ┌TV┐'},
      {k:'icon',  lbl:'Icon+Label', prev:'🏠 Home  📺 TV'},
    ].map(s=>`<div class="style-opt ${style===s.k?'on':''}" onclick="setNavStyle('${s.k}')">
      <div class="so-preview">${s.prev}</div>
      <div class="so-label">${s.lbl}</div>
    </div>`).join('')}
  </div>


  <div class="sec-title" style="font-size:12px;color:var(--text2);margin-bottom:10px;margin-top:4px">☰ Menu Items — drag to reorder</div>
  <div class="ni-list" id="nav-item-list">
    ${items.map((it,i) => `
    <div class="ni-row ${it.enabled?'':'disabled'}" data-id="${it.id}" data-idx="${i}"
         draggable="true"
         ondragstart="navDragStart(event,${i})"
         ondragover="navDragOver(event)"
         ondrop="navDrop(event,${i})"
         ondragend="navDragEnd(event)">
      <span class="ni-drag">⠿</span>
      <span class="ni-icon">${it.icon||'📄'}</span>
      <span class="ni-label">${esc(it.label)}</span>
      <span class="ni-key">${esc(it.key)}</span>
      ${it.is_system ? '<span class="ni-sys">system</span>' : '<span class="ni-sys" style="color:var(--blue)">custom</span>'}
      <label class="ni-toggle" title="${it.enabled?'Click to disable':'Click to enable'}">
        <input type="checkbox" ${it.enabled?'checked':''} onchange="toggleNavItem(${it.id},this)">
        <span class="ni-toggle-track"></span>
      </label>
      <button class="btn btn-g btn-xs" onclick="editNavItem(${it.id})">Edit</button>
      ${!it.is_system ? `<button class="btn btn-d btn-xs" onclick="deleteNavItem(${it.id})">Del</button>` : ''}
    </div>`).join('')}
  </div>`;

  // Drag state
  window._navDragSrc = null;
}

// ── Position & style ─────────────────────────────────────────────────────────
async function setNavPos(pos) {
  window._navPos = pos;
  const r = await req('/nav/position', {method:'POST', body:JSON.stringify({position:pos, style:window._navStyle})});
  if (r?.ok) { toast('✅ Position saved — ' + pos); renderNavPage(); }
}
async function setNavStyle(style) {
  window._navStyle = style;
  const r = await req('/nav/position', {method:'POST', body:JSON.stringify({position:window._navPos, style})});
  if (r?.ok) { toast('✅ Style saved — ' + style); renderNavPage(); }
}

// ── Save order ────────────────────────────────────────────────────────────────
async function saveNavOrder() {
  const rows = document.querySelectorAll('#nav-item-list .ni-row');
  const ids = [...rows].map(r => parseInt(r.dataset.id));
  const res = await req('/nav/reorder', {method:'POST', body:JSON.stringify({ids})});
  if (res?.ok) {
    toast('✅ Order saved');
    // Update local copy
    const items = window._navItems || [];
    rows.forEach((r, i) => {
      const item = items.find(it => it.id === parseInt(r.dataset.id));
      if (item) item.sort_order = i;
    });
  }
}

// ── Toggle enable ─────────────────────────────────────────────────────────────
async function toggleNavItem(id, checkbox) {
  const r = await req('/nav/items/' + id + '/toggle', {method:'POST'});
  if (r) {
    const item = (window._navItems||[]).find(it=>it.id===id);
    if (item) item.enabled = r.enabled;
    const row = checkbox.closest('.ni-row');
    if (row) row.classList.toggle('disabled', !r.enabled);
    toast(r.enabled ? '✅ ' + r.label + ' enabled' : '⊘ ' + r.label + ' disabled');
  } else {
    checkbox.checked = !checkbox.checked; // revert
  }
}

// ── Drag & drop ───────────────────────────────────────────────────────────────
function navDragStart(e, idx) {
  window._navDragSrc = idx;
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', idx);
}
function navDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  document.querySelectorAll('.ni-row').forEach(r => r.classList.remove('drag-over'));
  e.currentTarget.classList.add('drag-over');
}
function navDrop(e, targetIdx) {
  e.preventDefault();
  const srcIdx = window._navDragSrc;
  if (srcIdx === null || srcIdx === targetIdx) return;
  const list = document.getElementById('nav-item-list');
  const rows = [...list.querySelectorAll('.ni-row')];
  const src  = rows[srcIdx];
  const tgt  = rows[targetIdx];
  if (srcIdx < targetIdx) list.insertBefore(src, tgt.nextSibling);
  else                    list.insertBefore(src, tgt);
  window._navDragSrc = null;
  document.querySelectorAll('.ni-row').forEach(r => r.classList.remove('drag-over','dragging'));
  toast('↕ Drag to reorder, then click Save Order');
}
function navDragEnd(e) {
  e.currentTarget.classList.remove('dragging');
  document.querySelectorAll('.ni-row').forEach(r => r.classList.remove('drag-over'));
}

// ── Add custom item ───────────────────────────────────────────────────────────
function addNavItem() {
  const ICONS = ['📄','🎯','🌐','📱','🏷','📍','⭐','🔔','📰','🎪','🎭','🎨','📸','🎵','🎮','💡','🔍','📞','🛒','❓'];
  openModal('Add Custom Menu Item', `
  <div class="ibox info">
    Custom items can link to any URL (opens in browser) or to a built-in screen key like
    <code style="background:var(--bg4);padding:1px 6px;border-radius:4px;font-family:'DM Mono',monospace">home, tv, vod, radio, weather, info, services, prayers</code>
  </div>
  <div class="fgrid">
    <div class="fg fcol"><label>Menu Label *</label><input id="ni-label" placeholder="e.g. Spa, News, Deals..."></div>
    <div class="fg"><label>Icon (emoji)</label>
      <input id="ni-icon" value="📄" style="font-size:20px;text-align:center;width:80px">
      <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:6px">
        ${ICONS.map(ic=>`<button type="button" style="font-size:18px;background:var(--bg3);border:1px solid var(--border2);border-radius:5px;padding:3px 7px;cursor:pointer" onclick="document.getElementById('ni-icon').value='${ic}'">${ic}</button>`).join('')}
      </div>
    </div>
    <div class="fg fcol">
      <label>Screen Key or URL</label>
      <input id="ni-url" placeholder="e.g. 'prayers'  or  https://hotel.com/deals">
      <div style="font-size:11px;color:var(--text2);margin-top:4px">If this is a screen key, leave as-is. For external links, start with https://</div>
    </div>
    <div class="fg"><label>Enabled?</label>
      <select id="ni-enabled" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1">Yes — show in menu</option>
        <option value="0">No — hidden</option>
      </select>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="saveNewNavItem()">Add to Menu</button>`);
}

async function saveNewNavItem() {
  const label  = document.getElementById('ni-label').value.trim();
  const icon   = document.getElementById('ni-icon').value.trim() || '📄';
  const url    = document.getElementById('ni-url').value.trim();
  const enabled = parseInt(document.getElementById('ni-enabled').value);
  if (!label) { alert('Label is required'); return; }
  const key = url && !url.startsWith('http') ? url : label.toLowerCase().replace(/[^a-z0-9]/g,'_');
  const r = await req('/nav/items', {method:'POST', body:JSON.stringify({label, icon, target_url:url, enabled, key})});
  if (r?.error) { alert(r.error); return; }
  closeModal();
  toast('✅ ' + label + ' added to menu');
  await pages.navigation();
}

// ── Edit item ─────────────────────────────────────────────────────────────────
function editNavItem(id) {
  const it = (window._navItems||[]).find(x=>x.id===id);
  if (!it) return;
  openModal('Edit Menu Item — ' + it.label, `
  <div class="fgrid">
    <div class="fg fcol"><label>Label *</label><input id="ei-label" value="${esc(it.label)}"></div>
    <div class="fg"><label>Icon (emoji)</label><input id="ei-icon" value="${esc(it.icon||'📄')}" style="font-size:20px;text-align:center;width:80px"></div>
    ${!it.is_system ? `<div class="fg fcol"><label>Screen Key or URL</label><input id="ei-url" value="${esc(it.target_url||'')}"></div>` : ''}
    <div class="fg"><label>Enabled</label>
      <select id="ei-enabled" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1" ${it.enabled?'selected':''}>Yes</option>
        <option value="0" ${!it.enabled?'selected':''}>No</option>
      </select>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="saveEditNavItem(${id},${it.is_system})">Save</button>`);
}

async function saveEditNavItem(id, isSystem) {
  const d = {
    label:   document.getElementById('ei-label').value.trim(),
    icon:    document.getElementById('ei-icon').value.trim() || '📄',
    enabled: parseInt(document.getElementById('ei-enabled').value),
    target_url: !isSystem && document.getElementById('ei-url') ? document.getElementById('ei-url').value.trim() : '',
  };
  if (!d.label) return;
  const r = await req('/nav/items/' + id, {method:'PUT', body:JSON.stringify(d)});
  if (r?.error) { alert(r.error); return; }
  closeModal();
  toast('✅ Updated');
  await pages.navigation();
}

async function deleteNavItem(id) {
  if (!confirm('Delete this custom menu item?')) return;
  const r = await req('/nav/items/' + id, {method:'DELETE'});
  if (r?.error) { alert(r.error); return; }
  toast('🗑 Deleted');
  await pages.navigation();
}



// ═══════════════════════════════════════════════════════════════════════════════
// V8 — PROMO SLIDES PAGE
// ═══════════════════════════════════════════════════════════════════════════════

pages.slides = async function() {
  const [slides, settings] = await Promise.all([req('/slides/all'), req('/settings')]);
  if (!slides) return;
  window._slides = slides;
  const showFeatured = settings?.home_show_featured !== '0';
  const showSlides   = settings?.home_show_slides   !== '0';
  const slidesStyle  = settings?.home_slides_style  || 'full';

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">Promo Slides &amp; Marketing</div>
    <button class="btn btn-p" onclick="eSlide(null)">+ Add Slide</button>
  </div>


  <div class="tbl-wrap" style="padding:18px;margin-bottom:18px">
    <div class="sec-title" style="margin-bottom:14px;font-size:13px;color:var(--text2)">🏠 Home Screen Sections</div>
    <div class="home-setting-row">
      <div>
        <div class="home-setting-label">🖼 Promo / Marketing Slideshow</div>
        <div class="home-setting-sub">Show rotating image slides at the top of the Home screen</div>
      </div>
      <label class="big-toggle">
        <input type="checkbox" id="toggle-slides" ${showSlides?'checked':''} onchange="saveHomeSetting('home_show_slides',this.checked?'1':'0')">
        <span class="big-toggle-track"></span>
      </label>
    </div>
  </div>


  <div class="sec-title" style="font-size:12px;color:var(--text2);margin-bottom:10px">
    ${slides.length} slide${slides.length!==1?'s':''} — drag to reorder
  </div>

  ${slides.length === 0 ?
    '<div class="ibox">No slides yet. Add a slide with an image URL to start showing marketing content on the Home screen.</div>' :
    `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px">
      ${slides.map(s=>`
      <div class="card" style="${!s.active?'opacity:.5':''}">
        <div class="slide-preview" style="background-image:url('${esc(s.image_url)}')">
          <div class="slide-preview-overlay"></div>
          <div class="slide-preview-text">
            ${s.title?`<b>${esc(s.title)}</b><br>`:''}
            ${s.subtitle?`<span style="opacity:.8">${esc(s.subtitle)}</span>`:''}
          </div>
        </div>
        <div style="margin-top:10px;display:flex;align-items:center;justify-content:space-between">
          <div>
            <span class="bdg ${s.active?'bg':'br'}">${s.active?'Active':'Hidden'}</span>
            <span class="bdg bb" style="margin-left:4px">${s.duration_seconds}s</span>
            ${s.link_action?`<span class="bdg bp" style="margin-left:4px">🔗 Link</span>`:''}
          </div>
          <div class="tda">
            <button class="btn btn-g btn-xs" onclick="eSlide(${s.id})">Edit</button>
            <button class="btn btn-d btn-xs" onclick="dSlide(${s.id})">Del</button>
          </div>
        </div>
      </div>`).join('')}
    </div>`
  }`;
};

async function saveHomeSetting(key, val) {
  const r = await req('/settings', {method:'POST', body:JSON.stringify({[key]: val})});
  if (r?.ok) toast('✅ Setting saved');
}

function eSlide(id) {
  const s = id ? (window._slides||[]).find(x=>x.id===id) : null;
  openModal(s?'Edit Slide':'Add Slide', `
  <div class="fgrid">
    <div class="fg fcol">
      <label>Media Type</label>
      <div style="display:flex;gap:8px">
        <label style="display:flex;align-items:center;gap:6px;padding:7px 14px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;flex:1" id="sl-type-img-lbl">
          <input type="radio" name="sl-type" id="sl-type-img" value="image" ${!s||s.media_type!=='video'?'checked':''} onchange="toggleSlideType()" style="accent-color:var(--gold)">
          🖼 Image / Photo
        </label>
        <label style="display:flex;align-items:center;gap:6px;padding:7px 14px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;flex:1" id="sl-type-vid-lbl">
          <input type="radio" name="sl-type" id="sl-type-vid" value="video" ${s?.media_type==='video'?'checked':''} onchange="toggleSlideType()" style="accent-color:var(--gold)">
          🎥 Video
        </label>
      </div>
    </div>

    <div class="fg fcol" id="sl-img-section">
      <label>Image (URL or upload from device)</label>
      <div style="display:flex;gap:8px;align-items:stretch">
        <input id="sl-img" value="${esc(s?.image_url||'')}" placeholder="https://... or upload below" oninput="prevSlideImg(this.value)" style="flex:1">
        <label style="display:flex;align-items:center;gap:5px;padding:8px 14px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:8px;cursor:pointer;font-size:12px;white-space:nowrap">
          📁 Upload
          <input type="file" accept="image/*" style="display:none" onchange="uploadMediaFile(event,'sl-img','sl-img-prev','image')">
        </label>
      </div>
      <div id="sl-img-prev" style="${s?.image_url?'':'display:none'};margin-top:8px;width:100%;height:120px;background-size:cover;background-position:center;border-radius:8px;border:1px solid var(--border2);background-image:url('${esc(s?.image_url||'')}')"></div>
    </div>

    <div class="fg fcol" id="sl-vid-section" style="${s?.media_type==='video'?'':'display:none'}">
      <label>Video (URL or upload from device — mp4, webm)</label>
      <div style="display:flex;gap:8px;align-items:stretch">
        <input id="sl-vid" value="${esc(s?.video_url||'')}" placeholder="https://... or upload below" style="flex:1">
        <label style="display:flex;align-items:center;gap:5px;padding:8px 14px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:8px;cursor:pointer;font-size:12px;white-space:nowrap">
          📁 Upload
          <input type="file" accept="video/*" style="display:none" onchange="uploadMediaFile(event,'sl-vid',null,'video')">
        </label>
      </div>
      <div style="font-size:11px;color:var(--text2);margin-top:4px">Video plays muted & looped in the background. Max recommended: 30MB.</div>
    </div>
    <div class="fg"><label>Title overlay (optional)</label><input id="sl-title" value="${esc(s?.title||'')}" placeholder="Summer Promotion"></div>
    <div class="fg"><label>Subtitle (optional)</label><input id="sl-sub" value="${esc(s?.subtitle||'')}" placeholder="20% off all services this weekend"></div>
    <div class="fg">
      <label>On-click Action</label>
      <input id="sl-action" value="${esc(s?.link_action||'')}" placeholder="services  or  https://hotel.com/deals">
      <div style="font-size:11px;color:var(--text2);margin-top:3px">Screen key (e.g. services, vod) or full URL</div>
    </div>
    <div class="fg"><label>Duration (seconds, for images)</label>
      <input id="sl-dur" type="number" min="2" max="30" value="${s?.duration_seconds||5}"></div>
    <div class="fg"><label>Status</label>
      <select id="sl-active" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1" ${!s||s.active?'selected':''}>Active — show on TV</option>
        <option value="0" ${s&&!s.active?'selected':''}>Hidden</option>
      </select>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svSlide(${id||'null'})">Save Slide</button>`);
}

function prevSlideImg(url) {
  const el = document.getElementById('sl-img-prev');
  if (!el) return;
  el.style.backgroundImage = `url('${url}')`;
  el.style.display = url ? 'block' : 'none';
}

async function svSlide(id) {
  const mediaType = document.querySelector('input[name="sl-type"]:checked')?.value || 'image';
  const d = {
    media_type: mediaType,
    image_url:        document.getElementById('sl-img').value.trim(),
    title:            document.getElementById('sl-title').value.trim(),
    subtitle:         document.getElementById('sl-sub').value.trim(),
    video_url:        document.getElementById('sl-vid')?.value.trim() || '',
    link_action:      document.getElementById('sl-action').value.trim(),
    duration_seconds: parseInt(document.getElementById('sl-dur').value)||5,
    active:           parseInt(document.getElementById('sl-active').value),
  };
  if (mediaType === 'image' && !d.image_url) { alert('Image URL or upload required'); return; }
  if (mediaType === 'video' && !d.video_url) { alert('Video URL or upload required'); return; }
  const r = id
    ? await req('/slides/'+id, {method:'PUT', body:JSON.stringify(d)})
    : await req('/slides',     {method:'POST',body:JSON.stringify(d)});
  if (r?.error) { alert(r.error); return; }
  closeModal();
  toast(id ? '✅ Slide updated' : '✅ Slide added');
  await pages.slides();
}

async function dSlide(id) {
  if (!confirm('Delete this slide?')) return;
  await req('/slides/'+id, {method:'DELETE'});
  toast('🗑 Slide deleted');
  await pages.slides();
}

// ═══════════════════════════════════════════════════════════════════════════════
// V8 — M3U IMPORT FIX (add paste/upload option with clear instructions)
// ═══════════════════════════════════════════════════════════════════════════════
// Override openM3UImport with clearer UI
const _origOpenM3UImport = openM3UImport;
function openM3UImport() {
  openModal('M3U Channel Import', `
  <div class="ibox info">
    <b>Three ways to import:</b><br>
    1. <b>Server file</b> — leave URL blank to use the M3U file already available on the server<br>
    2. <b>Remote URL</b> — paste any public M3U URL (http/https)<br>
    3. <b>Paste M3U text</b> — copy M3U content and paste below
  </div>
  <div class="fgrid">
    <div class="fg fcol"><label>M3U URL (leave blank to use server file)</label>
      <input id="m3u-url" placeholder="http://provider.com/playlist.m3u8"></div>
    <div class="fg"><label>Filter Groups (comma-separated, blank = import all)</label>
      <input id="m3u-grp" placeholder="News, Sports, Entertainment"></div>
    <div class="fg"><label>Max channels to import (0 = unlimited)</label>
      <input id="m3u-max" type="number" value="0"></div>
    <div class="fg"><label>Channel Type for all imported channels</label>
      <select id="m3u-ctype" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="m3u">🟢 M3U / HLS (default for internet streams)</option>
        <option value="stream_udp">🔵 UDP / Multicast (for local network)</option>
      </select>
    </div>
    <div class="fg fcol"><label>— OR paste raw M3U content here —</label>
      <textarea id="m3u-text" style="width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:10px;color:var(--text);font-family:'DM Mono',monospace;font-size:11px;height:120px;outline:none;resize:vertical" placeholder="#EXTM3U&#10;#EXTINF:-1 tvg-logo=&quot;...&quot; group-title=&quot;News&quot;,BBC News&#10;http://example.com/bbc.m3u8&#10;..."></textarea>
    </div>
  </div>
  <div id="m3u-prog" style="display:none;margin-top:8px">
    <div class="prog-wrap"><div class="prog-fill" id="m3u-pfill" style="width:0%"></div></div>
    <div id="m3u-ptext" style="font-size:12px;color:var(--text2);margin-top:5px">Importing...</div>
  </div>
  <div id="m3u-result" style="margin-top:10px"></div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="runM3UImportV8()">📥 Start Import</button>`, 'modal-lg');
}

async function runM3UImportV8() {
  const url   = document.getElementById('m3u-url').value.trim();
  const grp   = document.getElementById('m3u-grp').value.trim();
  const max   = parseInt(document.getElementById('m3u-max').value)||0;
  const ctype = document.getElementById('m3u-ctype').value;
  const text  = document.getElementById('m3u-text').value.trim();

  document.getElementById('m3u-prog').style.display = 'block';
  document.getElementById('m3u-pfill').style.width  = '20%';
  document.getElementById('m3u-ptext').textContent  = 'Sending to server...';

  const body = { channel_type: ctype };
  if (url)  body.url = url;
  if (grp)  body.group_filter = grp;
  if (max)  body.max_channels = max;
  if (text && !url) body.m3u = text; // paste mode

  document.getElementById('m3u-pfill').style.width = '60%';
  const r = await req('/channels/import-m3u', {method:'POST', body:JSON.stringify(body)});
  document.getElementById('m3u-pfill').style.width = '100%';

  if (!r) {
    document.getElementById('m3u-result').innerHTML = '<div style="color:var(--red)">❌ Import failed — server error. Check that Flask is running.</div>';
    return;
  }
  document.getElementById('m3u-ptext').textContent = 'Done!';
  document.getElementById('m3u-result').innerHTML = `
    <div style="color:var(--green);font-size:13px;padding:10px;background:var(--gnd);border-radius:8px">
      ✅ <b>Imported: ${fmtNum(r.imported||0)}</b> channels &nbsp;•&nbsp;
      Skipped: ${r.skipped||0} &nbsp;•&nbsp;
      Groups created: ${r.groups_created||0}
    </div>`;
  await updateCounts();
}




// ═══════════════════════════════════════════════════════════════════════════════
// HOME LAYOUT PAGE — customize home screen sections
// ═══════════════════════════════════════════════════════════════════════════════
pages.homeLayout = async function() {
  const s = await req('/settings');
  if (!s) return;
  window._settings = s;

  const showSlides   = s.home_show_slides   !== '0';
  const showFeatured = s.home_show_featured !== '0';
  const showWelcome  = s.home_show_welcome  !== '0';
  const showChannels = s.home_show_channels !== '0';
  const showVod      = s.home_show_vod      !== '0';
  const slidesStyle  = s.home_slides_style  || 'full';
  const welcomeType  = s.home_welcome_type  || 'text';
  const welcomeText  = s.home_welcome_text  || s.welcome_message || 'Welcome! Enjoy your stay.';
  const welcomePhoto = s.home_welcome_photo || '';

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">Home Screen Layout</div>
    <button class="btn btn-p" onclick="saveHomeLayout()">💾 Save Layout</button>
  </div>
  <div class="ibox info">Customize what appears on the guest Home screen. Sections are shown top to bottom in the order below. Use the toggles to show/hide each section.</div>


  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">


    <div>
      <div class="sec-title" style="font-size:12px;color:var(--text2);margin-bottom:12px">Sections (shown in this order)</div>


      <div class="home-setting-row" style="margin-bottom:8px;flex-direction:column;align-items:stretch;gap:12px">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div>
            <div class="home-setting-label">🖼 Promo / Marketing Slides</div>
            <div class="home-setting-sub">Image or video slideshow — go to Promo Slides to add content</div>
          </div>
          <label class="big-toggle">
            <input type="checkbox" id="hl-slides" ${showSlides?'checked':''}>
            <span class="big-toggle-track"></span>
          </label>
        </div>
        <div>
          <label style="font-size:11px;color:var(--text2);margin-bottom:4px;display:block">Slide display style</label>
          <select id="hl-slides-style" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:7px 12px;font-size:13px;outline:none;width:100%">
            <option value="full" ${slidesStyle==='full'?'selected':''}>Full-width — one at a time</option>
            <option value="side" ${slidesStyle==='side'?'selected':''}>Side by side — two at once</option>
          </select>
        </div>
      </div>


      <div class="home-setting-row" style="margin-bottom:8px;flex-direction:column;align-items:stretch;gap:12px">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div>
            <div class="home-setting-label">💬 Welcome Message / Banner</div>
            <div class="home-setting-sub">Hotel welcome with text, photo, or both</div>
          </div>
          <label class="big-toggle">
            <input type="checkbox" id="hl-welcome" ${showWelcome?'checked':''}>
            <span class="big-toggle-track"></span>
          </label>
        </div>

        <div>
          <label style="font-size:11px;color:var(--text2);margin-bottom:6px;display:block">Welcome banner type</label>
          <div style="display:flex;gap:8px">
            <label style="display:flex;align-items:center;gap:5px;padding:7px 12px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;font-size:12px;flex:1">
              <input type="radio" name="hl-wtype" id="hl-wtype-text" value="text" ${welcomeType!=='photo'&&welcomeType!=='both'?'checked':''} onchange="toggleWelcomeFields()" style="accent-color:var(--gold)"> ✏ Text only
            </label>
            <label style="display:flex;align-items:center;gap:5px;padding:7px 12px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;font-size:12px;flex:1">
              <input type="radio" name="hl-wtype" id="hl-wtype-photo" value="photo" ${welcomeType==='photo'?'checked':''} onchange="toggleWelcomeFields()" style="accent-color:var(--gold)"> 🖼 Photo only
            </label>
            <label style="display:flex;align-items:center;gap:5px;padding:7px 12px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;font-size:12px;flex:1">
              <input type="radio" name="hl-wtype" id="hl-wtype-both" value="both" ${welcomeType==='both'?'checked':''} onchange="toggleWelcomeFields()" style="accent-color:var(--gold)"> 🖼+✏ Both
            </label>
          </div>
        </div>

        <div id="hl-text-section" style="${welcomeType==='photo'?'display:none':''}">
          <label style="font-size:11px;color:var(--text2);margin-bottom:4px;display:block">Welcome text</label>
          <div class="rte-toolbar">
            <button class="rte-btn" onclick="hlRte('bold')" title="Bold"><b>B</b></button>
            <button class="rte-btn" onclick="hlRte('italic')" title="Italic"><i>I</i></button>
            <button class="rte-btn" onclick="hlRte('underline')" title="Underline"><u>U</u></button>
            <button class="rte-btn" onclick="hlRteBlock('h2')" title="Large text">H2</button>
            <button class="rte-btn" onclick="hlRteBlock('h3')" title="Medium text">H3</button>
            <button class="rte-btn" onclick="hlRteBlock('p')" title="Normal text">¶</button>
            <button class="rte-btn" onclick="hlRte('insertUnorderedList')" title="Bullet list">• List</button>
            <button class="rte-btn" onclick="hlRteColor('#d4a843')" title="Gold" style="color:#d4a843">A</button>
            <button class="rte-btn" onclick="hlRteColor('#ffffff')" title="White" style="color:#fff">A</button>
            <button class="rte-btn" onclick="hlRteColor('#aaaaaa')" title="Grey" style="color:#aaa">A</button>
            <button class="rte-btn" onclick="hlRte('removeFormat')" title="Clear formatting">✕ Clear</button>
          </div>
          <div class="rte-body" id="hl-rte-body" contenteditable="true" style="min-height:80px;border-radius:0 0 8px 8px">${welcomeText}</div>
        </div>

        <div id="hl-photo-section" style="${welcomeType==='text'?'display:none':''}">
          <label style="font-size:11px;color:var(--text2);margin-bottom:4px;display:block">Welcome photo</label>
          <div style="display:flex;gap:8px;align-items:stretch">
            <input id="hl-welcome-photo" value="${esc(welcomePhoto)}" placeholder="https://... or upload" style="flex:1;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:9px 12px;color:var(--text);font-size:13px;outline:none">
            <label style="display:flex;align-items:center;gap:5px;padding:8px 14px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:8px;cursor:pointer;font-size:12px;white-space:nowrap;flex-shrink:0">
              📁 Upload<input type="file" accept="image/*" style="display:none" onchange="uploadMediaFile(event,'hl-welcome-photo','hl-photo-prev','image')">
            </label>
          </div>
          ${welcomePhoto ? `<img id="hl-photo-prev" src="${esc(welcomePhoto)}" style="margin-top:8px;width:100%;height:100px;object-fit:cover;border-radius:8px;border:1px solid var(--border2)">` : '<div id="hl-photo-prev"></div>'}
          <div style="margin-top:10px;display:flex;gap:16px;align-items:center;flex-wrap:wrap">
            <div style="display:flex;gap:6px;align-items:center">
              <span style="font-size:11px;color:var(--text2)">Position:</span>
              ${['top','center','bottom'].map(pos=>`<label style="display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer">
                <input type="radio" name="hl-photo-pos" value="${pos}" ${(s.home_welcome_photo_pos||'center')===pos?'checked':''} style="accent-color:var(--gold)"> ${pos.charAt(0).toUpperCase()+pos.slice(1)}</label>`).join('')}
            </div>
            <div style="display:flex;gap:8px;align-items:center;flex:1;min-width:180px">
              <span style="font-size:11px;color:var(--text2);white-space:nowrap">Dark overlay:</span>
              <input type="range" id="hl-photo-overlay" min="0" max="80" value="${parseInt(s.home_welcome_photo_overlay||40)}" oninput="document.getElementById('hl-overlay-val').textContent=this.value+'%'" style="flex:1;accent-color:var(--gold)">
              <span id="hl-overlay-val" style="font-size:11px;color:var(--text2);min-width:32px">${parseInt(s.home_welcome_photo_overlay||40)}%</span>
            </div>
          </div>
        </div>
      </div>


      <div class="home-setting-row" style="margin-bottom:8px">
        <div>
          <div class="home-setting-label">🎬 Featured Movie Hero</div>
          <div class="home-setting-sub">Large banner showing the first movie in VoD</div>
        </div>
        <label class="big-toggle">
          <input type="checkbox" id="hl-featured" ${showFeatured?'checked':''}>
          <span class="big-toggle-track"></span>
        </label>
      </div>

      <div class="home-setting-row" style="margin-bottom:8px">
        <div>
          <div class="home-setting-label">📺 Live Channels Row</div>
          <div class="home-setting-sub">Horizontal scroll of live TV channels</div>
        </div>
        <label class="big-toggle">
          <input type="checkbox" id="hl-channels" ${showChannels?'checked':''}>
          <span class="big-toggle-track"></span>
        </label>
      </div>

      <div class="home-setting-row" style="margin-bottom:8px">
        <div>
          <div class="home-setting-label">🎬 Movies / VOD Row</div>
          <div class="home-setting-sub">Horizontal scroll of VOD movies</div>
        </div>
        <label class="big-toggle">
          <input type="checkbox" id="hl-vod" ${showVod?'checked':''}>
          <span class="big-toggle-track"></span>
        </label>
      </div>
    </div>


    <div>
      <div class="sec-title" style="font-size:12px;color:var(--text2);margin-bottom:12px">Preview (approximate)</div>
      <div id="hl-preview" style="background:var(--bg);border:1px solid var(--border2);border-radius:10px;overflow:hidden;min-height:320px">
        ${buildHomePreview(showSlides, showWelcome, welcomeType, welcomeText, welcomePhoto, showFeatured, showChannels, showVod)}
      </div>
      <div style="font-size:11px;color:var(--text3);margin-top:6px;text-align:center">Save settings then refresh TV to see changes live</div>
    </div>
  </div>`;
};

function toggleWelcomeFields() {
  const type = document.querySelector('input[name="hl-wtype"]:checked')?.value || 'text';
  const ts = document.getElementById('hl-text-section');
  const ps = document.getElementById('hl-photo-section');
  if (ts) ts.style.display = type === 'photo' ? 'none' : '';
  if (ps) ps.style.display = type === 'text'  ? 'none' : '';
}

function buildHomePreview(slides, welcome, wtype, wtext, wphoto, featured, channels=true, vod=true) {
  let html = '<div style="font-family:\'DM Sans\',sans-serif;font-size:11px">';
  // Header bar mock
  html += '<div style="height:28px;background:#111;display:flex;align-items:center;padding:0 10px;gap:6px"><span style="color:#d4a843;font-size:10px;letter-spacing:2px">NV</span><div style="display:flex;gap:4px">';
  ['Home','TV','Movies','Radio'].forEach(n => html += '<span style="padding:2px 6px;background:rgba(255,255,255,.06);border-radius:3px;color:rgba(255,255,255,.4);font-size:9px">' + n + '</span>');
  html += '</div></div>';

  if (slides) {
    html += '<div style="height:64px;background:linear-gradient(135deg,#1a0a2e,#0a1520);display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.3);font-size:10px;letter-spacing:1px">🖼 PROMO SLIDES</div>';
  }
  if (welcome) {
    if (wtype === 'photo' || wtype === 'both') {
      html += '<div style="height:' + (wtype==='both'?'50':'80') + 'px;background:url(\'' + (wphoto||'') + '\') center/cover,#1a1a2e;display:flex;align-items:flex-end;padding:8px">';
      if ((wtype === 'both' || wtype === 'text') && wtext) {
        html += '<span style="color:#fff;font-size:10px;text-shadow:0 1px 4px #000">' + wtext.substring(0,50) + '</span>';
      }
      html += '</div>';
    } else if (wtext) {
      html += '<div style="padding:10px 12px;background:#111;border-bottom:1px solid #222"><div style="color:#d4a843;font-size:11px;margin-bottom:2px">Welcome</div><div style="color:rgba(255,255,255,.6);font-size:10px">' + wtext.substring(0,60) + '</div></div>';
    }
  }
  if (featured) {
    html += '<div style="height:70px;background:linear-gradient(to right,#0f0f1e,#1a0a2e);display:flex;align-items:center;padding:0 12px;gap:10px"><div style="width:40px;height:56px;background:#2a1a3e;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0">🎬</div><div><div style="color:rgba(212,168,76,.7);font-size:9px;letter-spacing:1px">FEATURED</div><div style="color:#fff;font-size:12px;font-weight:600">Movie Title</div><div style="display:flex;gap:4px;margin-top:3px"><span style="color:rgba(255,255,255,.4);font-size:9px">★ 8.5</span><span style="color:rgba(255,255,255,.4);font-size:9px">2024</span></div></div></div>';
  }
  if (channels) {
    html += '<div style="padding:8px 12px"><div style="color:rgba(255,255,255,.3);font-size:9px;letter-spacing:1px;margin-bottom:6px">LIVE CHANNELS</div><div style="display:flex;gap:6px;overflow:hidden">';
    for (let i=0;i<4;i++) html += '<div style="width:48px;height:36px;background:#1a1a2e;border-radius:5px;flex-shrink:0"></div>';
    html += '</div></div>';
  }
  if (vod) {
    html += '<div style="padding:8px 12px"><div style="color:rgba(255,255,255,.3);font-size:9px;letter-spacing:1px;margin-bottom:6px">MOVIES</div><div style="display:flex;gap:6px;overflow:hidden">';
    for (let i=0;i<3;i++) html += '<div style="width:36px;height:52px;background:#1a1a2e;border-radius:5px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:14px">🎬</div>';
    html += '</div></div>';
  }
  html += '</div>';
  return html;
}

async function saveHomeLayout() {
  const type = document.querySelector('input[name="hl-wtype"]:checked')?.value || 'text';
  const d = {
    home_show_slides:   document.getElementById('hl-slides')?.checked   ? '1' : '0',
    home_show_welcome:  document.getElementById('hl-welcome')?.checked   ? '1' : '0',
    home_show_featured: document.getElementById('hl-featured')?.checked  ? '1' : '0',
    home_show_channels: document.getElementById('hl-channels')?.checked  ? '1' : '0',
    home_show_vod:      document.getElementById('hl-vod')?.checked       ? '1' : '0',
    home_slides_style:  document.getElementById('hl-slides-style')?.value || 'full',
    home_welcome_type:  type,
    home_welcome_text:          document.getElementById('hl-rte-body')?.innerHTML || '',
    home_welcome_photo:         document.getElementById('hl-welcome-photo')?.value || '',
    home_welcome_photo_pos:     document.querySelector('input[name="hl-photo-pos"]:checked')?.value || 'center',
    home_welcome_photo_overlay: document.getElementById('hl-photo-overlay')?.value || '40',
  };
  const r = await req('/settings', {method:'POST', body:JSON.stringify(d)});
  if (r?.ok) toast('✅ Home layout saved');
}


// ── Home Layout RTE helpers ───────────────────────────────────────────────────
function hlRte(cmd){document.getElementById('hl-rte-body').focus();document.execCommand(cmd,false,null);}
function hlRteBlock(tag){document.getElementById('hl-rte-body').focus();document.execCommand('formatBlock',false,tag);}
function hlRteColor(color){document.getElementById('hl-rte-body').focus();document.execCommand('foreColor',false,color);}

// ── File upload helper ────────────────────────────────────────────────────────
async function uploadMediaFile(event, targetInputId, previewId, fileType) {
  const file = event.target.files[0];
  if (!file) return;
  const maxMB = fileType === 'video' ? 100 : 10;
  if (file.size > maxMB * 1024 * 1024) {
    toast('File too large. Max ' + maxMB + 'MB for ' + fileType + 's.'); return;
  }
  const formData = new FormData();
  formData.append('file', file);
  const btn = event.target.closest('label');
  const origHTML = btn ? btn.innerHTML : '';
  if (btn) btn.innerHTML = '<span>Uploading...</span>';
  try {
    const h = {};
    if (jwt) h['Authorization'] = 'Bearer ' + jwt;
    const res  = await fetch(API + '/upload', {method:'POST', headers:h, body:formData});
    const data = await res.json();
    if (!data.url) { toast('Upload failed: ' + (data.error||'unknown')); return; }
    const inp = document.getElementById(targetInputId);
    if (inp) { inp.value = data.url; inp.dispatchEvent(new Event('input')); }
    if (previewId) {
      const prev = document.getElementById(previewId);
      if (prev && fileType === 'image') {
        prev.style.backgroundImage = "url('" + data.url + "')";
        prev.style.display = 'block';
      }
    }
    toast('Uploaded: ' + data.filename);
  } catch(e) {
    toast('Upload error: ' + e.message);
  } finally {
    if (btn) btn.innerHTML = origHTML;
  }
}

function toggleSlideType() {
  const isVideo = document.getElementById('sl-type-vid')?.checked;
  const imgSec = document.getElementById('sl-img-section');
  const vidSec = document.getElementById('sl-vid-section');
  if (imgSec) imgSec.style.display = isVideo ? 'none' : '';
  if (vidSec) vidSec.style.display = isVideo ? '' : 'none';
}

async function uploadAdminLogoFile(event) {
  await uploadMediaFile(event, 's-admin-logo', null, 'image');
  await saveSettings();
}


/* ═══════════════════════════════════════════════════════════════════════════════
   ADS MANAGER
   ═══════════════════════════════════════════════════════════════════════════════ */

pages.ads = async function() {
  const ads = await req('/ads/all');
  if (!ads) return;
  window._ads = ads;

  const placementLabel = p => ({vod:'VOD Player',live:'Live TV',both:'Both Players'}[p]||p);
  const placementBadge = p => ({vod:'<span class="bdg bb">VOD</span>',live:'<span class="bdg bp">Live TV</span>',both:'<span class="bdg bg">Both</span>'}[p]||p);

  document.getElementById('content').innerHTML = `
  <div class="sec-hdr">
    <div class="sec-title">Ads Manager</div>
    <button class="btn btn-p" onclick="eAd(null)">+ Add Ad</button>
  </div>

  <div class="tbl-wrap" style="padding:14px 18px;margin-bottom:18px;font-size:13px;color:var(--text2)">
    <b style="color:var(--text)">How it works:</b> Ads are shown as pre-roll overlays before the viewer starts watching Live TV or a VOD movie.
    Image ads auto-dismiss after their duration. Video ads play until complete. You can allow viewers to skip after N seconds.
  </div>

  ${ads.length === 0
    ? '<div class="ibox">No ads yet. Add an image or video ad to display before playback starts.</div>'
    : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px">
      ${ads.map(a => `
      <div class="card" style="${!a.active?'opacity:.5':''}">
        ${a.media_type==='image'
          ? `<div style="width:100%;height:140px;background:var(--bg3);border-radius:8px;background-image:url('${esc(a.media_url)}');background-size:cover;background-position:center;border:1px solid var(--border2)"></div>`
          : `<div style="width:100%;height:140px;background:#000;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid var(--border2);position:relative">
               <span style="font-size:36px">🎥</span>
               <span style="position:absolute;bottom:8px;left:10px;font-size:11px;color:#aaa">${esc(a.media_url.split('/').pop())}</span>
             </div>`
        }
        <div style="margin-top:10px">
          <div style="font-weight:600;font-size:14px;margin-bottom:6px">${esc(a.title)}</div>
          <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px">
            <span class="bdg ${a.active?'bg':'br'}">${a.active?'Active':'Hidden'}</span>
            ${placementBadge(a.placement)}
            <span class="bdg bb">${a.media_type==='video'?'Video':'Image'}</span>
            ${a.skip_after>0?`<span class="bdg" style="background:rgba(255,200,0,.12);color:#f5c518">Skip +${a.skip_after}s</span>`:'<span class="bdg" style="background:rgba(255,80,80,.12);color:#f55">No Skip</span>'}
            ${a.media_type==='image'?`<span class="bdg" style="background:rgba(100,100,200,.12);color:#aaf">${a.duration_seconds}s</span>`:''}
          </div>
          <div class="tda">
            <button class="btn btn-g btn-xs" onclick="eAd(${a.id})">Edit</button>
            <button class="btn btn-d btn-xs" onclick="dAd(${a.id})">Delete</button>
          </div>
        </div>
      </div>`).join('')}
    </div>`
  }`;

  const cnt = document.getElementById('cnt-ads');
  if (cnt) cnt.textContent = ads.filter(a=>a.active).length || '—';
};

function eAd(id) {
  const a = id ? (window._ads||[]).find(x=>x.id===id) : null;
  openModal(a ? 'Edit Ad' : 'Add Ad', `
  <div class="fgrid">
    <div class="fg"><label>Ad Title (internal name)</label>
      <input id="ad-title" value="${esc(a?.title||'')}" placeholder="Summer Promo — Hotel Pool"></div>

    <div class="fg fcol">
      <label>Media Type</label>
      <div style="display:flex;gap:8px">
        <label style="display:flex;align-items:center;gap:6px;padding:7px 14px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;flex:1" id="ad-type-img-lbl">
          <input type="radio" name="ad-type" id="ad-type-img" value="image" ${!a||a.media_type!=='video'?'checked':''} onchange="toggleAdType()" style="accent-color:var(--gold)">
          🖼 Image / Photo
        </label>
        <label style="display:flex;align-items:center;gap:6px;padding:7px 14px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;cursor:pointer;flex:1" id="ad-type-vid-lbl">
          <input type="radio" name="ad-type" id="ad-type-vid" value="video" ${a?.media_type==='video'?'checked':''} onchange="toggleAdType()" style="accent-color:var(--gold)">
          🎥 Video
        </label>
      </div>
    </div>

    <div class="fg fcol" id="ad-img-section" style="${a?.media_type==='video'?'display:none':''}">
      <label>Image URL or upload</label>
      <div style="display:flex;gap:8px;align-items:stretch">
        <input id="ad-img" value="${esc(a?.media_url&&a.media_type!=='video'?a.media_url:'')}" placeholder="https://... or upload" oninput="prevAdImg(this.value)" style="flex:1">
        <label style="display:flex;align-items:center;gap:5px;padding:8px 14px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:8px;cursor:pointer;font-size:12px;white-space:nowrap">
          📁 Upload<input type="file" accept="image/*" style="display:none" onchange="uploadAdMedia(event,'img')">
        </label>
      </div>
      <div id="ad-img-prev" style="${a?.media_type!=='video'&&a?.media_url?'':'display:none'};margin-top:8px;width:100%;height:120px;background-size:cover;background-position:center;border-radius:8px;border:1px solid var(--border2);background-image:url('${esc(a?.media_type!=='video'?a?.media_url||'':'')}')"></div>
    </div>

    <div class="fg fcol" id="ad-vid-section" style="${a?.media_type==='video'?'':'display:none'}">
      <label>Video URL or upload (mp4, webm)</label>
      <div style="display:flex;gap:8px;align-items:stretch">
        <input id="ad-vid" value="${esc(a?.media_type==='video'?a?.media_url||'':'')}" placeholder="https://... or upload" style="flex:1">
        <label style="display:flex;align-items:center;gap:5px;padding:8px 14px;background:var(--bd);color:var(--blue);border:1px solid rgba(74,158,255,.2);border-radius:8px;cursor:pointer;font-size:12px;white-space:nowrap">
          📁 Upload<input type="file" accept="video/*" style="display:none" onchange="uploadAdMedia(event,'vid')">
        </label>
      </div>
    </div>

    <div class="fg">
      <label>Placement</label>
      <select id="ad-placement" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="both"  ${!a||a.placement==='both'?'selected':''}>Both — VOD &amp; Live TV</option>
        <option value="vod"   ${a?.placement==='vod'?'selected':''}>VOD Player only</option>
        <option value="live"  ${a?.placement==='live'?'selected':''}>Live TV Player only</option>
      </select>
    </div>

    <div class="fg" id="ad-dur-row" style="${a?.media_type==='video'?'display:none':''}">
      <label>Duration (seconds, for images)</label>
      <input id="ad-dur" type="number" min="3" max="60" value="${a?.duration_seconds||10}">
    </div>

    <div class="fg">
      <label>Skip Button — show after how many seconds (0 = no skip)</label>
      <input id="ad-skip" type="number" min="0" max="30" value="${a?.skip_after??5}">
      <div style="font-size:11px;color:var(--text2);margin-top:3px">Set 0 to make the ad unskippable</div>
    </div>

    <div class="fg">
      <label>Click Action URL (optional)</label>
      <input id="ad-link" value="${esc(a?.link_url||'')}" placeholder="https://hotel.com/deals  or  services">
      <div style="font-size:11px;color:var(--text2);margin-top:3px">Screen key or full URL opened when viewer taps the ad</div>
    </div>

    <div class="fg">
      <label>Status</label>
      <select id="ad-active" style="background:var(--bg3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:9px 12px;font-size:13px;outline:none;width:100%">
        <option value="1" ${!a||a.active?'selected':''}>Active — show on TV</option>
        <option value="0" ${a&&!a.active?'selected':''}>Hidden</option>
      </select>
    </div>
  </div>`,
  `<button class="btn btn-g" onclick="closeModal()">Cancel</button>
   <button class="btn btn-p" onclick="svAd(${id||'null'})">Save Ad</button>`);
}

function toggleAdType() {
  const isVid = document.getElementById('ad-type-vid').checked;
  document.getElementById('ad-img-section').style.display = isVid ? 'none' : '';
  document.getElementById('ad-vid-section').style.display = isVid ? '' : 'none';
  document.getElementById('ad-dur-row').style.display     = isVid ? 'none' : '';
}

function prevAdImg(url) {
  const el = document.getElementById('ad-img-prev');
  if (!el) return;
  el.style.backgroundImage = `url('${url}')`;
  el.style.display = url ? 'block' : 'none';
}

async function uploadAdMedia(event, type) {
  const file = event.target.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const base = type === 'img'
    ? current_app_config?.ALLOWED_IMAGE_EXTS
    : null;
  try {
    const resp = await fetch('/api/upload', {method:'POST', headers:{'Authorization':'Bearer '+jwt}, body:fd});
    const json = await resp.json();
    if (json.url) {
      const inputId = type === 'img' ? 'ad-img' : 'ad-vid';
      document.getElementById(inputId).value = json.url;
      if (type === 'img') prevAdImg(json.url);
    }
  } catch(e) { toast('Upload failed'); }
}

async function svAd(id) {
  const mediaType = document.querySelector('input[name="ad-type"]:checked')?.value || 'image';
  const mediaUrl  = mediaType === 'video'
    ? (document.getElementById('ad-vid')?.value.trim()||'')
    : (document.getElementById('ad-img')?.value.trim()||'');
  if (!mediaUrl) { alert('Media URL or upload required'); return; }
  const title = document.getElementById('ad-title').value.trim();
  if (!title) { alert('Ad title is required'); return; }
  const d = {
    title,
    media_type:       mediaType,
    media_url:        mediaUrl,
    placement:        document.getElementById('ad-placement').value,
    duration_seconds: parseInt(document.getElementById('ad-dur')?.value)||10,
    skip_after:       parseInt(document.getElementById('ad-skip').value)||0,
    link_url:         document.getElementById('ad-link').value.trim(),
    active:           parseInt(document.getElementById('ad-active').value),
  };
  const r = id
    ? await req('/ads/'+id,  {method:'PUT',  body:JSON.stringify(d)})
    : await req('/ads',      {method:'POST', body:JSON.stringify(d)});
  if (r?.error) { alert(r.error); return; }
  closeModal();
  toast(id ? '✅ Ad updated' : '✅ Ad created');
  await pages.ads();
}

async function dAd(id) {
  if (!confirm('Delete this ad?')) return;
  await req('/ads/'+id, {method:'DELETE'});
  toast('🗑 Ad deleted');
  await pages.ads();
}

// ═══════════════════════════════════════════════════════════════════════════════
// V8.20 — WORLD CLOCK & ALARM PAGE
// ═══════════════════════════════════════════════════════════════════════════════

const _TZ_LIST = [
  {tz:'UTC',                 label:'UTC (Universal)'},
  {tz:'America/New_York',    label:'New York (EST/EDT)'},
  {tz:'America/Chicago',     label:'Chicago (CST/CDT)'},
  {tz:'America/Denver',      label:'Denver (MST/MDT)'},
  {tz:'America/Los_Angeles', label:'Los Angeles (PST/PDT)'},
  {tz:'America/Anchorage',   label:'Anchorage (AKST)'},
  {tz:'Pacific/Honolulu',    label:'Honolulu (HST)'},
  {tz:'America/Toronto',     label:'Toronto (EST/EDT)'},
  {tz:'America/Vancouver',   label:'Vancouver (PST/PDT)'},
  {tz:'America/Sao_Paulo',   label:'São Paulo (BRT)'},
  {tz:'America/Argentina/Buenos_Aires', label:'Buenos Aires (ART)'},
  {tz:'America/Mexico_City', label:'Mexico City (CST/CDT)'},
  {tz:'America/Bogota',      label:'Bogotá (COT)'},
  {tz:'America/Lima',        label:'Lima (PET)'},
  {tz:'America/Santiago',    label:'Santiago (CLT)'},
  {tz:'Europe/London',       label:'London (GMT/BST)'},
  {tz:'Europe/Paris',        label:'Paris (CET/CEST)'},
  {tz:'Europe/Berlin',       label:'Berlin (CET/CEST)'},
  {tz:'Europe/Rome',         label:'Rome (CET/CEST)'},
  {tz:'Europe/Madrid',       label:'Madrid (CET/CEST)'},
  {tz:'Europe/Amsterdam',    label:'Amsterdam (CET/CEST)'},
  {tz:'Europe/Moscow',       label:'Moscow (MSK)'},
  {tz:'Europe/Istanbul',     label:'Istanbul (TRT)'},
  {tz:'Europe/Athens',       label:'Athens (EET/EEST)'},
  {tz:'Africa/Cairo',        label:'Cairo (EET)'},
  {tz:'Africa/Lagos',        label:'Lagos (WAT)'},
  {tz:'Africa/Johannesburg', label:'Johannesburg (SAST)'},
  {tz:'Africa/Nairobi',      label:'Nairobi (EAT)'},
  {tz:'Africa/Casablanca',   label:'Casablanca (WET)'},
  {tz:'Asia/Dubai',          label:'Dubai (GST)'},
  {tz:'Asia/Riyadh',         label:'Riyadh (AST)'},
  {tz:'Asia/Tehran',         label:'Tehran (IRST)'},
  {tz:'Asia/Karachi',        label:'Karachi (PKT)'},
  {tz:'Asia/Kolkata',        label:'Mumbai/Delhi (IST)'},
  {tz:'Asia/Dhaka',          label:'Dhaka (BST)'},
  {tz:'Asia/Bangkok',        label:'Bangkok (ICT)'},
  {tz:'Asia/Singapore',      label:'Singapore (SGT)'},
  {tz:'Asia/Hong_Kong',      label:'Hong Kong (HKT)'},
  {tz:'Asia/Shanghai',       label:'Beijing/Shanghai (CST)'},
  {tz:'Asia/Tokyo',          label:'Tokyo (JST)'},
  {tz:'Asia/Seoul',          label:'Seoul (KST)'},
  {tz:'Asia/Taipei',         label:'Taipei (CST)'},
  {tz:'Asia/Kuala_Lumpur',   label:'Kuala Lumpur (MYT)'},
  {tz:'Asia/Jakarta',        label:'Jakarta (WIB)'},
  {tz:'Australia/Perth',     label:'Perth (AWST)'},
  {tz:'Australia/Adelaide',  label:'Adelaide (ACST/ACDT)'},
  {tz:'Australia/Sydney',    label:'Sydney/Melbourne (AEST/AEDT)'},
  {tz:'Pacific/Auckland',    label:'Auckland (NZST/NZDT)'},
  {tz:'Pacific/Fiji',        label:'Fiji (FJT)'},
];

pages.clock = async function() {
  const [s, alarms] = await Promise.all([req('/settings'), req('/alarms')]);
  if (!s) return;
  window._settings = s;
  window._alarmList = Array.isArray(alarms) ? alarms : [];

  const alarmOn = s.alarm_enabled === '1';

  let zonesArr = [];
  try { zonesArr = JSON.parse(s.worldclock_zones || '[]'); } catch(e) {}

  const tzOptions = _TZ_LIST.map(t =>
    `<option value="${esc(t.tz)}">${esc(t.label)}</option>`
  ).join('');

  const zoneChips = zonesArr.map(tz => {
    const found = _TZ_LIST.find(t => t.tz === tz);
    const label = found ? found.label : tz;
    return `<div class="tz-chip" data-tz="${esc(tz)}">
      <span class="tz-chip-dot"></span>
      <span>${esc(label)}</span>
      <button onclick="removeTzChip(this)" title="Remove">✕</button>
    </div>`;
  }).join('');

  const alarmRows = window._alarmList.length
    ? window._alarmList.map(a => {
        const days = a.days === 'daily' ? '<span style="color:var(--gold)">Every day</span>' : (
          Array.isArray(a.days)
            ? a.days.map(d => ['Su','Mo','Tu','We','Th','Fr','Sa'][d]).join(' · ')
            : a.days
        );
        const sounds = {bell:'🔔 Bell', digital:'📟 Digital', gentle:'🎵 Gentle', loud:'🚨 Loud'};
        return `<tr>
          <td><b style="color:var(--text)">${esc(a.label)}</b></td>
          <td><span style="font-family:'DM Mono',monospace;font-size:18px;color:var(--gold);letter-spacing:1px">${esc(a.time)}</span></td>
          <td style="font-size:12px;color:var(--text2)">${days}</td>
          <td style="font-size:13px;color:var(--text2)">${sounds[a.sound]||a.sound}</td>
          <td>
            <label class="big-toggle" style="transform:scale(0.8);transform-origin:left">
              <input type="checkbox" ${a.active?'checked':''} onchange="toggleAlarm(${a.id},this.checked)">
              <span class="big-toggle-track"></span>
            </label>
          </td>
          <td>
            <button class="btn btn-g btn-sm" onclick="editAlarm(${a.id})">Edit</button>
            <button class="btn btn-d btn-sm" onclick="dAlarm(${a.id})">✕</button>
          </td>
        </tr>`;
      }).join('')
    : `<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:32px;font-size:14px">
        No alarms configured — click <b>+ New Alarm</b> to create one
       </td></tr>`;

  document.getElementById('content').innerHTML = `
  <!-- WORLD CLOCK -->
  <div class="section-card">
    <div class="sc-hdr">
      <span>🌍 World Clock Screen</span>
      <span style="font-size:12px;color:var(--text3);font-weight:400">Configure which timezones display on the World Clock TV screen</span>
    </div>
    <div class="sc-body">

      <div style="display:flex;align-items:center;gap:12px;background:var(--bg3);border:1px solid var(--border2);border-radius:10px;padding:12px 16px;margin-bottom:20px">
        <span style="font-size:20px">☰</span>
        <div>
          <div style="font-size:13px;font-weight:500;color:var(--text);margin-bottom:2px">Enable &amp; reorder in Navigation Menu</div>
          <div style="font-size:12px;color:var(--text3)">Go to <b onclick="go('navigation')" style="color:var(--gold);cursor:pointer">Navigation Menu</b> to enable the World Clock page, toggle it on/off, and drag to reorder it among other nav items.</div>
        </div>
        <button class="btn btn-g btn-sm" style="margin-left:auto;white-space:nowrap" onclick="go('navigation')">Open Nav Manager →</button>
      </div>

      <div style="height:1px;background:var(--border);margin:0 0 20px"></div>

      <div style="font-size:13px;font-weight:500;color:var(--text2);margin-bottom:12px;letter-spacing:.3px">TIMEZONES &nbsp;<span style="font-weight:400;color:var(--text3)">(up to 6 — displayed as clock cards on TV)</span></div>

      <div id="tz-chips" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;min-height:40px">${zoneChips||'<span style="color:var(--text3);font-size:13px;align-self:center">No timezones added yet</span>'}</div>

      <div style="display:flex;gap:10px;align-items:center">
        <select id="tz-picker" style="flex:1;max-width:360px;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:9px 12px;color:var(--text);font-size:13px">
          <option value="">— Select a timezone to add —</option>
          ${tzOptions}
        </select>
        <button class="btn btn-g" onclick="addTzChip()" style="white-space:nowrap">+ Add</button>
      </div>
      <div style="font-size:11px;color:var(--text3);margin-top:8px">Remove and re-add to change the order. Supports all IANA timezones.</div>

      <div style="margin-top:20px">
        <button class="btn btn-p" onclick="saveClockSettings()">💾 Save World Clock</button>
      </div>
    </div>
  </div>

  <!-- ALARM MANAGER -->
  <div class="section-card" style="margin-top:20px">
    <div class="sc-hdr">
      <span>⏰ Alarm Manager</span>
      <span style="font-size:12px;color:var(--text3);font-weight:400">Alarms fire on all active TV screens at the scheduled time</span>
    </div>
    <div class="sc-body">

      <div class="form-row" style="margin-bottom:20px">
        <div>
          <div style="font-weight:500;margin-bottom:2px">Enable Alarms</div>
          <div style="font-size:12px;color:var(--text3)">When enabled, alarms trigger a full-screen notification with audio on every TV displaying this system</div>
        </div>
        <label class="big-toggle">
          <input type="checkbox" id="alarm-enabled" ${alarmOn?'checked':''}>
          <span class="big-toggle-track"></span>
        </label>
      </div>

      <div style="background:var(--bg3);border-radius:10px;padding:12px 16px;margin-bottom:20px;border-left:3px solid var(--gold);font-size:13px;color:var(--text2);line-height:1.6">
        ℹ️ Alarms play through the speaker of whatever device is running the TV app — hotel TVs (LG, Samsung), Android boxes, and guest phones browsing the TV interface. Audio uses the browser's Web Audio engine; no external speakers or infrastructure required.
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <button class="btn btn-p" onclick="saveAlarmSettings()">💾 Save</button>
        <button class="btn btn-g" onclick="editAlarm(null)">+ New Alarm</button>
      </div>

      <div class="tbl-wrap" style="padding:0">
        <table>
          <thead>
            <tr>
              <th>Label</th>
              <th>Time</th>
              <th>Days</th>
              <th>Sound</th>
              <th>Active</th>
              <th style="width:100px">Actions</th>
            </tr>
          </thead>
          <tbody id="alarm-tbody">${alarmRows}</tbody>
        </table>
      </div>
    </div>
  </div>`;
};

function addTzChip() {
  const sel = document.getElementById('tz-picker');
  const tz  = sel.value;
  if (!tz) return;
  const chips = document.getElementById('tz-chips');
  const existing = chips.querySelectorAll('.tz-chip');
  if (existing.length >= 6) { toast('⚠ Maximum 6 timezones allowed'); return; }
  for (const c of existing) { if (c.dataset.tz === tz) { toast('Already added'); return; } }
  const found = _TZ_LIST.find(t => t.tz === tz);
  const label = found ? found.label : tz;
  // Remove placeholder text if present
  const placeholder = chips.querySelector('span[style]');
  if (placeholder) placeholder.remove();
  const chip = document.createElement('div');
  chip.className = 'tz-chip';
  chip.dataset.tz = tz;
  chip.innerHTML = `<span class="tz-chip-dot"></span><span>${esc(label)}</span><button onclick="removeTzChip(this)" title="Remove">✕</button>`;
  chips.appendChild(chip);
  sel.value = '';
}

function removeTzChip(btn) {
  const chip  = btn.closest('.tz-chip');
  const chips = document.getElementById('tz-chips');
  chip.remove();
  if (!chips.querySelectorAll('.tz-chip').length) {
    chips.innerHTML = '<span style="color:var(--text3);font-size:13px;align-self:center">No timezones added yet</span>';
  }
}

async function saveClockSettings() {
  const chips = document.querySelectorAll('#tz-chips .tz-chip');
  const zones = Array.from(chips).map(c => c.dataset.tz).filter(Boolean);
  const d = { worldclock_zones: JSON.stringify(zones) };
  const r = await req('/settings', {method:'POST', body:JSON.stringify(d)});
  if (r?.ok) {
    window._settings = {...(window._settings||{}), ...d};
    toast('✅ World Clock saved');
  }
}

async function saveAlarmSettings() {
  const d = {
    alarm_enabled: document.getElementById('alarm-enabled')?.checked ? '1' : '0',
  };
  const r = await req('/settings', {method:'POST', body:JSON.stringify(d)});
  if (r?.ok) {
    window._settings = {...(window._settings||{}), ...d};
    toast('✅ Alarm settings saved');
  }
}

async function toggleAlarm(id, active) {
  const alarm = (window._alarmList||[]).find(a=>a.id===id);
  if (!alarm) return;
  const d = {...alarm, active: active ? 1 : 0};
  await req('/alarms/'+id, {method:'PUT', body:JSON.stringify(d)});
  if (alarm) alarm.active = active ? 1 : 0;
}

function editAlarm(id) {
  const alarm   = id ? (window._alarmList||[]).find(a => a.id === id) : null;
  const daysArr = alarm ? (alarm.days === 'daily' ? [0,1,2,3,4,5,6] : (alarm.days||[])) : [0,1,2,3,4,5,6];
  const INP = 'width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:9px 12px;color:var(--text);font-size:14px';
  const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

  const dayCbx = dayNames.map((name,i) =>
    `<label style="display:inline-flex;align-items:center;gap:5px;padding:5px 10px;background:${daysArr.includes(i)?'var(--gold3)':'var(--bg3)'};border:1px solid ${daysArr.includes(i)?'var(--gold)':'var(--border2)'};border-radius:6px;cursor:pointer;font-size:13px;transition:.15s" id="day-lbl-${i}">
      <input type="checkbox" class="alarm-day-chk" value="${i}" ${daysArr.includes(i)?'checked':''} style="accent-color:var(--gold);display:none" onchange="_styleDayLabel(${i},this.checked)">
      ${name}
    </label>`
  ).join('');

  openModal(id ? 'Edit Alarm' : 'New Alarm', `
    <div style="display:grid;gap:16px">
      <div>
        <div style="font-size:12px;color:var(--text3);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">Label</div>
        <input id="al-label" value="${esc(alarm?.label||'Wake Up')}" placeholder="e.g. Morning Wake-up" style="${INP}">
      </div>
      <div>
        <div style="font-size:12px;color:var(--text3);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">Time</div>
        <input id="al-time" type="time" value="${esc(alarm?.time||'07:00')}" style="${INP}">
      </div>
      <div>
        <div style="font-size:12px;color:var(--text3);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px">Repeat</div>
        <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:10px">${dayCbx}</div>
        <div style="display:flex;gap:6px">
          <button class="btn btn-g btn-sm" onclick="alarmSelectDays([0,1,2,3,4,5,6])">Every Day</button>
          <button class="btn btn-g btn-sm" onclick="alarmSelectDays([1,2,3,4,5])">Weekdays</button>
          <button class="btn btn-g btn-sm" onclick="alarmSelectDays([0,6])">Weekend</button>
          <button class="btn btn-g btn-sm" onclick="alarmSelectDays([])">Clear</button>
        </div>
      </div>
      <div>
        <div style="font-size:12px;color:var(--text3);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">Sound</div>
        <select id="al-sound" style="${INP}">
          <option value="bell"    ${(alarm?.sound||'bell')==='bell'   ?'selected':''}>🔔 Bell — classic chime</option>
          <option value="gentle"  ${alarm?.sound==='gentle' ?'selected':''}>🎵 Gentle — soft rising tone</option>
          <option value="digital" ${alarm?.sound==='digital'?'selected':''}>📟 Digital — electronic beep</option>
          <option value="loud"    ${alarm?.sound==='loud'   ?'selected':''}>🚨 Loud — urgent alert</option>
        </select>
      </div>
    </div>
  `, `<button class="btn btn-p" onclick="saveAlarm(${id||'null'})">💾 Save Alarm</button>
      <button class="btn btn-g" onclick="closeModal()">Cancel</button>`);
}

function _styleDayLabel(i, checked) {
  const lbl = document.getElementById('day-lbl-'+i);
  if (!lbl) return;
  lbl.style.background = checked ? 'var(--gold3)' : 'var(--bg3)';
  lbl.style.borderColor = checked ? 'var(--gold)' : 'var(--border2)';
}

function alarmSelectDays(days) {
  document.querySelectorAll('.alarm-day-chk').forEach(c => {
    const v = parseInt(c.value);
    c.checked = days.includes(v);
    _styleDayLabel(v, c.checked);
  });
}

async function saveAlarm(id) {
  const label = document.getElementById('al-label')?.value.trim();
  const time  = document.getElementById('al-time')?.value;
  if (!label || !time) { alert('Label and time are required'); return; }
  const days = Array.from(document.querySelectorAll('.alarm-day-chk:checked')).map(c=>parseInt(c.value));
  const finalDays = days.length === 7 ? 'daily' : (days.length === 0 ? 'daily' : days);
  const d = {
    label,
    time,
    days:   finalDays,
    sound:  document.getElementById('al-sound')?.value || 'bell',
    active: parseInt(document.getElementById('al-active')?.value) || 0,
  };
  const r = id
    ? await req('/alarms/'+id, {method:'PUT',  body:JSON.stringify(d)})
    : await req('/alarms',     {method:'POST', body:JSON.stringify(d)});
  if (r?.error) { alert(r.error); return; }
  closeModal();
  toast(id ? '✅ Alarm updated' : '✅ Alarm created');
  await pages.clock();
}

async function dAlarm(id) {
  if (!confirm('Delete this alarm?')) return;
  await req('/alarms/'+id, {method:'DELETE'});
  toast('🗑 Alarm deleted');
  await pages.clock();
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.getElementById('overlay').addEventListener('click',e=>{if(e.target===document.getElementById('overlay'))closeModal();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();if(e.key==='Enter'&&document.getElementById('login').style.display!=='none')doLogin();});
(async()=>{if(jwt&&await checkAuth()){startApp();return;}document.getElementById('login').style.display='flex';})();


// ── Mobile sidebar ────────────────────────────────────────────────────────────
function toggleSidebar(){
  const sb=document.querySelector('.sidebar');
  const bd=document.getElementById('sb-backdrop');
  const open=sb.classList.toggle('open');
  bd.classList.toggle('on',open);
  document.body.classList.toggle('sb-open',open);
}
function closeSidebar(){
  document.querySelector('.sidebar').classList.remove('open');
  document.getElementById('sb-backdrop').classList.remove('on');
  document.body.classList.remove('sb-open');
}
// Auto-close sidebar on mobile when navigating
(()=>{
  const origGo=window.go;
  window.go=function(page){
    if(window.innerWidth<=768)closeSidebar();
    return origGo(page);
  };
})();
