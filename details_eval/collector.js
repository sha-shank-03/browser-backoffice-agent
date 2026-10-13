els => els.map((el,index) => {
 const labelNode=el.labels?.[0];
 let collapsedContent=false;
 for(let parent=el.parentElement;parent;parent=parent.parentElement){
  if(parent.tagName==='DETAILS'&&!parent.open){
   const summary=Array.from(parent.children).find(child=>child.tagName==='SUMMARY');
   if(!summary||!(summary===el||summary.contains(el))) collapsedContent=true;
  }
 }
 const visible=!collapsedContent && !!el.getClientRects().length && getComputedStyle(el).visibility!=='hidden';
 const role=el.tagName==='SELECT'?'combobox':el.tagName==='INPUT'?'textbox':el.tagName==='A'?'link':'button';
 const caption=labelNode?.querySelector('span');
 return {index,visible,enabled:!el.disabled,role,label:el.getAttribute('aria-label')||caption?.textContent?.trim()||labelNode?.innerText?.trim()||el.innerText.trim(),
  value:el.value||'',options:el.tagName==='SELECT'?Array.from(el.options).map(o=>({label:o.text,value:o.value})):[],
  description:el.getAttribute('aria-description')||'',context:el.closest('fieldset')?.querySelector('legend')?.textContent?.trim()||'',required:!!el.required};
}).filter(e=>e.visible&&e.enabled)
