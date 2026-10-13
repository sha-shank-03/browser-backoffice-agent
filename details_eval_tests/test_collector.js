/* Exact collector code on a small DOM double: no browser, socket or process. */
function runControls(legacySource, candidateSource) {
 let assertions=0;
 const tests=[];
 const equal=(actual,expected)=>{
  assertions++;
  if(JSON.stringify(actual)!==JSON.stringify(expected)) throw Error('pure_collector_assertion');
 };
 const test=(name,body)=>{body();tests.push(name);};
 class Element {
  constructor(tag,label='',settings={}) {
   this.tagName=tag;this.innerText=label;this.textContent=label;this.children=[];this.parentElement=null;
   this.open=!!settings.open;this.rects=settings.rects!==false;this.visibility=settings.visibility||'visible';
   this.disabled=!!settings.disabled;this.required=!!settings.required;this.value=settings.value||'';
   this.options=settings.options||[];this.labels=[];this.attrs=settings.attrs||{};
  }
  append(child){child.parentElement=this;this.children.push(child);return child;}
  contains(node){return this===node||this.children.some(child=>child.contains(node));}
  getClientRects(){return this.rects?[{}]:[];}
  getAttribute(name){return this.attrs[name]??null;}
  closest(tag){for(let node=this;node;node=node.parentElement)if(node.tagName===tag.toUpperCase())return node;return null;}
  querySelector(tag){for(const child of this.children){if(child.tagName===tag.toUpperCase())return child;const found=child.querySelector(tag);if(found)return found;}return null;}
 }
 const compile=source=>Function('getComputedStyle','return ('+source+');')(el=>({visibility:el.visibility}));
 const oldCollect=compile(legacySource),collect=compile(candidateSource);
 const indices=nodes=>collect(nodes).map(control=>control.index);
 const section=(open=false)=>{
  const details=new Element('DETAILS','',{open});
  const summary=details.append(new Element('SUMMARY','Organisation details'));
  const field=details.append(new Element('INPUT','',{attrs:{'aria-label':'Legal name'}}));
  return {details,summary,field};
 };
 test('native-observed geometry/style counterexample excluded',()=>{
  const {details,summary,field}=section();
  equal(oldCollect([summary,field]).map(c=>c.index),[0,1]);
  equal(indices([summary,field]),[0]);equal(details.open,false);
 });
 test('open details exposes content without metadata changes',()=>{
  const {summary,field}=section(true);
  equal(collect([summary,field]),oldCollect([summary,field]));
 });
 test('closed outer open inner hides inner summary and fields',()=>{
  const outer=section(false),inner=section(true);outer.details.append(inner.details);
  equal(indices([outer.summary,inner.summary,inner.field]),[0]);
 });
 test('open outer closed inner preserves inner summary only',()=>{
  const outer=section(true),inner=section(false);outer.details.append(inner.details);
  equal(indices([outer.summary,inner.summary,inner.field]),[0,1]);
 });
 test('both nested open exposes all selected controls',()=>{
  const outer=section(true),inner=section(true);outer.details.append(inner.details);
  equal(indices([outer.summary,inner.summary,inner.field]),[0,1,2]);
 });
 test('both nested closed preserves only outer first summary',()=>{
  const outer=section(false),inner=section(false);outer.details.append(inner.details);
  equal(indices([outer.summary,inner.summary,inner.field]),[0]);
 });
 test('first summary descendants stay accessible when closed',()=>{
  const {summary,field}=section(false),span=summary.append(new Element('SPAN'));
  const link=span.append(new Element('A','Help')),button=span.append(new Element('BUTTON','Explain'));
  equal(indices([summary,link,button,field]),[0,1,2]);
 });
 test('nested summary exemption does not bypass closed outer content',()=>{
  const outer=section(false),inner=section(false);outer.details.append(inner.details);
  const link=inner.summary.append(new Element('A','Help'));
  equal(indices([outer.summary,inner.summary,link,inner.field]),[0]);
 });
 test('only first direct summary exempt in closed details',()=>{
  const {details,summary,field}=section(false),second=details.append(new Element('SUMMARY','Second'));
  equal(indices([summary,field,second]),[0]);
  details.open=true;equal(indices([summary,field,second]),[0,1,2]);
 });
 test('summary is found after a preceding non-summary child',()=>{
  const details=new Element('DETAILS');details.append(new Element('DIV'));
  const summary=details.append(new Element('SUMMARY','Visible')),input=details.append(new Element('INPUT'));
  equal(indices([summary,input]),[0]);
 });
 test('closed details with no explicit summary exposes no content',()=>{
  const details=new Element('DETAILS'),input=details.append(new Element('INPUT'));
  equal(indices([input]),[]);
 });
 test('ordinary hidden or disabled controls remain excluded',()=>{
  const hidden=new Element('INPUT','',{rects:false}),css=new Element('INPUT','',{visibility:'hidden'});
  const disabled=new Element('BUTTON','',{disabled:true}),visible=new Element('INPUT');
  equal(indices([hidden,css,disabled,visible]),[3]);
 });
 test('otherwise hidden summary and descendants remain excluded',()=>{
  const {summary}=section(false);summary.rects=false;
  const link=summary.append(new Element('A','Help',{visibility:'hidden'}));
  equal(indices([summary,link]),[]);
 });
 test('filter retains original selector indices and public values',()=>{
  const closed=section(false),opened=section(true),hidden=new Element('INPUT','',{rects:false}),button=new Element('BUTTON','Review vendor');
  opened.field.value='fictional';
  const controls=collect([closed.summary,closed.field,opened.summary,opened.field,hidden,button]);
  equal(controls.map(c=>c.index),[0,2,3,5]);equal(controls[2].value,'fictional');
 });
 test('flat selector controls options roles and context unchanged',()=>{
  const fieldset=new Element('FIELDSET');fieldset.append(new Element('LEGEND','Public context'));
  const combo=fieldset.append(new Element('SELECT','',{required:true,attrs:{'aria-label':'Country','aria-description':'Jurisdiction'},options:[{text:'India',value:'IN'}]}));
  const input=fieldset.append(new Element('INPUT','',{attrs:{'aria-label':'Legal name'}}));
  equal(collect([combo,input]),oldCollect([combo,input]));
 });
 test('opening and closing changes collection without renumbering',()=>{
  const {details,summary,field}=section();equal(indices([summary,field]),[0]);
  details.open=true;equal(indices([summary,field]),[0,1]);
  details.open=false;equal(indices([summary,field]),[0]);
 });
 const taskDetails=new Element('DETAILS'),taskSummary=taskDetails.append(new Element('SUMMARY','Organisation details'));
 const controls=[taskSummary];
 const input=taskDetails.append(new Element('INPUT','',{required:true,attrs:{'aria-label':'Legal name','aria-description':'Supplier legal identity'}}));
 controls.push(input);
 const other=new Element('SUMMARY','Purchasing details'),review=new Element('BUTTON','Review vendor');controls.push(other,review);
 const policyControls=collect(controls).map(({index,visible,enabled,...rest})=>({...rest,ref:'c'+index}));
 return {kind:'exact JavaScript with authored DOM doubles; not native/browser evidence',passed:true,
         tests:tests.length,test_names:tests,assertions,closed_policy_controls:policyControls};
}

if(typeof module!=='undefined'&&module.exports){
 module.exports=runControls;
 if(require.main===module){
  const fs=require('node:fs');
  const legacy=fs.readFileSync('fresh_eval/browser.py','utf8').match(/EXTRACTOR="""([\s\S]*?)"""/)[1];
  const candidate=fs.readFileSync('details_eval/collector.js','utf8');
  process.stdout.write(JSON.stringify(runControls(legacy,candidate))+'\n');
 }
}
