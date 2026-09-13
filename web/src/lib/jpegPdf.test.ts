import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { isJpeg, jpegDimensions, jpegToPdf } from './jpegPdf'

/** Minimal 1×1 JPEG (SOF0 width/height = 1). */
function tinyJpeg(): Uint8Array {
  return Uint8Array.from([
    0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00,
    0x01, 0x00, 0x01, 0x00, 0x00, 0xff, 0xc0, 0x00, 0x0b, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01,
    0x01, 0x11, 0x00, 0xff, 0xd9,
  ])
}

describe('jpegToPdf', () => {
  it('wraps a JPEG as a PDF the existing upload API can accept', () => {
    const jpeg = tinyJpeg()
    assert.equal(isJpeg(jpeg), true)
    assert.deepEqual(jpegDimensions(jpeg), { width: 1, height: 1 })
    const pdf = jpegToPdf(jpeg)
    const text = new TextDecoder().decode(pdf.slice(0, 8))
    assert.equal(text.startsWith('%PDF-1.'), true)
    assert.equal(new TextDecoder().decode(pdf.slice(-6)).includes('EOF'), true)
  })

  it('refuses a non-JPEG so the UI can state the PDF/DOCX limit', () => {
    assert.equal(isJpeg(Uint8Array.from([0x89, 0x50, 0x4e, 0x47])), false)
    assert.throws(() => jpegToPdf(Uint8Array.from([0x00, 0x01])), /not a JPEG/)
  })
})
