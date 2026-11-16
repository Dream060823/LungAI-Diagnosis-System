# LungAI 前端

基于 Vue 3 + Vite 的肺结节 CT 影像 AI 辅助检测工作站。

## 启动

```bash
npm install
npm run dev
```

默认连接 `http://localhost:5000` 的 Flask 后端。也可以复制 `.env.example` 为 `.env`，通过 `VITE_API_BASE_URL` 修改接口地址。

## 功能

- **ZIP 影像序列导入**：拖放或选择整个 `.zip` 压缩包（内含 `.dcm` / `.png` / `.jpg` / `.jpeg` / `.bmp` / `.webp` 切片），自动识别并按自然顺序排列全部肺部 CT 切片
- **切片拖动浏览**：在阅片区按住鼠标上下（或左右）拖动即可翻阅切片，同时支持滚轮、方向键（← → ↑ ↓）、底部滑块与前后按钮
- DICOM 单张切片拖放上传与浏览器端预览（原功能保留）
- CT 影像缩放、亮度、对比度与 Grad-CAM 叠加控制
- 对接 `/api/upload` 与 `/api/analyze` 完成 AI 分析（ZIP 序列下上传当前浏览的 `.dcm` 切片）
- 结构化结节信息、诊断结论与随访建议
- 历史病例查询与详情回看
- 响应式布局与无障碍交互标签

## 技术说明

- ZIP 解析由 `src/zipReader.js` 实现：零第三方依赖，直接解析 ZIP 中央目录并按需惰性解压（`DecompressionStream`），大序列也不会一次性占用内存；支持 STORED / DEFLATE 与基础 ZIP64
- 切片按文件名自然排序（`IM1` < `IM2` < `IM10`），DICOM 切片使用 `dicom-parser` 窗宽窗位渲染，图片切片使用 `createImageBitmap` 渲染
- 已渲染切片以 FIFO 队列缓存（默认 96 张），来回翻阅时无需重复解压
