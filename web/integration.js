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
async function open(destination){if(busy)return;if(!window.flapart){return;}panel.showModal();content.replaceChildren();say('Checking your Flaptown sign-in…');try{auth=await call('/session');if(!auth.authenticated){say('Sign in to save privately or share. Drawing and exporting do not need an account.');content.append(link('sign in to Flaptown','https://accounts.flaptown.com/connect'),button('refresh sign-in',async()=>{panel.close();await open(destination);}));return;}say('Private cloud limit: '+Math.floor(auth.limits.projectBytes/1048576)+' MiB per work, '+auth.limits.projects+' works. Larger projects can be saved locally.');if(destination==='townhall')await publishForm('townhall');else await list();}catch(error){say(error.message);}}
$('#account-save')?.addEventListener('click',()=>open('profile'));
$('#account-post')?.addEventListener('click',()=>open('townhall'));
// New/open actions detach the cloud target, preventing accidental overwrites of another work.
for(const id of ['new','open'])$('#'+id)?.addEventListener('click',()=>{current=null;});
