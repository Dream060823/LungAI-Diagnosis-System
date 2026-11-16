// 零依赖 ZIP 读取器：解析 ZIP 中央目录，按需惰性解压切片。
// 支持 STORED(0) 与 DEFLATE(8) 两种常见压缩方式，兼容基础 ZIP64。

const SUPPORTED_EXTENSIONS = ['.dcm', '.dicom', '.png', '.jpg', '.jpeg', '.bmp', '.webp']

const MIME_BY_EXTENSION = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.bmp': 'image/bmp',
  '.webp': 'image/webp',
}

export const isSupportedImageName = (name) =>
  SUPPORTED_EXTENSIONS.some((extension) => name.toLowerCase().endsWith(extension))

export const isDicomName = (name) => {
  const lower = name.toLowerCase()
  return lower.endsWith('.dcm') || lower.endsWith('.dicom')
}

const readUint16 = (view, offset) => view.getUint16(offset, true)
const readUint32 = (view, offset) => view.getUint32(offset, true)

// 从文件尾部定位 End Of Central Directory 记录
async function locateEocd(file) {
  const tailStart = Math.max(0, file.size - 66_000)
  const tail = new Uint8Array(await file.slice(tailStart, file.size).arrayBuffer())
  for (let i = tail.length - 22; i >= 0; i -= 1) {
    if (
      tail[i] === 0x50 &&
      tail[i + 1] === 0x4b &&
      tail[i + 2] === 0x05 &&
      tail[i + 3] === 0x06
    ) {
      return { view: new DataView(tail.buffer, tail.byteOffset), offset: i, tailStart }
    }
  }
  throw new Error('无法识别该 ZIP 文件（未找到中央目录），请确认文件完整')
}

// 读取中央目录，返回所有支持的切片条目
async function readCentralDirectory(file) {
  const { view, offset, tailStart } = await locateEocd(file)

  let entryCount = readUint16(view, offset + 10)
  let cdOffset = readUint32(view, offset + 16)
  const diskNumber = readUint16(view, offset + 4)

  // 基础 ZIP64：条目数或偏移被填满时，从 Zip64 EOCD Locator 换算真实值
  if (entryCount === 0xffff || cdOffset === 0xffffffff || diskNumber === 0xffff) {
    const locatorOffset = offset - 20
    if (
      locatorOffset >= 0 &&
      view.getUint32(locatorOffset, true) === 0x07064b50
    ) {
      const zip64EocdOffset = Number(view.getBigUint64(locatorOffset + 8, true))
      const zip64Header = new DataView(
        await file.slice(zip64EocdOffset, zip64EocdOffset + 56).arrayBuffer(),
      )
      if (readUint32(zip64Header, 0) === 0x06064b50) {
        entryCount = Number(zip64Header.getBigUint64(32, true))
        cdOffset = Number(zip64Header.getBigUint64(48, true))
      }
    }
  }

  if (!entryCount) throw new Error('该 ZIP 文件为空')
  if (cdOffset >= file.size) throw new Error('ZIP 中央目录偏移超出文件范围，文件可能已损坏')

  const directoryBytes = new Uint8Array(
    await file.slice(cdOffset, Math.min(cdOffset + entryCount * 130 + 4_096, file.size)).arrayBuffer(),
  )
  const directoryView = new DataView(directoryBytes.buffer)
  const decoder = new TextDecoder()

  const entries = []
  let cursor = 0

  for (let i = 0; i < entryCount; i += 1) {
    if (cursor + 46 > directoryBytes.length) break
    if (readUint32(directoryView, cursor) !== 0x02014b50) break

    const compressionMethod = readUint16(directoryView, cursor + 10)
    let compressedSize = readUint32(directoryView, cursor + 20)
    let uncompressedSize = readUint32(directoryView, cursor + 24)
    const nameLength = readUint16(directoryView, cursor + 28)
    const extraLength = readUint16(directoryView, cursor + 30)
    const commentLength = readUint16(directoryView, cursor + 32)
    let localHeaderOffset = readUint32(directoryView, cursor + 42)

    const nameStart = cursor + 46
    const name = decoder.decode(directoryBytes.subarray(nameStart, nameStart + nameLength))

    // Zip64 扩展字段：尺寸或偏移占满 32 位时在 extra 中存放真实 64 位值
    let extraCursor = nameStart + nameLength
    const extraEnd = extraCursor + extraLength
    while (extraCursor + 4 <= extraEnd) {
      const tag = readUint16(directoryView, extraCursor)
      const size = readUint16(directoryView, extraCursor + 2)
      if (tag === 0x0001) {
        let field = extraCursor + 4
        if (uncompressedSize === 0xffffffff && field + 8 <= extraEnd) {
          uncompressedSize = Number(directoryView.getBigUint64(field, true))
          field += 8
        }
        if (compressedSize === 0xffffffff && field + 8 <= extraEnd) {
          compressedSize = Number(directoryView.getBigUint64(field, true))
          field += 8
        }
        if (localHeaderOffset === 0xffffffff && field + 8 <= extraEnd) {
          localHeaderOffset = Number(directoryView.getBigUint64(field, true))
        }
        break
      }
      extraCursor += 4 + size
    }

    if (name && !name.endsWith('/') && !name.includes('__MACOSX') && !name.startsWith('.')) {
      if (isSupportedImageName(name)) {
        entries.push({
          name,
          compressionMethod,
          compressedSize,
          uncompressedSize,
          localHeaderOffset,
        })
      }
    }

    cursor = nameStart + nameLength + extraLength + commentLength
  }

  return entries
}

// 读取单个条目内容：先读本地文件头，再按压缩方式取数据
async function readEntry(file, entry) {
  const header = new Uint8Array(
    await file.slice(entry.localHeaderOffset, entry.localHeaderOffset + 30).arrayBuffer(),
  )
  const headerView = new DataView(header.buffer)
  if (readUint32(headerView, 0) !== 0x04034b50) {
    throw new Error(`切片 ${entry.name} 的本地文件头损坏`)
  }

  const nameLength = readUint16(headerView, 26)
  const extraLength = readUint16(headerView, 28)
  const dataOffset = entry.localHeaderOffset + 30 + nameLength + extraLength
  const compressed = new Uint8Array(
    await file.slice(dataOffset, dataOffset + entry.compressedSize).arrayBuffer(),
  )

  if (entry.compressionMethod === 0) return compressed

  if (entry.compressionMethod === 8) {
    if (typeof DecompressionStream === 'undefined') {
      throw new Error('当前浏览器不支持 DEFLATE 解压，请使用新版 Chrome / Edge / Firefox')
    }
    const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('deflate-raw'))
    const buffer = await new Response(stream).arrayBuffer()
    return new Uint8Array(buffer)
  }

  throw new Error(`切片 ${entry.name} 使用了不支持的压缩方式（${entry.compressionMethod}）`)
}

const naturalCompare = (a, b) =>
  a.localeCompare(b, 'zh-Hans-CN-u-kn-lower', { numeric: true, sensitivity: 'base' })

// 解析 ZIP，返回按自然顺序排列的切片描述列表（不立即解压像素）
export async function readZipSlices(file) {
  if (file.size > 2 * 1024 * 1024 * 1024) {
    throw new Error('ZIP 文件超过 2 GB，请拆分后再导入')
  }

  const entries = await readCentralDirectory(file)
  if (!entries.length) {
    throw new Error('ZIP 中未找到可浏览的影像文件（支持 .dcm / .png / .jpg / .bmp / .webp）')
  }

  entries.sort((a, b) => naturalCompare(a.name, b.name))

  return entries.map((entry) => ({
    name: entry.name.split('/').pop() || entry.name,
    path: entry.name,
    kind: isDicomName(entry.name) ? 'dicom' : 'image',
    mime: MIME_BY_EXTENSION[entry.name.toLowerCase().match(/\.[a-z]+$/)?.[0]] || 'image/png',
    size: entry.uncompressedSize,
    // 惰性读取：闭包持有原始 File 与条目定位，翻到该切片时才解压
    read: async () => readEntry(file, entry),
  }))
}
