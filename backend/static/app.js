const state = {
  project: null,
  route: 'dashboard',
  map: { gis: null, objects: [], statuses: new Set(['已验真','部分匹配','缺失影像']), search: '', selected: null },
  evidence: { items: [], search: '', type: '', review: '', page: 1 },
  ledger: { items: [], gis: null, search: '', status: '全部', page: 1 },
  issues: { items: [], search: '', type: '', severity: '', status: '', page: 1 },
  management: { projectId: '', refreshTimer: null },
}
const page = document.querySelector('#page')
const drawer = document.querySelector('#drawer')
const drawerBody = document.querySelector('#drawer-body')
const drawerTitle = document.querySelector('#drawer-title')
const drawerBackdrop = document.querySelector('#drawer-backdrop')
const modal = document.querySelector('#modal')
const modalBody = document.querySelector('#modal-body')
const modalTitle = document.querySelector('#modal-title')
const modalActions = document.querySelector('#modal-actions')
const modalBackdrop = document.querySelector('#modal-backdrop')

async function request(url, options = {}) {
  const response = await fetch(url, options)
  if (!response.ok) {
    let text = `请求失败 (${response.status})`
    try { const body = await response.json(); text = body.detail || text } catch {}
    throw new Error(text)
  }
  const type = response.headers.get('content-type') || ''
  return type.includes('application/json') ? response.json() : response
}
function esc(value) { return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])) }
function fmtDate(v) { return v ? String(v).replace('T',' ').slice(0,16) : '-' }
function statusClass(status) { return ['已验真','完成','生成','已分析','已采集','已入库','已生成'].includes(status) ? 'verified' : ['部分匹配','排队中','抽帧中','YOLO检测中','验真中'].includes(status) ? 'partial' : ['缺失影像','缺失','分析失败'].includes(status) ? 'missing' : 'neutral' }
function statusBadge(status) { return `<span class="status ${statusClass(status)}">${esc(status)}</span>` }
function severityBadge(v) { return `<span class="severity ${v === '高' ? 'high' : v === '中' ? 'medium' : 'low'}">${esc(v)}</span>` }
function progress(value, width = 100) { const pct = Math.round(Number(value || 0) * (Number(value) <= 1 ? 100 : 1)); const color = pct === 100 ? '#20a36a' : pct > 0 ? '#f59e0b' : '#e5484d'; return `<div class="progress-cell" style="grid-template-columns:${width}px 34px"><div class="progress-track"><div class="progress-fill" style="width:${pct}%;background:${color}"></div></div><b>${pct}%</b></div>` }
function toast(text) { const el = document.querySelector('#toast'); el.textContent = text; el.classList.remove('hidden'); clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.add('hidden'), 2600) }
function pageHeader(title, subtitle, actions = '') { return `<div class="page-header"><div><h1>${title}</h1></div><div class="page-actions">${actions}</div></div>` }
function panel(title, body, extra = '') { return `<section class="panel"><div class="panel-head"><h2>${title}</h2>${extra}</div><div class="panel-body">${body}</div></section>` }
function openDrawer(title, html, width = 650) { drawer.style.width = `${width}px`; drawerTitle.textContent = title; drawerBody.innerHTML = html; drawer.classList.add('open'); drawerBackdrop.classList.remove('hidden') }
function closeDrawer() { drawer.classList.remove('open'); drawerBackdrop.classList.add('hidden') }
function openModal(title, html, actions = '') { modalTitle.textContent = title; modalBody.innerHTML = html; modalActions.innerHTML = actions; modal.classList.remove('hidden'); modalBackdrop.classList.remove('hidden') }
function closeModal() { modal.classList.add('hidden'); modalBackdrop.classList.add('hidden'); modalBody.innerHTML = ''; modalActions.innerHTML = '' }

document.querySelector('#drawer-close').onclick = closeDrawer
drawerBackdrop.onclick = closeDrawer
document.querySelector('#modal-close').onclick = closeModal
modalBackdrop.onclick = closeModal

document.querySelector('#export-btn').onclick = e => { e.stopPropagation(); document.querySelector('#export-menu').classList.toggle('hidden') }
document.addEventListener('click', () => document.querySelector('#export-menu').classList.add('hidden'))
document.querySelector('#export-menu').onclick = e => e.stopPropagation()

async function loadProject() {
  state.project = await request('/api/project')
  document.querySelector('#sidebar-scenario').textContent = state.project.scenario
  document.querySelector('#data-version').textContent = state.project.data_version
  document.querySelector('#project-name').textContent = state.project.name
  document.querySelector('#updated-at').textContent = fmtDate(state.project.updated_at)
}

document.querySelector('#audit-btn').onclick = () => {
  const g = state.project?.data_governance || {}
  const sources = Array.isArray(g.sources) ? g.sources.join('；') : '-'
  const processing = Array.isArray(g.processing) ? g.processing.join('；') : '-'
  openDrawer('数据来源与审计信息', `<span class="audit-badge">${esc(g.dataset_type || '标准化工程数据集')}</span><div class="identity" style="margin-top:12px"><div><small>项目</small><h3>${esc(state.project?.name)}</h3></div></div><p class="note" style="margin:14px 0 18px">本页用于数据治理和答辩审计。业务页面仅显示可执行的验真结论、证据状态和处置流程。</p><table class="descriptions"><tr><th>数据版本</th><td>${esc(state.project?.data_version)}</td></tr><tr><th>数据来源</th><td>${esc(sources)}</td></tr><tr><th>处理过程</th><td>${esc(processing)}</td></tr><tr><th>审计原则</th><td>${esc(g.audit_note || '-')}</td></tr></table><div class="section-title">系统业务主线</div><div class="workflow">${(state.project?.workflow || []).map((w,i,a)=>`<span>${esc(w)}${i<a.length-1?'<i>→</i>':''}</span>`).join('')}</div>`, 520)
}

document.querySelectorAll('#nav button').forEach(btn => btn.onclick = () => navigate(btn.dataset.route))
function navigate(route) {
  state.route = route
  location.hash = route
  document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('active', b.dataset.route === route))
  renderRoute()
}
window.addEventListener('hashchange', () => { const route = location.hash.replace('#','') || 'dashboard'; if (route !== state.route) navigate(route) })

async function renderRoute() {
  clearTimeout(state.management.refreshTimer);state.management.refreshTimer=null
  page.innerHTML = '<div class="empty">正在加载业务数据...</div>'
  try {
    if (state.route === 'dashboard') await renderDashboard()
    else if (state.route === 'collection') await renderCollection()
    else if (state.route === 'analysis') await renderAnalysis()
    else if (state.route === 'verification') await renderVerification()
    else if (state.route === 'map') await renderMap()
    else if (state.route === 'evidence') await renderEvidence()
    else if (state.route === 'ledger') await renderLedger()
    else if (state.route === 'issues') await renderIssues()
    else if (state.route === 'delivery') await renderDelivery()
  } catch (error) {
    console.error(error)
    page.innerHTML = `<div class="panel"><div class="panel-body"><strong>页面加载失败</strong><p class="note">${esc(error.message)}</p><button class="btn primary" id="retry-btn">重新加载</button></div></div>`
    document.querySelector('#retry-btn').onclick = renderRoute
  }
}

async function renderDashboard() {
  const [data, ai, stats, overview] = await Promise.all([request('/api/summary'), request('/api/ai/dashboard'), request('/api/management/dashboard'), request('/api/management/platform-overview')])
  const k = data.kpis, s = stats.statistics
  page.innerHTML = pageHeader('项目驾驶舱','', '<button class="btn primary" id="goto-collection">采集施工数据</button>') + `
    <div class="grid kpi-grid">
      ${kpiCard('施工任务',s.task_count,'','☷')}
      ${kpiCard('施工影像',s.media_count,'已上传的视频与现场图片','▣')}
      ${kpiCard('影像分析',s.analysis_count,s.processing_count?`${s.processing_count} 个任务处理中`:s.failed_count?`${s.failed_count} 个任务失败`:'已完成的视频任务','✓')}
      ${kpiCard('数字交付',s.delivery_count,'','▤')}
    </div>
    <section class="lifecycle-panel">
      ${[
        ['工程设计数据导入',overview.layers.gis_feature_count],
        ['施工现场数据采集',overview.layers.collected_count],
        ['施工影像分析',overview.layers.analyzed_video_count],
        ['施工状态识别',overview.layers.analyzed_video_count],
        ['智能验真',overview.layers.evidence_count],
        ['工程对象关联',overview.layers.object_count],
        ['数字交付',overview.layers.delivery_count],
      ].map((item,index,array)=>`<div><b>${index+1}</b><span>${item[0]}</span><strong>${item[1]}</strong></div>${index<array.length-1?'<i>→</i>':''}`).join('')}
    </section>
    <section class="panel" style="margin-top:16px">
      <div class="panel-head"><h2>施工全过程</h2><a class="btn text" href="/api/ai/projects/${encodeURIComponent(ai.project.project_id)}/report.pdf">数字交付报告</a></div>
      <div class="panel-body">
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
          ${ai.workflow.map(step=>`<div class="recommend"><div class="recommend-icon">${step.sequence}</div><div><strong>${esc(step.name)}</strong>${statusBadge(step.status)}</div></div>`).join('')}
        </div>
      </div>
    </section>
    <div class="grid two-col" style="margin-top:16px">
      ${panel('工程对象状态',`<div class="stats3"><div class="statbox"><span>已验真</span><strong>${k.verified}</strong></div><div class="statbox"><span>部分匹配</span><strong>${k.partial}</strong></div><div class="statbox"><span>缺失影像</span><strong>${k.missing}</strong></div></div>`, '<button class="btn text" id="goto-ledger">查看台账</button>')}
      ${panel('问题状态',`<div class="stats3"><div class="statbox"><span>待处置</span><strong>${k.open_issues}</strong></div><div class="statbox"><span>高风险对象</span><strong>${k.high_risk_objects}</strong></div><div class="statbox"><span>档案完整率</span><strong>${k.archive_completeness.toFixed(1)}%</strong></div></div>`, '<button class="btn text" id="goto-issues">查看问题</button>')}
    </div>`
  document.querySelector('#goto-collection').onclick = () => navigate('collection')
  document.querySelector('#goto-ledger').onclick = () => navigate('ledger')
  document.querySelector('#goto-issues').onclick = () => navigate('issues')
  if(s.processing_count)state.management.refreshTimer=setTimeout(()=>{if(state.route==='dashboard')renderDashboard()},2000)
}
function kpiCard(label,value,hint,icon){return `<div class="kpi"><div class="kpi-head"><span>${label}</span><div class="kpi-icon">${icon}</div></div><div class="kpi-value">${value}</div><div class="kpi-hint">${hint}</div></div>`}

const stageNames={equipment_setup:'设备准备',cable_loading:'光缆加载',blowing_process:'气吹施工',completion_check:'完成检查',fiber_stripping:'剥纤',fiber_cleaning:'清洁',fiber_cleaving:'切割',fusion_splicing:'熔接',fiber_organizing:'盘纤整理'}
const taskStages={air_blowing:['equipment_setup','cable_loading','blowing_process','completion_check'],fusion_splicing:['fiber_stripping','fiber_cleaning','fiber_cleaving','fusion_splicing','fiber_organizing']}
const detectionNames={blowing_machine:'吹缆机',cable_reel:'光缆盘',fusion_splicer:'熔接机'}
const objectNames={fiber_cable:'光缆',blowing_machine:'吹缆机',air_compressor:'空压机',worker:'施工人员',cable_reel:'光缆盘',safety_helmet:'安全帽',safety_vest:'反光背心',no_safety_helmet:'未佩戴安全帽',fusion_splicer:'光纤熔接机',fiber:'光纤',splice_tray:'接续盘',protection_sleeve:'保护套管',technician:'熔接技术人员'}
const riskNames={safety_helmet_not_confirmed:'安全帽未确认',safety_helmet_missing:'未佩戴安全帽',completion_check_not_fully_observed:'完工检查影像不完整',exposed_cable_loop_trip_hazard:'光缆盘绕存在绊倒风险',splice_tray_not_observed:'接续盘未观察到'}
const boxColors={blowing_machine:'#21d4fd',cable_reel:'#ffb547',fusion_splicer:'#c084fc',worker:'#60a5fa',safety_helmet:'#22c55e',safety_vest:'#f59e0b',no_safety_helmet:'#ef4444'}

function fmtVideoTime(value){const total=Math.max(0,Number(value||0));const minutes=Math.floor(total/60);const seconds=(total%60).toFixed(1).padStart(4,'0');return `${String(minutes).padStart(2,'0')}:${seconds}`}
function displayObjectName(label){return objectNames[label]||detectionNames[label]||label||'未知对象'}
function verdictClass(value){return value==='证据匹配'||value==='通过'?'pass':value==='风险提示'||value==='待补证'?'warn':'pending'}

async function renderCollection(){
  const projects=await request('/api/management/projects');if(!projects.length){page.innerHTML=pageHeader('施工数据采集中心','')+'<div class="empty">暂无施工项目</div>';return}
  state.management.projectId=state.management.projectId||projects[0].project_id
  const [tasks,data]=await Promise.all([request(`/api/management/tasks?project_id=${encodeURIComponent(state.management.projectId)}`),request(`/api/management/construction-data?project_id=${encodeURIComponent(state.management.projectId)}`)])
  page.innerHTML=pageHeader('施工数据采集中心','')+`<div class="collection-types"><div><b>▣</b><strong>施工视频</strong></div><div><b>▧</b><strong>现场图片</strong></div><div><b>▤</b><strong>工程资料</strong></div><div><b>⌖</b><strong>空间数据</strong></div></div><div class="grid two-col">${panel('上传施工数据',`<div class="field"><label>项目</label><select class="select" id="collect-project">${projects.map(p=>`<option value="${p.project_id}" ${p.project_id===state.management.projectId?'selected':''}>${esc(p.name)}</option>`).join('')}</select></div><div class="field"><label>施工任务</label><select class="select" id="collect-task">${tasks.map(t=>`<option value="${t.task_id}">${esc(t.name)}</option>`).join('')}</select></div><label class="dropzone" for="collect-file" style="margin-top:14px"><strong id="collect-file-name">选择施工数据</strong><span>视频、图片、资料、空间数据或工程清单</span></label><input id="collect-file" type="file" accept=".mp4,.jpg,.jpeg,.png,.webp,.pdf,.xls,.xlsx,.csv,.geojson,.zip,.shp,.dbf,.shx,.prj" class="hidden"><button class="btn primary" id="collect-submit" style="margin-top:14px">上传并提交处理</button>`)}${panel('统一处理流程','<div class="rule-list"><div class="rule-item"><i class="ok"></i><strong>数据入库</strong><span>项目与施工任务绑定</span></div><div class="rule-item"><i class="ok"></i><strong>分类处理</strong><span>影像分析、文本识别、空间解析</span></div><div class="rule-item"><i class="ok"></i><strong>工程关联</strong><span>证据、规则与工程对象关联</span></div></div>')}</div><div class="table-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>文件</th><th>施工任务</th><th>数据类型</th><th>上传时间</th><th>处理状态</th><th>进度/操作</th></tr></thead><tbody>${data.length?data.map(d=>`<tr><td>${esc(d.file_name)}</td><td>${esc(d.task_name)}</td><td>${esc(d.data_type)}</td><td>${fmtDate(d.upload_time)}</td><td>${statusBadge(d.status)}<small class="job-stage-message">${esc(d.error_message||d.stage_message||'')}</small></td><td>${d.data_type==='施工视频'?`${progress(d.progress||0,90)}${d.status==='分析失败'?`<button class="btn" data-analyze="${d.id}">重新处理</button>`:''}`:'-'}</td></tr>`).join(''):'<tr><td colspan="6"><div class="empty">暂无采集数据</div></td></tr>'}</tbody></table></div></div>`
  document.querySelector('#collect-project').onchange=e=>{state.management.projectId=e.target.value;renderCollection()}
  const input=document.querySelector('#collect-file');input.onchange=()=>{const file=input.files[0];document.querySelector('#collect-file-name').textContent=file?`${file.name}（${file.size<1024?file.size+' 字节':(file.size/1024/1024).toFixed(1)+' MB'}）`:'选择施工数据'}
  document.querySelector('#collect-submit').onclick=async()=>{if(!input.files[0])return toast('请选择文件');const task=document.querySelector('#collect-task').value;if(!task)return toast('请选择施工任务');const fd=new FormData();fd.append('project_id',state.management.projectId);fd.append('task_id',task);fd.append('file',input.files[0]);const button=document.querySelector('#collect-submit');button.disabled=true;button.textContent='正在上传并校验';try{const uploaded=await request('/api/management/construction-data',{method:'POST',body:fd});toast(uploaded.data_type==='施工视频'?'视频已提交，后台开始分析':'施工数据已采集');if(uploaded.analysis_job_id){state.management.analysisJobId=String(uploaded.analysis_job_id);navigate('analysis')}else renderCollection()}catch(err){button.disabled=false;button.textContent='上传并提交处理';toast(err.message)}}
  document.querySelectorAll('[data-analyze]').forEach(b=>b.onclick=async()=>{b.disabled=true;b.textContent='正在重新处理';try{await request(`/api/management/construction-data/${b.dataset.analyze}/analyze`,{method:'POST'});state.management.analysisJobId=b.dataset.analyze;navigate('analysis')}catch(err){b.disabled=false;b.textContent='重新处理';toast(`影像解析失败：${err.message}`)}})
  if(data.some(d=>['排队中','抽帧中','YOLO检测中','验真中'].includes(d.status)))state.management.refreshTimer=setTimeout(()=>{if(state.route==='collection')renderCollection()},1500)
}

async function renderAnalysis(){
  const [tasks,model,overview]=await Promise.all([
    request('/api/management/analysis-tasks'),
    request('/api/ai/yolo/status').catch(() => ({runtime_available:false,weights_available:false,runtime_version:'',runtime_error:'YOLO状态暂不可用'})),
    request('/api/management/platform-overview'),
  ])
  const preferred=tasks.find(t=>String(t.analysis_job_id)===String(state.management.analysisJobId))||tasks[0]
  state.management.analysisJobId=preferred?String(preferred.analysis_job_id):''
  page.innerHTML=pageHeader('施工影像分析中心','',`<span class="model-state ${model.runtime_available&&model.weights_available?'ready':'pending'}">${model.weights_available?'视觉检测已就绪':'视觉检测未就绪'}</span>`)+`
    <section class="analysis-engine-grid">
      ${[['通信施工视觉检测',overview.engines.construction_vision],['安全监管视觉检测',overview.engines.safety_supervision],['工程信息识别',overview.engines.engineering_ocr]].map(([name,engine])=>`<article><span>${esc(name)}</span><strong>${esc(engine.status)}</strong><b>${engine.result_count} 条结果</b></article>`).join('')}
    </section>
    <section class="analysis-task-switcher">
      ${tasks.length?tasks.map(t=>`<button class="analysis-task-tab ${String(t.analysis_job_id)===state.management.analysisJobId?'active':''}" data-analysis-job="${t.analysis_job_id}"><span>${esc(t.name)} · ${esc(t.video_file)}</span><strong>${t.evidence_count} 帧 · ${t.progress||0}%</strong><em>${esc(t.status)}</em></button>`).join(''):'<div class="empty">尚无影像分析任务。请先到施工数据采集中心上传施工视频。</div>'}
    </section>
    <div id="analysis-visualization" class="analysis-visualization"><div class="empty">${preferred?'正在载入视频帧与检测结果...':'上传成功后，分析任务和处理进度将在这里出现。'}</div></div>`
  document.querySelectorAll('[data-analysis-job]').forEach(button=>button.onclick=async()=>{
    state.management.analysisJobId=button.dataset.analysisJob
    document.querySelectorAll('[data-analysis-job]').forEach(item=>item.classList.toggle('active',item===button))
    await loadAnalysisVisualization(state.management.analysisJobId)
  })
  if(preferred)await loadAnalysisVisualization(preferred.analysis_job_id)
  if(tasks.some(t=>['排队中','抽帧中','YOLO检测中','验真中'].includes(t.status)))state.management.refreshTimer=setTimeout(()=>{if(state.route==='analysis')renderAnalysis()},1500)
}

async function loadAnalysisVisualization(jobId){
  const host=document.querySelector('#analysis-visualization');if(!host)return
  host.innerHTML='<div class="empty">正在关联施工影像、视觉检测结果与验真规则...</div>'
  try{state.management.analysisDetail=await request(`/api/management/analysis-jobs/${encodeURIComponent(jobId)}/visualization`);state.management.analysisFrameIndex=0;drawAnalysisVisualization()}
  catch(error){host.innerHTML=`<div class="empty">可视化数据加载失败：${esc(error.message)}</div>`}
}

function positionYoloBoxes(){
  document.querySelectorAll('[data-yolo-canvas]').forEach(canvas=>{
    const image=canvas.querySelector('img');if(!image)return
    const apply=()=>{if(!image.naturalWidth||!image.naturalHeight)return;const scale=Math.min(1,460/image.naturalHeight);canvas.style.width=`${image.naturalWidth*scale}px`;canvas.style.maxWidth='100%';canvas.style.height='auto';canvas.style.minHeight='0';canvas.querySelectorAll('[data-bbox]').forEach(box=>{const [x1,y1,x2,y2]=box.dataset.bbox.split(',').map(Number);box.style.left=`${x1/image.naturalWidth*100}%`;box.style.top=`${y1/image.naturalHeight*100}%`;box.style.width=`${(x2-x1)/image.naturalWidth*100}%`;box.style.height=`${(y2-y1)/image.naturalHeight*100}%`})}
    if(image.complete)apply();else image.onload=apply
  })
}

function drawAnalysisVisualization(){
  const detail=state.management.analysisDetail;const host=document.querySelector('#analysis-visualization');if(!detail||!host)return
  const frames=detail.frames||[];const index=Math.min(state.management.analysisFrameIndex||0,Math.max(frames.length-1,0));state.management.analysisFrameIndex=index
  if(!frames.length){const failed=detail.task.status==='分析失败';host.innerHTML=`<section class="analysis-flow-rail"><div class="flow-node active"><b>1</b><span>视频解析</span><strong>已入库</strong></div><i>→</i><div class="flow-node ${detail.task.progress>=20?'active':''}"><b>2</b><span>关键帧提取</span><strong>${detail.task.status==='抽帧中'?'处理中':'等待'}</strong></div><i>→</i><div class="flow-node ${detail.task.progress>=55?'active':''}"><b>3</b><span>施工阶段识别</span><strong>${detail.task.status==='YOLO检测中'?'处理中':'等待'}</strong></div><i>→</i><div class="flow-node"><b>4</b><span>完整性判断</span><strong>等待</strong></div><i>→</i><div class="flow-node ${failed?'warn':''}"><b>5</b><span>结构化证据</span><strong>${esc(detail.task.status)}</strong></div></section><div class="panel"><div class="panel-body"><div class="job-progress-large">${progress(detail.task.progress||0,360)}</div><div class="empty"><strong>${esc(detail.task.stage_message||detail.task.status)}</strong>${detail.task.error_message?`<p>${esc(detail.task.error_message)}</p>`:'<p>后台正在处理，完成后将自动显示检测结果和验真结论。</p>'}</div></div></div>`;return}
  const frame=frames[index];const boxes=frame.detected_objects.filter(item=>item&&Array.isArray(item.bbox_xyxy));const detections=frame.detected_objects||[];const rule=frame.acceptance_rule||{};const summary=detail.summary||{};const videoHash=detail.task.source_video_sha256||''
  host.innerHTML=`
    <section class="analysis-flow-rail">
      <div class="flow-node active"><b>1</b><span>视频解析</span><strong>已入库</strong></div><i>→</i>
      <div class="flow-node active"><b>2</b><span>关键帧提取</span><strong>${summary.frame_count} 帧</strong></div><i>→</i>
      <div class="flow-node active"><b>3</b><span>施工阶段识别</span><strong>${summary.boxed_frame_count}/${summary.frame_count} 帧有目标</strong></div><i>→</i>
      <div class="flow-node active"><b>4</b><span>完整性判断</span><strong>${summary.completed_stage_count}/${summary.total_stage_count} 工序</strong></div><i>→</i>
      <div class="flow-node ${verdictClass(summary.conclusion)}"><b>5</b><span>结构化证据</span><strong>${summary.detected_object_count} 条目标记录</strong></div>
    </section>
    <section class="analysis-visual-workbench">
      <article class="visual-stage-card video-stage-card">
        <header><div><span class="stage-kicker">第一步 · 原始影像</span><h2>施工原始视频</h2></div><span class="live-chip"><i></i>证据源</span></header>
        <div class="video-player-shell">${detail.task.video_url?`<video id="analysis-video" controls preload="metadata" src="${esc(detail.task.video_url)}"></video>`:'<div class="empty">原视频不可用</div>'}</div>
        <div class="source-meta"><div><span>文件</span><strong>${esc(detail.task.video_url?.split('/').pop()||'—')}</strong></div><div><span>任务</span><strong>${esc(detail.task.name)}</strong></div><div><span>SHA-256</span><code title="${esc(videoHash)}">${esc(videoHash.slice(0,16))}…</code></div></div>
        <button class="btn" id="seek-video-frame">定位到当前帧 · ${fmtVideoTime(frame.timestamp)}</button>
      </article>
      <article class="visual-stage-card detection-stage-card">
        <header><div><span class="stage-kicker">第二步 · 视觉检测</span><h2>施工目标检测</h2></div><span class="frame-counter">${index+1} / ${frames.length}</span></header>
        <div class="yolo-canvas" data-yolo-canvas>
          ${frame.frame_url&&frame.media_type==='video_frame'?`<img src="${esc(frame.frame_url)}" alt="${esc(frame.filename)}">`:'<div class="empty">当前记录为视频片段，未生成独立帧图</div>'}
          ${boxes.map(item=>{const color=boxColors[item.label]||'#4ade80';return `<div class="yolo-box" data-bbox="${item.bbox_xyxy.map(Number).join(',')}" style="--box-color:${color}"><span>${esc(displayObjectName(item.label))} ${Math.round(Number(item.confidence||0)*100)}%</span></div>`}).join('')}
          <div class="frame-timecode">${fmtVideoTime(frame.timestamp)}</div>
        </div>
        <div class="frame-toolbar"><button class="btn" id="prev-analysis-frame" ${index===0?'disabled':''}>上一帧</button><div><strong>${esc(stageNames[frame.stage]||frame.stage)}</strong><span>综合置信度 ${Math.round(Number(frame.confidence||0)*100)}%</span></div><button class="btn" id="next-analysis-frame" ${index===frames.length-1?'disabled':''}>下一帧</button></div>
      </article>
      <article class="visual-stage-card result-stage-card">
        <header><div><span class="stage-kicker">第三步 · 规则判断</span><h2>识别结果</h2></div><span class="result-verdict ${verdictClass(frame.frame_verdict)}">${esc(frame.frame_verdict)}</span></header>
        <div class="result-section"><h3>检测对象</h3><div class="object-token-list">${detections.length?detections.map(item=>{const value=typeof item==='string'?{label:item}:item;return `<span class="object-token ${value.bbox_xyxy?'boxed':''}"><i style="background:${boxColors[value.label]||'#4f9bc8'}"></i>${esc(displayObjectName(value.label))}${value.confidence!=null?` <b>${Math.round(Number(value.confidence)*100)}%</b>`:''}</span>`}).join(''):'<span class="muted-token">本帧未检出目标</span>'}</div></div>
        <div class="result-section rule-result"><h3>${esc(rule.rule_id||'工程规则')} · ${esc(rule.name||'施工阶段规则')}</h3><div><span>要求</span><strong>${frame.required_labels.length?frame.required_labels.map(displayObjectName).join('、'):'无指定目标'}</strong></div><div><span>已命中</span><strong class="match-text">${frame.matched_labels.length?frame.matched_labels.map(displayObjectName).join('、'):'—'}</strong></div><div><span>待补充</span><strong class="missing-text">${frame.missing_labels.length?frame.missing_labels.map(displayObjectName).join('、'):'无'}</strong></div></div>
      </article>
      <article class="visual-stage-card verification-stage-card">
        <header><div><span class="stage-kicker">第四步 · 证据固化</span><h2>验真输出</h2></div><span class="result-verdict ${verdictClass(summary.conclusion)}">${esc(summary.conclusion)}</span></header>
        <div class="verification-orbit"><div class="verification-score"><strong>${summary.completed_stage_count}/${summary.total_stage_count}</strong><span>工序覆盖</span></div><div><span>当前帧状态</span><strong>${esc(frame.review_status||'待人工验真')}</strong><span>关联对象</span><strong>${esc(frame.engineering_object?.object_id||detail.task.linked_object_id||'待关联')}</strong></div></div>
        <div class="risk-list">${frame.risk.length?frame.risk.map(item=>`<div><b>!</b><span>${esc(riskNames[item.risk]||item.risk||'需人工复核')}</span><em>${esc(item.severity||'')}</em></div>`).join(''):'<div class="risk-clear"><b>✓</b><span>当前帧未发现风险提示</span></div>'}</div>
        <div class="evidence-fingerprint"><span>证据指纹</span><code title="${esc(frame.evidence_hash)}">${esc(frame.evidence_hash.slice(0,24))}…</code></div>
        <button class="btn primary" id="goto-verification-workbench">进入智能验真工作台</button>
      </article>
    </section>
    <section class="frame-filmstrip"><header><h2>关键帧处理序列</h2><span>点击帧查看检测框与验真结果</span></header><div>${frames.map((item,i)=>`<button class="frame-thumb ${i===index?'active':''}" data-frame-index="${i}">${item.frame_url&&item.media_type==='video_frame'?`<img src="${esc(item.frame_url)}" alt="">`:'<span class="frame-placeholder">▶</span>'}<strong>${fmtVideoTime(item.timestamp)}</strong><em>${esc(stageNames[item.stage]||item.stage)}</em><i class="${verdictClass(item.frame_verdict)}"></i></button>`).join('')}</div></section>`
  document.querySelectorAll('[data-frame-index]').forEach(button=>button.onclick=()=>{state.management.analysisFrameIndex=Number(button.dataset.frameIndex);drawAnalysisVisualization()})
  document.querySelector('#prev-analysis-frame').onclick=()=>{state.management.analysisFrameIndex=index-1;drawAnalysisVisualization()}
  document.querySelector('#next-analysis-frame').onclick=()=>{state.management.analysisFrameIndex=index+1;drawAnalysisVisualization()}
  document.querySelector('#seek-video-frame').onclick=()=>{const video=document.querySelector('#analysis-video');if(!video)return;video.pause();video.currentTime=Number(frame.timestamp||0)}
  document.querySelector('#goto-verification-workbench').onclick=()=>navigate('verification')
  positionYoloBoxes()
}

async function renderVerification(){
  const tasks=await request('/api/management/verification-workbench')
  page.innerHTML=pageHeader('智能验真工作台','')+`<div class="verification-list">${tasks.map(t=>{const expected=taskStages[t.task_type]||[];const risks=t.risks;return `<section class="verification-card"><header><h2>${esc(t.name)}</h2>${statusBadge(t.status)}</header><div class="verification-layout"><div class="verification-process"><h3>施工流程</h3>${expected.map(stage=>`<div class="verification-stage ${t.stages[stage]?'done':'pending'}"><span>${t.stages[stage]?'✓':'—'}</span><strong>${stageNames[stage]}</strong><em>${t.stages[stage]||'待补证'}</em></div>`).join('')}</div><div class="verification-result"><h3>验真结果</h3><div class="verification-numbers"><div><span>分析证据</span><strong>${t.evidence_count}</strong></div><div><span>风险提示</span><strong>${risks.length}</strong></div></div>${risks.length?`<div class="verification-risks">${risks.slice(0,3).map(r=>`<span>! ${esc(riskNames[r.risk]||'需人工复核')}</span>`).join('')}</div>`:'<div class="verification-pass">未发现风险提示</div>'}</div></div><footer><div><span>验真结论</span><div class="conclusion-options">${['通过','部分通过','待补证'].map(value=>`<b class="${value===t.conclusion?'active':''}">${value}</b>`).join('')}</div></div><div><span>证据完整性</span><strong>${t.completed_count}/${t.total_stage_count}</strong></div></footer></section>`}).join('')}</div>`
}

async function renderMap() {
  const [gis, objects] = await Promise.all([request('/api/gis'), request('/api/objects')])
  state.map.gis = gis; state.map.objects = objects
  drawMapPage()
}
function drawMapPage() {
  const {gis, objects, statuses, search, selected} = state.map
  const filtered = objects.filter(o => statuses.has(o.verification_status) && (!search || o.object_id.toLowerCase().includes(search.toLowerCase())))
  page.innerHTML = pageHeader('地图验真工作台','基于真实 BOITE、CABLE、PTECH、SITE 与基础设施 GIS 图层，定位对象状态和证据缺口。','<button class="btn" id="map-import">导入证据</button><button class="btn primary" id="map-ledger">进入对象验真</button>') + `
  <div class="map-shell"><aside class="map-sidebar"><input class="input" id="map-search" placeholder="搜索对象编码" value="${esc(search)}"><div class="filter-title">验真状态</div><div class="check-list">${['已验真','部分匹配','缺失影像'].map(s=>`<label><input type="checkbox" data-status="${s}" ${statuses.has(s)?'checked':''}><span class="dot ${s==='已验真'?'green':s==='部分匹配'?'orange':'red'}"></span>${s}</label>`).join('')}</div><div class="filter-title">GIS 图层</div><div class="layer-list"><div><span class="dot green" style="margin-right:8px"></span>BOITE 验真对象<b>${filtered.length}</b></div><div><span class="layer-line"></span>CABLE 光缆<b>${gis.features.filter(f=>f.layer==='CABLE').length}</b></div><div><span class="dot" style="background:#7e8995;margin-right:8px"></span>PTECH / SITE<b>${gis.features.filter(f=>['PTECH','SITE'].includes(f.layer)).length}</b></div><div><span class="layer-line" style="background:#a7b1bc"></span>基础设施<b>${gis.features.filter(f=>f.layer==='INFRASTRUCTURE').length}</b></div></div><div class="filter-title">对象列表</div><div class="object-list">${filtered.map(o=>`<button data-object="${o.object_id}" class="${selected===o.object_id?'active':''}"><div class="object-row-head"><strong>${o.object_id}</strong>${statusBadge(o.verification_status)}</div><small>完整率 ${Math.round(o.completeness*100)}% · ${o.issue_count} 个问题</small></button>`).join('')}</div></aside><div class="map-stage" id="map-stage">${buildSvgMap(gis, filtered, selected)}<div class="map-toolbar">真实 GIS 图层 · WGS 84</div></div></div>`
  document.querySelector('#map-import').onclick = () => { navigate('evidence'); setTimeout(openUploadModal,200) }
  document.querySelector('#map-ledger').onclick = () => selected ? openObjectLedger(selected) : toast('请先选择地图对象')
  document.querySelector('#map-search').oninput = e => { state.map.search=e.target.value; drawMapPage() }
  document.querySelectorAll('[data-status]').forEach(c=>c.onchange=()=>{c.checked?statuses.add(c.dataset.status):statuses.delete(c.dataset.status);drawMapPage()})
  document.querySelectorAll('[data-object]').forEach(b=>b.onclick=()=>{state.map.selected=b.dataset.object;drawMapPage();openMapObject(b.dataset.object)})
}
function buildSvgMap(gis, objects, selected) {
  const points = objects.map(o=>[o.longitude,o.latitude])
  gis.features.forEach(f=>{ if(f.geometry_type==='Point') points.push(f.coordinates); else flattenCoords(f.coordinates).forEach(p=>points.push(p)) })
  let minx=Math.min(...points.map(p=>p[0])), maxx=Math.max(...points.map(p=>p[0])), miny=Math.min(...points.map(p=>p[1])), maxy=Math.max(...points.map(p=>p[1]))
  const padX=(maxx-minx)*.08||.001,padY=(maxy-miny)*.08||.001; minx-=padX;maxx+=padX;miny-=padY;maxy+=padY
  const W=1000,H=690,P=36; const project=p=>[P+(p[0]-minx)/(maxx-minx)*(W-2*P),H-P-(p[1]-miny)/(maxy-miny)*(H-2*P)]
  const pathFor = coords => { const parts = Array.isArray(coords[0][0]) ? coords : [coords]; return parts.map(part=>part.map((p,i)=>`${i?'L':'M'}${project(p)[0].toFixed(1)},${project(p)[1].toFixed(1)}`).join(' ')).join(' ') }
  const grid = Array.from({length:10},(_,i)=>`<line x1="${i*W/9}" y1="0" x2="${i*W/9}" y2="${H}"/><line x1="0" y1="${i*H/9}" x2="${W}" y2="${i*H/9}"/>`).join('')
  const infra=gis.features.filter(f=>f.layer==='INFRASTRUCTURE').map(f=>`<path class="map-infra" d="${pathFor(f.coordinates)}"/>`).join('')
  const cables=gis.features.filter(f=>f.layer==='CABLE').map(f=>`<path class="map-cable" d="${pathFor(f.coordinates)}"/>`).join('')
  const ptech=gis.features.filter(f=>['PTECH','SITE'].includes(f.layer)).map(f=>{const [x,y]=project(f.coordinates);return `<circle class="map-ptech" cx="${x}" cy="${y}" r="3"/>`}).join('')
  const obj=objects.map(o=>{const [x,y]=project([o.longitude,o.latitude]);const color=o.verification_status==='已验真'?'#20a36a':o.verification_status==='部分匹配'?'#f59e0b':'#e5484d';const label=selected===o.object_id?`<text class="map-label selected-label" x="${x+10}" y="${y-9}">${o.object_id}</text>`:'';return `<g data-object="${o.object_id}"><title>${o.object_id} · ${o.verification_status} · 完整率 ${Math.round((o.completeness||0)*100)}%</title><circle class="map-object ${selected===o.object_id?'selected':''}" cx="${x}" cy="${y}" r="${selected===o.object_id?7:5.5}" fill="${color}"/>${label}</g>`}).join('')
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><g class="map-grid">${grid}</g>${infra}${cables}${ptech}${obj}</svg>`
}
function flattenCoords(coords){ if(!Array.isArray(coords))return[]; if(typeof coords[0]?.[0]==='number')return coords; return coords.flatMap(flattenCoords) }
async function openMapObject(id) {
  const d=await request(`/api/objects/${encodeURIComponent(id)}`)
  const html=`<div class="identity"><div><small>工程编码</small><h3>${esc(d.object.object_id)}</h3></div>${statusBadge(d.result.status)}</div><div class="stats3"><div class="statbox"><span>完整率</span><strong>${Math.round(d.result.completeness*100)}%</strong></div><div class="statbox"><span>证据</span><strong>${d.evidence.length}</strong></div><div class="statbox"><span>问题</span><strong>${d.issues.filter(i=>i.status!=='已关闭').length}</strong></div></div>${progress(d.result.completeness,430)}<table class="descriptions"><tr><th>对象类型</th><td>${esc(d.object.object_type)} / ${esc(d.object.structure_type)}</td></tr><tr><th>所属区域</th><td>${esc(d.object.site_id)}</td></tr><tr><th>关联设施</th><td>${esc(d.object.ptc_code)}</td></tr><tr><th>敷设方式</th><td>${esc(d.object.mode_pose)}</td></tr><tr><th>上游光缆</th><td>${esc(d.object.upstream_cable)}</td></tr></table><div class="section-title">强制验真节点</div><div class="rule-list">${d.timeline.map(t=>`<div class="rule-item"><i class="${t.status==='完成'?'ok':'bad'}"></i><strong>${esc(t.stage)}</strong>${statusBadge(t.status)}</div>`).join('')}</div><div class="section-title">关联证据</div>${d.evidence.length?`<div class="thumb-grid">${d.evidence.slice(0,6).map(e=>`<div class="thumb-card">${e.url?`<img src="${e.url}">`:'<div class="thumb">▣</div>'}<span>${esc(e.evidence_label)}</span></div>`).join('')}</div>`:'<div class="empty">暂无关联证据</div>'}<div style="margin-top:18px"><button class="btn primary" id="drawer-ledger">打开完整对象档案</button></div>`
  openDrawer('工程对象档案',html,470); document.querySelector('#drawer-ledger').onclick=()=>{closeDrawer();openObjectLedger(id)}
}

async function renderLegacyEvidence() {
  state.evidence.items = await request('/api/evidence')
  drawEvidencePage()
}
function drawLegacyEvidencePage() {
  const s=state.evidence; const types=[...new Map(s.items.map(i=>[i.evidence_type,i.evidence_label])).entries()]
  const filtered=s.items.filter(e=>(!s.search||[e.filename,e.detected_code,e.linked_object_id,e.ocr_text].some(v=>String(v||'').toLowerCase().includes(s.search.toLowerCase())))&&(!s.type||e.evidence_type===s.type)&&(!s.review||e.review_status===s.review))
  const pageSize=10,totalPages=Math.max(1,Math.ceil(filtered.length/pageSize));s.page=Math.min(s.page,totalPages);const rows=filtered.slice((s.page-1)*pageSize,s.page*pageSize)
  page.innerHTML=pageHeader('影像证据中心','统一完成证据导入、文件解析、编码识别、候选对象匹配和人工确认。','<button class="btn" id="ev-refresh">刷新</button><button class="btn" id="ev-video">视频抽帧</button><button class="btn primary" id="ev-upload">导入证据</button>')+`<div class="toolbar"><input class="input" id="ev-search" placeholder="搜索文件名、编码、对象或OCR文本" value="${esc(s.search)}"><select class="select" id="ev-type"><option value="">全部证据类型</option>${types.map(([v,l])=>`<option value="${v}" ${s.type===v?'selected':''}>${esc(l)}</option>`).join('')}</select><select class="select" id="ev-review"><option value="">全部审核状态</option>${['已确认','待确认','待复核'].map(v=>`<option ${s.review===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="table-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>证据文件</th><th>识别编码</th><th>关联对象</th><th>证据类型</th><th>可信度</th><th>审核状态</th><th>操作</th></tr></thead><tbody>${rows.map(e=>`<tr><td><div class="file-cell" data-evidence="${e.evidence_id}">${e.url?`<img class="thumb" src="${e.url}">`:'<div class="thumb">▣</div>'}<div><strong>${esc(e.filename)}</strong><small>${esc(e.evidence_id)} · ${esc(e.source_type)}</small></div></div></td><td>${e.detected_code==='未识别'?'<span class="note">未获得稳定编码</span>':`<code>${esc(e.detected_code)}</code>`}</td><td>${e.linked_object_id?`<button class="btn text">${esc(e.linked_object_id)}</button>`:statusBadge('待关联')}</td><td>${esc(e.evidence_label)}</td><td><div class="confidence"><div class="progress-track"><div class="progress-fill" style="width:${Math.round(e.confidence_score*100)}%;background:${e.confidence_score>=.9?'#20a36a':'#f59e0b'}"></div></div><small>${Math.round(e.confidence_score*100)}% · ${esc(e.confidence_label)}</small></div></td><td>${statusBadge(e.review_status==='已确认'?'完成':'待确认')}</td><td><button class="btn text" data-evidence="${e.evidence_id}">查看</button></td></tr>`).join('')}</tbody></table></div>${pagination(filtered.length,s.page,totalPages,'ev-page')}</div>`
  document.querySelector('#ev-refresh').onclick=()=>renderEvidence();document.querySelector('#ev-video').onclick=openVideoModal;document.querySelector('#ev-upload').onclick=openUploadModal
  document.querySelector('#ev-search').oninput=e=>{s.search=e.target.value;s.page=1;drawEvidencePage()};document.querySelector('#ev-type').onchange=e=>{s.type=e.target.value;s.page=1;drawEvidencePage()};document.querySelector('#ev-review').onchange=e=>{s.review=e.target.value;s.page=1;drawEvidencePage()}
  document.querySelectorAll('[data-evidence]').forEach(el=>el.onclick=()=>openEvidence(el.dataset.evidence))
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{s.page=Number(b.dataset.page);drawEvidencePage()})
}
function pagination(total,pageNo,totalPages,prefix){return `<div class="pager"><span>共 ${total} 条记录</span><div class="pager-buttons">${Array.from({length:totalPages},(_,i)=>i+1).map(p=>`<button data-page="${p}" class="${p===pageNo?'active':''}">${p}</button>`).join('')}</div></div>`}
function openVideoModal() {
  openModal('MP4 视频抽帧',`<label class="dropzone" for="video-file"><strong id="video-file-label">点击选择一个 MP4 文件</strong><span>系统按固定 2 秒间隔提取关键帧，并逐帧写入证据库</span></label><input id="video-file" type="file" accept=".mp4,video/mp4" class="hidden"><div class="form-grid"><div class="field"><label>证据类型</label><select class="select" id="video-type"><option value="">由系统依据文件名推断</option><option value="site_overview">箱体整体及安装环境</option><option value="permanent_label">永久编码与标识</option><option value="nap_internal_overview">箱内整体布置</option><option value="nap_port">NAP端口近景</option><option value="fiber_routing">引下光纤独立路由</option></select></div><div class="field"><label>已知工程编码（可选）</label><input class="input" id="video-code" placeholder="例如 PBO-JAD-MAR-0008"></div></div><div class="ocr-box"><strong>处理规则</strong><p>上传原视频保留在本地证据仓库；从 00:00:00 开始每隔 2 秒抽取 1 帧；关键帧 media_type 固定标记为 video_frame；所有帧进入待确认状态，可逐帧人工确认关联对象。</p></div>`,`<button class="btn" id="video-cancel">取消</button><button class="btn primary" id="video-submit">上传并抽帧</button>`)
  const input=document.querySelector('#video-file')
  input.onchange=()=>document.querySelector('#video-file-label').textContent=input.files[0]?.name||'点击选择一个 MP4 文件'
  document.querySelector('#video-cancel').onclick=closeModal
  document.querySelector('#video-submit').onclick=async()=>{
    if(!input.files[0])return toast('请选择 MP4 文件')
    const fd=new FormData();fd.append('file',input.files[0])
    const type=document.querySelector('#video-type').value,code=document.querySelector('#video-code').value
    if(type)fd.append('evidence_type',type);if(code)fd.append('detected_code',code)
    const submit=document.querySelector('#video-submit');submit.disabled=true;submit.textContent='正在抽帧...'
    try{
      const result=await request('/api/evidence/upload-video',{method:'POST',body:fd})
      closeModal();state.evidence.items=await request('/api/evidence');drawEvidencePage()
      openModal('视频抽帧完成',`<div class="metric-grid" style="grid-template-columns:repeat(3,1fr)"><div class="metric-card"><span>视频时长</span><strong>${Number(result.duration_seconds).toFixed(1)}s</strong></div><div class="metric-card"><span>抽帧间隔</span><strong>${result.interval_seconds}s</strong></div><div class="metric-card"><span>关键帧</span><strong>${result.extracted_frame_count}</strong></div></div><div class="section-title">已写入证据库</div><div class="thumb-grid">${result.frames.slice(0,12).map(f=>`<div class="thumb-card" data-video-frame="${f.evidence_id}"><img src="${f.url}"><span><b>${esc(f.evidence_id)}</b><br>${esc(f.filename)}</span></div>`).join('')}</div><p class="note" style="margin-top:12px">全部关键帧均处于“待确认”状态。点击任一关键帧进入候选对象匹配与人工确认。</p>`,`<button class="btn primary" id="video-done">完成</button>`)
      document.querySelector('#video-done').onclick=closeModal
      document.querySelectorAll('[data-video-frame]').forEach(el=>el.onclick=()=>{closeModal();openEvidence(el.dataset.videoFrame)})
      toast(`已生成 ${result.extracted_frame_count} 个视频关键帧`)
    }catch(err){submit.disabled=false;submit.textContent='上传并抽帧';toast(err.message)}
  }
}

function openUploadModal() {
  openModal('导入现场证据',`<label class="dropzone" for="upload-file"><strong id="upload-file-label">点击选择或拖入证据文件</strong><span>支持 JPG、PNG、WEBP、PDF；MP4 请使用“视频抽帧”</span></label><input id="upload-file" type="file" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"><div class="form-grid"><div class="field"><label>影像来源</label><select class="select" id="upload-source"><option>现场照片</option><option>PDF图像</option><option>视频帧</option><option>验收报告</option></select></div><div class="field"><label>证据类型</label><select class="select" id="upload-type"><option value="">由系统推断</option><option value="site_overview">箱体整体及安装环境</option><option value="permanent_label">永久编码与标识</option><option value="nap_internal_overview">箱内整体布置</option><option value="nap_port">NAP端口近景</option><option value="fiber_routing">引下光纤独立路由</option><option value="otdr_report">OTDR测试报告</option></select></div></div><div class="field"><label>已知工程编码（可选）</label><input class="input" id="upload-code" placeholder="例如 PBO-JAD-MAR-0008；留空则从文件名解析"></div>`,`<button class="btn" id="upload-cancel">取消</button><button class="btn primary" id="upload-submit">开始解析</button>`)
  const input=document.querySelector('#upload-file');input.onchange=()=>document.querySelector('#upload-file-label').textContent=input.files[0]?.name||'点击选择或拖入证据文件';document.querySelector('#upload-cancel').onclick=closeModal;document.querySelector('#upload-submit').onclick=async()=>{if(!input.files[0])return toast('请选择证据文件');const fd=new FormData();fd.append('file',input.files[0]);fd.append('source_type',document.querySelector('#upload-source').value);const type=document.querySelector('#upload-type').value,code=document.querySelector('#upload-code').value;if(type)fd.append('evidence_type',type);if(code)fd.append('detected_code',code);try{const e=await request('/api/evidence/upload',{method:'POST',body:fd});closeModal();toast('证据解析完成，请确认候选对象');state.evidence.items=await request('/api/evidence');drawEvidencePage();openEvidence(e.evidence_id)}catch(err){toast(err.message)}}
}
async function openEvidence(id) {
  const e=await request(`/api/evidence/${encodeURIComponent(id)}`)
  openDrawer('证据解析与对象匹配',`<div class="evidence-preview">${e.url&&['image','video_frame'].includes(e.media_type)?`<img src="${e.url}">`:`<div class="empty">${esc(e.filename)}</div>`}</div><table class="descriptions"><tr><th>证据编号</th><td>${esc(e.evidence_id)}</td><th>来源</th><td>${esc(e.source_type)}</td></tr><tr><th>识别编码</th><td>${esc(e.detected_code||'未识别')}</td><th>证据类型</th><td>${esc(e.evidence_label)}</td></tr><tr><th>审核状态</th><td>${esc(e.review_status)}</td><th>当前对象</th><td>${esc(e.linked_object_id||'未关联')}</td></tr></table><div class="ocr-box"><strong>文本 / OCR 结果</strong><p>${esc(e.ocr_text)}</p></div><div class="section-title">候选对象与可解释评分</div><div>${(e.candidates||[]).map((c,i)=>`<div class="candidate"><div class="candidate-rank">${i+1}</div><div><h4>${esc(c.object_id)} ${statusBadge(c.status)} <span class="status neutral">${c.score}%</span></h4><div class="candidate-reasons">${c.reasons.map(r=>`<span>${esc(r)}</span>`).join('')}</div><div class="progress-track"><div class="progress-fill" style="width:${c.score}%;background:${c.score>=90?'#20a36a':'#f59e0b'}"></div></div></div><button class="btn ${i===0?'primary':''}" data-confirm="${esc(c.object_id)}" data-score="${c.score}">确认关联</button></div>`).join('')}</div>${e.linked_object_id?`<div class="recommend" style="margin-top:18px"><div class="recommend-icon">✓</div><div><strong>当前归档关系：${esc(e.linked_object_id)}</strong><p>${esc(e.match_reason)}</p></div></div>`:''}`,560)
  document.querySelectorAll('[data-confirm]').forEach(b=>b.onclick=async()=>{try{const candidate=e.candidates.find(c=>c.object_id===b.dataset.confirm);await request(`/api/evidence/${encodeURIComponent(id)}/confirm-link`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({object_id:b.dataset.confirm,confidence_score:Number(b.dataset.score)/100,match_reason:candidate.reasons.join('；')})});toast(`已关联 ${b.dataset.confirm} 并完成对象复验`);state.evidence.items=await request('/api/evidence');openEvidence(id)}catch(err){toast(err.message)}})
}

async function renderLedger(){state.ledger.items=await request('/api/objects');drawLedgerPage()}
function drawLedgerPage(){const s=state.ledger;const filtered=s.items.filter(o=>(s.status==='全部'||o.verification_status===s.status)&&(!s.search||[o.object_id,o.object_type,o.site_id].some(v=>String(v).toLowerCase().includes(s.search.toLowerCase()))));const size=12,pages=Math.max(1,Math.ceil(filtered.length/size));s.page=Math.min(s.page,pages);const rows=filtered.slice((s.page-1)*size,s.page*size);page.innerHTML=pageHeader('对象验真台账','以工程对象为中心汇集设计属性、工序节点、规则判定、影像证据和问题记录。','<button class="btn" id="ledger-refresh">刷新数据</button>')+`<div class="toolbar"><select class="select" id="ledger-status">${['全部','已验真','部分匹配','缺失影像'].map(v=>`<option ${s.status===v?'selected':''}>${v}</option>`).join('')}</select><input class="input" id="ledger-search" placeholder="搜索对象编码、类型或所属区域" value="${esc(s.search)}"></div><div class="table-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>状态</th><th>对象编码</th><th>图层 / 类型</th><th>所属区域</th><th>完整率</th><th>必需节点</th><th>已完成</th><th>问题数</th><th>缺失工序 / 证据</th><th>最近更新</th></tr></thead><tbody>${rows.map(o=>`<tr><td>${statusBadge(o.verification_status)}</td><td><button class="btn text" data-ledger="${o.object_id}">${o.object_id}</button></td><td><strong>${o.layer}</strong><small style="display:block;color:#80909e">${esc(o.object_type)} · ${esc(o.structure_type)}</small></td><td>${esc(o.site_id)}</td><td>${progress(o.completeness)}</td><td>${o.required_count}</td><td>${o.matched_count}</td><td>${o.issue_count?`<span class="severity high">${o.issue_count}</span>`:'<span class="severity low">0</span>'}</td><td>${o.missing_evidence==='无'?'<span style="color:#18794e">✓ 无缺失</span>':`<span class="note">${esc(o.missing_evidence)}</span>`}</td><td>${fmtDate(o.updated_at)}</td></tr>`).join('')}</tbody></table></div>${pagination(filtered.length,s.page,pages,'ledger-page')}</div>`;document.querySelector('#ledger-refresh').onclick=renderLedger;document.querySelector('#ledger-status').onchange=e=>{s.status=e.target.value;s.page=1;drawLedgerPage()};document.querySelector('#ledger-search').oninput=e=>{s.search=e.target.value;s.page=1;drawLedgerPage()};document.querySelectorAll('[data-ledger]').forEach(b=>b.onclick=()=>openObjectLedger(b.dataset.ledger));document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{s.page=Number(b.dataset.page);drawLedgerPage()})}
async function openObjectLedger(id){const d=await request(`/api/objects/${encodeURIComponent(id)}`);const rules=d.rules.filter(r=>r.mandatory);const evidenceCards=d.evidence.length?`<div class="thumb-grid">${d.evidence.map(e=>`<div class="thumb-card">${e.url?`<img src="${e.url}">`:'<div class="thumb">▣</div>'}<span><b>${esc(e.evidence_label)}</b><br>${esc(e.filename)}</span></div>`).join('')}</div>`:'<div class="empty">暂无关联证据</div>';const issueCards=d.issues.length?d.issues.map(i=>`<div class="rule-item" style="grid-template-columns:auto 1fr auto;margin-bottom:8px">${severityBadge(i.severity)}<div><strong>${esc(i.title)}</strong><div class="note">${esc(i.description)}</div></div><span class="status neutral">${esc(i.status)}</span></div>`).join(''):'<div class="empty">暂无问题</div>';openDrawer('对象验真档案',`<div class="identity"><div><small>工程对象</small><h3>${esc(d.object.object_id)}</h3></div>${statusBadge(d.result.status)}</div><div class="recommend" style="margin:16px 0"><div class="recommend-icon">${Math.round(d.result.completeness*100)}%</div><div><strong>档案完整率</strong><p>${esc(d.result.missing_evidence==='无'?'所有强制节点均已匹配':'缺少：'+d.result.missing_evidence)}</p></div><button class="btn primary" id="reverify-btn">重新验真</button></div><div class="tabs"><button class="active" data-tab="info">对象信息</button><button data-tab="timeline">工序时间轴</button><button data-tab="rules">规则矩阵 (${rules.length})</button><button data-tab="evidence">证据 (${d.evidence.length})</button><button data-tab="issues">问题 (${d.issues.filter(i=>i.status!=='已关闭').length})</button></div><div class="tab-pane active" id="tab-info"><table class="descriptions"><tr><th>类型</th><td>${esc(d.object.object_type)} / ${esc(d.object.structure_type)}</td><th>图层</th><td>${esc(d.object.layer)}</td></tr><tr><th>所属区域</th><td>${esc(d.object.site_id)}</td><th>关联PTECH</th><td>${esc(d.object.ptc_code)}</td></tr><tr><th>敷设方式</th><td>${esc(d.object.mode_pose)}</td><th>容量</th><td>${esc(d.object.capacity)} 芯</td></tr><tr><th>上游光缆</th><td colspan="3">${esc(d.object.upstream_cable)}</td></tr><tr><th>坐标</th><td colspan="3">${Number(d.object.longitude).toFixed(6)}, ${Number(d.object.latitude).toFixed(6)}</td></tr></table></div><div class="tab-pane" id="tab-timeline"><div class="timeline">${d.timeline.map(t=>`<div class="timeline-item ${t.status==='完成'?'ok':'bad'}"><strong>${esc(t.stage)}</strong><p>${t.evidence.length?'证据：'+t.evidence.join('、'):'缺少对应证据'}</p></div>`).join('')}</div></div><div class="tab-pane" id="tab-rules"><div class="table-wrap"><table class="data-table" style="min-width:900px"><thead><tr><th>顺序</th><th>验收节点</th><th>规则要求</th><th>规则来源</th><th>匹配证据</th><th>结果</th></tr></thead><tbody>${rules.map(r=>`<tr><td>${r.sequence}</td><td>${esc(r.stage)}</td><td>${esc(r.required_evidence)}</td><td>${esc(r.source_doc)}</td><td>${r.matched_evidence.length?r.matched_evidence.map(x=>`<code>${x}</code>`).join(' '):'无'}</td><td>${statusBadge(r.passed?'完成':'缺失')}</td></tr>`).join('')}</tbody></table></div></div><div class="tab-pane" id="tab-evidence">${evidenceCards}</div><div class="tab-pane" id="tab-issues">${issueCards}</div>`,760);document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.tab-pane').forEach(p=>p.classList.toggle('active',p.id===`tab-${b.dataset.tab}`))});document.querySelector('#reverify-btn').onclick=async()=>{await request(`/api/objects/${encodeURIComponent(id)}/reverify`,{method:'POST'});toast('规则引擎已完成复验');if(state.route==='ledger')state.ledger.items=await request('/api/objects');openObjectLedger(id)}}

async function renderEvidence(){state.evidence.items=await request('/api/management/evidence');drawEvidencePage()}
function drawEvidencePage(){const s=state.evidence;const filtered=s.items.filter(e=>!s.search||[e.filename,e.task_name,e.object_name,stageNames[e.stage]].some(v=>String(v||'').includes(s.search)));page.innerHTML=pageHeader('影像证据中心','')+`<div class="toolbar"><input class="input" id="ev-search" placeholder="搜索文件、任务、对象或施工阶段" value="${esc(s.search)}"></div><div class="table-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>关键影像</th><th>视频来源</th><th>时间</th><th>施工阶段</th><th>施工任务</th><th>工程对象</th><th>验真状态</th></tr></thead><tbody>${filtered.length?filtered.map(e=>`<tr data-managed-evidence="${e.evidence_id}"><td>${e.url&&['image','video_frame'].includes(e.media_type)?`<img class="thumb" src="${e.url}">`:'<div class="thumb">▣</div>'}</td><td>${esc(e.filename)}</td><td>${fmtDate(e.captured_at||e.created_at)}</td><td>${esc(stageNames[e.stage]||e.stage||'待分析')}</td><td>${esc(e.task_name||'未关联施工任务')}</td><td>${esc(e.object_name||e.linked_object_id||'待关联')}</td><td>${statusBadge(e.review_status)}</td></tr>`).join(''):'<tr><td colspan="7"><div class="empty">暂无影像证据</div></td></tr>'}</tbody></table></div></div>`;document.querySelector('#ev-search').oninput=e=>{s.search=e.target.value;drawEvidencePage()};document.querySelectorAll('[data-managed-evidence]').forEach(row=>row.onclick=()=>openManagedEvidence(row.dataset.managedEvidence))}
function openManagedEvidence(id){const e=state.evidence.items.find(x=>x.evidence_id===id);if(!e)return;openDrawer('影像证据详情',`<div class="evidence-preview">${e.url&&['image','video_frame'].includes(e.media_type)?`<img src="${e.url}">`:`<div class="empty">${esc(e.filename)}</div>`}</div><table class="descriptions"><tr><th>视频来源</th><td>${esc(e.filename)}</td></tr><tr><th>记录时间</th><td>${fmtDate(e.captured_at||e.created_at)}</td></tr><tr><th>施工阶段</th><td>${esc(stageNames[e.stage]||e.stage||'待分析')}</td></tr><tr><th>施工任务</th><td>${esc(e.task_name)}</td></tr><tr><th>工程对象</th><td>${esc(e.object_name||e.linked_object_id||'待关联')}</td></tr><tr><th>验真状态</th><td>${esc(e.review_status)}</td></tr></table>`,520)}

renderLedger=async function(){state.ledger.items=await request('/api/management/engineering-objects');drawLedgerPage()}
drawLedgerPage=function(){const s=state.ledger;const filtered=s.items.filter(o=>(s.status==='全部'||o.verification_status===s.status)&&(!s.search||[o.id,o.name,o.type,o.location].some(v=>String(v||'').includes(s.search))));page.innerHTML=pageHeader('工程对象台账','')+`<div class="toolbar"><select class="select" id="ledger-status">${['全部','已验真','部分匹配','缺失影像'].map(v=>`<option ${s.status===v?'selected':''}>${v}</option>`).join('')}</select><input class="input" id="ledger-search" placeholder="搜索工程对象" value="${esc(s.search)}"></div><div class="table-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>工程对象</th><th>类型</th><th>位置</th><th>施工任务</th><th>影像证据</th><th>证据完整性</th><th>验真结果</th></tr></thead><tbody>${filtered.map(o=>`<tr><td><button class="btn text" data-ledger="${o.id}">${esc(o.name)}</button></td><td>${esc(o.type)}</td><td>${esc(o.location)}</td><td>${o.task_count}${o.task_names?`<span style="display:block">${esc(o.task_names)}</span>`:''}</td><td>${o.evidence_count}</td><td>${progress(o.completeness)}</td><td>${statusBadge(o.verification_status)}</td></tr>`).join('')}</tbody></table></div></div>`;document.querySelector('#ledger-status').onchange=e=>{s.status=e.target.value;drawLedgerPage()};document.querySelector('#ledger-search').oninput=e=>{s.search=e.target.value;drawLedgerPage()};document.querySelectorAll('[data-ledger]').forEach(b=>b.onclick=()=>openObjectLedger(b.dataset.ledger))}

function drawLedgerSpatialMap(items, gis) {
  const objects = items
    .filter(item => Number.isFinite(Number(item.longitude)) && Number.isFinite(Number(item.latitude)))
    .map(item => ({
      object_id: item.id,
      longitude: Number(item.longitude),
      latitude: Number(item.latitude),
      verification_status: item.verification_status || '缺失影像',
      completeness: Number(item.completeness || 0),
      issue_count: Number(item.issue_count || 0),
    }))
  if (!objects.length || !gis?.features?.length) {
    return '<div class="empty">当前没有可用于空间展示的 GIS 几何</div>'
  }
  return `${buildSvgMap(gis, objects, null)}<div class="map-toolbar">设计 GIS 图层 · 点击对象查看验真档案</div>`
}

async function renderIssues(){state.issues.items=await request('/api/issues');drawIssuesPage()}

renderLedger = async function(){
  const [items, gis] = await Promise.all([
    request('/api/management/engineering-objects'),
    request('/api/gis'),
  ])
  state.ledger.items = items
  state.ledger.gis = gis
  drawLedgerPage()
}

drawLedgerPage = function(){
  const s=state.ledger
  const filtered=s.items.filter(o=>(s.status==='全部'||o.verification_status===s.status)&&(!s.search||[o.id,o.name,o.type,o.location,o.layer].some(v=>String(v||'').toLowerCase().includes(s.search.toLowerCase()))))
  const mapItems=filtered.filter(o=>Number.isFinite(Number(o.longitude))&&Number.isFinite(Number(o.latitude)))
  page.innerHTML=pageHeader('工程对象台账','以工程对象为中心汇集设计空间、施工任务、影像证据和验真结果.','<button class="btn" id="ledger-refresh">刷新数据</button>')+
    `<div class="toolbar"><select class="select" id="ledger-status">${['全部','已验真','部分匹配','缺失影像'].map(v=>`<option ${s.status===v?'selected':''}>${v}</option>`).join('')}</select><input class="input" id="ledger-search" placeholder="搜索工程对象、图层或区域" value="${esc(s.search)}"></div>`+
    `<section class="panel ledger-map-panel"><div class="panel-head"><h2>工程对象空间分布</h2><span class="note">${mapItems.length} 个对象有坐标 · ${s.gis?.features?.length||0} 个设计图形</span></div><div class="ledger-map-stage" id="ledger-map-stage">${drawLedgerSpatialMap(mapItems,s.gis)}</div></section>`+
    `<div class="table-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>工程对象</th><th>图层 / 类型</th><th>位置</th><th>坐标</th><th>施工任务</th><th>影像证据</th><th>证据完整性</th><th>验真结果</th></tr></thead><tbody>${filtered.map(o=>`<tr><td><button class="btn text" data-ledger="${esc(o.id)}">${esc(o.name)}</button></td><td><strong>${esc(o.layer||o.type)}</strong><small style="display:block;color:#80909e">${esc(o.object_type||o.type)}</small></td><td>${esc(o.location)}</td><td>${o.longitude!=null&&o.latitude!=null?`${Number(o.longitude).toFixed(6)}, ${Number(o.latitude).toFixed(6)}`:'-'}</td><td>${o.task_count}${o.task_names?`<span style="display:block">${esc(o.task_names)}</span>`:''}</td><td>${o.evidence_count}</td><td>${progress(o.completeness)}</td><td>${statusBadge(o.verification_status)}</td></tr>`).join('')}</tbody></table></div></div>`
  document.querySelector('#ledger-refresh').onclick=renderLedger
  document.querySelector('#ledger-status').onchange=e=>{s.status=e.target.value;drawLedgerPage()}
  document.querySelector('#ledger-search').oninput=e=>{s.search=e.target.value;drawLedgerPage()}
  document.querySelectorAll('[data-ledger]').forEach(b=>b.onclick=()=>openObjectLedger(b.dataset.ledger))
  document.querySelectorAll('#ledger-map-stage [data-object]').forEach(g=>g.onclick=()=>openObjectLedger(g.dataset.object))
}
function drawIssuesPage(){const s=state.issues;const types=['安全违规','影像缺失','工序缺失','资料缺失','编码未匹配','对象未关联','完整率不足','缺少测试/报告','节点顺序异常'];const counts=Object.fromEntries(types.map(t=>[t,s.items.filter(i=>i.issue_type===t&&i.status!=='已关闭').length]));const filtered=s.items.filter(i=>(!s.search||[i.issue_id,i.title,i.description,i.object_id].some(v=>String(v||'').toLowerCase().includes(s.search.toLowerCase())))&&(!s.type||i.issue_type===s.type)&&(!s.severity||i.severity===s.severity)&&(!s.status||i.status===s.status));const size=12,pages=Math.max(1,Math.ceil(filtered.length/size));s.page=Math.min(s.page,pages);const rows=filtered.slice((s.page-1)*size,s.page*size);page.innerHTML=pageHeader('问题处置中心','','<button class="btn" id="issue-refresh">刷新</button>')+`<div class="issue-closure-flow">${['发现问题','补充证据','重新分析','关闭问题'].map((step,index,array)=>`<strong>${step}</strong>${index<array.length-1?'<i>→</i>':''}`).join('')}</div><div class="issue-type-grid">${types.map(t=>`<button data-issue-type="${t}" class="${s.type===t?'active':''}"><span>${t}</span><strong>${counts[t]}</strong></button>`).join('')}</div><div class="toolbar" style="margin-top:12px"><input class="input" id="issue-search" placeholder="搜索问题编号、对象或描述" value="${esc(s.search)}"><select class="select" id="issue-severity"><option value="">全部等级</option>${['高','中','低'].map(v=>`<option ${s.severity===v?'selected':''}>${v}</option>`).join('')}</select><select class="select" id="issue-status"><option value="">全部状态</option>${['新发现','待确认','待整改','已补证','已关闭'].map(v=>`<option ${s.status===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="table-panel"><div class="table-wrap"><table class="data-table"><thead><tr><th>问题编号</th><th>等级</th><th>问题类型</th><th>工程对象</th><th>问题内容</th><th>触发来源</th><th>责任人</th><th>状态</th><th>更新时间</th></tr></thead><tbody>${rows.map(i=>`<tr><td><button class="btn text" data-issue="${i.issue_id}">${i.issue_id}</button></td><td>${severityBadge(i.severity)}</td><td>${esc(i.issue_type)}</td><td>${esc(i.object_id||'未关联')}</td><td><strong>${esc(i.title)}</strong></td><td>${esc(i.source)}</td><td>${esc(i.assignee||'未分派')}</td><td><span class="status neutral">${esc(i.status)}</span></td><td>${fmtDate(i.updated_at)}</td></tr>`).join('')}</tbody></table></div>${pagination(filtered.length,s.page,pages,'issue-page')}</div>`;document.querySelector('#issue-refresh').onclick=renderIssues;document.querySelector('#issue-search').oninput=e=>{s.search=e.target.value;s.page=1;drawIssuesPage()};document.querySelector('#issue-severity').onchange=e=>{s.severity=e.target.value;s.page=1;drawIssuesPage()};document.querySelector('#issue-status').onchange=e=>{s.status=e.target.value;s.page=1;drawIssuesPage()};document.querySelectorAll('[data-issue-type]').forEach(b=>b.onclick=()=>{s.type=s.type===b.dataset.issueType?'':b.dataset.issueType;s.page=1;drawIssuesPage()});document.querySelectorAll('[data-issue]').forEach(b=>b.onclick=()=>openIssue(b.dataset.issue));document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{s.page=Number(b.dataset.page);drawIssuesPage()})}
function openIssue(id){const i=state.issues.items.find(x=>x.issue_id===id);if(!i)return;openDrawer('问题详情',`<div class="identity"><div><small>${esc(i.issue_type)}</small><h3>${esc(i.title)}</h3></div>${severityBadge(i.severity)}</div><p class="note" style="font-size:12px;line-height:1.7;margin:14px 0">${esc(i.description)}</p><table class="descriptions"><tr><th>问题编号</th><td>${esc(i.issue_id)}</td></tr><tr><th>工程对象</th><td>${esc(i.object_id||'未关联')}</td></tr><tr><th>关联证据</th><td>${esc(i.evidence_id||'无')}</td></tr><tr><th>触发规则</th><td>${esc(i.rule_id||'系统检查')}</td></tr><tr><th>发现来源</th><td>${esc(i.source)}</td></tr><tr><th>当前状态</th><td>${esc(i.status)}</td></tr><tr><th>责任人</th><td>${esc(i.assignee||'未分派')}</td></tr><tr><th>整改期限</th><td>${esc(i.due_date||'未设置')}</td></tr></table>${i.resolution_note?`<div class="ocr-box"><strong>处置记录</strong><p>${esc(i.resolution_note)}</p></div>`:''}<div style="margin-top:18px"><button class="btn primary" id="update-issue">更新处置</button></div>`,520);document.querySelector('#update-issue').onclick=()=>openIssueUpdate(i)}
function openIssueUpdate(i){openModal('更新问题处置',`<div class="field"><label>处置状态</label><select class="select" id="upd-status">${['新发现','待确认','待整改','已补证','已关闭'].map(v=>`<option ${i.status===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="form-grid"><div class="field"><label>责任人</label><input class="input" id="upd-assignee" value="${esc(i.assignee||'')}" placeholder="施工队A / 张工"></div><div class="field"><label>整改期限</label><input class="input" id="upd-due" value="${esc(i.due_date||'')}" placeholder="YYYY-MM-DD"></div></div><div class="field"><label>处置记录</label><textarea id="upd-note" placeholder="说明整改措施、补充证据或关闭依据">${esc(i.resolution_note||'')}</textarea></div>`,`<button class="btn" id="upd-cancel">取消</button><button class="btn primary" id="upd-save">保存</button>`);document.querySelector('#upd-cancel').onclick=closeModal;document.querySelector('#upd-save').onclick=async()=>{try{await request(`/api/issues/${encodeURIComponent(i.issue_id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:document.querySelector('#upd-status').value,assignee:document.querySelector('#upd-assignee').value||null,due_date:document.querySelector('#upd-due').value||null,resolution_note:document.querySelector('#upd-note').value||null})});closeModal();closeDrawer();toast('问题处置状态已更新');state.issues.items=await request('/api/issues');drawIssuesPage()}catch(err){toast(err.message)}}}

const openManagedIssue=function(id){const i=state.issues.items.find(x=>x.issue_id===id);if(!i)return;openDrawer('问题详情',`<div class="identity"><div><small>${esc(i.issue_type)}</small><h3>${esc(i.title)}</h3></div>${severityBadge(i.severity)}</div><p class="note" style="font-size:12px;line-height:1.7;margin:14px 0">${esc(i.description)}</p><table class="descriptions"><tr><th>工程对象</th><td>${esc(i.object_id||'待关联')}</td></tr><tr><th>问题类型</th><td>${esc(i.issue_type)}</td></tr><tr><th>当前状态</th><td>${esc(i.status)}</td></tr><tr><th>责任人</th><td>${esc(i.assignee||'未分派')}</td></tr><tr><th>整改期限</th><td>${esc(i.due_date||'未设置')}</td></tr></table>${i.resolution_note?`<div class="ocr-box"><strong>处置记录</strong><p>${esc(i.resolution_note)}</p></div>`:''}<div style="display:flex;gap:8px;margin-top:18px"><button class="btn" id="issue-supply">补证上传</button><button class="btn" id="issue-reverify">重新验真</button><button class="btn primary" id="update-issue">更新处置</button></div>`,520);document.querySelector('#update-issue').onclick=()=>openIssueUpdate(i);document.querySelector('#issue-supply').onclick=()=>{closeDrawer();navigate('collection')};document.querySelector('#issue-reverify').onclick=async()=>{if(!i.object_id)return toast('问题尚未关联工程对象');try{await request(`/api/objects/${encodeURIComponent(i.object_id)}/reverify`,{method:'POST'});toast('已完成重新验真')}catch(err){toast(err.message)}}}
openIssue=openManagedIssue

async function renderDelivery(){
  const overview=await request('/api/management/platform-overview')
  const layers=overview.layers
  page.innerHTML=pageHeader('数字交付中心','',`<button class="btn primary" id="build-delivery">生成可信交付档案</button>`)+`
    <section class="delivery-chain">
      ${[['项目',1],['工程对象',layers.object_count],['施工过程',layers.collected_count],['分析结果',layers.analyzed_video_count],['影像证据',layers.evidence_count],['验真交付',layers.delivery_count]].map(([name,count],index,array)=>`<div><span>${esc(name)}</span><strong>${count}</strong></div>${index<array.length-1?'<i>→</i>':''}`).join('')}
    </section>
    <div class="grid two-col delivery-downloads">
      ${panel('可信交付报告',`<div class="delivery-actions"><a class="btn" href="/api/exports/excel">验真数据表</a><a class="btn" href="/api/exports/pdf">验真报告</a><a class="btn primary" href="/api/exports/archive">数字资产包</a></div>`)}
      ${panel('交付记录',overview.reports.length?overview.reports.map(report=>`<div class="delivery-report"><div><strong>${esc(report.title)}</strong><span>${fmtDate(report.generated_at)}</span></div>${statusBadge(report.status)}</div>`).join(''):'<div class="empty">尚未生成项目交付记录</div>')}
    </div>`
  document.querySelector('#build-delivery').onclick=async()=>{
    const button=document.querySelector('#build-delivery');button.disabled=true;button.textContent='正在生成交付档案'
    try{await request(`/api/ai/projects/${encodeURIComponent(overview.project_id)}/deliver`,{method:'POST'});toast('可信交付档案已生成');renderDelivery()}
    catch(error){button.disabled=false;button.textContent='生成可信交付档案';toast(error.message)}
  }
}

async function init(){try{await loadProject();const route=location.hash.replace('#','')||'dashboard';navigate(['dashboard','collection','analysis','verification','evidence','ledger','issues','delivery'].includes(route)?route:'dashboard')}catch(error){page.innerHTML=`<div class="panel"><div class="panel-body"><h2>系统初始化失败</h2><p>${esc(error.message)}</p></div></div>`}}
init()
