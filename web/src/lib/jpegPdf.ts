/**
 * Wrap a JPEG as a one-page PDF so a camera capture can go through the existing
 * Promote upload API (PDF/DOCX only). No new ingestion MIME type.
 */

function readUint16(bytes: Uint8Array, offset: number): number {
  return (bytes[offset] << 8) | bytes[offset + 1]
}

export function jpegDimensions(bytes: Uint8Array): { width: number; height: number } {
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) {
    throw new Error('That capture is not a JPEG.')
  }
  let offset = 2
  while (offset + 8 < bytes.length) {
    if (bytes[offset] !== 0xff) {
      offset += 1
      continue
    }
    const marker = bytes[offset + 1]
    const sof =
      marker === 0xc0 ||
      marker === 0xc1 ||
      marker === 0xc2 ||
      marker === 0xc3 ||
      marker === 0xc5 ||
      marker === 0xc6 ||
      marker === 0xc7 ||
      marker === 0xc9 ||
      marker === 0xca ||
      marker === 0xcb
    if (sof) {
      return { height: readUint16(bytes, offset + 5), width: readUint16(bytes, offset + 7) }
    }
    if (marker === 0xd8 || marker === 0xd9) {
      offset += 2
      continue
    }
    const length = readUint16(bytes, offset + 2)
    if (length < 2) break
    offset += 2 + length
  }
  throw new Error('Could not read that image.')
}

function ascii(text: string): Uint8Array {
  const out = new Uint8Array(text.length)
  for (let i = 0; i < text.length; i += 1) out[i] = text.charCodeAt(i) & 0xff
  return out
}

function concat(parts: Uint8Array[]): Uint8Array {
  const size = parts.reduce((sum, part) => sum + part.length, 0)
  const out = new Uint8Array(size)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

/**
 * Minimal PDF-1.4 with one /DCTDecode image XObject. Azure Document Intelligence
 * already accepts PDFs; this is the smallest wrap that keeps the existing MIME.
 */
export function jpegToPdf(jpeg: Uint8Array): Uint8Array {
  const { width, height } = jpegDimensions(jpeg)
  const content = `q\n${width} 0 0 ${height} 0 0 cm\n/Im0 Do\nQ\n`
  const objects: string[] = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${width} ${height}] /Contents 4 0 R /Resources << /XObject << /Im0 5 0 R >> >> >>`,
    `<< /Length ${content.length} >>\nstream\n${content}endstream`,
  ]

  const imageDict = `<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`
  const header = ascii('%PDF-1.4\n')
  const built: Uint8Array[] = [header]
  const offsets = [0]

  function writeObject(index: number, body: Uint8Array) {
    offsets[index] = built.reduce((sum, part) => sum + part.length, 0)
    built.push(ascii(`${index} 0 obj\n`), body, ascii('\nendobj\n'))
  }

  objects.forEach((body, i) => writeObject(i + 1, ascii(body)))
  writeObject(5, concat([ascii(imageDict), jpeg, ascii('\nendstream')]))

  const xrefAt = built.reduce((sum, part) => sum + part.length, 0)
  let xref = `xref\n0 6\n0000000000 65535 f \n`
  for (let i = 1; i <= 5; i += 1) {
    xref += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`
  }
  const trailer = `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xrefAt}\n%%EOF\n`
  built.push(ascii(xref), ascii(trailer))
  return concat(built)
}

export function isJpeg(bytes: Uint8Array): boolean {
  return bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
}
