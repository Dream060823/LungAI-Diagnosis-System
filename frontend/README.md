# LungAI 前端

基于 Vue 3 + Vite 的肺结节 CT 影像 AI 辅助检测工作站。

## 启动

```bash
npm install
npm run dev
```

默认连接 `http://localhost:5000` 的 Flask 后端。也可以复制 `.env.example` 为 `.env`，通过 `VITE_API_BASE_URL` 修改接口地址。

## 功能

- DICOM 单张切片拖放上传与浏览器端预览
- CT 影像缩放、亮度、对比度与 Grad-CAM 叠加控制
- 对接 `/api/upload` 与 `/api/analyze` 完成 AI 分析
- 结构化结节信息、诊断结论与随访建议
- 历史病例查询与详情回看
- 响应式布局与无障碍交互标签
