import { cache, imageLoader, init as initCornerstoneCore } from '@cornerstonejs/core'
import { init as initDicomImageLoader, wadouri } from '@cornerstonejs/dicom-image-loader'
import dicomParser from 'dicom-parser'

let cornerstoneInitialization

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

const firstNumber = (value, fallback) => {
  const candidate = Array.isArray(value) ? value[0] : value
  const number = Number(candidate)
  return Number.isFinite(number) ? number : fallback
}

async function ensureCornerstone() {
  if (!cornerstoneInitialization) {
    cornerstoneInitialization = Promise.resolve().then(() => {
      initCornerstoneCore()
      initDicomImageLoader({
        useLegacyMetadataProvider: true,
        maxWebWorkers: Math.max(
          1,
          Math.min(4, Math.floor((navigator.hardwareConcurrency || 2) / 2)),
        ),
      })
    })
  }

  return cornerstoneInitialization
}

function createColorImageData(image, pixels, columns, rows) {
  const components = image.numberOfComponents || (image.rgba ? 4 : 3)
  const pixelCount = rows * columns

  if (![3, 4].includes(components) || pixels.length < pixelCount * components) {
    throw new Error('该彩色 DICOM 的像素排列暂不受支持')
  }

  const imageData = new ImageData(columns, rows)
  for (let index = 0; index < pixelCount; index += 1) {
    const source = index * components
    const target = index * 4
    imageData.data[target] = pixels[source]
    imageData.data[target + 1] = pixels[source + 1]
    imageData.data[target + 2] = pixels[source + 2]
    imageData.data[target + 3] = components === 4 ? pixels[source + 3] : 255
  }

  return imageData
}

function createMonochromeImageData(image, pixels, dataset, columns, rows) {
  const pixelCount = rows * columns
  if (pixels.length < pixelCount) {
    throw new Error('DICOM 解码后的像素数量不足')
  }

  const alreadyScaled = image.preScale?.scaled === true
  const slope = alreadyScaled ? 1 : firstNumber(image.slope, numberValue(dataset, 'x00281053', 1))
  const intercept = alreadyScaled
    ? 0
    : firstNumber(image.intercept, numberValue(dataset, 'x00281052', 0))

  let minimum = Number.POSITIVE_INFINITY
  let maximum = Number.NEGATIVE_INFINITY
  for (let index = 0; index < pixelCount; index += 1) {
    const value = Number(pixels[index]) * slope + intercept
    minimum = Math.min(minimum, value)
    maximum = Math.max(maximum, value)
  }

  const windowCenter = firstNumber(
    image.windowCenter,
    numberValue(dataset, 'x00281050', (minimum + maximum) / 2),
  )
  const windowWidth = Math.max(
    firstNumber(image.windowWidth, numberValue(dataset, 'x00281051', maximum - minimum)),
    1,
  )
  const lower = windowCenter - windowWidth / 2
  const upper = windowCenter + windowWidth / 2
  const inverted = image.invert || stringValue(dataset, 'x00280004') === 'MONOCHROME1'
  const imageData = new ImageData(columns, rows)

  for (let index = 0; index < pixelCount; index += 1) {
    const value = Number(pixels[index]) * slope + intercept
    const normalized = Math.min(1, Math.max(0, (value - lower) / (upper - lower)))
    const gray = Math.round((inverted ? 1 - normalized : normalized) * 255)
    const target = index * 4
    imageData.data[target] = gray
    imageData.data[target + 1] = gray
    imageData.data[target + 2] = gray
    imageData.data[target + 3] = 255
  }

  return { imageData, windowCenter, windowWidth }
}

export async function parseDicomFile(file) {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  const dataset = dicomParser.parseDicom(bytes)

  if (!dataset.elements.x7fe00010) {
    throw new Error('该 DICOM 文件不包含可读取的像素数据')
  }

  await ensureCornerstone()
  cache.purgeCache()
  wadouri.fileManager.purge()

  const imageId = wadouri.fileManager.add(file)
  let image
  try {
    image = await imageLoader.loadAndCacheImage(imageId)
  } catch (error) {
    throw new Error(`Cornerstone DICOM 解码失败：${error.message}`)
  }

  const rows = image.rows || dataset.uint16('x00280010')
  const columns = image.columns || dataset.uint16('x00280011')
  if (!rows || !columns) {
    throw new Error('DICOM 文件缺少有效的影像矩阵信息')
  }

  const pixels = image.getPixelData()
  let imageData
  let windowCenter = firstNumber(image.windowCenter, numberValue(dataset, 'x00281050', 0))
  let windowWidth = firstNumber(image.windowWidth, numberValue(dataset, 'x00281051', 0))

  if (image.color) {
    imageData = createColorImageData(image, pixels, columns, rows)
  } else {
    const monochrome = createMonochromeImageData(image, pixels, dataset, columns, rows)
    imageData = monochrome.imageData
    windowCenter = monochrome.windowCenter
    windowWidth = monochrome.windowWidth
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
      transferSyntax: stringValue(dataset, 'x00020010'),
      windowCenter: Math.round(windowCenter),
      windowWidth: Math.round(windowWidth),
      rows,
      columns,
    },
  }
}
