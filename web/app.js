const API_BASE = ""; // Same-origin local backend; no public server required.
const $ = id => document.getElementById(id);
let selected = [];
$("files").addEventListener("change", e => { selected=[...e.target.files]; showFiles(); });
$("drop").addEventListener("dragover", e=>{e.preventDefault();$("drop").classList.add("drag");});
$("drop").addEventListener("dragleave",()=>$ ("drop").classList.remove("drag"));
$("drop").addEventListener("drop",e=>{e.preventDefault();selected=[...e.dataTransfer.files].filter(f=>f.type.startsWith("video/"));showFiles();});
function showFiles(){ $("filelist").textContent=selected.length?selected.map(f=>f.name).join(" · "):""; }
$("generate").addEventListener("click", async()=>{
 const url=$("yt").value.trim();
 if(!url&&!selected.length){$("message").textContent="Add a YouTube URL or choose video files first.";return;}
 const fd=new FormData(); if(url)fd.append("youtube_url",url);
 selected.forEach(f=>fd.append("files",f));
 fd.append("clips",$("count").value);fd.append("clip_len",$("length").value);
 $("generate").disabled=true;$("message").textContent="Sending videos to your local processing engine…";
 $("results").classList.remove("hidden");$("cards").innerHTML="";$("bar").style.width="0%";
 try{
  const r=await fetch(API_BASE+"/api/process",{method:"POST",body:fd});
  const data=await r.json();if(!r.ok)throw new Error(data.detail||"Could not start job.");
  $("message").textContent="Your clips are being created. Keep this tab open.";
  poll(data.job_id);
 }catch(e){$("message").textContent="Error: "+e.message;$("generate").disabled=false;}
});
async function poll(id){
 try{
  const r=await fetch(API_BASE+"/api/jobs/"+id);const j=await r.json();
  $("bar").style.width=(j.progress||0)+"%";$("jobstatus").textContent=j.status;
  $("cards").innerHTML=(j.results||[]).map(x=>`<div class="clip"><video controls playsinline src="${API_BASE+x.url}"></video><b>${x.name}</b><small class="muted">Score ${x.score} · ${x.duration}s</small><br><a href="${API_BASE+x.url}" download>↓ Download MP4</a></div>`).join("");
  if(j.status==="completed"){$("message").textContent="Done! Your Shorts are ready.";$("generate").disabled=false;return;}
  if(j.status==="error"){$("message").textContent="Processing error: "+j.error;$("generate").disabled=false;return;}
  setTimeout(()=>poll(id),2500);
 }catch(e){$("message").textContent="Connection lost: "+e.message;$("generate").disabled=false;}
}
fetch(API_BASE+"/api/status").then(r=>r.json()).then(()=>{$("message").textContent="Processing engine connected. Your videos stay on your computer."}).catch(()=>{$("message").textContent="Frontend preview only. Start the local backend to enable video processing."});
