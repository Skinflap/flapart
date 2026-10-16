/* Shared Flaptown identity. Artwork stays local/private until an explicit publish. */
const API='https://accounts.flaptown.com/flapart';
let auth=null,current=null,busy=false;
const $=s=>document.querySelector(s);
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const panel=el('dialog',undefined,'account-dialog');panel.setAttribute('aria-labelledby','account-title');
const title=el('h2','your artwork');title.id='account-title';const note=el('p','', 'account-notice');note.setAttribute('role','status');
const content=el('div');const close=el('button','close');close.type='button';close.addEventListener('click',()=>panel.close());panel.append(title,note,content,close);document.body.append(panel);
const say=text=>{note.textContent=text;};
async function call(path,data){const response=await fetch(API+path,{credentials:'include',method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':auth?.csrf||''},body:data===undefined?undefined:JSON.stringify(data)});let value;try{value=await response.json();}catch{}if(!response.ok){const messages={401:'Sign in to your Flaptown account, then reopen this window.',403:'This account action is unavailable. Sign in with a verified account.',404:'This saved artwork is unavailable.',409:'This artwork changed elsewhere. Save a local project file before loading the latest cloud copy.',413:'This work is larger than the cloud limit. Your local work is safe: use save project to keep a portable copy.',429:'Please take a short breather, then try again.'};throw Error(value?.message||messages[response.status]||'The artwork service could not finish. Your local work is safe.');}return value;}
function button(label,fn){const b=el('button',label);b.type='button';b.addEventListener('click',async()=>{if(busy)return;busy=true;panel.querySelectorAll('button').forEach(x=>x.disabled=true);try{await fn();}catch(error){say(error.message);}finally{busy=false;panel.querySelectorAll('button').forEach(x=>x.disabled=false);}});return b;}
function link(label,href){const a=el('a',label);a.href=href;a.target='_blank';a.rel='noopener';return a;}
function field(label,value,multiline=false){const wrap=el('label',label),input=el(multiline?'textarea':'input');input.value=value;input.maxLength=multiline?1000:160;wrap.append(input);return {wrap,input};}
async function save(asNew=false){const project=await window.flapart.exportProject();const name=window.flapart.getName()||'untitled';const value={title:name,project};if(current&&!asNew)value.expectedRevision=current.revision;const r=await call(current&&!asNew?'/projects/'+current.id:'/projects',value);current=r;return r;}
function currentText(){return current?'cloud copy: '+current.title+' · revision '+current.revision:'not linked to a cloud copy';}
async function list(){content.replaceChildren();const intro=el('p','Cloud saves are private. Publishing shares a flattened image; your layers stay private. Local drawing and exports are always free without signing in.');content.append(intro,el('p',currentText()));
content.append(button('save a new private copy',async()=>{await save(true);say('Private cloud copy saved.');await list();}));
if(current)content.append(button('update this private copy',async()=>{await save();say('Private cloud copy updated. Any public image stays unchanged.');await list();}));
content.append(button('publish to profile library',()=>publishForm('profile')));
const h=el('h3','your saved artwork');content.append(h);const data=await call('/projects');
if(!data.projects.length)content.append(el('p','No cloud saves yet. Your current canvas is still here.'));
for(const item of data.projects){const row=el('section',undefined,'saved-art');row.append(el('h4',item.title),el('p',item.publication?'Public image available'+(item.publication.profile?' in profile library':''):'Private'));
row.append(button('open',()=>confirmAction('Opening this cloud copy replaces the current canvas. Save a local project file first if you want to keep the current work.',async()=>{const data=await call('/projects/'+item.id);await window.flapart.loadProject(data.project);current=data;panel.close();})),button('delete cloud copy',()=>confirmAction('Delete this cloud copy and withdraw its public image? This cannot be undone. Your current canvas and exported files stay on this device.',async()=>{await call('/projects/'+item.id+'/delete',{expectedRevision:item.revision});if(current?.id===item.id)current=null;say('Cloud copy deleted; public image withdrawn.');await list();})));
if(item.publication)row.append(button('withdraw public image',async()=>{const r=await call('/projects/'+item.id+'/unpublish',{expectedRevision:item.revision});if(current?.id===item.id)current={...current,...r};say('Public image withdrawn. Existing downloads cannot be recalled.');await list();}),link('view public image',item.publication.url));
content.append(row);}}
function confirmAction(message,action){content.replaceChildren(el('p',message),button('continue',action),button('back',list));}
async function publishForm(destination){content.replaceChildren();const name=field('public title',window.flapart.getName()||'untitled');const description=field(destination==='townhall'?'post text':'description','',true);
content.append(el('p',destination==='townhall'?'Publish a flattened image in Town Square. Anyone can view, download or copy it. Your private layers are not shared.':'Publish a flattened image to your profile library. Anyone with its link can view, download or copy it. Then choose it in your profile editor to place it on your page. Your private layers are not shared.'),name.wrap,description.wrap);
content.append(el('p','Publishing this cloud work again replaces its public image link. Earlier posts and profile placements using the old image may need updating.'));
content.append(button(destination==='townhall'?'publish to townhall':'publish image to profile library',async()=>{
if(!name.input.value.trim())throw Error('Give your public image a title.');
if(destination==='townhall'){
if(!description.input.value.trim())throw Error('Add a few words for your post.');
const r=await fetch('https://accounts.flaptown.com/forum/session',{credentials:'include'});if(!r.ok)throw Error('Town Square is unavailable. Your artwork is safe.');const forum=await r.json();
if(!forum.authenticated)throw Error('Sign in to your Flaptown account first.');if(forum.banned)throw Error('Town Square participation is restricted for this account.');
if(!forum.alias){say('Choose your public name in Town Square, then return here.');content.append(link('choose a Town Square name','https://flaptown.com/forum/'));return;}}
await save();const r=await call('/projects/'+current.id+'/publish',{expectedRevision:current.revision,png:await window.flapart.exportPreview(),title:name.input.value.trim(),description:description.input.value.trim(),profile:destination==='profile',public:true});current={...current,...r};
if(destination==='townhall'){
try{const post=await call('/projects/'+current.id+'/townhall',{expectedRevision:current.revision,title:name.input.value.trim(),body:description.input.value.trim(),public:true});content.replaceChildren(el('p','Your artwork is posted.'),link('open your Town Square post',post.url),button('your artwork',list));say('Published.');}catch(error){say('The image was published, but the post failed: '+error.message);content.append(button('manage or withdraw the public image',list));}
}else{content.replaceChildren(el('p','Your image is now available in your profile image library. Open your profile editor, insert an image from your library, preview and publish your page.'),link('open profile editor','https://flaptown.com/flapdraft/profile/'),link('view image',r.publication.url),button('your artwork',list));say('Published to your profile library.');}
}),button('back',list));}
async function showAccount(destination,review=false){content.replaceChildren();say('Checking your Flaptown sign-in…');try{auth=await call('/session');if(!auth.authenticated){say('Sign in to save privately or share. Drawing and exporting do not need an account.');content.append(link('sign in to Flaptown','https://accounts.flaptown.com/connect'),button('refresh sign-in',()=>showAccount(destination,review)));return;}say('Private cloud limit: '+Math.floor(auth.limits.projectBytes/1048576)+' MiB per work, '+auth.limits.projects+' works. Larger projects can be saved locally.');if(destination==='townhall'||review){await publishForm(destination);if(review)content.querySelector('input')?.focus();}else await list();}catch(error){say(error.message);}}
async function open(destination,review=false){if(busy||!window.flapart)return;if(!panel.open)panel.showModal();await showAccount(destination,review);}
$('#account-save')?.addEventListener('click',()=>open('profile'));
$('#account-post')?.addEventListener('click',()=>open('townhall'));
// New/open actions detach the cloud target, preventing accidental overwrites of another work.
for(const id of ['new','open'])$('#'+id)?.addEventListener('click',()=>{current=null;});

// Native exports remain local until the person chooses their PNG and publishes.
// URL values select guidance only; never carry a filename, image or account data.
const handoffQuery=new URLSearchParams(location.search);
if(handoffQuery.getAll('from').length===1&&handoffQuery.get('from')==='native'&&handoffQuery.getAll('destination').length===1&&['profile','townhall'].includes(handoffQuery.get('destination'))){
  const destination=handoffQuery.get('destination');
  const banner=el('section',undefined,'native-handoff');banner.setAttribute('aria-labelledby','native-handoff-title');
  const heading=el('h2',destination==='profile'?'bring your desktop art to your profile':'bring your desktop art to townhall');heading.id='native-handoff-title';
  const instructions=el('p','Choose how to open your exported PNG. A new drawing contains only that picture at its original size. Nothing is saved online or published until you choose to publish.');
  const hint=el('p','Adding to the current drawing keeps its visible layers: sharing will include the whole combined canvas. Your desktop layers stay in your original Studio file.','handoff-hint');
  const notice=el('p','', 'handoff-status');notice.setAttribute('role','status');
  const choose=el('button','open PNG as new drawing');choose.type='button';choose.id='native-handoff-choose';
  const review=el('button',destination==='profile'?'review profile sharing':'review townhall post');review.type='button';review.hidden=true;
  const dismiss=el('button','keep drawing');dismiss.type='button';
  const add=el('button','add PNG to current drawing');add.type='button';add.id='native-handoff-layer';
  const saveLocal=el('button','save current project first');saveLocal.type='button';saveLocal.addEventListener('click',()=>$('#save').click());
  let armed=false,active=true;
  const pick=mode=>{armed=true;notice.textContent='Choose your exported PNG. Cancelling keeps your current drawing.';if(!window.flapart.chooseImage({mode})){armed=false;notice.textContent='Finish the current editor operation, then choose your PNG.';}};
  choose.addEventListener('click',async()=>{if(!window.flapart||!active)return;const yes=await window.flapart.ask('open PNG as a new drawing?',[],'This replaces the current canvas only after the PNG is read successfully. Save your current project first if you want a durable copy. Local recovery will then switch to the new drawing; undo can immediately restore this canvas.');if(!active)return;if(yes)pick('new');else notice.textContent='Your current drawing is unchanged.';});
  add.addEventListener('click',()=>{if(window.flapart&&active)pick('layer');});
  review.addEventListener('click',()=>open(destination,true));
  const file=$('#image-file');
  const guard=event=>{if(!armed||!active)return;const selected=file.files[0];if(selected&&selected.type!=='image/png'){event.stopImmediatePropagation();file.value='';armed=false;notice.textContent='Choose a PNG exported from Flapart Studio. Your canvas has not changed.';}};
  file.addEventListener('change',guard,true);
  const imported=event=>{if(!armed||!active)return;armed=false;const detail=event.detail||{};if(detail.state==='success'&&detail.type==='image/png'){current=null;notice.textContent=detail.mode==='new'?'PNG opened on its own. Review before publishing.':'PNG added to your current drawing. Sharing includes all visible layers.';review.hidden=false;open(destination,true);}else{notice.textContent=detail.state==='cancel'?'No file chosen. Your canvas is still here.':'The PNG could not be added. Check the editor message, then choose another PNG.';}};
  window.addEventListener('flapart:image-import',imported);
  dismiss.addEventListener('click',()=>{active=false;armed=false;file.removeEventListener('change',guard,true);window.removeEventListener('flapart:image-import',imported);banner.remove();$('#import').focus();});
  const actions=el('div',undefined,'handoff-actions');actions.append(choose,add,saveLocal,review,dismiss);
  banner.append(heading,instructions,hint,notice,actions);document.querySelector('main').prepend(banner);
}
