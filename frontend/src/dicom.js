import dicomParser from 'dicom-parser'

const stringValue = (dataset, tag, fallback = '') => {
  try {
    return dataset.string(tag)?.trim() || fallback
  } catch {
    return fallback
  }
}

const numberValue = (dataset, tag, fallback = 0) => {
  const value = Number(stringValue(dataset, tag, ''))
  return Number.isFinite(value) ? value : fallback
}

export async function parseDicomFile(file) {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  const dataset = dicomParser.parseDicom(bytes)
  const pixelElement = dataset.elements.x7fe00010

  if (!pixelElement) {
    throw new Error('该 DICOM 文件不包含可读取的像素数据')
  }

  const rows = dataset.uint16('x00280010')
  const columns = dataset.uint16('x00280011')
  const bitsAllocated = dataset.uint16('x00280100') || 16
  const signed = dataset.uint16('x00280103') === 1
  const samples = dataset.uint16('x00280002') || 1

  if (!rows || !columns || samples !== 1 || ![8, 16].includes(bitsAllocated)) {
    throw new Error('当前浏览器预览仅支持 8/16 位单通道 DICOM 影像')
  }

  const transferSyntax = stringValue(dataset, 'x00020010')
  const isBigEndian = transferSyntax === '1.2.840.10008.1.2.2'
  const view = new DataView(bytes.buffer, bytes.byteOffset + pixelElement.dataOffset)
  const pixelCount = rows * columns
  const values = new Float32Array(pixelCount)
  const slope = numberValue(dataset, 'x00281053', 1)
  const intercept = numberValue(dataset, 'x00281052', 0)
  let min = Number.POSITIVE_INFINITY
  let max = Number.NEGATIVE_INFINITY

  for (let i = 0; i < pixelCount; i += 1) {
    const offset = i * (bitsAllocated / 8)
    let stored

    if (bitsAllocated === 8) {
      stored = signed ? view.getInt8(offset) : view.getUint8(offset)
    } else {
      stored = signed
        ? view.getInt16(offset, !isBigEndian)
        : view.getUint16(offset, !isBigEndian)
    }

    const calibrated = stored * slope + intercept
    values[i] = calibrated
    min = Math.min(min, calibrated)
    max = Math.max(max, calibrated)
  }

  const windowCenter = numberValue(dataset, 'x00281050', (min + max) / 2)
  const windowWidth = Math.max(numberValue(dataset, 'x00281051', max - min), 1)
  const lower = windowCenter - windowWidth / 2
  const upper = windowCenter + windowWidth / 2
  const imageData = new ImageData(columns, rows)
  const inverted = stringValue(dataset, 'x00280004') === 'MONOCHROME1'

  for (let i = 0; i < pixelCount; i += 1) {
    const normalized = Math.min(1, Math.max(0, (values[i] - lower) / (upper - lower)))
    const gray = Math.round((inverted ? 1 - normalized : normalized) * 255)
    const target = i * 4
    imageData.data[target] = gray
    imageData.data[target + 1] = gray
    imageData.data[target + 2] = gray
    imageData.data[target + 3] = 255
  }

  return {
    imageData,
    width: columns,
    height: rows,
    metadata: {
      patientId: stringValue(dataset, 'x00100020'),
      patientName: stringValue(dataset, 'x00100010').replaceAll('^', ' '),
      studyDate: stringValue(dataset, 'x00080020'),
      modality: stringValue(dataset, 'x00080060', 'CT'),
      sliceThickness: stringValue(dataset, 'x00180050'),
      windowCenter: Math.round(windowCenter),
      windowWidth: Math.round(windowWidth),
      rows,
      columns,
    },
  }
}
