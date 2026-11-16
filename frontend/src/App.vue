<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Activity,
  AlertTriangle,
  BadgeInfo,
  Bell,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  Clock3,
  Database,
  Eye,
  FileArchive,
  FileImage,
  FileUp,
  Hash,
  History,
  ImagePlus,
  Layers3,
  LoaderCircle,
  Menu,
  MousePointer2,
  PanelLeftClose,
  Play,
  RefreshCw,
  ScanLine,
  Search,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Stethoscope,
  SunMedium,
  UploadCloud,
  UserRound,
  Wifi,
  WifiOff,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-vue-next'
import { apiRequest } from './api'
import { parseDicomFile } from './dicom'
import { readZipSlices } from './zipReader'

const currentView = ref('workspace')
const mobileNavOpen = ref(false)
const backendOnline = ref(null)
const checkingHealth = ref(false)
const draggedOver = ref(false)
const patientId = ref('')
const patientName = ref('')
const fileError = ref('')
const viewerError = ref('')
const requestError = ref('')
const uploadedCase = ref(null)
const analysis = ref(null)
const operation = ref('idle')
const historyItems = ref([])
const historyLoading = ref(false)
const historyQuery = ref('')
const selectedCase = ref(null)
const zoom = ref(1)
const brightness = ref(1)
const contrast = ref(1)
const overlayOpacity = ref(0.58)
const showOverlay = ref(true)
const imageCanvas = ref(null)
const markCanvas = ref(null)
const fileInput = ref(null)

// ===== CT 序列（ZIP 导入）状态 =====
const series = ref(null)
const sliceIndex = ref(0)
const sliceMeta = ref(null)
const sliceDragging = ref(false)
const sliceCache = new Map()
const SLICE_CACHE_LIMIT = 96
let sliceRenderToken = 0
let sliceDragState = null
const DRAG_STEP_PX = 14

const navigation = [
  { id: 'workspace', label: '影像工作台', icon: ScanLine },
  { id: 'history', label: '病例记录', icon: History },
  { id: 'model', label: '模型说明', icon: BrainCircuit },
]

const workflowStep = computed(() => {
  if (analysis.value) return 3
  if (uploadedCase.value) return 2
  if (series.value) return 1
  return 0
})

const isBusy = computed(() => ['uploading', 'analyzing'].includes(operation.value))
const sliceCount = computed(() => series.value?.slices.length || 0)
const currentSlice = computed(() => series.value?.slices[sliceIndex.value] || null)
const currentIsDicom = computed(() => currentSlice.value?.kind === 'dicom')
const canUpload = computed(() => series.value && currentIsDicom.value && !isBusy.value && !uploadedCase.value)
const canAnalyze = computed(() => uploadedCase.value && !analysis.value && !isBusy.value)
const currentCase = computed(() => uploadedCase.value || selectedCase.value)
const dicomMeta = computed(() => currentCase.value?.dicom_metadata || sliceMeta.value || {})
const nodules = computed(() => analysis.value?.nodules || currentCase.value?.analysis?.nodules || [])

const filteredHistory = computed(() => {
  const query = historyQuery.value.trim().toLowerCase()
  if (!query) return historyItems.value
  return historyItems.value.filter((item) =>
    [item.patient_name, item.patient_id, item.case_id, item.filename]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query)),
  )
})

const formatDate = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

const formatStudyDate = (value) => {
  if (!value || value.length !== 8) return value || '—'
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`
}

const formatBytes = (size) => {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const statusLabel = (status) => {
  const labels = {
    uploaded: '待分析',
    analyzed: '已完成',
    processing: '分析中',
  }
  return labels[status] || status || '未知'
}

async function checkBackend() {
  checkingHealth.value = true
  try {
    await apiRequest('/health')
    backendOnline.value = true
  } catch {
    backendOnline.value = false
  } finally {
    checkingHealth.value = false
  }
}

function openFilePicker() {
  fileInput.value?.click()
}

function onDrop(event) {
  draggedOver.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) handleFile(file)
}

function onFileChange(event) {
  const file = event.target.files?.[0]
  if (file) handleFile(file)
  event.target.value = ''
}

const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.bmp', '.webp']
const isImageFile = (name) => IMAGE_EXTENSIONS.some((ext) => name.toLowerCase().endsWith(ext))
const isDicomFile = (name) => ['.dcm', '.dicom'].some((ext) => name.toLowerCase().endsWith(ext))

async function handleFile(file) {
  fileError.value = ''
  viewerError.value = ''
  requestError.value = ''

  const lowerName = file.name.toLowerCase()
  const slices = []

  if (lowerName.endsWith('.zip')) {
    operation.value = 'reading'
    try {
      const zipSlices = await readZipSlices(file)
      slices.push(...zipSlices)
    } catch (error) {
      fileError.value = error.message
      operation.value = 'idle'
      return
    }
  } else if (isDicomFile(lowerName) || isImageFile(lowerName)) {
    slices.push({
      name: file.name,
      path: file.name,
      kind: isDicomFile(lowerName) ? 'dicom' : 'image',
      mime: isDicomFile(lowerName) ? 'application/dicom' : file.type || 'image/png',
      size: file.size,
      read: async () => new Uint8Array(await file.arrayBuffer()),
    })
  } else {
    fileError.value = '请导入 ZIP 压缩包（内含 CT 切片）或单张 .dcm / 影像文件'
    return
  }

  uploadedCase.value = null
  analysis.value = null
  selectedCase.value = null
  sliceCache.clear()
  sliceMeta.value = null
  resetViewer()
  series.value = {
    fileName: file.name,
    fileSize: file.size,
    source: lowerName.endsWith('.zip') ? 'zip' : 'single',
    slices,
  }
  await showSlice(0)
}

function removeSeries() {
  series.value = null
  sliceIndex.value = 0
  sliceMeta.value = null
  sliceCache.clear()
  uploadedCase.value = null
  analysis.value = null
  requestError.value = ''
  viewerError.value = ''
  patientId.value = ''
  patientName.value = ''
  resetViewer()
  drawEmptyViewer()
}

// ===== 切片渲染：惰性解压 + FIFO 缓存 =====
function cacheSlice(index, rendered) {
  sliceCache.set(index, rendered)
  while (sliceCache.size > SLICE_CACHE_LIMIT) {
    sliceCache.delete(sliceCache.keys().next().value)
  }
}

async function showSlice(index) {
  if (!series.value) return
  const target = Math.min(Math.max(index, 0), series.value.slices.length - 1)
  sliceIndex.value = target
  const token = ++sliceRenderToken
  operation.value = 'reading'
  viewerError.value = ''

  try {
    let rendered = sliceCache.get(target)
    const slice = series.value.slices[target]

    if (!rendered) {
      const bytes = await slice.read()
      if (token !== sliceRenderToken) return

      if (slice.kind === 'dicom') {
        try {
          const parsed = await parseDicomFile(new Blob([bytes]))
          rendered = { type: 'dicom', ...parsed }
        } catch (error) {
          viewerError.value = `${slice.name}：${error.message}`
          drawEmptyViewer()
          return
        }
      } else {
        const bitmap = await createImageBitmap(new Blob([bytes], { type: slice.mime }))
        if (token !== sliceRenderToken) {
          bitmap.close?.()
          return
        }
        rendered = { type: 'image', bitmap, width: bitmap.width, height: bitmap.height, metadata: null }
      }
      cacheSlice(target, rendered)
    }

    if (token !== sliceRenderToken) return
    sliceMeta.value = rendered.metadata || null

    if (!patientId.value && rendered.metadata?.patientId) patientId.value = rendered.metadata.patientId
    if (!patientName.value && rendered.metadata?.patientName) patientName.value = rendered.metadata.patientName

    drawSlice(rendered)
  } finally {
    if (token === sliceRenderToken) operation.value = 'idle'
  }
}

function drawSlice(rendered) {
  const canvas = imageCanvas.value
  if (!canvas) return
  canvas.width = rendered.width
  canvas.height = rendered.height
  const context = canvas.getContext('2d')
  if (rendered.type === 'dicom') {
    context.putImageData(rendered.imageData, 0, 0)
  } else {
    context.drawImage(rendered.bitmap, 0, 0, rendered.width, rendered.height)
  }
  drawAnnotations()
}

function changeSlice(delta) {
  if (!series.value || sliceCount.value < 2) return
  showSlice(sliceIndex.value + delta)
}

function onSliceInput(event) {
  showSlice(Number(event.target.value))
}

// 滚轮翻阅切片
function onViewerWheel(event) {
  if (!series.value || sliceCount.value < 2) return
  changeSlice(event.deltaY > 0 ? 1 : -1)
}

// 拖动翻阅切片：按住影像上下（或左右）拖动即可切换切片
function onPointerDown(event) {
  if (!series.value || sliceCount.value < 2) return
  if (event.button !== 0) return
  sliceDragState = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    startIndex: sliceIndex.value,
  }
  sliceDragging.value = true
  try {
    event.currentTarget.setPointerCapture(event.pointerId)
  } catch {
    /* 某些环境不支持指针捕获时忽略 */
  }
}

function onPointerMove(event) {
  if (!sliceDragState || event.pointerId !== sliceDragState.pointerId) return
  const deltaX = event.clientX - sliceDragState.startX
  const deltaY = event.clientY - sliceDragState.startY
  const offset = Math.abs(deltaX) > Math.abs(deltaY) ? deltaX : deltaY
  const steps = Math.round(-offset / DRAG_STEP_PX)
  const target = Math.min(
    Math.max(sliceDragState.startIndex + steps, 0),
    sliceCount.value - 1,
  )
  if (target !== sliceIndex.value) {
    sliceIndex.value = target
    showSlice(target)
  }
}

function endSliceDrag(event) {
  if (sliceDragState && event?.pointerId !== undefined && event?.pointerId !== sliceDragState.pointerId) return
  sliceDragState = null
  sliceDragging.value = false
}

function onKeydown(event) {
  if (currentView.value !== 'workspace' || !series.value) return
  if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
    event.preventDefault()
    changeSlice(-1)
  } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
    event.preventDefault()
    changeSlice(1)
  }
}

async function buildUploadFile() {
  const slice = currentSlice.value
  if (!slice || slice.kind !== 'dicom') return null
  const bytes = await slice.read()
  return new File([bytes], slice.name, { type: 'application/dicom' })
}

async function uploadCase() {
  if (!canUpload.value) return
  operation.value = 'uploading'
  requestError.value = ''

  try {
    const file = await buildUploadFile()
    if (!file) throw new Error('当前切片不是 DICOM 文件，无法上传')
    const form = new FormData()
    form.append('file', file)
    if (patientId.value.trim()) form.append('patient_id', patientId.value.trim())
    if (patientName.value.trim()) form.append('patient_name', patientName.value.trim())

    const response = await apiRequest('/api/upload', { method: 'POST', body: form })
    uploadedCase.value = response.case
    backendOnline.value = true
  } catch (error) {
    requestError.value = error.message
    backendOnline.value = false
  } finally {
    operation.value = 'idle'
  }
}

async function analyzeCase() {
  if (!uploadedCase.value?.case_id) return
  operation.value = 'analyzing'
  requestError.value = ''

  try {
    const response = await apiRequest('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case_id: uploadedCase.value.case_id }),
    })
    analysis.value = response.analysis
    uploadedCase.value = { ...uploadedCase.value, status: response.status, analysis: response.analysis }
    backendOnline.value = true
    await nextTick()
    drawAnnotations()
  } catch (error) {
    requestError.value = error.message
  } finally {
    operation.value = 'idle'
  }
}

async function loadHistory() {
  historyLoading.value = true
  requestError.value = ''
  try {
    const response = await apiRequest('/api/history?limit=100')
    historyItems.value = response.items || []
    backendOnline.value = true
  } catch (error) {
    requestError.value = error.message
    backendOnline.value = false
  } finally {
    historyLoading.value = false
  }
}

async function openHistoryCase(item) {
  requestError.value = ''
  try {
    const response = await apiRequest(`/api/cases/${item.case_id}`)
    selectedCase.value = response.case
    uploadedCase.value = null
    series.value = null
    sliceIndex.value = 0
    sliceMeta.value = null
    sliceCache.clear()
    analysis.value = response.case.analysis || null
    currentView.value = 'workspace'
    mobileNavOpen.value = false
    drawEmptyViewer()
    await nextTick()
    drawAnnotations()
  } catch (error) {
    requestError.value = error.message
  }
}

function selectView(view) {
  currentView.value = view
  mobileNavOpen.value = false
  if (view === 'history') loadHistory()
  if (view === 'workspace') {
    nextTick(() => {
      if (series.value) showSlice(sliceIndex.value)
      else drawEmptyViewer()
    })
  }
}

function drawEmptyViewer() {
  const canvas = imageCanvas.value
  if (!canvas) return
  const size = 720
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')
  context.fillStyle = '#071012'
  context.fillRect(0, 0, size, size)

  context.strokeStyle = 'rgba(132, 170, 174, .08)'
  context.lineWidth = 1
  for (let i = 40; i < size; i += 40) {
    context.beginPath()
    context.moveTo(i, 0)
    context.lineTo(i, size)
    context.stroke()
    context.beginPath()
    context.moveTo(0, i)
    context.lineTo(size, i)
    context.stroke()
  }

  context.strokeStyle = 'rgba(80, 211, 190, .3)'
  context.lineWidth = 2
  context.beginPath()
  context.arc(size / 2, size / 2, 170, 0, Math.PI * 2)
  context.stroke()
  context.beginPath()
  context.arc(size / 2, size / 2, 255, 0, Math.PI * 2)
  context.stroke()

  context.fillStyle = 'rgba(133, 161, 164, .55)'
  context.textAlign = 'center'
  context.font = '500 20px Inter, sans-serif'
  context.fillText('等待载入 CT 影像序列', size / 2, size / 2 - 2)
  context.fillStyle = 'rgba(133, 161, 164, .32)'
  context.font = '400 14px Inter, sans-serif'
  context.fillText('DROP ZIP SERIES OR .DCM FILE TO PREVIEW', size / 2, size / 2 + 30)
  drawAnnotations()
}

function drawAnnotations() {
  const source = imageCanvas.value
  const canvas = markCanvas.value
  if (!source || !canvas) return
  canvas.width = source.width
  canvas.height = source.height
  const context = canvas.getContext('2d')
  context.clearRect(0, 0, canvas.width, canvas.height)

  nodules.value.forEach((nodule, index) => {
    const box = nodule.bbox
    if (!box) return
    const color = '#ffb44a'
    context.strokeStyle = color
    context.fillStyle = 'rgba(255, 180, 74, .12)'
    context.lineWidth = Math.max(2, canvas.width / 280)
    context.strokeRect(box.x, box.y, box.width, box.height)
    context.fillRect(box.x, box.y, box.width, box.height)

    const label = `N${index + 1}`
    context.font = `600 ${Math.max(12, canvas.width / 38)}px Inter, sans-serif`
    const labelWidth = context.measureText(label).width + 12
    const labelHeight = Math.max(22, canvas.width / 25)
    const labelY = Math.max(0, box.y - labelHeight)
    context.fillStyle = color
    context.fillRect(box.x, labelY, labelWidth, labelHeight)
    context.fillStyle = '#16120b'
    context.fillText(label, box.x + 6, labelY + labelHeight * 0.72)
  })
}

function resetViewer() {
  zoom.value = 1
  brightness.value = 1
  contrast.value = 1
  overlayOpacity.value = 0.58
}

watch(
  () => nodules.value,
  () => nextTick(drawAnnotations),
  { deep: true },
)

onMounted(() => {
  drawEmptyViewer()
  checkBackend()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ 'sidebar--open': mobileNavOpen }">
      <div class="brand">
        <div class="brand__mark"><ScanLine :size="24" stroke-width="1.8" /></div>
        <div>
          <strong>Lung<span>AI</span></strong>
          <small>智能影像分析平台</small>
        </div>
        <button class="icon-button sidebar__close" aria-label="关闭导航" @click="mobileNavOpen = false">
          <PanelLeftClose :size="19" />
        </button>
      </div>

      <div class="sidebar__section-label">临床工作区</div>
      <nav class="sidebar__nav" aria-label="主导航">
        <button
          v-for="item in navigation"
          :key="item.id"
          :class="{ active: currentView === item.id }"
          @click="selectView(item.id)"
        >
          <component :is="item.icon" :size="18" stroke-width="1.8" />
          <span>{{ item.label }}</span>
          <ChevronRight v-if="currentView === item.id" class="nav-chevron" :size="16" />
        </button>
      </nav>

      <div class="sidebar__foot">
        <div class="privacy-card">
          <ShieldCheck :size="18" />
          <div>
            <strong>数据隐私保护</strong>
            <span>影像仅用于本次分析流程</span>
          </div>
        </div>
        <div class="version-row">
          <span>Clinical preview</span>
          <span>v1.1</span>
        </div>
      </div>
    </aside>

    <div v-if="mobileNavOpen" class="sidebar-backdrop" @click="mobileNavOpen = false"></div>

    <main class="main-shell">
      <header class="topbar">
        <div class="topbar__left">
          <button class="icon-button mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true">
            <Menu :size="20" />
          </button>
          <div>
            <p class="eyebrow">Lung nodule CAD workstation</p>
            <h1>{{ navigation.find((item) => item.id === currentView)?.label }}</h1>
          </div>
        </div>
        <div class="topbar__right">
          <button
            class="connection-pill"
            :class="{ online: backendOnline === true, offline: backendOnline === false }"
            @click="checkBackend"
          >
            <LoaderCircle v-if="checkingHealth" class="spin" :size="14" />
            <Wifi v-else-if="backendOnline" :size="14" />
            <WifiOff v-else :size="14" />
            {{ backendOnline ? '服务已连接' : '后端未连接' }}
          </button>
          <button class="icon-button notification" aria-label="通知">
            <Bell :size="18" />
            <span></span>
          </button>
          <div class="clinician">
            <div class="clinician__avatar"><Stethoscope :size="17" /></div>
            <div><strong>影像科工作站</strong><span>辅助诊断模式</span></div>
          </div>
        </div>
      </header>

      <div class="content-area">
        <div v-if="requestError" class="global-alert" role="alert">
          <AlertTriangle :size="18" />
          <span>{{ requestError }}</span>
          <button aria-label="关闭提示" @click="requestError = ''"><X :size="16" /></button>
        </div>

        <template v-if="currentView === 'workspace'">
          <section class="workspace-intro">
            <div>
              <span class="section-kicker"><Activity :size="14" /> AI 辅助检测</span>
              <h2>从影像上传到结构化结论，<br /><em>让每一步都清晰可见。</em></h2>
            </div>
            <div class="workflow-track" aria-label="分析流程">
              <div v-for="(step, index) in ['载入序列', '上传病例', 'AI 分析', '查看报告']" :key="step" class="workflow-step">
                <span :class="{ complete: workflowStep > index, current: workflowStep === index }">
                  <CheckCircle2 v-if="workflowStep > index" :size="15" />
                  <template v-else>{{ index + 1 }}</template>
                </span>
                <small>{{ step }}</small>
              </div>
            </div>
          </section>

          <section class="workspace-grid">
            <div class="viewer-card panel">
              <div class="panel__header viewer-header">
                <div>
                  <span class="panel__index">01</span>
                  <div>
                    <h3>CT 影像阅片</h3>
                    <p>{{ series?.fileName || currentCase?.filename || '尚未载入影像' }}</p>
                  </div>
                </div>
                <div class="viewer-tools">
                  <button class="icon-button" aria-label="缩小" @click="zoom = Math.max(0.6, zoom - 0.1)"><ZoomOut :size="17" /></button>
                  <span>{{ Math.round(zoom * 100) }}%</span>
                  <button class="icon-button" aria-label="放大" @click="zoom = Math.min(2.4, zoom + 0.1)"><ZoomIn :size="17" /></button>
                  <button class="icon-button" aria-label="重置阅片参数" @click="resetViewer"><RefreshCw :size="16" /></button>
                </div>
              </div>

              <div
                class="viewer-stage"
                :class="{ 'viewer-stage--series': series && sliceCount > 1, 'viewer-stage--dragging': sliceDragging }"
                @wheel.prevent="onViewerWheel"
                @pointerdown="onPointerDown"
                @pointermove="onPointerMove"
                @pointerup="endSliceDrag"
                @pointercancel="endSliceDrag"
              >
                <div class="viewer-stage__meta viewer-stage__meta--top">
                  <span>{{ dicomMeta.modality || 'CT' }}</span>
                  <span>{{ currentCase?.patient_id || patientId || 'ANONYMOUS' }}</span>
                  <span>{{ formatStudyDate(dicomMeta.study_date || dicomMeta.studyDate) }}</span>
                </div>
                <div
                  class="viewer-image"
                  :style="{
                    transform: `scale(${zoom})`,
                    filter: `brightness(${brightness}) contrast(${contrast})`,
                  }"
                >
                  <canvas ref="imageCanvas"></canvas>
                  <img
                    v-if="analysis?.cam_overlay_base64 && showOverlay"
                    :src="analysis.cam_overlay_base64"
                    class="cam-overlay"
                    :style="{ opacity: overlayOpacity }"
                    alt="AI Grad-CAM 热力图"
                  />
                  <canvas ref="markCanvas" class="mark-layer"></canvas>
                </div>
                <div class="viewer-stage__meta viewer-stage__meta--bottom">
                  <span>WW {{ dicomMeta.window_width || dicomMeta.windowWidth || '—' }}</span>
                  <span>WL {{ dicomMeta.window_center || dicomMeta.windowCenter || '—' }}</span>
                  <span>{{ dicomMeta.slice_thickness || dicomMeta.sliceThickness || '—' }} mm</span>
                </div>

                <div v-if="series && sliceCount > 1" class="slice-badge" aria-live="polite">
                  <Layers3 :size="12" /> IM {{ sliceIndex + 1 }} / {{ sliceCount }}
                </div>
                <div v-if="series && sliceCount > 1 && !sliceDragging" class="slice-hint">
                  <MousePointer2 :size="12" /> 拖动 / 滚轮 / 方向键翻阅切片
                </div>
                <div v-if="operation === 'reading'" class="slice-loading">
                  <LoaderCircle class="spin" :size="16" /> 正在解析切片…
                </div>
                <div v-if="!series && !selectedCase" class="viewer-empty-hint">
                  <ScanLine :size="24" />
                  <strong>载入 CT 影像序列开始阅片</strong>
                  <span>支持导入 ZIP 压缩包或单张 .dcm 切片浏览器预览</span>
                </div>
              </div>

              <div v-if="series && sliceCount > 1" class="slice-bar">
                <button class="icon-button" aria-label="上一张切片" :disabled="sliceIndex === 0" @click="changeSlice(-1)">
                  <ChevronLeft :size="16" />
                </button>
                <input
                  class="slice-slider"
                  type="range"
                  min="0"
                  :max="sliceCount - 1"
                  step="1"
                  :value="sliceIndex"
                  :aria-label="`切片序号，共 ${sliceCount} 张`"
                  @input="onSliceInput"
                />
                <span class="slice-counter">切片 {{ sliceIndex + 1 }} / {{ sliceCount }}</span>
                <button class="icon-button" aria-label="下一张切片" :disabled="sliceIndex >= sliceCount - 1" @click="changeSlice(1)">
                  <ChevronRight :size="16" />
                </button>
              </div>

              <div class="viewer-controls">
                <label>
                  <SunMedium :size="15" />
                  <span>亮度</span>
                  <input v-model.number="brightness" type="range" min="0.5" max="1.5" step="0.05" />
                </label>
                <label>
                  <SlidersHorizontal :size="15" />
                  <span>对比度</span>
                  <input v-model.number="contrast" type="range" min="0.6" max="1.8" step="0.05" />
                </label>
                <label :class="{ disabled: !analysis?.cam_overlay_base64 }">
                  <Layers3 :size="15" />
                  <span>热力图</span>
                  <input v-model.number="overlayOpacity" type="range" min="0" max="1" step="0.05" :disabled="!analysis?.cam_overlay_base64" />
                </label>
                <button
                  class="overlay-toggle"
                  :class="{ active: showOverlay }"
                  :disabled="!analysis?.cam_overlay_base64"
                  @click="showOverlay = !showOverlay"
                >
                  <Eye :size="15" /> {{ showOverlay ? '叠加已开' : '叠加已关' }}
                </button>
              </div>
            </div>

            <div class="control-column">
              <div class="upload-card panel">
                <div class="panel__header">
                  <div><span class="panel__index">02</span><div><h3>病例与影像</h3><p>ZIP 序列或 DICOM 单片</p></div></div>
                </div>

                <input ref="fileInput" type="file" accept=".zip,.dcm,.dicom,.png,.jpg,.jpeg,.bmp,.webp" hidden @change="onFileChange" />
                <button
                  v-if="!series"
                  class="dropzone"
                  :class="{ 'dropzone--active': draggedOver }"
                  @click="openFilePicker"
                  @dragover.prevent="draggedOver = true"
                  @dragleave.prevent="draggedOver = false"
                  @drop.prevent="onDrop"
                >
                  <span class="dropzone__icon"><UploadCloud :size="25" /></span>
                  <strong>拖放 ZIP 影像序列或 DICOM 文件到这里</strong>
                  <span>导入整个 ZIP 压缩包可拖动浏览全部肺部 CT 切片</span>
                  <small>支持 .zip（内含 .dcm / .png / .jpg 序列）或单张 .dcm</small>
                </button>

                <div v-else class="selected-file">
                  <div class="selected-file__icon">
                    <FileArchive v-if="series.source === 'zip'" :size="22" />
                    <FileImage v-else :size="22" />
                  </div>
                  <div>
                    <strong>{{ series.fileName }}</strong>
                    <span v-if="series.source === 'zip'">{{ sliceCount }} 张切片 · {{ formatBytes(series.fileSize) }} · 当前：{{ currentSlice?.name }}</span>
                    <span v-else>{{ formatBytes(series.fileSize) }} · {{ currentIsDicom ? 'DICOM' : '影像' }}</span>
                  </div>
                  <button class="icon-button" aria-label="移除序列" :disabled="isBusy" @click="removeSeries"><X :size="16" /></button>
                </div>

                <p v-if="fileError" class="field-error"><AlertTriangle :size="14" />{{ fileError }}</p>
                <p v-if="viewerError" class="field-notice"><BadgeInfo :size="14" />{{ viewerError }}</p>
                <p v-if="series && !currentIsDicom" class="field-notice">
                  <BadgeInfo :size="14" />当前切片为图片格式，如需 AI 分析请翻到 .dcm 切片再上传
                </p>

                <div class="patient-fields">
                  <label><span>患者编号 <small>可选</small></span><label><Hash :size="15" /><input v-model="patientId" placeholder="自动读取或手动输入" /></label></label>
                  <label><span>患者姓名 <small>可选</small></span><label><UserRound :size="15" /><input v-model="patientName" placeholder="自动读取或手动输入" /></label></label>
                </div>

                <button v-if="!uploadedCase" class="primary-button" :disabled="!canUpload" @click="uploadCase">
                  <LoaderCircle v-if="operation === 'uploading'" class="spin" :size="17" />
                  <FileUp v-else :size="17" />
                  {{ operation === 'uploading' ? '正在上传影像…' : (series?.source === 'zip' ? '上传当前切片并创建病例' : '上传并创建病例') }}
                </button>
                <button v-else-if="!analysis" class="primary-button primary-button--accent" :disabled="!canAnalyze" @click="analyzeCase">
                  <LoaderCircle v-if="operation === 'analyzing'" class="spin" :size="17" />
                  <Play v-else :size="16" fill="currentColor" />
                  {{ operation === 'analyzing' ? 'AI 正在分析，请稍候…' : '开始 AI 分析' }}
                </button>
                <div v-else class="analysis-complete"><CheckCircle2 :size="18" /><span><strong>分析已完成</strong><small>{{ analysis.model_version || '模型结果已返回' }} · {{ analysis.inference_ms ? `${analysis.inference_ms} ms` : '完成' }}</small></span></div>
              </div>

              <div class="info-card panel">
                <div class="info-card__head">
                  <div><span class="panel__index">03</span><h3>影像信息</h3></div>
                  <span v-if="currentCase" class="case-status" :class="currentCase.status">{{ statusLabel(currentCase.status) }}</span>
                </div>
                <div class="meta-grid">
                  <div><span>检查方式</span><strong>{{ dicomMeta.modality || '—' }}</strong></div>
                  <div><span>影像矩阵</span><strong>{{ dicomMeta.rows ? `${dicomMeta.rows} × ${dicomMeta.columns}` : '—' }}</strong></div>
                  <div><span>层厚</span><strong>{{ dicomMeta.slice_thickness || dicomMeta.sliceThickness ? `${dicomMeta.slice_thickness || dicomMeta.sliceThickness} mm` : '—' }}</strong></div>
                  <div><span>切片数量</span><strong>{{ sliceCount ? `${sliceCount} 张` : '—' }}</strong></div>
                  <div><span>检查日期</span><strong>{{ formatStudyDate(dicomMeta.study_date || dicomMeta.studyDate) }}</strong></div>
                  <div><span>当前切片</span><strong>{{ currentSlice?.name || currentCase?.filename || '—' }}</strong></div>
                </div>
              </div>
            </div>
          </section>

          <section class="results-section panel" :class="{ 'results-section--empty': !analysis }">
            <div class="panel__header results-header">
              <div><span class="panel__index">04</span><div><h3>AI 分析报告</h3><p>结构化辅助检测结果</p></div></div>
              <span v-if="analysis" class="report-time"><Clock3 :size="14" />推理 {{ analysis.inference_ms || '—' }} ms</span>
            </div>

            <div v-if="analysis" class="report-grid">
              <div class="report-summary">
                <span class="section-kicker"><BrainCircuit :size="14" /> MODEL {{ analysis.model_version || 'v1.0' }}</span>
                <h3>{{ analysis.summary || '分析完成' }}</h3>
                <p>{{ analysis.report?.conclusion || '请结合临床资料与影像科医生判断。' }}</p>
                <div class="follow-up"><CalendarDays :size="18" /><div><span>随访建议</span><strong>{{ analysis.report?.follow_up || '暂无随访建议' }}</strong></div></div>
              </div>
              <div class="nodule-list">
                <div class="nodule-list__head"><span>可疑区域</span><strong>{{ nodules.length }} 处</strong></div>
                <article v-for="(nodule, index) in nodules" :key="nodule.id || index" class="nodule-item">
                  <span class="nodule-item__number">N{{ index + 1 }}</span>
                  <div class="nodule-item__main"><strong>{{ nodule.location || '位置待确认' }}</strong><span>长径 {{ nodule.diameter_mm || '—' }} mm · 置信度 {{ Math.round((nodule.confidence || 0) * 100) }}%</span></div>
                  <div class="risk-score"><span>恶性概率</span><strong>{{ Math.round((nodule.malignancy_probability || 0) * 100) }}<small>%</small></strong></div>
                </article>
                <div v-if="!nodules.length" class="no-nodules"><CheckCircle2 :size="18" />未返回可疑结节区域</div>
              </div>
            </div>

            <div v-else class="report-empty">
              <div class="report-empty__icon"><BrainCircuit :size="27" /></div>
              <div><strong>报告将在完成 AI 分析后生成</strong><span>包含可疑区域、定位信息、恶性概率及随访建议</span></div>
              <div class="report-empty__features"><span><ScanLine :size="15" /> Grad-CAM 定位</span><span><Activity :size="15" /> ResNet-50 分类</span><span><ShieldCheck :size="15" /> 辅助判断</span></div>
            </div>

            <div class="medical-disclaimer"><AlertTriangle :size="15" /><span>{{ analysis?.disclaimer || '本系统输出仅供计算机辅助检测参考，不作为独立诊断依据。最终诊断应由具备资质的医疗专业人员作出。' }}</span></div>
          </section>
        </template>

        <template v-else-if="currentView === 'history'">
          <section class="page-heading">
            <div><span class="section-kicker"><Database :size="14" /> CASE ARCHIVE</span><h2>病例记录</h2><p>查看已上传影像与 AI 分析状态，快速返回诊断工作台。</p></div>
            <button class="secondary-button" :disabled="historyLoading" @click="loadHistory"><RefreshCw :class="{ spin: historyLoading }" :size="16" />刷新记录</button>
          </section>
          <section class="history-panel panel">
            <div class="history-toolbar">
              <label class="search-field"><Search :size="17" /><input v-model="historyQuery" placeholder="搜索患者姓名、编号或病例 ID" /></label>
              <span>共 {{ filteredHistory.length }} 条记录</span>
            </div>
            <div v-if="historyLoading" class="loading-state"><LoaderCircle class="spin" :size="24" /><span>正在读取病例记录…</span></div>
            <div v-else-if="!filteredHistory.length" class="empty-state"><Database :size="30" /><strong>暂无病例记录</strong><span>上传第一张 DICOM 影像后，病例会显示在这里。</span><button class="secondary-button" @click="selectView('workspace')"><ImagePlus :size="16" />前往影像工作台</button></div>
            <div v-else class="case-table-wrap">
              <table class="case-table">
                <thead><tr><th>患者</th><th>影像文件</th><th>创建时间</th><th>可疑区域</th><th>状态</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="item in filteredHistory" :key="item.case_id">
                    <td><div class="patient-cell"><span><CircleUserRound :size="18" /></span><div><strong>{{ item.patient_name || '未命名患者' }}</strong><small>{{ item.patient_id || item.case_id.slice(0, 10) }}</small></div></div></td>
                    <td><div class="file-cell"><FileImage :size="16" /><span>{{ item.filename }}</span></div></td>
                    <td>{{ formatDate(item.created_at) }}</td>
                    <td><strong>{{ item.nodule_count ?? '—' }}</strong></td>
                    <td><span class="case-status" :class="item.status">{{ statusLabel(item.status) }}</span></td>
                    <td><button class="row-action" @click="openHistoryCase(item)">查看<ChevronRight :size="15" /></button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>

        <template v-else>
          <section class="page-heading model-heading">
            <div><span class="section-kicker"><BrainCircuit :size="14" /> EXPLAINABLE AI</span><h2>理解模型，才能更好地使用结果。</h2><p>从 CT 像素到结构化辅助结论，LungAI 保留每一步关键处理信息。</p></div>
            <div class="model-version"><span>当前模型</span><strong>ResNet-50 · v1.0</strong></div>
          </section>
          <section class="model-flow">
            <article><span class="flow-number">01</span><div class="flow-icon"><FileImage :size="23" /></div><h3>DICOM 解析</h3><p>读取像素数据、窗宽窗位、层厚及基础检查信息。</p></article>
            <ChevronRight class="flow-arrow" :size="20" />
            <article><span class="flow-number">02</span><div class="flow-icon"><SlidersHorizontal :size="23" /></div><h3>影像预处理</h3><p>完成 CT 窗口化、归一化与模型输入尺寸转换。</p></article>
            <ChevronRight class="flow-arrow" :size="20" />
            <article><span class="flow-number">03</span><div class="flow-icon"><BrainCircuit :size="23" /></div><h3>ResNet-50 分类</h3><p>基于 LUNA16 微调权重输出良恶性概率与置信度。</p></article>
            <ChevronRight class="flow-arrow" :size="20" />
            <article><span class="flow-number">04</span><div class="flow-icon"><ScanLine :size="23" /></div><h3>Grad-CAM 定位</h3><p>以热力图高激活区域定位可疑结节并生成边界框。</p></article>
          </section>
          <section class="model-details-grid">
            <article class="panel model-detail"><div class="model-detail__head"><Activity :size="20" /><h3>输出内容</h3></div><ul><li><CheckCircle2 :size="16" />可疑结节数量与定位框</li><li><CheckCircle2 :size="16" />结节直径与肺叶位置</li><li><CheckCircle2 :size="16" />恶性概率与检测置信度</li><li><CheckCircle2 :size="16" />综合结论与随访建议</li></ul></article>
            <article class="panel model-detail"><div class="model-detail__head"><ShieldCheck :size="20" /><h3>使用边界</h3></div><p>模型是临床决策支持工具，不替代影像科医生。小结节、低对比度病灶与伪影可能影响输出，应结合完整序列、病史及其他检查综合判断。</p><div class="boundary-note"><AlertTriangle :size="16" />不用于急诊独立诊断或自动出具医疗结论</div></article>
            <article class="panel model-detail"><div class="model-detail__head"><Server :size="20" /><h3>技术栈</h3></div><div class="tech-pills"><span>PyTorch</span><span>Flask</span><span>Vue 3</span><span>DICOM</span><span>ZIP 序列</span><span>ResNet-50</span><span>Grad-CAM</span></div><p>前后端解耦架构，便于模型迭代、临床界面扩展与本地化部署。</p></article>
          </section>
        </template>
      </div>
    </main>
  </div>
</template>
