# 肺结节CT影像AI辅助检测系统 - 后端API文档

## 基础信息

- 服务地址：`http://localhost:5000`
- API前缀：`/api`
- CORS：已开启，支持前端 `http://localhost:5173`、`http://localhost:8080`

---

## 1. 健康检查接口

### GET /health

**用途**：检查后端服务是否正常运行

**请求示例**：
```bash
curl http://localhost:5000/health
```

**响应示例**：
```json
{
  "status": "ok",
  "service": "lung-nodule-backend"
}
```

---

## 2. 上传影像接口

### POST /api/upload

**用途**：上传单张 DICOM 切片文件

**请求格式**：`multipart/form-data`

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file | File | 是 | `.dcm` 格式的DICOM切片文件 |
| patient_id | String | 否 | 患者ID（如不填则从DICOM元数据中提取） |
| patient_name | String | 否 | 患者姓名（如不填则从DICOM元数据中提取） |

**请求示例**：
```bash
curl -X POST http://localhost:5000/api/upload \
  -F "file=@test.dcm" \
  -F "patient_id=P001" \
  -F "patient_name=张三"
```

**成功响应（201 Created）**：
```json
{
  "message": "上传成功",
  "case": {
    "case_id": "abc123def456...",
    "patient_id": "P001",
    "patient_name": "张三",
    "filename": "CT001.dcm",
    "file_type": ".dcm",
    "status": "uploaded",
    "created_at": "2024-01-15T10:30:00Z",
    "dicom_metadata": {
      "patient_id": "P001",
      "patient_name": "张三",
      "study_date": "20240115",
      "modality": "CT",
      "rows": 512,
      "columns": 512,
      "pixel_spacing": [0.5, 0.5],
      "slice_thickness": 1.0,
      "window_center": -600,
      "window_width": 1500,
      "sop_instance_uid": "1.2.3.4..."
    }
  }
}
```

**失败响应（400 Bad Request）**：
```json
{
  "error": "当前版本仅支持单张 DICOM 切片上传",
  "allowed_extensions": [".dcm"]
}
```

---

## 3. AI分析接口

### POST /api/analyze

**用途**：对已上传的影像进行AI分析，检测肺结节

**请求格式**：`application/json`

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| case_id | String | 是 | 病例ID（从upload接口获取） |

**请求示例**：
```bash
curl -X POST http://localhost:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"case_id": "abc123def456..."}'
```

**成功响应（200 OK）**：
```json
{
  "message": "分析完成",
  "case_id": "abc123def456...",
  "status": "analyzed",
  "analysis": {
    "summary": "检测到 1 个可疑结节",
    "disclaimer": "本结果仅供计算机辅助检测参考，不作为独立诊断依据。",
    "coordinate_system": "image_pixels_top_left",
    "nodules": [
      {
        "id": "nodule-1",
        "bbox": {"x": 120, "y": 180, "width": 40, "height": 38},
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
    "cam_overlay_base64": "data:image/png;base64,iVBORw0KGgo...",
    "model_version": "v1.0.0",
    "inference_ms": 120
  }
}
```

**响应字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| analysis.summary | String | 分析摘要 |
| analysis.disclaimer | String | 免责声明 |
| analysis.coordinate_system | String | 坐标系统说明（image_pixels_top_left 表示图像像素坐标，左上角为原点） |
| analysis.nodules | Array | 检测到的结节列表 |
| nodules[].id | String | 结节唯一标识 |
| nodules[].bbox | Object | 结节边界框（图像像素坐标） |
| nodules[].bbox.x | Number | 边界框左上角X坐标 |
| nodules[].bbox.y | Number | 边界框左上角Y坐标 |
| nodules[].bbox.width | Number | 边界框宽度（像素） |
| nodules[].bbox.height | Number | 边界框高度（像素） |
| nodules[].diameter_mm | Number | 结节直径（毫米） |
| nodules[].location | String | 结节位置描述 |
| nodules[].malignancy_probability | Number | 恶性概率（0-1） |
| nodules[].confidence | Number | 检测置信度（0-1） |
| analysis.report | Object | 诊断报告 |
| analysis.report.conclusion | String | 诊断结论 |
| analysis.report.follow_up | String | 随访建议 |
| analysis.cam_overlay_base64 | String | CAM热力图（base64编码PNG，前端可直接渲染） |
| analysis.model_version | String | 模型版本 |
| analysis.inference_ms | Number | 推理耗时（毫秒） |

**失败响应**：
- 400：缺少case_id
- 404：病例不存在
- 500：AI分析失败

---

## 4. 获取病例详情接口

### GET /api/cases/<case_id>

**用途**：获取单个病例的完整信息

**请求示例**：
```bash
curl http://localhost:5000/api/cases/abc123def456...
```

**成功响应（200 OK）**：
```json
{
  "case": {
    "case_id": "abc123def456...",
    "patient_id": "P001",
    "patient_name": "张三",
    "filename": "CT001.dcm",
    "file_type": ".dcm",
    "dicom_metadata": {...},
    "status": "analyzed",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:31:00Z",
    "analysis": {...}
  }
}
```

---

## 5. 获取DICOM影像文件接口

### GET /api/cases/<case_id>/image

**用途**：返回已上传的DICOM原始文件，供前端Cornerstone.js加载渲染

**请求示例**：
```bash
curl http://localhost:5000/api/cases/abc123def456.../image
```

**成功响应**：
- Content-Type: `application/dicom`
- Body: DICOM文件二进制流

**失败响应**：
- 404：病例不存在或影像文件不存在

**前端使用方式**（Cornerstone.js）：
```javascript
const imageId = `http://localhost:5000/api/cases/${caseId}/image`;
cornerstone.loadAndCacheImage(imageId).then(image => {
  cornerstone.displayImage(element, image);
});
```

---

## 6. 历史记录接口

### GET /api/history

**用途**：获取所有历史病例列表

**请求参数**：

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| limit | Number | 50 | 返回条数上限（1-200） |

**请求示例**：
```bash
curl "http://localhost:5000/api/history?limit=20"
```

**成功响应（200 OK）**：
```json
{
  "items": [
    {
      "case_id": "abc123def456...",
      "patient_id": "P001",
      "patient_name": "张三",
      "filename": "CT001.dcm",
      "status": "analyzed",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:31:00Z",
      "nodule_count": 1
    }
  ],
  "total": 10
}
```

---

## 7. 随访对比接口（预留）

### GET /api/compare

**用途**：获取两个病例的信息，供前端同屏对比

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| case_id_a | String | 是 | 第一个病例ID |
| case_id_b | String | 是 | 第二个病例ID |

**请求示例**：
```bash
curl "http://localhost:5000/api/compare?case_id_a=xxx&case_id_b=yyy"
```

**成功响应（200 OK）**：
```json
{
  "message": "对比数据已返回（预留接口，后续可扩展结节变化分析）",
  "case_a": {...},
  "case_b": {...}
}
```

---

## 状态码汇总

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功（上传接口） |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
