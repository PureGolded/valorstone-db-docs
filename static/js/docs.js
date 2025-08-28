// Enhancements for document editing: improved chooser with collapsible groups and better labels
(function(){
  let DOCS_STATE = null; // {folders, documents}
  let DB_STATE = null;   // databases map
  async function ensureState(){
    if (DOCS_STATE) return DOCS_STATE;
    const res = await fetch('/api/docs/state');
    const j = await res.json();
    if (j.ok){ DOCS_STATE = {folders: j.folders||{}, documents: j.documents||{}}; }
    return DOCS_STATE;
  }
  async function ensureDbState(){
    if (DB_STATE) return DB_STATE;
    const res = await fetch('/api/state');
    if (!res.ok) return {};
    DB_STATE = await res.json(); // { dbId: { name, tables: {...} } }
    return DB_STATE;
  }
  async function searchItems(q){
    const res = await fetch('/api/search?q='+encodeURIComponent(q));
    const j = await res.json();
    return j.ok? j.results: [];
  }
  function buildPathForDoc(docId){
    if (!DOCS_STATE) return '';
    const folders = DOCS_STATE.folders; const documents = DOCS_STATE.documents;
    const d = documents[docId]; if (!d) return '';
    const parts = [d.name];
    let cur = d.parent_id; let guard = 0;
    while (cur && folders[cur] && guard++ < 50){ parts.push(folders[cur].name); cur = folders[cur].parent_id; }
    return parts.reverse().join(' / ');
  }
  function createChooser(items, onPick){
    const root = document.createElement('div');
    const input = document.createElement('input'); input.type='text'; input.placeholder='Type to filter… ($ to open)'; input.style.width='100%';
    const list = document.createElement('div'); list.style.maxHeight='420px'; list.style.overflow='auto'; list.style.marginTop='.5rem';
    root.appendChild(input); root.appendChild(list);
    const sections = [
      {key:'docs', title:'Documents & Headings', match:(t)=> t==='doc' || t==='heading'},
      {key:'dbs', title:'Databases', match:(t)=> t==='database'},
      {key:'tables', title:'Tables & Columns', match:(t)=> t==='table' || t==='column'},
    ];
    async function render(){
      await ensureDbState();
      list.innerHTML='';
      const groups = new Map();
      for (const s of sections) groups.set(s.key, []);
      for (const it of items){
        const sec = sections.find(s=> s.match(it.type));
        (sec? groups.get(sec.key): (groups.get('docs'))).push(it);
      }
      for (const sec of sections){
        const arr = groups.get(sec.key) || [];
        if (arr.length === 0) continue;
        const head = document.createElement('div'); head.className='note'; head.style.margin='.25rem 0'; head.style.cursor='pointer';
        const twisty = document.createElement('span'); twisty.textContent = '▸'; twisty.style.display='inline-block'; twisty.style.width='1rem'; twisty.style.marginRight='.25rem';
        const title = document.createElement('span'); title.textContent = `${sec.title} (${arr.length})`;
        const sectionWrap = document.createElement('div');
        sectionWrap.appendChild(head);
        list.appendChild(sectionWrap);
        const body = document.createElement('div'); body.style.marginLeft='1rem'; body.style.display='none'; sectionWrap.appendChild(body);
        let expanded = false; const setExp = (b)=>{ expanded=b; body.style.display=b? 'block':'none'; twisty.style.transform = b? 'rotate(90deg)':'none'; };
        head.appendChild(twisty); head.appendChild(title);
        head.addEventListener('click', ()=> setExp(!expanded));
        // Default expanded for the first section
        if (sec.key === 'docs') setExp(true);
  if (sec.key === 'docs'){
          // Group headings under their document
          const byDoc = new Map();
          for (const it of arr){
            if (it.type === 'doc'){ byDoc.set(it.id, {doc: it, heads: []}); }
          }
          for (const it of arr){
            if (it.type === 'heading'){
              const key = it.doc_id || it.docId || it.id; // try best
              if (!byDoc.has(key)) byDoc.set(key, {doc: {id: key, name: it.doc_name || '(Document)'}, heads: []});
              byDoc.get(key).heads.push(it);
            }
          }
          // Render docs in name order
          const entries = Array.from(byDoc.values()).sort((a,b)=> (a.doc?.name||'').localeCompare(b.doc?.name||''));
          for (const grp of entries){
            const row = document.createElement('div'); row.className='subcard'; row.style.display='flex'; row.style.flexDirection='column'; row.style.gap='.2rem';
            const primary = grp.doc?.name || '(Document)';
            const secondary = buildPathForDoc(grp.doc?.id);
            const p = document.createElement('div'); p.textContent = primary; p.style.cursor='pointer'; p.style.fontWeight='600';
            const s = document.createElement('div'); s.textContent = secondary; s.className='note';
            row.appendChild(p); if (secondary) row.appendChild(s);
            row.onclick = ()=> onPick(grp.doc);
            // headings nested and indented
            if (grp.heads?.length){
              const nest = document.createElement('div'); nest.style.marginLeft = '1rem'; nest.style.marginTop = '.25rem'; row.appendChild(nest);
              for (const h of grp.heads){
                const hr = document.createElement('div'); hr.style.display='flex'; hr.style.alignItems='center'; hr.style.gap='.35rem'; hr.style.cursor='pointer';
                const bullet = document.createElement('span'); bullet.className='badge'; bullet.textContent = '#'; hr.appendChild(bullet);
                const ht = document.createElement('div'); ht.textContent = h.heading; hr.appendChild(ht);
                hr.onclick = (ev)=>{ ev.stopPropagation(); onPick(h); };
                nest.appendChild(hr);
              }
            }
            body.appendChild(row);
          }
        } else {
          // Group DB -> Tables -> Columns for clarity
          const byDb = new Map(); // dbId -> { name, item, tables: Map<tableId, { item, cols: [] }> }
          for (const it of arr){
            if (it.type === 'database'){
              const dbObj = DB_STATE?.[it.db_id];
              byDb.set(it.db_id, { name: dbObj?.name || it.name, item: it, tables: new Map() });
            }
          }
          // Ensure DB buckets exist for table/column rows
          for (const it of arr){
            if (it.type === 'table' || it.type === 'column'){
              if (!byDb.has(it.db_id)){
                const dbObj = DB_STATE?.[it.db_id];
                byDb.set(it.db_id, { name: dbObj?.name || `(DB ${it.db_id})`, item: { type:'database', db_id: it.db_id, name: dbObj?.name || `(DB ${it.db_id})` }, tables: new Map() });
              }
            }
          }
          // Populate tables
          for (const it of arr){
            if (it.type === 'table'){
              const bucket = byDb.get(it.db_id); if (!bucket) continue;
              bucket.tables.set(it.table_id, { item: it, cols: [] });
            }
          }
          // Populate columns
          for (const it of arr){
            if (it.type === 'column'){
              const bucket = byDb.get(it.db_id); if (!bucket) continue;
              if (!bucket.tables.has(it.table_id)){
                const tObj = DB_STATE?.[it.db_id]?.tables?.[it.table_id];
                bucket.tables.set(it.table_id, { item: { type:'table', db_id: it.db_id, table_id: it.table_id, name: tObj?.name || `(Table ${it.table_id})` }, cols: [] });
              }
              bucket.tables.get(it.table_id).cols.push(it);
            }
          }
          // Render grouped
          const dbList = Array.from(byDb.values()).sort((a,b)=> (a.name||'').localeCompare(b.name||''));
          for (const dbEntry of dbList){
            const row = document.createElement('div'); row.className='subcard'; row.style.display='flex'; row.style.flexDirection='column'; row.style.gap='.2rem';
            const p = document.createElement('div'); p.textContent = `DB: ${dbEntry.name}`; p.style.cursor='pointer'; p.style.fontWeight='600';
            row.appendChild(p);
            row.onclick = ()=> onPick(dbEntry.item);
            const wrap = document.createElement('div'); wrap.style.marginLeft = '1rem'; wrap.style.marginTop = '.25rem'; row.appendChild(wrap);
            const tables = Array.from(dbEntry.tables.values()).sort((a,b)=> (a.item?.name||'').localeCompare(b.item?.name||''));
            for (const tEntry of tables){
              const tr = document.createElement('div'); tr.style.cursor='pointer'; tr.style.margin = '.1rem 0';
              tr.innerHTML = `<span class="badge">T</span> ${tEntry.item?.name || '(Table)'}
                <span class="note" style="margin-left:.5rem;">${dbEntry.name}</span>`;
              tr.addEventListener('click', (ev)=>{ ev.stopPropagation(); onPick(tEntry.item); });
              wrap.appendChild(tr);
              if (tEntry.cols?.length){
                const colsWrap = document.createElement('div'); colsWrap.style.marginLeft = '1rem'; colsWrap.style.marginTop = '.1rem'; wrap.appendChild(colsWrap);
                for (const col of tEntry.cols){
                  const label = col.label || col.name || col.slug || '(column)';
                  const cr = document.createElement('div'); cr.style.cursor='pointer';
                  cr.innerHTML = `<span class="badge">C</span> ${label}`;
                  cr.addEventListener('click', (ev)=>{ ev.stopPropagation(); onPick(col); });
                  colsWrap.appendChild(cr);
                }
              }
            }
            body.appendChild(row);
          }
        }
      }
    }
    render();
    input.addEventListener('input', async ()=>{
      const q = input.value.trim();
      const results = await searchItems(q);
      items = results; render();
    });
    return root;
  }

  window.openSlashChooser = async function(insertCb){
    await ensureState();
    const initial = await searchItems('');
    const body = createChooser(initial, it=>{ Modal.close(); insertCb(it); });
    Modal.open({ title: 'Insert Link', body, actions:[{label:'Cancel'}]});
    const input = body.querySelector('input');
    setTimeout(()=> input && input.focus(), 50);
  };
  
  // ----- Link hover preview in documents -----
  function buildLinkPreview(dataStr){
    try {
      const [type, rest] = dataStr.split(':', 2);
      if (type === 'doc'){
        const docId = rest.split('#')[0];
        const path = buildPathForDoc(docId) || `Document ${docId}`;
        return `Doc: ${path}`;
      }
      if (type === 'db'){
        const parts = (rest||'').split(':'); const dbId = parts[0];
        const db = DB_STATE?.[dbId];
        return db ? `DB: ${db.name}` : `DB: ${dbId}`;
      }
      if (type === 'table'){
        const parts = (rest||'').split(':'); const dbId = parts[0]; const tableId = parts[1];
        const db = DB_STATE?.[dbId];
        const tbl = db?.tables?.[tableId];
        if (db && tbl) return `Table: ${db.name} / ${tbl.name}`;
        if (db) return `Table @ ${db.name}`;
        return `Table: ${tableId || ''}`.trim();
      }
      if (type === 'col'){
        const parts = (rest||'').split(':'); const dbId = parts[0]; const tableId = parts[1]; const colId = parts[2];
        const db = DB_STATE?.[dbId];
        const tbl = db?.tables?.[tableId];
        const col = tbl?.columns?.[colId];
        // Prefer the compact style similar to tables
        if (db && tbl) return `Column @ ${db.name} > ${tbl.name}`;
        // Fallbacks
        if (db) return `Column @ ${db.name}`;
        return `Column`;
      }
    } catch (e) { /* ignore */ }
    return '';
  }
  async function annotateLinkTooltips(scope){
    try { await ensureState(); await ensureDbState(); } catch(e){}
    (scope || document).querySelectorAll('a[data-link]')?.forEach(a => {
      const data = decodeURIComponent(a.getAttribute('data-link'));
      const tip = buildLinkPreview(data);
      if (tip) a.setAttribute('data-tooltip', tip);
    });
  }
  // Expose so document view can call after render
  window.__annotateLinkTooltips = annotateLinkTooltips;
})();
