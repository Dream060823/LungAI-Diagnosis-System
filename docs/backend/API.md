# 后端 API 接口文档（v0.2 已确认）

> 基础地址：`http://localhost:5000`

## 已确认的团队方案

1. **上传格式**：前端传 `.dcm` 原始文件，后端用 `pydicom` 解析元数据。
2. **bbox 坐标系**：算法返回图像像素坐标（左上角为原点），前端自行转换为 Cornerstone 视口坐标。
3. **多切片**：当前版本仅支持**单张切片**上传，满足比赛演示需求。
4. **预处理归属**：窗宽窗位、归一化等全部由算法模块（林钟鑫）内部完成；后端只传文件路径。
5. **CAM 热力图**：算法生成 base64 编码的 PNG，前端直接 `<img src="data:image/png;base64,...">` 展示。

---

## 通用约定

- 请求/响应均为 JSON（上传接口除外）
- 时间字段：ISO 8601 UTC 字符串
- 错误响应格式：

```json
{
  "error": "错误描述"
}
```

---

## 1. 健康检查

`GET /health`

```json
{
  "status": "ok",
  "service": "lung-nodule-backend"
}
```

---

## 2. 上传 DICOM 切片

`POST /api/upload`

Content-Type: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 单张 `.dcm` 原始切片 |
| patient_id | string | 否 | 表单未填时，回退使用 DICOM 内 PatientID |
| patient_name | string | 否 | 表单未填时，回退使用 DICOM 内 PatientName |

成功响应 `201`：

```json
{
  "message": "上传成功",
  "case": {
    "case_id": "abc123",
    "patient_id": "P001",
    "patient_name": "张三",
    "filename": "scan.dcm",
    "file_type": ".dcm",
    "status": "uploaded",
    "created_at": "2026-07-20T02:00:00+00:00",
    "dicom_metadata": {
      "patient_id": "P001",
      "patient_name": "张三",
      "study_date": "20260101",
      "modality": "CT",
      "rows": 512,
      "columns": 512,
      "pixel_spacing": [0.7, 0.7],
      "slice_thickness": 1.0,
      "window_center": -600,
      "window_width": 1500,
      "sop_instance_uid": "1.2.3.4.5"
    }
  }
}
```

说明：
- 后端只负责保存文件并解析 DICOM 元数据，不做窗宽窗位预处理。
- `rows` / `columns` 供前端将 bbox 像素坐标转换为 Cornerstone 视口坐标。

---

## 3. AI 分析

`POST /api/analyze`

请求体：

```json
{
  "case_id": "abc123"
}
```

后端行为：
1. 读取病例对应的 `.dcm` 本地路径
2. 调用算法模块 `detect_nodules(stored_path)`
3. 算法内部完成预处理、检测、分类、CAM 生成
4. 返回结构化 JSON 并持久化

成功响应：

```json
{
  "message": "分析完成",
  "case_id": "abc123",
  "status": "analyzed",
  "analysis": {
    "summary": "检测到 1 个可疑结节",
    "disclaimer": "本结果仅供计算机辅助检测参考，不作为独立诊断依据。",
    "coordinate_system": "image_pixels_top_left",
    "nodules": [
      {
        "id": "nodule-1",
        "bbox": { "x": 120, "y": 180, "width": 40, "height": 38 },
        "diameter_mm": 6.2,
        "location": "右肺上叶",
        "malignancy_probability": 0.23,
        "confidence": 0.87
      }
    ],
    "report": {
      "conclusion": "发现 1 个可疑结节，建议结合临床并定期随访。",
      "follow_up": "建议 3-6 个月后复查 CT。"
    },
    "cam_overlay_base64": "iVBORw0KGgoAAAANSUhEUg...",
    "model_version": "unet-resnet-v1",
    "inference_ms": 3200
  }
}
```

### 字段说明

| 字段 | 负责方 | 说明 |
|------|--------|------|
| `bbox` | 算法 | 图像像素坐标，左上角原点，`x/y/width/height` |
| `coordinate_system` | 算法 | 固定值 `image_pixels_top_left` |
| `cam_overlay_base64` | 算法 | PNG 的 base64 字符串，不含 `data:` 前缀 |
| 预处理 | 算法 | 后端不参与窗宽窗位、归一化 |

前端 CAM 展示示例：

```html
<img :src="'data:image/png;base64,' + analysis.cam_overlay_base64" />
```

---

## 4. 历史记录列表

`GET /api/history?limit=50`

```json
{
  "items": [
    {
      "case_id": "abc123",
      "patient_id": "P001",
      "patient_name": "张三",
      "filename": "scan.dcm",
      "status": "analyzed",
      "created_at": "2026-07-20T02:00:00+00:00",
      "updated_at": "2026-07-20T02:00:05+00:00",
      "nodule_count": 1
    }
  ],
  "total": 1
}
```

---

## 5. 病例详情

`GET /api/cases/{case_id}`

返回完整病例对象，包含 `dicom_metadata` 与 `analysis`。

---

## 6. 随访对比（预留）

`GET /api/compare?case_id_a=xxx&case_id_b=yyy`

第一版仅返回两个病例详情，供前端并排展示。

---

## 分工边界（给组员）

### 黄宇悦（前端）

- 上传单张 `.dcm` 到 `/api/upload`
- 使用返回的 `dicom_metadata.rows/columns` 做 bbox 坐标转换
- 直接展示 `cam_overlay_base64`

### 林钟鑫（算法）

- 实现 `run_inference(dicom_path: str) -> dict`
- 内部完成：DICOM 读取、窗宽窗位、归一化、检测、分类、CAM 生成
- 输出字段遵循本文档 `analysis` 结构

### 刘佳峻（后端）

- 保存 `.dcm`、解析元数据、调用算法、持久化结果
- 不参与影像预处理
