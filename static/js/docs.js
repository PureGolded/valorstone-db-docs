// Enhancements for document editing: improved chooser with collapsible groups and better labels
(function(){
  let DOCS_STATE = null; // {folders, documents}
  async function ensureState(){
    if (DOCS_STATE) return DOCS_STATE;
    const res = await fetch('/api/docs/state');
    const j = await res.json();
    if (j.ok){ DOCS_STATE = {folders: j.folders||{}, documents: j.documents||{}}; }
    return DOCS_STATE;
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
    function render(){
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
        for (const it of arr){
          const row = document.createElement('div'); row.className='subcard'; row.style.display='flex'; row.style.flexDirection='column'; row.style.gap='.2rem';
          let primary = ''; let secondary = '';
          if (it.type === 'doc'){
            primary = it.name;
            secondary = buildPathForDoc(it.id);
          } else if (it.type === 'heading'){
            primary = `# ${it.heading}`;
            if (it.doc_id){
              const path = buildPathForDoc(it.doc_id);
              secondary = path || it.doc_name || '';
            }
          } else if (it.type === 'database'){
            primary = `DB: ${it.name}`;
          } else if (it.type === 'table'){
            primary = `Table: ${it.name}`;
          } else if (it.type === 'column'){
            primary = `Column: ${it.label}`;
          } else {
            primary = it.name || it.heading || it.label || it.type;
          }
          const p = document.createElement('div'); p.textContent = primary; p.style.cursor='pointer';
          const s = document.createElement('div'); s.textContent = secondary; s.className='note';
          row.appendChild(p); if (secondary) row.appendChild(s);
          row.onclick = ()=> onPick(it);
          body.appendChild(row);
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
})();
