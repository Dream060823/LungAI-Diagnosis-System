# LungAI-Diagnosis-System
An AI-assisted lung nodule detection system based on deep learning and medical image processing, supporting CT image analysis, DICOM data processing, and intelligent diagnostic assistance.
# LungAI-Diagnosis-System

## Overview

LungAI-Diagnosis-System is an AI-assisted lung nodule detection system based on deep learning and medical image processing.

The system aims to assist doctors in CT image analysis through artificial intelligence technology and provide computer-aided diagnosis support.


## Features

- CT image upload and analysis
- DICOM medical image processing
- Deep learning based lung nodule detection
- AI-assisted diagnostic report generation
- Medical image visualization


## Technology Stack

### Backend
- Python
- Flask

### Frontend
- Vue3

The clinical workstation frontend is located in [`frontend/`](frontend/). It
includes DICOM preview, case upload, AI analysis, structured reports, and case
history views.

```bash
cd frontend
npm install
npm run dev
```

### AI
- Deep Learning
- Medical Image Processing
- PyTorch


## Dataset

The project uses public medical imaging datasets, such as LIDC-IDRI.


## Project Structure



## Team

Backend & Medical Data:
Your Name

AI Model:
Team Member

Frontend:
Team Member


## Status

Under development.

## 本地一键启动

1. Windows 电脑需要安装 Python 3.10+ 和 Node.js 20+。
2. 双击项目根目录的 `一键启动.bat`。
3. 首次运行会自动安装依赖，完成后浏览器会打开 `http://127.0.0.1:5173`。

前端已接入 Cornerstone DICOM Image Loader，可在浏览器中解码常见 DICOM
传输语法，包括本项目测试影像使用的 JPEG Lossless（Process 14 SV1）。上传后可
在 CT 阅片区域直接查看影像，创建病例后也可从“病例记录”重新载入影像。

`start-local.bat` 会复用已运行的 LungAI 服务，并在端口被其他程序占用时显示明确
提示，避免重复启动造成无响应。
