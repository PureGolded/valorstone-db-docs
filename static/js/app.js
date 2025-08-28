function escapeHtml(str){
  if(!str) return '';
  return String(str)
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;')
    .replaceAll("'",'&#39;');
}

// Modal system
const Modal = {
  open({title = 'Edit', body, actions = []}){
    const root = document.getElementById('modal-root');
    const t = document.getElementById('modal-title');
    const b = document.getElementById('modal-body');
    const f = document.getElementById('modal-footer');
    // guard: if no content and no actions, do not open
    if (!body && (!actions || actions.length === 0)) return;
    t.textContent = title || '';
    b.innerHTML = '';
    if (typeof body === 'string') b.innerHTML = body; else if (body) b.appendChild(body);
    f.innerHTML = '';
    for (const act of actions){
      const btn = document.createElement('button');
      btn.className = 'btn ' + (act.className || '') + (act.primary ? ' primary' : '');
      btn.textContent = act.label || 'OK';
      btn.type = 'button';
      btn.onclick = async (ev)=>{ ev.preventDefault(); const res = await act.onClick?.(); if (res !== false) Modal.close(); };
      f.appendChild(btn);
    }
    root.hidden = false;
    return ()=> Modal.close();
  },
  close(){
    const root = document.getElementById('modal-root');
    if (!root) return;
    const b = document.getElementById('modal-body');
    const f = document.getElementById('modal-footer');
    if (b) b.innerHTML = '';
    if (f) f.innerHTML = '';
    root.hidden = true;
  },
  // builders
  inputs(def){
    // def: [{key,label,type:'text'|'textarea'|'select'|'toggle', options?:[], value?:any, help?:string, full?:bool }]
    const form = document.createElement('div');
    form.className = 'form-grid';
    for (const item of def){
      const wrap = document.createElement('label');
      wrap.className = 'field' + (item.full ? ' full' : '');
      const label = document.createElement('span');
      label.textContent = item.label || item.key;
      if (item.help) wrap.setAttribute('data-tooltip', item.help);
      wrap.appendChild(label);
      let input;
      if (item.type === 'textarea'){
        input = document.createElement('textarea');
        input.value = item.value || '';
    } else if (item.type === 'select'){
        input = document.createElement('select');
        for (const opt of (item.options || [])){
          const o = document.createElement('option');
      if (typeof opt === 'string'){ o.value = opt; o.textContent = opt; }
      else { o.value = opt.value; o.textContent = opt.label; if (opt.title) o.title = opt.title; }
          if (String(o.value) === String(item.value)) o.selected = true;
          input.appendChild(o);
        }
      } else if (item.type === 'toggle'){
        const row = document.createElement('div');
        row.className = 'toggle';
        input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = !!item.value;
        row.appendChild(input);
        wrap.appendChild(row);
        wrap.dataset.toggleKey = item.key;
        form.appendChild(wrap);
        continue;
      } else {
        input = document.createElement('input');
        input.type = 'text';
        input.value = item.value || '';
      }
      input.dataset.key = item.key;
      wrap.appendChild(input);
      form.appendChild(wrap);
    }
    form.getValues = ()=>{
      const out = {};
      form.querySelectorAll('[data-key]').forEach(el=>{ out[el.dataset.key] = el.value; });
      form.querySelectorAll('[data-toggle-key]').forEach(w=>{ const key = w.dataset.toggleKey; out[key] = w.querySelector('input[type=checkbox]').checked; });
      return out;
    };
    return form;
  }
};

// Common datatype options with guidance
const BASIC_TYPES = [
  { value:'INT', label:'INT', title:'32-bit integer, good for small counts and IDs.' },
  { value:'BIGINT', label:'BIGINT', title:'64-bit integer for very large counts or IDs.' },
  { value:'UUID', label:'UUID', title:'Universally unique identifier (string form). Useful as distributed-safe IDs.' },
  { value:'TEXT', label:'TEXT', title:'Unlimited-length text (not indexed efficiently by default).' },
  { value:'VARCHAR(255)', label:'VARCHAR(255)', title:'Variable-length string up to 255 chars (common for names, emails).' },
  { value:'BOOLEAN', label:'BOOLEAN', title:'True/False values.' },
  { value:'DATE', label:'DATE', title:'Calendar date without time zone.' },
  { value:'TIMESTAMP', label:'TIMESTAMP', title:'Date-time, often with timezone depending on database.' },
];

// UI helpers for building forms
function makeColumnForm({name='column', datatype='TEXT', is_primary=false, is_nullable=true, def='', note='', foreign_ref=null, tablesMap=null}){
  const items = [
    {key:'name', label:'Column Name', type:'text', value: name, help:'A human-friendly identifier for this column.'},
    {key:'datatype', label:'Datatype', type:'select', options:BASIC_TYPES, value: datatype, help:'The kind of data stored in this column.'},
    {key:'is_primary', label:'Primary Key', type:'toggle', value: is_primary, help:'Marks this column as the unique identifier of the table.'},
    {key:'is_nullable', label:'Allow NULLs', type:'toggle', value: is_nullable, help:'If off, the column must have a value for each row.'},
    {key:'default', label:'Default', type:'text', value: def || '', help:'Optional default value used when none is provided.'},
    {key:'note', label:'Note', type:'textarea', value: note || '', help:'Any additional context for this column.', full:true},
  ];
  if (tablesMap){
    // Foreign reference selectors
    const tableOptions = Object.entries(tablesMap).map(([id, obj])=>({value:id, label: obj.label}));
    const selectedTable = foreign_ref?.table_id || '';
    const selectedColumn = foreign_ref?.column_id || '';
    items.push({key:'ref_table', label:'References Table', type:'select', options:[{value:'',label:'— None —'}, ...tableOptions], value:selectedTable, help:'If set, this column references a column in another table (like a foreign key).'});
    items.push({key:'ref_column', label:'References Column', type:'select', options:[{value:'',label:'— Select table first —'}], value:selectedColumn, help:'Select the target ID column in the referenced table.'});
  }
  const form = Modal.inputs(items);
  // Enhance datatype with live hint below the select based on option title
  const dtSel = form.querySelector('select[data-key="datatype"]');
  if (dtSel){
    const hint = document.createElement('div');
    hint.className = 'note';
    function setHint(){ const opt = dtSel.selectedOptions[0]; hint.textContent = opt?.title || ''; }
    setHint();
    dtSel.parentElement.appendChild(hint);
    dtSel.addEventListener('change', setHint);
  }
  // populate column options when table changes
  if (tablesMap){
    const tableSel = form.querySelector('select[data-key="ref_table"]');
    const colSel = form.querySelector('select[data-key="ref_column"]');
    function refreshCols(){
      const tId = tableSel.value;
      colSel.innerHTML = '';
      if (!tId){
        const o = document.createElement('option'); o.value=''; o.textContent='— None —'; colSel.appendChild(o); colSel.value=''; return;
      }
      const cols = tablesMap[tId].columns || {};
      const opts = Object.entries(cols).map(([cid,c])=>({value: cid, label: c.name}));
      const none = document.createElement('option'); none.value=''; none.textContent='— None —'; colSel.appendChild(none);
      for (const opt of opts){ const o = document.createElement('option'); o.value=opt.value; o.textContent=opt.label; colSel.appendChild(o); }
      if (foreign_ref?.column_id) colSel.value = foreign_ref.column_id;
    }
    tableSel.addEventListener('change', refreshCols);
    refreshCols();
  }
  return form;
}

async function fetchState(){ const r = await fetch('/api/state'); return r.ok? r.json(): {}; }

// Expose in window for template inline handlers
window.Modal = Modal;
window.makeColumnForm = makeColumnForm;
window.fetchState = fetchState;

// Floating tooltip manager
(function(){
  let tipEl = null; let active = null; let activeIsHtml = false;
  function ensure(){ if (!tipEl){ tipEl = document.createElement('div'); tipEl.className = 'tooltip'; tipEl.style.display = 'none'; document.body.appendChild(tipEl);} }
  function show(content, isHtml, x, y){
    ensure();
    if (isHtml){ tipEl.innerHTML = content; }
    else { tipEl.textContent = content; }
    tipEl.style.display = 'block';
    const pad=10; const {innerWidth:w, innerHeight:h}=window; const rect = tipEl.getBoundingClientRect();
    let left = x + pad; let top = y + pad;
    if (left + rect.width > w) left = x - rect.width - pad;
    if (top + rect.height > h) top = y - rect.height - pad;
    tipEl.style.left = left+'px'; tipEl.style.top = top+'px';
  }
  function hide(){ if (tipEl){ tipEl.style.display = 'none'; tipEl.innerHTML=''; } }
  document.addEventListener('mouseover', (e)=>{
    const t = e.target.closest('[data-tooltip],[data-tooltip-html]');
    if (!t){ hide(); active=null; activeIsHtml=false; return; }
    const html = t.getAttribute('data-tooltip-html');
    if (html != null){ active = html; activeIsHtml = true; }
    else { active = t.getAttribute('data-tooltip'); activeIsHtml = false; }
  });
  document.addEventListener('mousemove', (e)=>{ if (active){ show(active, activeIsHtml, e.clientX, e.clientY); } });
  document.addEventListener('mouseout', (e)=>{ const t = e.target.closest('[data-tooltip],[data-tooltip-html]'); if (t) { hide(); active=null; activeIsHtml=false; } });
})();
